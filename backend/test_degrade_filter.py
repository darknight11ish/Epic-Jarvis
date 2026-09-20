"""A cloud turn that steps down to local and back out again went unfiltered.

The cloud-lane privacy control is one comprehension near the top of the chat
handler: on a cloud decision, keep only `role == "user"` messages. Its comment
explains why at length - the assistant turn is a carrier, it restates injected
memory, so only what you typed goes upstream.

It runs ONCE. `is_cloud` is computed once, above the degrade loop, and never
re-evaluated. The loop then has a branch that, on landing at the local model,
restores the RAW client transcript:

    if lane == local_model and not decision.inject_memory:
        messages = body.get("messages") or []
        decision.inject_memory = True

and nothing ever put the filter back. The loop is sized `len(lanes) + 2`
precisely because it expects hops after that one.

The other direction had no guard at all: a LOCAL turn carrying the
recalled-facts block could be handed a cloud lane by `degrade()` and the facts
would go with it.

This test executes the real loop, lifted from the source with ast, and drives
it with a stub router.

    python3 test_degrade_filter.py
"""
import ast, sys, traceback, types, urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# BACKEND is where the modules under test actually live - this folder in
# the dev container, $JARVIS_BACKEND on a real install. REPO is this
# repository. They used to be the same path and are not on the machine
# that runs Jarvis.
from _where import BACKEND, REPO, missing, explain
SRC = BACKEND / "jarvis_hud.py"

FAILED, PASSED = [], []
SECRET = "42 Elm Street"
CARRIER = "your Joplin vault says the lease ends in March"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _loop():
    """The real `for _hop in range(len(lanes) + 2):` block."""
    src = SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    found = [n for n in ast.walk(tree)
             if isinstance(n, ast.For) and "len(lanes) + 2" in (ast.unparse(n.iter) or "")]
    if len(found) != 1:
        raise AssertionError(f"expected one degrade loop, found {len(found)}")
    return compile(ast.Module(body=[found[0]], type_ignores=[]), "<lifted>", "exec")


class Decision:
    def __init__(self, lane, inject):
        self.lane, self.inject_memory, self.reason, self.gate = lane, inject, "r", "g"


def run(*, start_lane, inject_memory, messages, codes, raw=None):
    """Drive the loop.

    `messages` is what the handler has built for this lane (filtered on a
    cloud turn). `raw` is what the CLIENT sent, which is what lives in
    body["messages"] and what the local-rebuild branch restores from - so it
    must be the unfiltered transcript, or the control below tests nothing.
    `codes` is the HTTP status each _open call raises.
    """
    raw = messages if raw is None else raw
    LOCAL = "qwen3:8b"
    LANES = ["jarvis-escalate", "jarvis-critic"]
    seen = []
    it = iter(codes)

    def _open(lane):
        seen.append((lane, [m.get("role") for m in ns["messages"]],
                     [m.get("content", "") for m in ns["messages"]]))
        code = next(it, None)
        if code is None:
            return object()
        raise urllib.error.HTTPError("u", code, "e", {}, None)

    router = types.SimpleNamespace(
        # The worst case the loop's own comment says cannot happen. It is a
        # contract with a module this loop never checks, so the test breaks it.
        degrade=lambda lane, lanes, local: (
            local if lane in lanes else LANES[1] if lane == local else None))

    ns = {
        "lanes": LANES, "local_model": LOCAL, "_open": _open,
        "jarvis_router": router, "urllib": urllib,
        "decision": Decision(start_lane, inject_memory),
        "lane": start_lane, "upstream": None, "first_error": None,
        "DEGRADABLE": {429, 500, 502, 503, 504},
        "messages": list(messages),
        "body": {"messages": list(raw)},
        "route_header": {"reason": "r", "lane": start_lane,
                         "inject_memory": inject_memory,
                         "injected_facts": 2 if inject_memory else 0,
                         "injected_ids": ["mem:1"] if inject_memory else [],
                         "memory_side": "hud" if inject_memory else "none"},
        "_build_payload": lambda lane: {"model": lane},
    }
    exec(CODE, {"len": len, "range": range, "isinstance": isinstance,
                "dict": dict, "list": list, "str": str}, ns)
    return seen, ns


CODE = _loop()

CLOUD_TURN = [
    {"role": "user", "content": "where does Mario live"},
    {"role": "assistant", "content": f"{SECRET}. Also {CARRIER}"},
    {"role": "user", "content": "thanks"},
]
LOCAL_TURN = [
    {"role": "user", "content": "where does Mario live"},
    {"role": "assistant", "content": f"{CARRIER}"},
    {"role": "system", "content": f"Things you know about the user:\n- Mario lives at {SECRET}"},
    {"role": "user", "content": "and his allergy"},
]


def _leaks(seen, local="qwen3:8b"):
    out = []
    for lane, roles, contents in seen:
        if lane == local:
            continue
        for c in contents:
            if SECRET in c or CARRIER in c:
                out.append((lane, c[:60]))
    return out


def t_cloud_then_local_then_cloud():
    seen, ns = run(start_lane="jarvis-escalate", inject_memory=False,
                   messages=[m for m in CLOUD_TURN if m["role"] == "user"],
                   raw=CLOUD_TURN, codes=[429, 503])
    lanes = [s[0] for s in seen]
    check("the loop really does hop cloud -> local -> cloud",
          lanes == ["jarvis-escalate", "qwen3:8b", "jarvis-critic"], repr(lanes))
    check("nothing the assistant said reaches the second cloud lane",
          _leaks(seen) == [], f"leaked: {_leaks(seen)}")
    check("the second cloud lane sees user turns only",
          all(set(r) <= {"user"} for l, r, _ in seen if l != "qwen3:8b"),
          repr([(l, r) for l, r, _ in seen]))


def t_local_with_memory_degrading_to_cloud():
    seen, ns = run(start_lane="qwen3:8b", inject_memory=True,
                   messages=LOCAL_TURN, codes=[503])
    lanes = [s[0] for s in seen]
    check("a local turn can be handed a cloud lane", len(lanes) == 2 and lanes[1] != "qwen3:8b",
          repr(lanes))
    check("the recalled-facts block does not go with it", _leaks(seen) == [],
          f"leaked: {_leaks(seen)}")
    check("and the route header stops claiming memory was injected",
          ns["route_header"]["inject_memory"] is False
          and ns["route_header"]["injected_facts"] == 0
          and ns["route_header"]["memory_side"] == "none",
          repr(ns["route_header"]))
    check("the header says why", "not local" in ns["route_header"]["reason"],
          ns["route_header"]["reason"])


def t_the_local_rebuild_still_works():
    """CONTROL. The fix must not break the branch it sits beside."""
    seen, ns = run(start_lane="jarvis-escalate", inject_memory=False,
                   messages=[m for m in CLOUD_TURN if m["role"] == "user"],
                   raw=CLOUD_TURN, codes=[429])
    local = [s for s in seen if s[0] == "qwen3:8b"]
    check("landing on local restores the full transcript", bool(local)
          and "assistant" in local[0][1], repr(seen))
    check("and turns memory back on for it", ns["decision"].inject_memory is True)


def t_a_cloud_turn_that_never_degrades():
    """CONTROL. No hop, no filtering, no change."""
    seen, ns = run(start_lane="jarvis-escalate", inject_memory=False,
                   messages=[m for m in CLOUD_TURN if m["role"] == "user"],
                   raw=CLOUD_TURN, codes=[])
    check("one lane, one call", len(seen) == 1 and seen[0][0] == "jarvis-escalate", repr(seen))
    check("nothing was stripped that was not already stripped",
          len(ns["messages"]) == 2, repr(ns["messages"]))


if __name__ == "__main__":
    for fn in (t_cloud_then_local_then_cloud, t_local_with_memory_degrading_to_cloud,
               t_the_local_rebuild_still_works, t_a_cloud_turn_that_never_degrades):
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
