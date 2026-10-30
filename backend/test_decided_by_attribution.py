"""A decision says WHO made it, and a decided card leaves the queue.

    python3 test_decided_by_attribution.py

WHY THIS EXISTS

The owner's field evidence of 2026-10-29: a card **denied from the Android
phone** was stored by the PC as `decided_by:"hud"`. The attribution is the
smallest possible lie - the card really was decided, and nothing ran that should
not have - but it is a lie the Activity list on both apps repeats back to the
owner ("answered at the HUD" about a card answered in his hand), and it makes
the one question an audit of approvals has to answer ("who said yes?")
unanswerable.

The cause was one absent field, not a missing rule:

    Desktop  ->  {"id": "<id>", "by": "desktop_spotlight"}   commands.rs
    HUD page ->  {"id": "<id>", "by": "hud"}                 jarvis_hud.html
    Android  ->  {"id": "<id>"}                              JarvisApi.postId

`jarvis_hud.py`'s route reads `by` and defaults an absent one to `"hud"`, so
every phone decision was recorded as the browser HUD's.
`docs/JARVIS-API.md` §7 carried this as an OPEN disagreement between the two
clients - "the two clients send different bodies ... neither client knows
whether the server reads `by` at all". The server does read it. This suite
pins both halves of the answer:

  1. t_the_route_reads_by_and_defaults_to_hud
     The route the phone posts to takes `by` from the body (so the client can
     name itself) and falls back to "hud" only when it is absent or empty.
  2. t_a_decision_is_stored_with_the_word_it_was_sent
     `jarvis_gate.decide(..., by="phone")` stores "phone" verbatim, and the card
     is gone from the next `pending()` - the ONE read every surface (the phone's
     widget, its notification, Home, the desktop bar, the widget, the HUD) takes
     its queue from.
  3. t_a_second_answer_is_refused_shape_only
     "Answering once" is what makes a decided card harmless on a surface that
     has not learned about it yet: the second POST is refused rather than
     recording a verdict on a settled row. This is the server half of the story;
     the client half is the 409 the phone turns into "Already handled" and the
     queue re-read that clears the card.

WHAT IT DRIVES. `jarvis_gate.py` is the owner's file; this repository holds the
published base in `jarvis-backend/` (`backend/test_base_matches_repo.py` keeps
the two in step). The gate is loaded from that base with `JARVIS_APPROVALS_DB`
pointed into a scratch folder, so nothing here touches the owner's real
approvals database, needs his PC, or needs the network.

Runs anywhere Python 3 does. `python3 -B test_decided_by_attribution.py`.
"""
from __future__ import annotations

import ast
import importlib
import os
import sys
import tempfile
import time
import traceback
from contextlib import closing

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _where import BACKEND, REPO  # noqa: E402

BASE = REPO / "jarvis-backend"

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok   " if cond else "FAIL ") + name + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this run cannot make, printed as `skip` and counted on its own -
    never as a pass."""
    SKIPPED.append(why)
    print("skip  " + why)


# --------------------------------------------------------------------------
#  1. The route
# --------------------------------------------------------------------------

def t_the_route_reads_by_and_defaults_to_hud():
    src_path = BASE / "jarvis_hud.py"
    if not src_path.is_file():
        skip(f"jarvis_hud.py is not in {BASE} - only the owner's PC has the live one")
        return
    src = src_path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    found = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if getattr(func, "attr", None) != "decide":
            continue
        # `jarvis_gate.decide(rid, route == "/api/approve", by=...)`
        if getattr(func, "value", None) is None:
            continue
        if getattr(func.value, "id", "") != "jarvis_gate":
            continue
        found = node
    check("the /api/approve and /api/deny route calls jarvis_gate.decide",
          found is not None, "no jarvis_gate.decide(...) call in jarvis_hud.py")
    if found is None:
        return
    by = [k for k in found.keywords if k.arg == "by"]
    check("it passes `by` through from the request body", bool(by),
          f"keywords: {[k.arg for k in found.keywords]}")
    if not by:
        return
    # `by=str(body.get("by") or "hud")[:64]` - the default is what the phone
    # used to inherit by sending no field at all.
    text = ast.get_source_segment(src, by[0].value) or ""
    check('an absent "by" still defaults to "hud"', '"hud"' in text, text)
    check("and it is capped, because it lands in a stored column", "64" in text, text)


# --------------------------------------------------------------------------
#  2 and 3. The gate
# --------------------------------------------------------------------------

def load_gate(tmp: str):
    """The published base's own jarvis_gate, against a scratch database."""
    os.environ["JARVIS_APPROVALS_DB"] = os.path.join(tmp, "approvals.db")
    sys.path.insert(0, str(BASE))
    for name in [m for m in list(sys.modules) if m.startswith("jarvis_gate")]:
        del sys.modules[name]
    return importlib.import_module("jarvis_gate")


def raise_card(gate, request_id: str, action: str = "send_email") -> None:
    """One waiting row, written the way the gate's own `check()` writes it -
    the columns it reads back are the ones `pending()` SELECTs. The waiting
    thread `check()` would normally hold open is deliberately not here: the row
    is the card, and a decision on it is what these checks are about."""
    gate._init()
    with closing(gate._connect()) as c:
        c.execute(
            "INSERT INTO approvals (id, action, tier, detail, prompt, state, created)"
            " VALUES (?,?,?,?,?,'pending',?)",
            (request_id, action, "ask", '{"to": "a@example.com"}', "send it", time.time()),
        )


def t_a_decision_is_stored_with_the_word_it_was_sent():
    tmp = tempfile.mkdtemp(prefix="jarvis-decided-by-")
    gate = load_gate(tmp)
    raise_card(gate, "card-phone-1")
    waiting = [r["id"] for r in gate.pending()]
    check("the card is served by pending() before it is answered",
          "card-phone-1" in waiting, repr(waiting))

    ok = gate.decide("card-phone-1", False, by="phone")
    check("the denial was accepted", ok is True, repr(ok))

    waiting = [r["id"] for r in gate.pending()]
    check("and it is gone from the next read - the ONE read every surface takes",
          "card-phone-1" not in waiting, repr(waiting))

    rows = {r["id"]: r for r in gate.history(50)}
    row = rows.get("card-phone-1")
    check("history still carries it, as denied", bool(row) and row["state"] == "denied",
          repr(row))
    check('and the phone is who it says answered - not the "hud" default',
          bool(row) and row["decided_by"] == "phone", repr(row and row["decided_by"]))
    check("with a decision time, which is what both apps' Activity list reads",
          bool(row) and isinstance(row["decided"], float) and row["decided"] > 0,
          repr(row and row["decided"]))


def t_a_second_answer_is_refused_shape_only():
    tmp = tempfile.mkdtemp(prefix="jarvis-decided-once-")
    gate = load_gate(tmp)
    raise_card(gate, "card-phone-2")
    check("first answer accepted", gate.decide("card-phone-2", False, by="phone") is True)
    check("second answer refused - a stale surface cannot record a verdict on a settled row",
          gate.decide("card-phone-2", True, by="hud") is False)
    row = {r["id"]: r for r in gate.history(50)}["card-phone-2"]
    check("and the first answer is the one kept",
          row["state"] == "denied" and row["decided_by"] == "phone", repr(row))


# --------------------------------------------------------------------------
#  4. The ring - "two surfaces, decide on one, the other is told"
# --------------------------------------------------------------------------

def t_the_ring_follows_a_decision_within_one_tick():
    """The end-to-end shape of the whole change, hermetically.

    Two readers stand in for two surfaces - the phone's widget and the
    desktop's bar - and both take their queue from the ONE read. A card is
    raised; both see it. It is answered as if on the phone (`by="phone"`); the
    backend's own pump ticks once; both surfaces are told, and the next read
    both make holds no card.

    Why this is worth a test of its own: the `approval` frame is what every
    surface re-reads ON, and it is published only when the id list CHANGES
    (`jarvis_events._poll_approvals` -> `Bus.note`). A decision that left the
    queue without changing the ids - or a poller that never ran - would leave
    both surfaces believing a decided card was still waiting, which is exactly
    the owner's report. This drives the real `jarvis_events.Pump` against the
    real gate, so the claim is measured rather than argued.
    """
    try:
        sys.path.insert(0, str(REPO / "backend" / "rebuilt"))
        import jarvis_events as ev
    except Exception as exc:                                  # pragma: no cover
        skip(f"jarvis_events is not importable here ({exc})")
        return

    tmp = tempfile.mkdtemp(prefix="jarvis-ring-")
    gate = load_gate(tmp)
    bus = ev.Bus()
    pump = ev.Pump(bus=bus, engine=None)

    def read_queue():
        """What a surface actually gets: the one read, ids only."""
        return sorted(str(r["id"]) for r in gate.pending())

    raise_card(gate, "ring-1")
    pump.tick()                       # a poller's first observation is a baseline
    check("the rise is the baseline: no event yet", _drain(bus) == [], "an arrival rings once it moves")
    first = read_queue()
    check("surface A (the phone's widget) sees the card", first == ["ring-1"], repr(first))
    check("surface B (the desktop's bar) reads the same one list", read_queue() == first,
          "a second read is the same list - one source, not two")

    pump.tick()                       # an unchanged queue is still the baseline
    check("an unchanged queue publishes nothing", _drain(bus) == [],
          "a quiet system must produce a quiet stream")

    gate.decide("ring-1", False, by="phone")
    pump.tick()                       # ONE tick after the decision
    seen = [e for e in _drain(bus) if e.kind == "approval"]
    check("one tick after the decision, the ring has gone out", len(seen) == 1,
          f"published {len(seen)} approval event(s)")
    if seen:
        check("and it carries the empty id list, so a surface can only conclude 'gone'",
              seen[0].data.get("value") == [] and seen[0].data.get("count") == 0,
              repr(seen[0].data))
    check("both surfaces' next read holds no card", read_queue() == [], repr(read_queue()))


_CURSOR = {}


def _drain(bus):
    """Only what has been published since the last drain of THIS bus."""
    out, last = [], _CURSOR.get(id(bus), 0)
    for _ in range(50):
        r = bus.since(last)
        evs = r[0] if isinstance(r, tuple) else r
        if not evs:
            break
        last = max(getattr(e, "id", last) for e in evs)
        out.extend(evs)
    _CURSOR[id(bus)] = last
    return out



if __name__ == "__main__":
    for fn in (t_the_route_reads_by_and_defaults_to_hud,
               t_a_decision_is_stored_with_the_word_it_was_sent,
               t_a_second_answer_is_refused_shape_only,
               t_the_ring_follows_a_decision_within_one_tick):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
