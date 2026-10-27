"""test_auto_router.py - the cost advisor, and the four gates that bound it.

    python3 backend/test_auto_router.py

WHAT THIS SUITE IS FOR. `jarvis_auto_router.evaluate_route()` is a SECOND entry
point into "should this turn go to a cloud lane?", and a second entry point in a
privacy-critical place is only safe if it is STRICTLY WEAKER than the first.
`jarvis_router.choose()` is the first. So this suite proves, in this order:

  1. the module is shaped the way the loader and the catalogue need it to be
     (`install()` present, a byte-identical twin, a `plugin.json` with no
     `replaces_patch`);
  2. it never raises, whatever it is handed;
  3. each of the FOUR GATES can fail - including the shapes where it must
     refuse, which is the only way a gate can be shown to be a gate at all;
  4. AND THE CHECK THAT MATTERS MOST: this module can never recommend a lane
     that `jarvis_router.choose()` would refuse. That is asserted two ways -
     behaviourally, by driving `choose()` itself with a private question and
     watching the advice collapse to local, and as a PROPERTY over a table of
     prompts, by re-asking the real authority about every prompt this module
     said yes to and requiring the same answer.

WHAT IT CANNOT DO HERE. `jarvis_gate.py` is a core file of the published base,
not one of the modules this repository keeps under `backend/`, so on a clone it
is simply absent. That is not worked around - it is USED: one of the checks
below proves gate 2 refuses when the latch cannot be read at all, which is the
fail-closed direction and the state a clone is really in. The gate's other
shapes are driven with a stand-in.

No network, no model, no owner's PC. Writes only inside a scratch folder of its
own, and removes it.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import sys
import traceback
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _where import BACKEND, REPO, missing, explain  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name
          + (("\n      " + str(detail)) if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print("skip  " + why)


# --------------------------------------------------------------------------
#   The module under test
# --------------------------------------------------------------------------

_GONE = missing("jarvis_auto_router.py")
if _GONE:
    print(f"FAIL  jarvis_auto_router.py is not in {BACKEND} - {explain()}")
    raise SystemExit(1)
sys.path.insert(0, str(BACKEND))
import jarvis_auto_router as AR  # noqa: E402

#: A scratch folder beside the system temp. os.makedirs on a plain base, never
#: tempfile.mkdtemp() on its own: its 0o700 mode raises PermissionError here.
SCRATCH_BASE = Path(os.environ.get("TEMP") or "/tmp") / "jarvis_auto_router_suite"
SCRATCH = None


def scratch() -> Path:
    global SCRATCH
    if SCRATCH is None:
        os.makedirs(SCRATCH_BASE, exist_ok=True)
        SCRATCH = SCRATCH_BASE / uuid.uuid4().hex
        os.makedirs(SCRATCH, exist_ok=True)
    return SCRATCH


# --------------------------------------------------------------------------
#   Stand-ins for the modules a clone may not have
# --------------------------------------------------------------------------

class FakeGate:
    def __init__(self, active=False, raises=False):
        self.active, self.raises = active, raises

    def taint_active(self):
        if self.raises:
            raise RuntimeError("the latch could not be read")
        return self.active


#: A "not set" marker. `returns=None` must be expressible as a RETURN VALUE,
#: which is why None cannot double as "unset".
_UNSET = object()


class FakeScrub:
    """A scrubber. No `out` means "return whatever was passed in"."""

    def __init__(self, out=_UNSET, secret=None, scrub_raises=False,
                 find_raises=False, returns=_UNSET):
        self.out, self.secret = out, secret
        self.scrub_raises, self.find_raises = scrub_raises, find_raises
        self.returns = returns

    def scrub_text(self, text, identifiers=True):
        if self.scrub_raises:
            raise RuntimeError("the scrubber failed")
        if self.returns is not _UNSET:
            return self.returns
        if self.out is _UNSET:
            return text
        return self.out

    def find_secret(self, text):
        if self.find_raises:
            raise RuntimeError("the scrubber could not check")
        return self.secret


class FakeMoney:
    def __init__(self, why="", pid="deepseek_api", model="deepseek-flash", raises=False):
        self.why, self.pid, self.model, self.raises = why, pid, model, raises

    def lane_service(self, lane):
        if self.raises:
            raise RuntimeError("no such lane")
        return self.pid, self.model

    def money_check(self, pid, model, *, next_chars=0, next_messages=0):
        if self.raises:
            raise RuntimeError("the money file could not be read")
        return self.why, 0


class FakeBudget:
    def __init__(self, allows=True):
        self.allows = allows

    def allows_cloud(self):
        return self.allows

    def minute_exceeded(self):
        return not self.allows

    def day_exceeded(self):
        return False


class FakeRouter:
    """Only the two things `budget_allows()` asks a router for."""

    def __init__(self, allows=True):
        self.Budget = type("B", (), {"load": staticmethod(lambda: FakeBudget(allows))})


@contextlib.contextmanager
def stubs(**mods):
    """Replace module-level lookups for one check, restored whatever happens."""
    saved = {name: getattr(AR, name) for name in mods}
    for name, value in mods.items():
        setattr(AR, name, value)
    try:
        yield
    finally:
        for name, value in saved.items():
            setattr(AR, name, value)


def clean(**over):
    """The stand-ins that let the advice reach its cost question, unless a
    check overrides one of them."""
    mods = {"_gate_module": lambda: FakeGate(False),
            "_scrub_module": lambda: FakeScrub(),
            "_money_module": lambda: FakeMoney(),
            "_speed_module": lambda: None}
    mods.update(over)
    return mods


#: A question that is hard enough for `jarvis_router`'s own 0.40 threshold
#: (measured here as 0.6), about nothing private, and long enough that the
#: answer is worth worrying about.
HARD = ("Explain, step by step, how the scheduler decides which job runs first, "
        "and describe the trade-offs in detail.")
#: The same, but asking for a REVIEW - the shape a second, stronger lane used
#: to exist for. It is ONE lane since 2026-10-27; the review words still size
#: the expected ANSWER (`REVIEW_ANSWER_TOKENS`) and nothing else.
REVIEW = "Review this: explain, step by step, the trade-offs in the design."
#: Short and private. `jarvis_router.choose()` must refuse this one on gate
#: "private", and this module must agree.
PRIVATE = "What is my password for the bank?"
PROJECT_OK = {"id": "p1", "shareable": True, "auto_route_cloud": True}


# ==========================================================================
#   1. shape: what the loader and the catalogue need
# ==========================================================================

def t_module_is_where_the_loader_looks():
    check("module: jarvis_auto_router.py is in backend/", (BACKEND / "jarvis_auto_router.py").is_file())
    check("module: evaluate_route() is there and callable", callable(getattr(AR, "evaluate_route", None)))
    check("module: install() is there and callable", callable(getattr(AR, "install", None)))


def t_install_takes_no_arguments_and_serves_no_route():
    """`instal: "none"` calls install() with NOTHING - so it must accept
    nothing, and it must not be a route table in disguise."""
    try:
        line = AR.install()
    except Exception as exc:
        check("install(): callable with no arguments", False, f"{type(exc).__name__}: {exc}")
        return
    check("install(): callable with no arguments", True)
    check("install(): returns the one banner line the loader prints",
          isinstance(line, str) and bool(line.strip()), repr(line))
    check("install(): adds no HTTP handler of its own - this module serves no route",
          not any(hasattr(AR, n) for n in ("handle_get", "handle_post", "do_GET", "do_POST", "PATHS")))


def t_twin_is_byte_identical():
    twin = REPO / "jarvis-backend" / "jarvis_auto_router.py"
    check("twin: jarvis-backend/jarvis_auto_router.py exists", twin.is_file())
    if twin.is_file():
        check("twin: it is byte-identical to backend/jarvis_auto_router.py",
              twin.read_bytes() == (BACKEND / "jarvis_auto_router.py").read_bytes())


def t_plugin_folder():
    folder = REPO / "plugins" / "ready" / "auto-router"
    manifest = folder / "plugin.json"
    check("plugin: plugins/ready/auto-router/plugin.json exists", manifest.is_file())
    if not manifest.is_file():
        return
    data = json.loads(manifest.read_text(encoding="utf-8"))
    check("plugin: it names this module", data.get("module") == "jarvis_auto_router", str(data))
    check("plugin: its name is the folder's name", data.get("name") == "auto-router", str(data))
    check("plugin: no replaces_patch - this feature was born as a folder",
          "replaces_patch" not in data, str(sorted(data)))
    check("plugin: install is handler or none", data.get("install") in ("handler", "none"), str(data))
    check("plugin: it serves no route, so install is none", data.get("install") == "none", str(data))
    check("plugin: stack_order is a whole number", isinstance(data.get("stack_order"), int), str(data))
    check("plugin: it has a summary in plain words", len(str(data.get("summary") or "")) > 40, str(data))
    check("plugin: the README is there", (folder / "README.md").is_file())
    # REWRITTEN 2026-10-15, by the merge that brought `plugins/ready/vault` (145)
    # into the same tree. This used to read "it is the LAST folder in the loader's
    # order" - `stack_order == max(...)` over EVERY folder - which is a claim about
    # every folder added after it as much as about this one, so the next
    # patch-free folder broke it while nothing about the auto-router had changed.
    # That is the same over-claim `backend/test_receipts.py` carried, and it is
    # repaired the same way rather than by moving a folder's number to keep it
    # true. What the claim was for, and what it says now: the auto-router sits
    # AFTER every folder the old patch stack wrote. 141 is `pictures`, the highest
    # position the patch stack has; everything at or below it came from a patch,
    # and the auto-router is above all of them. A folder added later lands after
    # it and this stays true.
    stack_orders = [json.loads(p.read_text(encoding="utf-8")).get("stack_order", 0)
                    for p in (REPO / "plugins" / "ready").glob("*/plugin.json")]
    from_stack = [o for o in stack_orders if isinstance(o, int) and o <= 141]
    check("plugin: it sits after every folder the old patch stack wrote",
          bool(from_stack) and max(from_stack) < data.get("stack_order", 0),
          f"auto-router at {data.get('stack_order')}, the highest from the stack is "
          f"{max(from_stack) if from_stack else None}")


def t_docstring_says_it_advises():
    """The Lead's own instruction, kept as a check: a reader must be able to
    tell in one line that this is not the decision authority."""
    doc = AR.__doc__ or ""
    check("doc: the module docstring says it advises and does not decide",
          bool(re.search(r"ADVISES.*DOES NOT DECIDE", doc, re.S | re.I)), doc[:200])
    check("doc: it cites jarvis_router.choose() by file and line",
          "jarvis_router.py:590" in doc)
    check("doc: it names jarvis_router.choose() as the authority",
          "jarvis_router.choose()" in doc)


# ==========================================================================
#   2. it never raises, and the shape of what it returns
# ==========================================================================

def t_never_raises():
    inputs = [None, "", 123, 4.5, [], {}, (), b"bytes", True,
              "x" * 20000, object()]
    bad = []
    for value in inputs:
        try:
            out = AR.evaluate_route(value)
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{type(value).__name__}: {type(exc).__name__}: {exc}")
            continue
        if not isinstance(out, dict):
            bad.append(f"{type(value).__name__}: returned {type(out).__name__}")
    check("total: any input gives a dict, and none of them raises", not bad, "\n".join(bad))


def t_never_raises_on_odd_keywords():
    odd = [{"context_tokens": "lots"}, {"context_tokens": True},
           {"context_tokens": -5000}, {"context_tokens": float("inf")},
           {"active_project": "not a dict"}, {"active_project": 7},
           {"speed_stats": "fast"}, {"speed_stats": {"tokens_per_s": "x"}},
           {"speed_stats": {"tokens_per_s": -3}}, {"speed_stats": []},
           {"last_turn": 5}, {"last_turn": {"ok": "no"}}, {"enabled": "yes"}]
    bad = []
    for kwargs in odd:
        try:
            out = AR.evaluate_route("hello", **kwargs)
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{kwargs}: {type(exc).__name__}: {exc}")
            continue
        if not isinstance(out, dict):
            bad.append(f"{kwargs}: returned {type(out).__name__}")
    check("total: odd keyword values give a dict too", not bad, "\n".join(bad))


def t_negative_and_bool_context_are_not_tokens():
    check("total: context_tokens=True is not one token",
          AR.evaluate_route("hi", context_tokens=True)["est_local_seconds"]
          == AR.evaluate_route("hi", context_tokens=0)["est_local_seconds"])
    check("total: a negative context does not shrink the estimate below zero context",
          AR.evaluate_route("hi", context_tokens=-9999)["est_local_seconds"]
          == AR.evaluate_route("hi", context_tokens=0)["est_local_seconds"])


def t_result_shape():
    out = AR.evaluate_route("hello")
    need = {"lane", "recommended", "advisory", "gate", "reason", "why",
            "est_local_seconds", "complexity_score", "category", "tokens_per_s",
            "would_send", "lane_if_allowed"}
    check("shape: every key a caller may act on is present",
          need <= set(out), f"missing {sorted(need - set(out))}")
    check("shape: advisory is True - this is advice, never a permission",
          out.get("advisory") is True)
    check("shape: complexity_score is between 0 and 1",
          isinstance(out["complexity_score"], float) and 0.0 <= out["complexity_score"] <= 1.0,
          repr(out["complexity_score"]))
    check("shape: a refusal always names the gate that refused",
          out["lane"] == "local" and bool(out["gate"]) and bool(out["reason"]), repr(out))


def t_a_recommendation_always_carries_scrubbed_text():
    """The invariant a caller must be able to rely on: no recommendation
    without the exact text the scrubber produced."""
    with stubs(**clean()):
        out = AR.evaluate_route(HARD, context_tokens=3000, active_project=PROJECT_OK)
    check("shape: the hard question is actually recommended here (so the next check means something)",
          out["recommended"] is True and out["lane"] == "jarvis-escalate", repr(out))
    check("shape: a recommendation always carries the scrubbed text",
          bool(out.get("would_send")), repr(out.get("would_send")))
    check("shape: the raw prompt is never handed back as the thing to send",
          "would_send" in out and out["would_send"] == HARD or out["would_send"] != "")


# ==========================================================================
#   3. GATE 1 - the mode switch. OFF by default.
# ==========================================================================

def t_gate1_off_by_default():
    out = AR.evaluate_route(HARD, context_tokens=999999)
    check("gate 1: OFF by default in general chat", out["lane"] == "local", repr(out))
    check("gate 1: and it says so", out["gate"] == "auto_route_off", repr(out))
    check("gate 1: complexity alone cannot turn it on - nothing does by existing",
          out["complexity_score"] > 0.0 and out["recommended"] is False, repr(out))


def t_gate1_is_decided_before_anything_else_is_touched():
    """If gate 1 runs first, nothing downstream may be read at all. Modules
    that explode when touched is how that is proved."""
    boom = {"_gate_module": lambda: (_ for _ in ()).throw(AssertionError("gate 2 ran")),
            "_scrub_module": lambda: (_ for _ in ()).throw(AssertionError("gate 4 ran")),
            "_money_module": lambda: (_ for _ in ()).throw(AssertionError("gate 3 ran"))}
    with stubs(**boom):
        out = AR.evaluate_route(HARD, context_tokens=999999)
    check("gate 1: it is decided FIRST - no later gate is even read",
          out["gate"] == "auto_route_off", repr(out))


def t_gate1_explicit_enable():
    with stubs(**clean()):
        out = AR.evaluate_route(HARD, context_tokens=1, enabled=True)
    check("gate 1: enabled=True turns it on and lets the advice through to cost",
          out["gate"] != "auto_route_off", repr(out))


def t_gate1_explicit_disable_beats_the_project():
    with stubs(**clean()):
        out = AR.evaluate_route(HARD, context_tokens=999999,
                                active_project=PROJECT_OK, enabled=False)
    check("gate 1: enabled=False wins over a project that says auto_route_cloud",
          out["gate"] == "auto_route_off", repr(out))


def t_gate1_project_workspace():
    with stubs(**clean()):
        out = AR.evaluate_route(HARD, context_tokens=3000,
                                active_project={"shareable": True, "auto_route_cloud": True})
    check("gate 1: an active Project Mode workspace with auto_route_cloud turns it on",
          out["gate"] != "auto_route_off", repr(out))


def t_gate1_only_exactly_true():
    """The same strictness the rest of this project applies to a flag that lets
    more leave the PC: 1, "yes" and "true" are not True."""
    for value in (1, "yes", "true", [], {}, "True"):
        with stubs(**clean()):
            out = AR.evaluate_route(HARD, context_tokens=3000,
                                    active_project={"shareable": True, "auto_route_cloud": value})
        check(f"gate 1: auto_route_cloud={value!r} does NOT turn it on",
              out["gate"] == "auto_route_off", repr(out))


def t_gate1_switch_file():
    path = scratch() / "auto-route.json"
    with stubs(switch_path=lambda: path):
        check("gate 1: a missing switch file reads as OFF", AR.switch_state()[0] is False)
        path.write_text("{ this is not json", encoding="utf-8")
        check("gate 1: a corrupt switch file reads as OFF", AR.switch_state()[0] is False)
        path.write_text(json.dumps({"enabled": 1}), encoding="utf-8")
        check("gate 1: enabled: 1 (not true) reads as OFF", AR.switch_state()[0] is False)
        path.write_text(json.dumps(["enabled"]), encoding="utf-8")
        check("gate 1: a switch file that is not an object reads as OFF", AR.switch_state()[0] is False)
        path.write_text(json.dumps({"enabled": True}), encoding="utf-8")
        check("gate 1: enabled: true reads as ON", AR.switch_state()[0] is True)
        path.unlink()
        out = AR.evaluate_route(HARD, context_tokens=999999)
    check("gate 1: with no switch file the default really is OFF", out["gate"] == "auto_route_off")


# ==========================================================================
#   4. GATE 2 - the taint latch. A HARD BLOCK, reason taint_latched_local_only.
# ==========================================================================

TAINT_REASON = "taint_latched_local_only"


def t_gate2_refuses_when_the_latch_cannot_be_read():
    """THE REAL STATE OF A CLONE: jarvis_gate.py is a base file, not a backend
    one, so it is absent on a clone. Gate 2 must refuse, not shrug.

    ON THE OWNER'S PC THAT STATE CANNOT BE REACHED: the real gate is installed
    beside the backend (`apply-patches.ps1` later runs this suite against that
    folder, with JARVIS_BACKEND set), so "jarvis_gate is genuinely absent" is a
    check that COULD NOT RUN here. It is therefore said out loud as a skip -
    never counted as a pass and never as a failure (BLOCKED is never a pass) -
    and the gate-2 checks that follow use a stand-in either way.
    """
    real = AR._gate_module()
    if real is None:
        check("gate 2: (about this machine) jarvis_gate is genuinely absent on a clone",
              real is None)
    else:
        skip("(about this machine) jarvis_gate is installed here, so the "
             "'genuinely absent on a clone' check was NOT RUN on this PC; the gate-2 "
             "checks below use a stand-in")
    with stubs(**clean(_gate_module=lambda: None)):
        out = AR.evaluate_route(HARD, context_tokens=3000, active_project=PROJECT_OK)
    check("gate 2: a latch that cannot be read is a HARD BLOCK",
          out["lane"] == "local" and out["recommended"] is False, repr(out))
    check("gate 2: and the reason is exactly the documented one",
          out["reason"] == TAINT_REASON and out["gate"] == TAINT_REASON, repr(out))


def t_gate2_active_latch_blocks():
    with stubs(**clean(_gate_module=lambda: FakeGate(True))):
        out = AR.evaluate_route(HARD, context_tokens=999999, active_project=PROJECT_OK)
    check("gate 2: an ACTIVE taint latch hard-blocks the cloud",
          out["lane"] == "local" and out["reason"] == TAINT_REASON, repr(out))


def t_gate2_raising_latch_blocks():
    with stubs(**clean(_gate_module=lambda: FakeGate(raises=True))):
        out = AR.evaluate_route(HARD, context_tokens=999999, active_project=PROJECT_OK)
    check("gate 2: a latch that raises is a block too",
          out["lane"] == "local" and out["reason"] == TAINT_REASON, repr(out))


def t_gate2_project_not_shareable_blocks():
    """`enabled=True` so gate 1 cannot be what refused: the reason checked below
    has to be gate 2's own."""
    for project in ({"shareable": False}, {"shareable": 0}, {}, {"shareable": None},
                    {"shareable": "no"}, {"id": "p1"}):
        with stubs(**clean()):
            out = AR.evaluate_route(HARD, context_tokens=999999,
                                    active_project=project, enabled=True)
        check(f"gate 2: a project with {project!r} is local-only and blocks",
              out["lane"] == "local" and out["reason"] == TAINT_REASON, repr(out))


def t_gate2_shareable_project_passes():
    with stubs(**clean()):
        out = AR.evaluate_route(HARD, context_tokens=3000, active_project=PROJECT_OK)
    check("gate 2: a project the owner HAS marked shareable passes the gate",
          out["reason"] != TAINT_REASON, repr(out))
    with stubs(**clean()):
        out = AR.evaluate_route(HARD, context_tokens=3000,
                                active_project={"shareable": 1, "auto_route_cloud": True})
    check("gate 2: shareable=1 (the SQLite integer) counts as on",
          out["reason"] != TAINT_REASON, repr(out))


def t_gate2_beats_both_switches():
    """Both switches on, and the latch still wins. That ordering is the policy."""
    with stubs(**clean(_gate_module=lambda: FakeGate(True))):
        out = AR.evaluate_route(HARD, context_tokens=999999, active_project=PROJECT_OK,
                                enabled=True)
    check("gate 2: it blocks even with the mode on AND the workspace on",
          out["lane"] == "local" and out["reason"] == TAINT_REASON, repr(out))


def t_gate2_taint_never_returns_a_lane():
    with stubs(**clean(_gate_module=lambda: FakeGate(True))):
        out = AR.evaluate_route(HARD, context_tokens=999999, active_project=PROJECT_OK)
    check("gate 2: a tainted turn carries no lane and no text to send",
          out["lane"] == "local" and out["would_send"] == "", repr(out))


# ==========================================================================
#   5. GATE 3 - the on-disk budget and the monthly money cap
# ==========================================================================

def t_gate3_monthly_cap_reached_blocks():
    with stubs(**clean(_money_module=lambda: FakeMoney(why="The monthly limit is reached."))):
        out = AR.evaluate_route(HARD, context_tokens=999999, active_project=PROJECT_OK)
    check("gate 3: a reached monthly cap is a no",
          out["lane"] == "local" and out["gate"] == "budget", repr(out))
    check("gate 3: and the owner is told in the cap's own words",
          "monthly limit is reached" in out["why"], repr(out["why"]))


def t_gate3_unconfigured_cap_blocks():
    """THE ONE THAT IS EASY TO GET WRONG: `money_check` returns plain words for
    a limit that was never SET. Unconfigured is not permission to spend."""
    with stubs(**clean(_money_module=lambda: FakeMoney(why="No monthly limit is set for DeepSeek."))):
        out = AR.evaluate_route(HARD, context_tokens=999999, active_project=PROJECT_OK)
    check("gate 3: an UNCONFIGURED cap is a no, not a yes",
          out["lane"] == "local" and out["gate"] == "budget", repr(out))


def t_gate3_missing_module_blocks():
    with stubs(**clean(_money_module=lambda: None)):
        out = AR.evaluate_route(HARD, context_tokens=999999, active_project=PROJECT_OK)
    check("gate 3: no money module at all is a no", out["gate"] == "budget", repr(out))


def t_gate3_raising_money_blocks():
    with stubs(**clean(_money_module=lambda: FakeMoney(raises=True))):
        out = AR.evaluate_route(HARD, context_tokens=999999, active_project=PROJECT_OK)
    check("gate 3: a money file that cannot be read is a no", out["gate"] == "budget", repr(out))


def t_gate3_lane_with_no_service_blocks():
    with stubs(**clean(_money_module=lambda: FakeMoney(pid="", model=""))):
        out = AR.evaluate_route(HARD, context_tokens=999999, active_project=PROJECT_OK)
    check("gate 3: a lane with no service behind it is a no", out["gate"] == "budget", repr(out))


def t_gate3_rate_budget_blocks():
    with stubs(**clean(_router_module=lambda: FakeRouter(allows=False))):
        out = AR.evaluate_route(HARD, context_tokens=999999, active_project=PROJECT_OK)
    check("gate 3: the on-disk per-minute/per-day budget is checked too",
          out["gate"] == "budget", repr(out))


def t_gate3_missing_router_blocks():
    with stubs(**clean(_router_module=lambda: None)):
        out = AR.evaluate_route(HARD, context_tokens=999999, active_project=PROJECT_OK)
    check("gate 3: no router on this PC means nothing can be priced, so it is a no",
          out["gate"] == "budget", repr(out))


# ==========================================================================
#   6. GATE 4 - the scrubber
# ==========================================================================

def t_gate4_missing_scrubber_blocks():
    with stubs(**clean(_scrub_module=lambda: None)):
        out = AR.evaluate_route(HARD, context_tokens=999999, active_project=PROJECT_OK)
    check("gate 4: no scrubber on this PC is a refusal",
          out["lane"] == "local" and out["gate"] == "scrubber_unavailable", repr(out))
    check("gate 4: and nothing is offered to send", out["would_send"] == "", repr(out))


def t_gate4_scrubber_shapes_that_block():
    shapes = {
        "scrub_text raises": FakeScrub(scrub_raises=True),
        "scrub_text returns nothing": FakeScrub(returns=""),
        "scrub_text returns a non-string": FakeScrub(returns=None),
        "find_secret still finds something": FakeScrub(secret="an AWS access key (AKIA… (20 characters))"),
        "find_secret raises": FakeScrub(secret="", find_raises=True),
    }
    for label, fake in shapes.items():
        with stubs(**clean(_scrub_module=lambda fake=fake: fake)):
            out = AR.evaluate_route(HARD, context_tokens=999999, active_project=PROJECT_OK)
        check(f"gate 4: {label} -> refusal",
              out["lane"] == "local" and out["gate"] == "scrubber_unavailable", repr(out))


def t_gate4_returns_the_scrubbed_text_not_the_prompt():
    scrubbed = "Explain [REDACTED API KEY] step by step."
    with stubs(**clean(_scrub_module=lambda: FakeScrub(out=scrubbed))):
        out = AR.evaluate_route(HARD, context_tokens=3000, active_project=PROJECT_OK)
    check("gate 4: what a caller is told to send is the SCRUBBED text",
          out["would_send"] == scrubbed, repr(out["would_send"]))
    check("gate 4: and it is NOT the raw prompt",
          out["would_send"] != HARD, repr(out["would_send"]))


def t_gate4_plain_scrubber_passes():
    with stubs(**clean()):
        out = AR.evaluate_route(HARD, context_tokens=3000, active_project=PROJECT_OK)
    check("gate 4: an ordinary scrubber passes and the text is carried through",
          out["would_send"] == HARD, repr(out["would_send"]))


# ==========================================================================
#   7. THE PROPERTY THAT MAKES A SECOND ENTRY POINT SAFE
# ==========================================================================

def _real_router_decision(text, lane):
    """Ask the shipped authority directly, independently of the module."""
    import jarvis_router as R
    return R.choose(text, local_model="", lanes=[lane], conversation_tainted=False,
                    owner_said_yes=True)


def t_delegation_private_question_collapses_to_local():
    with stubs(**clean()):
        out = AR.evaluate_route(PRIVATE, context_tokens=999999, active_project=PROJECT_OK)
    check("delegation: a PRIVATE question cannot be recommended, however slow it looks",
          out["lane"] == "local" and out["recommended"] is False, repr(out))
    check("delegation: and the refusal is the shipped authority's, by name",
          str(out["gate"]).startswith("router_refused:"), repr(out["gate"]))
    check("delegation: the shipped authority really does refuse it (so the check above means something)",
          _real_router_decision(PRIVATE, "jarvis-escalate").gate != "escalate")


def t_delegation_secret_shaped_text_collapses_to_local():
    secret = ("Explain, step by step, why this fails: "
              "AWS_SECRET=AKIAIOSFODNN7EXAMPLE and token = ghp_" + "a" * 36)
    with stubs(**clean(_scrub_module=lambda: FakeScrub())):
        out = AR.evaluate_route(secret, context_tokens=999999, active_project=PROJECT_OK)
    check("delegation: text carrying a real secret is not recommended off the back of a topic check",
          out["lane"] == "local", repr(out))
    check("delegation: and again the refusal is the authority's own gate",
          str(out["gate"]).startswith("router_refused:"), repr(out["gate"]))


def t_delegation_property_over_a_table():
    """THE CHECK THE LEAD ASKED FOR. For every prompt this module says yes to,
    re-ask the real `jarvis_router.choose()` and require the same answer. If a
    future edit ever lets the advice outrun the authority, this fails."""
    prompts = [HARD, REVIEW, PRIVATE, "hi", "", "x" * 5000,
               "Explain, in detail, the trade-offs, and design the schema.",
               "Summarise my inbox and tell me what is in the files.",
               "What is my api key?", "Review the code, step by step.",
               "Explain, step by step, how the scheduler decides.",
               "Compare, in detail, the two designs; design the protocol."]
    escapes = []
    recommended = []
    for text in prompts:
        with stubs(**clean(_scrub_module=lambda t=text: FakeScrub(out=t))):
            out = AR.evaluate_route(text, context_tokens=4000,
                                    active_project=PROJECT_OK, enabled=True,
                                    speed_stats=1.0, last_turn="failed")
        if out["recommended"]:
            recommended.append((text[:24], out["lane"]))
            # Re-ask the authority about the FULL text it said was safe to
            # send - not a truncation of it, which is a different question.
            decision = _real_router_decision(out["would_send"], out["lane"])
            if decision.gate != "escalate" or decision.lane != out["lane"]:
                escapes.append((text[:24], out["lane"], decision.gate, decision.lane))
    check("delegation property: it recommended something at all (so the property is not vacuously true)",
          bool(recommended), repr(recommended[:3]))
    check("delegation property: NO prompt this module recommends is refused by jarvis_router.choose()",
          not escapes, "\n".join(str(e) for e in escapes))
    check("delegation property: every recommendation named a real cloud lane",
          all(lane == AR.LANE_ESCALATE for _t, lane in recommended),
          repr(recommended[:3]))


def t_delegation_router_absent_or_broken():
    # `evaluate_route`'s gate 3 reads the same module, so with no router at all
    # gate 3 refuses FIRST and `_router_allows`'s own guard is never reached
    # from there. That guard is still real for a direct caller, so it is tested
    # directly rather than through a path that cannot reach it.
    with stubs(**clean(_router_module=lambda: None)):
        out = AR.evaluate_route(HARD, context_tokens=999999, active_project=PROJECT_OK)
    check("delegation: with no router at all, gate 3 refuses (it reads the same module first)",
          out["gate"] == "budget", repr(out))
    with stubs(_router_module=lambda: None):
        allowed, gate, why = AR._router_allows(HARD, AR.LANE_ESCALATE, budget=FakeBudget(True))
    check("delegation: and _router_allows() itself refuses when the router is absent",
          allowed is False and gate == "router_unavailable" and bool(why),
          f"{allowed} {gate} {why}")

    class Boom:
        class Budget:
            @staticmethod
            def load():
                return FakeBudget(True)

        @staticmethod
        def choose(*a, **k):
            raise RuntimeError("no")

    with stubs(**clean(_router_module=lambda: Boom)):
        out = AR.evaluate_route(HARD, context_tokens=999999, active_project=PROJECT_OK)
    check("delegation: a router that will not answer means no advice",
          out["gate"] == "router_error", repr(out))


def t_delegation_low_complexity_is_the_shipped_threshold():
    """A short question is under `jarvis_router`'s own 0.40 complexity line, so
    even with all four gates passing the authority keeps it local - and this
    module must not argue with that."""
    short = "Explain it."
    with stubs(**clean()):
        out = AR.evaluate_route(short, context_tokens=999999, active_project=PROJECT_OK)
    check("delegation: a question under the SHIPPED complexity threshold stays local",
          out["lane"] == "local", repr(out))
    check("delegation: and the shipped authority agrees it is under its threshold",
          _real_router_decision(short, "jarvis-escalate").gate == "complexity",
          repr(_real_router_decision(short, "jarvis-escalate").gate))


# ==========================================================================
#   8. the cost estimate
# ==========================================================================

def t_cost_uses_the_measured_rate():
    slow = AR.evaluate_route(HARD, context_tokens=1000, speed_stats=10.0)
    fast = AR.evaluate_route(HARD, context_tokens=1000, speed_stats=100.0)
    check("cost: a slower measured rate gives a longer estimate",
          slow["est_local_seconds"] > fast["est_local_seconds"],
          f"{slow['est_local_seconds']} vs {fast['est_local_seconds']}")
    check("cost: the rate used is reported back", slow["tokens_per_s"] == 10.0, repr(slow["tokens_per_s"]))
    check("cost: and where it came from is reported too",
          "caller" in slow["tokens_per_s_why"], repr(slow["tokens_per_s_why"]))


def t_cost_more_context_is_more_waiting():
    small = AR.evaluate_route(HARD, context_tokens=100, speed_stats=25.0, enabled=True)
    large = AR.evaluate_route(HARD, context_tokens=10000, speed_stats=25.0, enabled=True)
    check("cost: a longer conversation is more waiting",
          large["est_local_seconds"] > small["est_local_seconds"],
          f"{small['est_local_seconds']} vs {large['est_local_seconds']}")


def t_cost_threshold_is_the_documented_one():
    """Just under the seconds threshold and under the complexity threshold:
    local. The same question with a big conversation: recommended."""
    with stubs(**clean()):
        quick = AR.evaluate_route(HARD, context_tokens=0, active_project=PROJECT_OK,
                                 speed_stats=100.0)
    check("cost: a quick turn is not worth mentioning",
          quick["lane"] == "local" and quick["gate"] == "not_worth_it", repr(quick))
    check("cost: and the seconds threshold really is 25.0", AR.SECONDS_THRESHOLD == 25.0)
    check("cost: and the complexity threshold really is 0.75", AR.COMPLEXITY_THRESHOLD == 0.75)
    with stubs(**clean()):
        slow = AR.evaluate_route(HARD, context_tokens=3000, active_project=PROJECT_OK,
                                 speed_stats=25.0)
    check("cost: a predicted wait over the threshold IS worth mentioning",
          slow["recommended"] is True and slow["est_local_seconds"] > 25.0, repr(slow))


def t_cost_reported_numbers_are_the_ones_used():
    out = AR.evaluate_route(HARD, context_tokens=2000, speed_stats=20.0, enabled=True)
    expected = AR.est_local_seconds(HARD, 2000, out["category"], 20.0)
    check("cost: the reported estimate is the one the module computed",
          out["est_local_seconds"] == expected, f"{out['est_local_seconds']} vs {expected}")
    check("cost: the thresholds travel with the answer, so a caller need not hard-code them",
          out["thresholds"] == {"seconds": 25.0, "complexity": 0.75}, repr(out["thresholds"]))


def t_measured_rate_says_which_number_it_used():
    rate, why = AR.measured_rate(42.0)
    check("rate: a caller's own number is used and said so", rate == 42.0 and "caller" in why, f"{rate} {why}")
    with stubs(_speed_module=lambda: None):
        rate, why = AR.measured_rate()
    check("rate: with no measurement on this PC the DEFAULT is used, and admitted",
          rate == AR.DEFAULT_TOKENS_PER_S and "default" in why, f"{rate} {why}")
    rate, why = AR.measured_rate({"by_model": {"m": {"median_tokens_per_s": 33.0}}})
    check("rate: a per-model table is read", rate == 33.0, f"{rate} {why}")
    rate, why = AR.measured_rate({"tokens_per_s": 0})
    check("rate: a zero in the caller's numbers is not used as a rate",
          rate == AR.DEFAULT_TOKENS_PER_S or "caller" not in why, f"{rate} {why}")


# ==========================================================================
#   9. the complexity score
# ==========================================================================

def t_complexity_indicators():
    plain = AR.complexity_score("Explain the scheduler.")
    multi = AR.complexity_score("Refactor this across every file and each module.")
    arch = AR.complexity_score("Design the schema and the protocol, with the trade-offs.")
    check("complexity: multi-file words raise the score", multi > plain, f"{plain} -> {multi}")
    check("complexity: architecture words raise the score", arch > plain, f"{plain} -> {arch}")
    check("complexity: it is capped at 0.45 on words alone",
          AR.complexity_score("refactor every file across files, each module, all modules, "
                              "the whole repo, sweep, throughout the codebase, "
                              "architect the schema, design the protocol, migrate, "
                              "concurrency, deadlock, dependency graph, distributed") <= 0.45 + 1e-9)


def t_complexity_heavy_context():
    base = AR.complexity_score("Explain the scheduler.", 0)
    heavy = AR.complexity_score("Explain the scheduler.", 4000)
    check("complexity: a conversation over 3500 tokens adds its weight",
          heavy == round(base + AR.W_HEAVY_CONTEXT, 3), f"{base} -> {heavy}")
    check("complexity: exactly 3500 tokens does NOT (it must be over)",
          AR.complexity_score("Explain the scheduler.", 3500) == base,
          repr(AR.complexity_score("Explain the scheduler.", 3500)))


def t_complexity_prior_bad_turn():
    base = AR.complexity_score("Explain the scheduler.")
    for turn in ({"ok": False}, {"empty": True}, {"status": "failed"},
                 "failed", "empty", "timeout", {"outcome": "error"}):
        got = AR.complexity_score("Explain the scheduler.", 0, turn)
        check(f"complexity: a prior {turn!r} adds its weight",
              got == round(base + AR.W_PRIOR_BAD_TURN, 3), f"{base} -> {got}")


def t_complexity_good_turn_adds_nothing():
    base = AR.complexity_score("Explain the scheduler.")
    for turn in ({"ok": True}, {"empty": False}, {"status": "ok"}, "fine", 5, []):
        got = AR.complexity_score("Explain the scheduler.", 0, turn)
        check(f"complexity: {turn!r} is not a failure and adds nothing", got == base, f"{base} -> {got}")


def t_complexity_clamped_and_bounded():
    worst = AR.complexity_score(
        "refactor every file across files, each module, all modules, the whole repo, "
        "architect the schema, design the protocol, migrate, concurrency, deadlock",
        100000, {"ok": False, "empty": True})
    check("complexity: it is clamped to 1.0 and never above", worst == 1.0, repr(worst))
    check("complexity: an empty prompt scores 0", AR.complexity_score("") == 0.0)
    check("complexity: a non-string prompt scores 0", AR.complexity_score(None) == 0.0)
    check("complexity: the threshold is reachable on indicators plus a failed turn alone",
          AR.complexity_score("Refactor this across every file and design the schema.", 0,
                              {"ok": False}) >= AR.COMPLEXITY_THRESHOLD)


# ==========================================================================
#   10. the ONE lane, and the category
# ==========================================================================

def t_review_is_the_same_one_lane():
    """`jarvis-critic` is gone (2026-10-27): a review is a longer ANSWER, not a
    second lane. This replaced `t_review_goes_to_the_critic`, and it keeps the
    bite that matters - the module cannot offer a lane that no longer exists,
    and a review still gets a suggestion rather than nothing."""
    with stubs(**clean()):
        out = AR.evaluate_route(REVIEW, context_tokens=3000, active_project=PROJECT_OK)
    check("review: a review task is offered the ONE lane, jarvis-escalate",
          out["recommended"] is True and out["lane"] == AR.LANE_ESCALATE, repr(out))
    check("review: the module has no critic lane to offer any more",
          not hasattr(AR, "LANE_CRITIC") and not hasattr(AR, "_REVIEW"),
          [n for n in ("LANE_CRITIC", "_REVIEW") if hasattr(AR, n)])
    with stubs(**clean()):
        out = AR.evaluate_route(HARD, context_tokens=3000, active_project=PROJECT_OK)
    check("review: an ordinary hard task is offered the same lane",
          out["lane"] == AR.LANE_ESCALATE, repr(out))


def t_review_detection():
    check("review: 'Review this' is a review", AR.is_review("Review this, step by step."))
    check("review: a coding job is one too, because the ANSWER is long",
          AR.is_review("Write a script that renames every file in this folder."))
    check("review: an ordinary explain is not", not AR.is_review("Explain the scheduler."))
    check("review: a caller may say the turn being reviewed IS a review",
          AR.is_review("Explain it.", {"kind": "review"}))
    check("review: and a caller's non-review is not", not AR.is_review("Explain it.", {"kind": "answer"}))


def t_category_is_a_string_from_jarvis_work_or_general():
    got = AR.category_of(HARD)
    check("category: it is always a non-empty string",
          isinstance(got, str) and bool(got.strip()), repr(got))
    check("category: a non-string prompt gives 'general'", AR.category_of(None) == "general")
    with stubs(_work_module=lambda: None):
        check("category: no jarvis_work on this PC gives 'general'",
              AR.category_of(HARD) == "general")


# ==========================================================================
#   11. the page no caller has to read: it writes nothing
# ==========================================================================

def t_it_writes_nothing_and_reaches_nothing():
    src = (BACKEND / "jarvis_auto_router.py").read_text(encoding="utf-8")
    for forbidden in ("urllib", "requests", "socket", "subprocess", "webbrowser",
                      "http.client", "open(", "write_text", "mkdir", "logging"):
        check(f"quiet: it never does {forbidden!r}", forbidden not in src, forbidden)


def main() -> int:
    global SCRATCH  # noqa: PLW0603
    funcs = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("t_") and callable(fn)]
    for name, fn in funcs:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            check(f"{name} raised", False,
                  f"{type(exc).__name__}: {exc}\n" + traceback.format_exc())
    if SCRATCH is not None:
        shutil.rmtree(SCRATCH, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + "\n        ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
