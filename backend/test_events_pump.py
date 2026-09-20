"""The pollers exist, they work, and now something runs them.

`jarvis_events.Pump` was written, POLLERS was populated, both clients were
built against `event: approval` - and nothing in jarvis_hud.py ever
constructed the Pump, so that event had never once been published. These
tests cover the mechanism and the missing call site, because the mechanism
was never the broken part.

    python3 test_events_pump.py
"""
import ast, sys, types, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# BACKEND is where the modules under test actually live - this folder
# in the dev container, $JARVIS_BACKEND on a real install. REPO is this
# repository. They used to be the same path and are not on the machine
# that runs Jarvis.
from _where import BACKEND, REPO, missing, explain

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def stub_gate(items):
    m = types.ModuleType("jarvis_gate")
    m.pending = lambda: list(items)
    sys.modules["jarvis_gate"] = m


def t_pump_publishes_approvals():
    import jarvis_events as ev
    bus = ev.Bus()
    pump = ev.Pump(bus=bus, engine=None)

    stub_gate([{"id": "a1"}, {"id": "a2"}])
    pump.tick()
    check("the first tick is a baseline, not an event",
          bus.since(0)[0] == [] if isinstance(bus.since(0), tuple) else True)
    seen = [e for e in _drain(bus) if e.kind == "approval"]
    check("no approval event on the first observation", seen == [],
          f"published {len(seen)}")

    stub_gate([{"id": "a2"}])                    # a1 was decided
    pump.tick()
    seen = [e for e in _drain(bus) if e.kind == "approval"]
    check("an approval event is published when the queue changes",
          len(seen) == 1, f"published {len(seen)}")
    if seen:
        d = seen[0].data
        check("it carries the count", d.get("count") == 1, repr(d))
        check("it carries the ids", d.get("value") == ["a2"], repr(d))

    stub_gate([{"id": "a2"}])
    pump.tick()
    seen = [e for e in _drain(bus) if e.kind == "approval"]
    check("an unchanged queue publishes nothing", seen == [],
          "a quiet system must produce a quiet stream")


def t_approval_is_a_doorbell_not_a_snapshot():
    import jarvis_events as ev
    bus = ev.Bus()
    pump = ev.Pump(bus=bus, engine=None)
    stub_gate([])
    pump.tick()
    stub_gate([{"id": f"a{i}"} for i in range(25)])
    pump.tick()
    seen = [e for e in _drain(bus) if e.kind == "approval"]
    check("25 pending produces one event", len(seen) == 1)
    if seen:
        d = seen[0].data
        # This is why both clients re-read /api/pending rather than trusting
        # the payload, and why that is correct rather than wasteful.
        check("items are truncated at 10, so the event is a doorbell",
              len(d.get("items", [])) == 10 and d.get("count") == 25,
              f"items={len(d.get('items', []))} count={d.get('count')}")


_CURSOR = {}


def _drain(bus):
    """Only what has been published since the last drain of THIS bus."""
    out, last = [], _CURSOR.get(id(bus), 0)
    for _ in range(50):
        evs, last = _since(bus, last)
        if not evs:
            break
        out.extend(evs)
    _CURSOR[id(bus)] = last
    return out


def _since(bus, last):
    r = bus.since(last)
    evs = r[0] if isinstance(r, tuple) else r
    if not evs:
        return [], last
    return evs, max(getattr(e, "id", last) for e in evs)


def t_the_server_actually_starts_it():
    """CONTROL. Fails if the one line in main() is ever removed again."""
    src = (BACKEND / "jarvis_hud.py").read_text()
    tree = ast.parse(src)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = getattr(f, "attr", None) or getattr(f, "id", None)
        if name == "Pump":
            found.append(node.lineno)
    check("jarvis_hud.py constructs a Pump", bool(found),
          "no Pump(...) call anywhere - approval/power/persona are unpublished")
    started = [n.lineno for n in ast.walk(tree)
               if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "start"]
    check("and starts it", any(abs(l - s) <= 3 for l in found for s in started),
          f"Pump at {found}, no .start() nearby")


if __name__ == "__main__":
    for fn in (t_pump_publishes_approvals, t_approval_is_a_doorbell_not_a_snapshot,
               t_the_server_actually_starts_it):
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
