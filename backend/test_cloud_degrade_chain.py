"""test_cloud_degrade_chain.py - a degrade step may only land on a lane that exists.

    python3 backend/test_cloud_degrade_chain.py

THE FINDING (owner's PC, 2026-11-18, brought in with the cloud-escalation
trace). The owner's live `jarvis-framework.toml` still said:

    [budget]
    degrade_chain = ["jarvis-escalate", "jarvis-bulk", "jarvis-critic"]

The owner's decision of 2026-10-27 collapsed the three cloud lanes into ONE
(`jarvis-escalate`; docs/DECISIONS.md that date), and the repository's own
`rebuilt/jarvis-framework.toml` has said `["jarvis-escalate"]` since then. His
file was never corrected because `scripts/apply-patches.ps1` keeps every line
of an existing settings file - correctly, since most of those lines are HIS
choices - so the corrected value reached a fresh install and never his.

WHY THAT MATTERED, AND WHY IT IS A CODE DEFECT AND NOT ONLY A CONFIG ONE.
`jarvis_router.degrade()` read the chain and returned the next name, whatever
it was. The HUD's relay then calls that name:

  * `jarvis_chatbot_api.lane_service()` maps a name it does not know to the
    CHOSEN service, so "jarvis-bulk" was not "no such lane" - it was a SECOND
    real request to the same provider with the same key, after a 429 had
    already said stop. "jarvis-critic" was a third;
  * the lane that finally answered was not in the caller's `lanes` list, so
    `jarvis_hud`'s `if ... lane in lanes: budget.spend()` did not count the
    call - the per-minute / per-day cloud budget could be walked around by
    the rate limit it exists to absorb;
  * only when the stale chain ran out did the turn reach this PC.

WHAT THIS SUITE PROVES

  1. Both repository copies of the shipped settings file name only lanes the
     code really has - so a fresh install and the base cannot reintroduce the
     dead names.
  2. The REPRODUCED live shape (the three stale names stubbed as the chain)
     cannot make `degrade()` return a dead name: it lands on the next real
     lane and then on local.
  3. A day-limit hit is answered on this PC with gate "budget" (a safe push
     back to local, never a drop), and the lane it lands on exists.
  4. The per-minute / per-day cap EXISTS in the shipped config and in the
     module's own defaults - an absent `budget.json` means "no calls recorded
     yet", not "no cap" - and it binds once a call is recorded.

No network, no key, no model, no live lane: `choose()` and `degrade()` are pure
Python and the budget is a scratch file. The owner's real config and data are
never read or written (a temporary config folder is set before import).
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
REBUILT = HERE / "rebuilt"

#: A scratch settings folder BEFORE anything imports the modules: the budget
#: file, the audit log and any state they read live under it.
SCRATCH = Path(tempfile.mkdtemp(prefix="jarvis-degrade-chain-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ.setdefault("JARVIS_APPROVAL_TIMEOUT", "2.0")
os.environ["JARVIS_NTFY_TOPIC"] = ""
os.environ["JARVIS_NTFY_SERVER"] = ""

#: The shipped settings file - the same one `scripts/apply-patches.ps1` installs
#: on a fresh PC and compares a live file against.
SHIPPED = (REBUILT / "jarvis-framework.toml", REPO / "jarvis-backend" / "jarvis-framework.toml")
CONFIG = REBUILT / "jarvis-framework.toml"
os.environ["JARVIS_FRAMEWORK_TOML"] = str(CONFIG)

sys.dont_write_bytecode = True
sys.path.insert(0, str(REBUILT))

import jarvis_router as RT  # noqa: E402

FAILED, PASSED = [], []

#: The owner's live line, read off his PC on 2026-11-18 (`jarvis-framework.toml`
#: line 348). It is the INPUT of the reproduction, never a claimed lane.
STALE = ["jarvis-escalate", "jarvis-bulk", "jarvis-critic"]
#: The lane the code really has (the owner's 2026-10-27 decision).
CLOUD = RT.CLOUD_LANE
LOCAL = "qwen3.5:9b"
#: Long and clause-heavy, plainly non-private: the complexity gate alone would
#: let it out, so a refusal below can only come from the gate named.
HARD = ("Explain in detail how the three-body problem differs from the two-body "
        "problem, and why the difference matters for predicting orbits.")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def _toml(path: Path) -> dict:
    try:
        import tomllib
    except ImportError:                                  # Python < 3.11
        import tomli as tomllib                          # type: ignore
    return tomllib.loads(path.read_bytes().decode("utf-8-sig"))


def _chain(cfg: dict) -> list:
    return list((cfg.get("budget") or {}).get("degrade_chain") or [])


def _with_chain(chain):
    """Stub the configured chain, keeping every other config answer real."""
    keep = RT._cfg

    def stubbed(section, key, default=None):
        if (section, key) == ("budget", "degrade_chain"):
            return list(chain)
        return keep(section, key, default)

    RT._cfg = stubbed
    return keep


def _restore(keep):
    RT._cfg = keep


def _existing_lanes(lanes=()):
    """Every name a degrade step is allowed to answer: the real cloud lane(s)
    in the caller's own list, plus the local floor."""
    return set(RT.cloud_lanes(list(lanes))) | {LOCAL}


# ==========================================================================
#  1. the settings files the deploy ships
# ==========================================================================

def t_the_shipped_settings_files_name_only_lanes_that_exist():
    chains = {}
    for path in SHIPPED:
        check(f"{path.parent.parent.name}/{path.name} is here", path.is_file(), path)
        if not path.is_file():
            continue
        chains[str(path)] = _chain(_toml(path))
    for path, chain in chains.items():
        check(f"{path.split(os.sep)[-3]}/{path.split(os.sep)[-1]}: degrade_chain "
              f"names the ONE cloud lane and nothing else",
              chain == [CLOUD], chain)
        check(f"... every name in it is a lane the code really has ({path})",
              set(chain) <= set(RT.cloud_lanes(chain)), chain)
    values = {tuple(chain) for chain in chains.values()}
    check("both repository copies agree about the chain", len(values) == 1, values)


# ==========================================================================
#  2. the reproduced live shape
# ==========================================================================

def t_a_stale_chain_cannot_step_to_a_lane_that_does_not_exist():
    keep = _with_chain(STALE)
    try:
        # The HUD passes the caller's own cloud lanes; with a provider chosen
        # that list is exactly [CLOUD]. The stale chain is what his file said.
        got = RT.degrade(CLOUD, lanes=[CLOUD], local_model=LOCAL)
        check("a 429 on the cloud lane steps to THIS PC, not to a dead name",
              got == LOCAL, repr(got))
        check("... and the name it returned is a lane that exists",
              got in _existing_lanes([CLOUD]), repr(got))
        # The historical names directly, as a lane list an old client might
        # send: the walk must still end on the caller's real lane or local.
        for lane in STALE:
            got = RT.degrade(lane, lanes=[CLOUD], local_model=LOCAL)
            check(f"degrade({lane!r}) against the real lane list never returns a "
                  f"dead name", got in _existing_lanes([CLOUD]), repr(got))
        # An empty caller list has no cloud lane at all; local is the answer.
        got = RT.degrade(CLOUD, lanes=[], local_model=LOCAL)
        check("with no cloud lane offered, the step is local", got == LOCAL, repr(got))
    finally:
        _restore(keep)


def t_a_dead_name_alone_is_dropped_not_substituted():
    keep = _with_chain(["jarvis-bulk", "jarvis-critic"])
    try:
        got = RT.degrade(CLOUD, lanes=[CLOUD], local_model=LOCAL)
        check("a chain of nothing but removed names steps to this PC",
              got == LOCAL, repr(got))
        got = RT.degrade("jarvis-bulk", lanes=[CLOUD], local_model=LOCAL)
        check("... and starting FROM a removed name does not walk the next one",
              got == LOCAL, repr(got))
    finally:
        _restore(keep)


# ==========================================================================
#  3. the day-limit hit
# ==========================================================================

def t_a_day_limit_hit_answers_locally():
    exhausted = RT.Budget(path=None, per_day=1, day_hits=[time.time()])
    check("the test's budget really is over its day cap", exhausted.day_exceeded())
    d = RT.choose(HARD, local_model=LOCAL, lanes=[CLOUD], budget=exhausted,
                  owner_said_yes=True, conversation_tainted=False)
    check("a day-limited hard question is answered on THIS PC", d.lane == LOCAL,
          (d.lane, d.gate, d.reason))
    check("... with gate 'budget' (a refusal that pushes back to local, not a drop)",
          d.gate == "budget", (d.gate, d.reason))
    check("... and it offers nothing to the cloud", d.offer == "", d.offer)
    check("... the lane it landed on exists (degrade has nowhere below local)",
          d.lane in _existing_lanes([CLOUD]) and RT.degrade(d.lane, [CLOUD], LOCAL) is None,
          d.lane)
    # CONTROL: the same question with room on the cap really does escalate, so
    # the check above is about the cap and not about a broken lane.
    fresh = RT.Budget(path=None, per_day=800)
    control = RT.choose(HARD, local_model=LOCAL, lanes=[CLOUD], budget=fresh,
                        owner_said_yes=True, conversation_tainted=False)
    check("control: with room on the cap the same question reaches the real lane",
          (control.lane, control.gate) == (CLOUD, "escalate"),
          (control.lane, control.gate, control.reason))


# ==========================================================================
#  4. the spend cap: an absent file is not an absent cap
# ==========================================================================

def t_the_rate_cap_exists_without_a_budget_file():
    b = RT.Budget.load()
    shipped_budget = _toml(CONFIG).get("budget") or {}
    check("the shipped config carries a requests-per-minute cap",
          int(shipped_budget.get("requests_per_minute") or 0) > 0, shipped_budget)
    check("... and a requests-per-day cap",
          int(shipped_budget.get("requests_per_day") or 0) > 0, shipped_budget)
    check("with no budget file, no calls are recorded yet",
          b.status()["used_today"] == 0 and b.status()["used_this_minute"] == 0,
          b.status())
    check("... and the loaded cap is the shipped one, not zero/unlimited",
          (b.per_minute, b.per_day) == (int(shipped_budget["requests_per_minute"]),
                                       int(shipped_budget["requests_per_day"])),
          (b.per_minute, b.per_day))
    check("... so the first call is allowed (nothing has been spent)",
          b.allows_cloud() is True, b.status())


def t_the_rate_cap_binds_once_a_cloud_call_is_recorded():
    b = RT.Budget(path=SCRATCH / "budget.json", per_minute=15, per_day=2)
    b.spend()
    again = RT.Budget.load()
    check("a recorded cloud call reads back from disk (the cap can advance)",
          again.status()["used_today"] == 1, again.status())
    # The loaded cap comes from the config (800/day there); this test is about
    # the mechanism, so it puts its own small day cap on the same object and
    # spends the second call through the same file.
    again.per_day = 2
    again.spend()
    check("reaching the day cap refuses the next cloud call",
          again.day_exceeded() and again.allows_cloud() is False, again.status())
    d = RT.choose(HARD, local_model=LOCAL, lanes=[CLOUD],
                  budget=RT.Budget(path=None, per_day=1, day_hits=[time.time()]),
                  owner_said_yes=True, conversation_tainted=False)
    check("... and choose() turns that refusal into a LOCAL answer, not an error",
          d.lane == LOCAL and d.gate == "budget", (d.lane, d.gate))


# ==========================================================================
#  5. the lane list itself
# ==========================================================================

def t_the_stale_names_are_not_cloud_lanes_any_more():
    check("the old three-name list collapses to the ONE lane",
          RT.cloud_lanes(STALE) == [CLOUD], RT.cloud_lanes(STALE))
    for dead in ("jarvis-bulk", "jarvis-critic"):
        check(f"{dead} alone is no cloud lane", RT.cloud_lanes([dead]) == [],
              RT.cloud_lanes([dead]))


# ==========================================================================

TESTS = [
    t_the_shipped_settings_files_name_only_lanes_that_exist,
    t_a_stale_chain_cannot_step_to_a_lane_that_does_not_exist,
    t_a_dead_name_alone_is_dropped_not_substituted,
    t_a_day_limit_hit_answers_locally,
    t_the_rate_cap_exists_without_a_budget_file,
    t_the_rate_cap_binds_once_a_cloud_call_is_recorded,
    t_the_stale_names_are_not_cloud_lanes_any_more,
]


def main() -> int:
    for fn in TESTS:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(f"{fn.__name__} raised")
            print(f"FAIL  {fn.__name__} raised")
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"  failed: {name}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
