"""The extractor had no trigger, and the queue had no doorbell.

`jarvis_extract.propose()` had zero call sites anywhere in the tree. Every
piece around it worked - the prompt, the proposals table, the review queue,
the accept path that supersedes the fact it replaces, the HTTP routes - and
nothing ever ran it, so the queue was always empty and the memory store only
ever held what was typed into it by hand.

These tests execute the real `_Learner`, lifted out of jarvis_hud.py with ast
so the server module is never imported, driven with a fake extractor and
millisecond timings.

    python3 test_extraction_wiring.py
"""
import ast, json, os, sys, threading, time, traceback, types, urllib.parse
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# BACKEND is where the modules under test actually live - this folder
# in the dev container, $JARVIS_BACKEND on a real install. REPO is this
# repository. They used to be the same path and are not on the machine
# that runs Jarvis.
from _where import BACKEND, REPO, missing, explain
HUD = BACKEND / "jarvis_hud.py"

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _learner_ns():
    """The real `_Learner` and its three constants, executed in isolation."""
    tree = ast.parse(HUD.read_text(encoding="utf-8"))
    want = {"_Learner", "_loopback_ok", "_extract_model", "_int_env",
            # offer() consults the runtime switch rather than the constant, so
            # the pane can turn learning off without an environment variable
            # and a restart.
            "learning_enabled", "set_learning"}
    consts = {"EXTRACT_ENABLED", "EXTRACT_IDLE", "EXTRACT_MIN_GAP",
              "LEARNING_FILE"}
    body = []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in want:
            body.append(node)
        elif isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in consts for t in node.targets):
            body.append(node)
    names = {getattr(n, "name", None) or n.targets[0].id for n in body}
    missing = (want | consts) - names - {"_int_env"}   # _int_env lives in memory-prefix
    if missing:
        raise AssertionError(f"not found at module level in jarvis_hud.py: {sorted(missing)}")
    import tempfile
    ns = {"os": os, "json": json, "sys": sys, "threading": threading,
          "Optional": Optional, "urllib": urllib, "time": time,
          # a scratch CONFIG_DIR, because LEARNING_FILE is derived from it
          "CONFIG_DIR": Path(tempfile.mkdtemp()), "Path": Path,
          # _extract_model reads the config; an empty one is the interesting
          # case because it is what sends it to the JARVIS_LOCAL_MODEL branch.
          "_read_toml": lambda _p: {}, "CONFIG_FILE": None}
    exec(compile(ast.Module(body=body, type_ignores=[]), "<lifted>", "exec"), ns)
    # Real timings would make this suite take ten minutes.
    ns["EXTRACT_ENABLED"], ns["EXTRACT_IDLE"], ns["EXTRACT_MIN_GAP"] = True, 0.08, 0.02
    return ns


class FakeExtract:
    """Stands in for jarvis_extract. Records every transcript it is handed."""

    def __init__(self, raises=False, ollama="http://127.0.0.1:11434", answers=True):
        self.calls, self.raises, self.answers = [], raises, answers
        self.asked = []                       # (prompt, model) the llm saw
        self.lock = threading.Lock()
        self.ollama = ollama

    def install(self):
        m = types.ModuleType("jarvis_extract")
        m.propose = self.propose
        m.pending = lambda: [{"id": 7, "text": "Mario is allergic to shellfish"}]
        m.OLLAMA = self.ollama
        m._local_llm = self._local_llm
        sys.modules["jarvis_extract"] = m
        return self

    def _local_llm(self, prompt, model=None, timeout=60):
        self.asked.append((prompt, model))
        return '{"facts":[]}' if self.answers else None

    def propose(self, messages, llm=None, source="conversation"):
        with self.lock:
            self.calls.append(messages)
        if self.raises:
            raise RuntimeError("the local model is not up")
        if llm is not None:
            llm("prompt")                     # the real propose() always calls it
        return [{"id": len(self.calls), "text": "something durable"}]


def _run(learner, seconds=1.2, until=None):
    learner.start()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if until and until():
            break
        time.sleep(0.01)
    learner.stop()


CONVO = [
    {"role": "system", "content": "Things you know about the user:\n- Mario lives at 42 Elm Street"},
    {"role": "user", "content": "what did my note say about the flat"},
    {"role": "assistant", "content": "Your Joplin vault says the lease ends in March and the deposit was 2400."},
    {"role": "user", "content": "right, and I am moving to Berlin in June"},
]


def t_it_reads_only_what_you_typed():
    ns = _learner_ns()
    fake = FakeExtract().install()
    L = ns["_Learner"]()
    L.offer(list(CONVO))
    _run(L, 1.2, until=lambda: fake.calls)

    check("a pass actually ran", len(fake.calls) >= 1,
          "propose() was never called - the trigger is still missing")
    if not fake.calls:
        return
    got = fake.calls[0]
    check("every message handed over is a user turn",
          all(m["role"] == "user" for m in got), repr(got))
    text = json.dumps(got)
    check("what you typed is there", "moving to Berlin in June" in text, text)
    check("the assistant's turn is NOT there", "deposit was 2400" not in text,
          "a Joplin read comes back through the assistant turn; extracting from it "
          "would file vault content as a durable fact")
    check("the recalled-memory block is NOT there", "42 Elm Street" not in text,
          "re-extracting injected memory would launder old facts into new ones")


def t_it_waits_for_you_to_stop_talking():
    ns = _learner_ns()
    fake = FakeExtract().install()
    L = ns["_Learner"]()
    L.start()
    # Four turns in quick succession, each well inside the idle window.
    for i in range(4):
        L.offer([{"role": "user", "content": f"turn {i}"}])
        time.sleep(0.03)
    time.sleep(0.5)
    L.stop()
    check("a burst of turns produces one pass, not one per turn",
          len(fake.calls) == 1, f"{len(fake.calls)} passes for 4 turns")
    if fake.calls:
        check("and it sees the whole burst, not just the first turn",
              "turn 3" in json.dumps(fake.calls[0]), repr(fake.calls[0]))


def t_nothing_new_said_is_not_a_pass():
    ns = _learner_ns()
    fake = FakeExtract().install()
    L = ns["_Learner"]()
    L.start()
    same = [{"role": "user", "content": "I use a Ryzen 9 3900X"}]
    L.offer(list(same))
    time.sleep(0.4)
    L.offer(list(same))
    time.sleep(0.4)
    L.stop()
    check("an unchanged transcript is not sent to the model again",
          len(fake.calls) == 1, f"{len(fake.calls)} passes over identical text")


def t_a_dead_model_does_not_kill_the_thread():
    ns = _learner_ns()
    fake = FakeExtract(raises=True).install()
    L = ns["_Learner"]()
    L.start()
    L.offer([{"role": "user", "content": "first thing"}])
    for _ in range(80):
        if fake.calls:
            break
        time.sleep(0.01)
    check("the failing pass was attempted", len(fake.calls) == 1, f"{len(fake.calls)}")

    # Liveness is the wrong assertion - a stopped thread and a crashed one look
    # the same from outside. The property that matters is that the NEXT thing
    # you say still gets learned from.
    fake.raises = False
    L.offer([{"role": "user", "content": "a second, different thing"}])
    for _ in range(80):
        if len(fake.calls) > 1:
            break
        time.sleep(0.01)
    L.stop()
    check("the next turn is still picked up", len(fake.calls) == 2,
          f"{len(fake.calls)} passes - an exception killed the learner for the session")
    if len(fake.calls) == 2:
        check("and the failed transcript was not silently retried forever",
              "a second, different thing" in json.dumps(fake.calls[1]), repr(fake.calls[1]))


def t_nothing_to_learn_from():
    ns = _learner_ns()
    fake = FakeExtract().install()
    L = ns["_Learner"]()
    for junk in ([], [{"role": "assistant", "content": "hello"}],
                 [{"role": "user", "content": "   "}], [{"role": "user"}], ["not a dict"]):
        L.offer(junk)
    _run(L, 0.4)
    check("a transcript with nothing you typed in it does not wake the model",
          fake.calls == [], repr(fake.calls))


def t_it_can_be_switched_off():
    ns = _learner_ns()
    ns["EXTRACT_ENABLED"] = False
    fake = FakeExtract().install()
    L = ns["_Learner"]()
    L.offer(list(CONVO))
    _run(L, 0.4)
    check("JARVIS_EXTRACT=0 means no pass ever runs", fake.calls == [], repr(fake.calls))


def t_it_refuses_a_non_loopback_ollama():
    """jarvis_extract says "NEVER CLOUD ... localhost and nothing else".

    That was vacuously true while propose() had no callers. It reads OLLAMA_URL,
    so one environment variable pointing at a shared or remote Ollama would
    ship everything typed here to it - automatically, 45s after every
    conversation, with nobody in the loop.
    """
    ns = _learner_ns()
    for url in ("https://ollama.attacker.example", "http://192.168.1.50:11434",
                "http://ollama.internal:11434", "", "not a url at all"):
        fake = FakeExtract(ollama=url).install()
        L = ns["_Learner"]()
        L.offer([{"role": "user", "content": "the safe combination is 11-22-33"}])
        _run(L, 0.5)
        check(f"refuses {url!r}", fake.calls == [] and fake.asked == [],
              f"sent {len(fake.calls)} transcript(s) to {url}")

    # CONTROL, all four spellings of this machine.
    for url in ("http://127.0.0.1:11434", "http://localhost:11434",
                "http://[::1]:11434"):
        fake = FakeExtract(ollama=url).install()
        L = ns["_Learner"]()
        L.offer([{"role": "user", "content": "I use a Ryzen 9 3900X"}])
        _run(L, 1.0, until=lambda: fake.calls)
        check(f"CONTROL: allows {url!r}", len(fake.calls) == 1,
              "loopback was refused - the check is too strict to be useful")


def t_it_asks_for_the_chat_lanes_model():
    ns = _learner_ns()
    import os as _os
    _os.environ["JARVIS_LOCAL_MODEL"] = "qwen3:8b-from-env"
    try:
        fake = FakeExtract().install()
        L = ns["_Learner"]()
        L.offer([{"role": "user", "content": "something worth keeping here"}])
        _run(L, 1.0, until=lambda: fake.asked)
        check("the model is passed explicitly, not left to the default",
              bool(fake.asked) and fake.asked[0][1] == "qwen3:8b-from-env",
              f"asked: {fake.asked}")
    finally:
        _os.environ.pop("JARVIS_LOCAL_MODEL", None)


def t_a_model_that_never_answers_is_not_silent():
    """An empty list means BOTH "nothing durable was said" and "the model
    never answered", and only one of those is fine."""
    ns = _learner_ns()
    fake = FakeExtract(answers=False).install()
    L = ns["_Learner"]()
    L.offer([{"role": "user", "content": "I moved to Berlin in June"}])
    _run(L, 1.0, until=lambda: fake.asked)
    check("the model was asked", len(fake.asked) == 1, f"{fake.asked}")
    # _pass must not mark the transcript as seen, or the same unanswered text
    # would never be retried.
    check("an unanswered transcript is not marked as already learned from",
          L._last == "", f"_last was set to {L._last[:60]!r}")


def t_the_doorbell():
    """_poll_proposals, executed against the real Bus."""
    import jarvis_events as ev
    FakeExtract().install()
    check("the poller is registered",
          any(getattr(f, "__name__", "") == "_poll_proposals" for f in ev.POLLERS),
          "the queue fills on its own now; without this nobody is told")
    if not hasattr(ev, "_poll_proposals"):
        check("_poll_proposals exists", False)
        return
    bus = ev.Bus()
    ev._poll_proposals(bus)                       # first observation is a baseline
    sys.modules["jarvis_extract"].pending = lambda: [
        {"id": 7, "text": "Mario is allergic to shellfish"},
        {"id": 8, "text": "Mario is moving to Berlin in June"}]
    ev._poll_proposals(bus)
    out, _ = bus.since(0)
    events = [e for e in out if e.kind == "proposal"]
    check("a new proposal publishes exactly one event", len(events) == 1,
          f"published {len(events)}")
    if not events:
        return
    d = json.dumps(events[0].data)
    check("it carries the count", events[0].data.get("count") == 2, d)
    check("it does NOT carry the fact text", "shellfish" not in d and "Berlin" not in d,
          "this bus reaches a phone lock screen; a proposal quotes whatever produced it")
    ev._poll_proposals(bus)
    again = [e for e in bus.since(0)[0] if e.kind == "proposal"]
    check("an unchanged queue publishes nothing further", len(again) == 1,
          f"{len(again)} events for one change")


def t_the_approval_event_is_a_doorbell_too():
    """The rule _poll_proposals states about itself was not true next door.

    jarvis_gate.pending() SELECTs detail and prompt verbatim, and
    _poll_approvals attached them to the event. The phone surfaces approvals
    with the screen off, so an email body was headed for a lock screen.
    """
    import jarvis_events as ev
    gate = types.ModuleType("jarvis_gate")
    gate.pending = lambda: [{
        "id": "a1", "action": "email_send", "tier": "ask", "created": 1.0,
        "raised": None, "risk": {"swipe_ok": False},
        "detail": '{"to": "doctor@clinic.example"}',
        "prompt": "Jarvis wants to email doctor@clinic.example: "
                  "'my test came back positive'"}]
    sys.modules["jarvis_gate"] = gate
    bus = ev.Bus()
    ev._poll_approvals(bus)                    # baseline
    gate.pending = lambda: []
    ev._poll_approvals(bus)
    gate.pending = lambda: [{
        "id": "a2", "action": "email_send", "tier": "ask", "created": 2.0,
        "raised": None, "risk": {"swipe_ok": False},
        "detail": '{"to": "doctor@clinic.example"}',
        "prompt": "Jarvis wants to email doctor@clinic.example: "
                  "'my test came back positive'"}]
    ev._poll_approvals(bus)
    events = [e for e in bus.since(0)[0] if e.kind == "approval"]
    check("approvals still publish", len(events) >= 1, f"{len(events)}")
    if not events:
        return
    blob = events[-1].sse()
    check("no email address on the wire", "doctor@clinic.example" not in blob, blob[:300])
    check("no message body on the wire", "came back positive" not in blob, blob[:300])
    check("no prompt key at all", '"prompt"' not in blob, blob[:300])
    check("no detail key at all", '"detail"' not in blob, blob[:300])
    # CONTROL: it must still be a useful doorbell.
    check("CONTROL: the count survives", events[-1].data.get("count") == 1, blob[:200])
    items = events[-1].data.get("items") or []
    check("CONTROL: the id and action survive, so a client can still route",
          bool(items) and items[0].get("id") == "a2"
          and items[0].get("action") == "email_send", repr(items))
    check("CONTROL: raised survives, because the quick-action rule needs it",
          bool(items) and "raised" in items[0], repr(items))


def t_the_call_site():
    """CONTROL on the wiring itself."""
    src = HUD.read_text(encoding="utf-8")
    check("the turn hands its transcript over", "LEARNER.offer(" in src,
          "propose() is back to having zero call sites")
    check("it hands over the CLIENT's messages, not the rewritten ones",
          'LEARNER.offer(body.get("messages")' in src,
          "the local `messages` is filtered on a cloud turn and carries the "
          "recalled-facts block on a local one")
    check("and only when memory is this side",
          "MEMORY and not jarvis_side_memory" in src)
    tree = ast.parse(src)
    started = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                  and n.func.attr == "start"
                  and getattr(n.func.value, "id", "") == "LEARNER"
                  for n in ast.walk(tree))
    check("the thread is started at boot", started,
          "offer() would queue transcripts nothing ever reads")


if __name__ == "__main__":
    for fn in (t_it_reads_only_what_you_typed, t_it_waits_for_you_to_stop_talking,
               t_nothing_new_said_is_not_a_pass, t_a_dead_model_does_not_kill_the_thread,
               t_nothing_to_learn_from, t_it_can_be_switched_off,
               t_it_refuses_a_non_loopback_ollama, t_it_asks_for_the_chat_lanes_model,
               t_a_model_that_never_answers_is_not_silent,
               t_the_doorbell, t_the_approval_event_is_a_doorbell_too,
               t_the_call_site):
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
