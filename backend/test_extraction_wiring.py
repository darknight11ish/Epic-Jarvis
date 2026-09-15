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
import ast, json, os, sys, threading, time, traceback, types
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
HUD = HERE / "jarvis_hud.py"

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _learner_ns():
    """The real `_Learner` and its three constants, executed in isolation."""
    tree = ast.parse(HUD.read_text(encoding="utf-8"))
    want, body = {"_Learner"}, []
    consts = {"EXTRACT_ENABLED", "EXTRACT_IDLE", "EXTRACT_MIN_GAP"}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in want:
            body.append(node)
        elif isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in consts for t in node.targets):
            body.append(node)
    names = {getattr(n, "name", None) or n.targets[0].id for n in body}
    missing = (want | consts) - names
    if missing:
        raise AssertionError(f"not found at module level in jarvis_hud.py: {sorted(missing)}")
    ns = {"os": os, "json": json, "sys": sys, "threading": threading, "Optional": Optional}
    exec(compile(ast.Module(body=body, type_ignores=[]), "<lifted>", "exec"), ns)
    # Real timings would make this suite take ten minutes.
    ns["EXTRACT_ENABLED"], ns["EXTRACT_IDLE"], ns["EXTRACT_MIN_GAP"] = True, 0.08, 0.02
    return ns


class FakeExtract:
    """Stands in for jarvis_extract. Records every transcript it is handed."""

    def __init__(self, raises=False):
        self.calls, self.raises = [], raises
        self.lock = threading.Lock()

    def install(self):
        m = types.ModuleType("jarvis_extract")
        m.propose = self.propose
        m.pending = lambda: [{"id": 7, "text": "Mario is allergic to shellfish"}]
        sys.modules["jarvis_extract"] = m
        return self

    def propose(self, messages, source="conversation"):
        with self.lock:
            self.calls.append(messages)
        if self.raises:
            raise RuntimeError("the local model is not up")
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
               t_the_doorbell, t_the_call_site):
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
