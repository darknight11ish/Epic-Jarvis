"""No approval card has a deadline, and a late "yes" is refused, not invented.

    python3 test_gate_no_deadline.py

WHY THIS EXISTS

The owner's ruling of 2026-10-28: **"if there doesn't need to be a time limit
don't have one."** Until then a routine card waited `approval_timeout_seconds`
(900 s in the shipped settings) and then refused itself. The card left every
screen at the same moment, and a card that took longer than the window - a
phone he picked up late, a question he wanted to think about - was simply gone.

WHAT THE STACK DOES NOW (`backend/no-deadline-cards.patch`, applied after
`no-expiry-cards.patch`):

  * the CARD has no deadline and no `expires_in`; it stays on every screen
    until the owner answers it or the PC withdraws the work;
  * the REQUEST that raised it still stops waiting after the shipped window -
    a thread held for ever is not a permission - and when it stops, the row
    stays 'pending'. `waited_until`, written at the INSERT, is the last moment
    a "yes" can still be carried out;
  * an APPROVE after that moment is refused by the gate (`still_waiting()`,
    `decide()`) and by `jarvis_owner_check` with one plain sentence, and the
    card is withdrawn at that moment: never silently expired, never "approved"
    into nothing;
  * a DENY always works. Refusing is the safe direction, and clearing an old
    card with it is exactly what the ruling leaves the owner able to do;
  * the four ceremonies of the 2026-10-23 ruling (pairing a device, an approval
    key, a restore) keep their own NO-wait behaviour: their request waits for
    its flow to withdraw the card, so they are answerable for as long as the
    owner needs.

WHAT THIS PROVES

  1. t_the_stack_is_the_published_base_plus_both_patches
     Both patches apply with `git apply` to `jarvis-backend/jarvis_gate.py`,
     the result compiles, `timeout_for()` answers None for every action,
     `wait_for()` is the four ceremonies plus the shipped window for the rest,
     and the rows carry `waited_until`. The base is not edited to make it fit.
  2. t_a_routine_card_is_still_pending_after_the_old_fifteen_minutes
     The request ends at the shipped window (the caller reads timed_out); the
     ROW is still 'pending', `pending()` still serves it, and it carries no
     `expires_in` - so no screen can draw a countdown or "Timed out".
  3. t_a_late_approval_is_refused_with_the_reason_and_the_card_leaves
     `still_waiting()` is False, `decide(True)` is False, the owner's own
     approve route answers 409 with one plain sentence, the row is 'expired'
     (a lapse, never a denial) and the queue is empty afterwards.
  4. t_a_decision_inside_the_window_is_still_accepted
     The control: the same card, answered while its request waits, is approved
     through `decide()` exactly as before.
  5. t_a_deny_still_clears_a_card_whose_request_has_gone
     Refusing is never held: the late card can always be dismissed.
  6. t_the_four_ceremonies_still_wait_with_no_number_at_all
     A pairing or restore card is answerable hours later - the 2026-10-23
     ruling is not narrowed by this one.
  7. t_a_card_the_pc_withdrew_is_still_gone
     `withdraw()` still takes a card off the list and ends its waiter.
  8. t_a_row_left_by_a_dead_process_is_settled_at_start_up
     The 2026-10-28 unanswerable-card defect stays fixed: a lapsed routine row
     (and an old fieldless one) is settled at start-up, while a ceremony row
     with no wait is left alone.
  9. t_a_lapsed_card_does_not_swallow_a_new_identical_request
     The "the same request is already waiting for you" bug cannot come back
     through a card whose request has gone.

HOW THE GATE IS LOADED. As `backend/test_gate_no_expiry.py` does it: the
published base in `jarvis-backend/` is copied to a scratch folder, both patches
are applied with `git apply` (no fuzz), and the result is imported. Needs
nothing from the owner's PC and no network; runs anywhere git does.
"""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import types
import uuid
from contextlib import closing
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _gitapply  # noqa: E402  (beside this file; its docstring says why)
from _where import REPO  # noqa: E402

EXPIRY_PATCH = HERE / "no-expiry-cards.patch"
DEADLINE_PATCH = HERE / "no-deadline-cards.patch"
BASE = REPO / "jarvis-backend"
BACKEND = REPO / "backend"
TOML = BASE / "jarvis-framework.toml"

#: The shipped `approval_timeout_seconds` #378 left on 2026-10-13: 15 minutes.
MINUTES_15 = 15 * 60

#: The four ceremonies whose request waits for its own flow (2026-10-23, Q1).
NEVER_EXPIRES = ("pair_device", "unretire_shared_key", "register_approval_key",
                 "restore_backup")
ROUTINE = ("send_email", "search_the_web", "run_shell_on_host", "spend_money",
           "unclassified_action")

#: The one sentence the phone and the desktop show for a late approval. Kept
#: as a literal here on purpose: the owner reads it, so a test that imported it
#: from the module would pass even if the words changed to jargon.
LATE_WORDS = ("That card is not waiting for you any more: the request that asked "
              "has finished, so nothing can be approved from it. Nothing was "
              "changed - ask Jarvis again if you still want it.")

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


# ---------------------------------------------------------------------------
# The published base, plus both patches, as a module
# ---------------------------------------------------------------------------

_BUILT: dict = {}


def built() -> tuple:
    """(folder holding the patched gate and the two SHIPPED copies, why not)."""
    if "dir" in _BUILT:
        return _BUILT["dir"], ""
    git = shutil.which("git")
    if not git:
        return None, "git is not installed, so the patch cannot be applied"
    for patch in (EXPIRY_PATCH, DEADLINE_PATCH):
        if not patch.is_file():
            return None, f"{patch.name} is missing"
    base_gate = BASE / "jarvis_gate.py"
    if not base_gate.is_file():
        return None, f"{base_gate} is missing"
    d = Path(tempfile.mkdtemp(prefix="jarvis-no-deadline-"))
    d.joinpath("jarvis_gate.py").write_bytes(
        base_gate.read_bytes().replace(b"\r\n", b"\n"))
    # The two SHIPPED modules: this repository's own copies, which the base
    # twins must equal (tools/check_stale_twins.py checks it in a second).
    for name in ("jarvis_owner_check.py", "jarvis_devices.py"):
        src = BACKEND / name
        if not src.is_file():
            return None, f"{src} is missing"
        d.joinpath(name).write_bytes(src.read_bytes().replace(b"\r\n", b"\n"))
    env = _gitapply.env_for(git, d)
    for patch in (EXPIRY_PATCH, DEADLINE_PATCH):
        r = subprocess.run([git, "-c", "core.autocrlf=false", "-c", "core.eol=lf",
                            "apply", str(patch)], cwd=str(d), capture_output=True,
                           text=True, env=env)
        if r.returncode != 0:
            return None, (f"git apply refused {patch.name}: "
                          f"{(r.stderr or r.stdout).strip().splitlines()[:3]}")
    _BUILT["dir"] = d
    return d, ""


def load_module(name: str, folder: Path, **env):
    """Import `name` out of `folder`, freshly, with its own approvals DB."""
    cfg = Path(tempfile.mkdtemp(prefix="jarvis-no-deadline-state-"))
    os.environ["JARVIS_APPROVALS_DB"] = str(cfg / "approvals.db")
    os.environ.pop("JARVIS_APPROVAL_TIMEOUT", None)
    os.environ["JARVIS_NTFY_TOPIC"] = ""      # never a socket, said explicitly
    os.environ["JARVIS_NTFY_SERVER"] = ""
    for k, v in env.items():
        os.environ[k] = str(v)
    fw = types.ModuleType("jarvis_framework")
    fw.CONFIG_DIR = cfg
    fw.LOG_DIR = cfg
    tiers = {a: "ask" for a in NEVER_EXPIRES + ROUTINE}
    fw.load_framework = lambda: {
        "logging": {"redact_private_content_in_logs": True},
        "autonomy": {"unknown_action_tier": "ask",
                     "approval_timeout_seconds": MINUTES_15,
                     "tiers": tiers},
    }
    fw.audit_log = lambda *a, **k: None
    sys.modules["jarvis_framework"] = fw
    for mod in [n for n in sys.modules if n.startswith(name)]:
        del sys.modules[mod]
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    return __import__(name)


class _Clock:
    """A clock the test moves, standing in for the gate's `time` module."""

    def __init__(self, start: float = None):
        self.now = float(time.time() if start is None else start)
        self.slept = 0.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept += float(seconds)     # frozen: no simulated time passes

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


class simulated_clock:
    def __init__(self, module, start: float = None):
        self.module = module
        self.clock = _Clock(start)

    def __enter__(self):
        self.module.time = self.clock
        return self.clock

    def __exit__(self, *exc):
        self.module.time = time
        return False


def ask(gate, action: str, box: dict, **kw):
    """`check()` on its own thread, so the test can answer while it waits."""
    box["at"] = time.time()

    def run():
        try:
            box["v"] = gate.check(action, {"why": "a test"},
                                  prompt=f"a test {action}", **kw)
        except Exception:
            box["v"] = None
            box["error"] = traceback.format_exc()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def wait_for_row(gate, box, seconds: float = 10.0, why: str = ""):
    end = time.time() + seconds
    while time.time() < end:
        rows = gate.pending()
        if rows:
            return rows[0]
        time.sleep(0.02)
    box["no_row"] = (f"{why}: nothing pending in {gate.DB_PATH} "
                     f"(exists={gate.DB_PATH.exists()}); history={gate.history(5)}")
    return None


def state_of(gate, rid: str) -> Optional[str]:
    for row in gate.history(10):
        if row.get("id") == rid:
            return row.get("state")
    return None


def seed(gate, action: str, waited_until, age: float = 0.0) -> str:
    """Write one stored card exactly as `check()` would have left it."""
    gate._init()
    rid = uuid.uuid4().hex[:12]
    with closing(gate._connect()) as c:
        c.execute(
            "INSERT INTO approvals (id,action,tier,detail,prompt,state,created,"
            "raised,target_digest,waited_until) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (rid, action, "ask", "{}", "", "pending", time.time() - age,
             None, None, waited_until))
    return rid


# ---------------------------------------------------------------------------
# 1. The stack's own footing
# ---------------------------------------------------------------------------

def t_the_stack_is_the_published_base_plus_both_patches():
    text = TOML.read_text(encoding="utf-8")
    m = re.search(r"^\s*approval_timeout_seconds\s*=\s*(\d+)\s*$", text, re.M)
    check("the shipped settings declare approval_timeout_seconds", m is not None)
    check("...and it is still 900 - the window the REQUEST keeps",
          m is not None and int(m.group(1)) == MINUTES_15,
          m.group(1) if m else None)

    d, why = built()
    if d is None:
        return check("both patches apply to the published base", False, why)
    check("no-expiry-cards.patch and no-deadline-cards.patch apply with git", True)
    check("...and the base was not edited to make them fit",
          "def wait_for(" not in (BASE / "jarvis_gate.py").read_text(encoding="utf-8"),
          "the base already contains the change - re-anchor the patch instead")

    G = load_module("jarvis_gate", d)
    after = Path(G.__file__).read_text(encoding="utf-8")
    check("the patched module compiles", True)     # importing it is the proof
    for action in ROUTINE + NEVER_EXPIRES:
        check(f"{action}: the CARD has no deadline", G.timeout_for(action) is None,
              G.timeout_for(action))
    for action in NEVER_EXPIRES:
        check(f"{action}: its REQUEST waits for its own flow",
              G.wait_for(action) is None, G.wait_for(action))
    for action in ROUTINE:
        check(f"{action}: its REQUEST keeps the shipped 900",
              G.wait_for(action) == float(MINUTES_15), G.wait_for(action))
    check("the patch adds no second copy of a shipped module",
          set(re.findall(r"^\+\+\+ b/(.+)$",
                         DEADLINE_PATCH.read_text(encoding="utf-8"), re.M))
          == {"jarvis_gate.py"})
    check("...and it is the one that removes the countdown",
          'd["expires_in"]' not in after.split("def pending")[1].split("def decide")[0],
          "pending() still emits expires_in")
    check("...and rows record when their request stops waiting",
          "waited_until" in after)
    # The two shipped modules are byte-identical twins (the rule in CLAUDE.md).
    for name in ("jarvis_owner_check.py", "jarvis_devices.py"):
        a = (BACKEND / name).read_bytes().replace(b"\r\n", b"\n")
        b = (BASE / name).read_bytes().replace(b"\r\n", b"\n")
        check(f"{name}: backend/ and jarvis-backend/ are byte-identical", a == b)


# ---------------------------------------------------------------------------
# 2. The card outlives its request
# ---------------------------------------------------------------------------

def t_a_routine_card_is_still_pending_after_the_old_fifteen_minutes():
    d, why = built()
    if d is None:
        return skip(why)
    G = load_module("jarvis_gate", d)
    with simulated_clock(G) as clock:
        box = {}
        t = ask(G, "send_email", box)
        row = wait_for_row(G, box)
        if row is None:
            return check("the routine card was raised", False,
                         box.get("no_row", "no pending row"))
        check("a routine card carries no expires_in at all", "expires_in" not in row, row)

        clock.advance(MINUTES_15 - 1)
        time.sleep(0.4)
        check("one second before the request's window ends, it is still waiting",
              t.is_alive() and any(r["id"] == row["id"] for r in G.pending()),
              {"alive": t.is_alive(), "state": state_of(G, row["id"])})

        clock.advance(2)
        t.join(timeout=10)
        v = box.get("v")
        check("the REQUEST ends at the shipped window, refused as timed_out",
              v is not None and v.allowed is False and v.outcome == "timed_out",
              (v, box.get("error")))
        check("...and the ROW IS STILL PENDING - the card did not vanish",
              state_of(G, row["id"]) == "pending", state_of(G, row["id"]))
        listed = [r["id"] for r in G.pending()]
        check("...and the queue still serves it, with no countdown field",
              row["id"] in listed and all("expires_in" not in r for r in G.pending()),
              listed)


def t_a_late_approval_is_refused_with_the_reason_and_the_card_leaves():
    d, why = built()
    if d is None:
        return skip(why)
    G = load_module("jarvis_gate", d)
    OC = load_module("jarvis_owner_check", d)
    with simulated_clock(G) as clock:
        box = {}
        t = ask(G, "send_email", box)
        row = wait_for_row(G, box)
        if row is None:
            return check("the routine card was raised", False, "no row")
        clock.advance(MINUTES_15 + 1)
        t.join(timeout=10)

        check("the gate knows no request is waiting on it",
              G.still_waiting(row["id"]) is False)
        check("decide(approve) refuses it", G.decide(row["id"], True, by="the test") is False)
        check("...and records no yes: the row is still 'pending'",
              state_of(G, row["id"]) == "pending", state_of(G, row["id"]))

        # The owner's route: the same row, the same moment, the sentence he reads.
        out = OC.approve_check({"id": row["id"]}, peer="127.0.0.1", local="127.0.0.1",
                               own=lambda: frozenset({"127.0.0.1"}),
                               pending=lambda: [row])
        check("the approve route answers 409", out is not None and out[0] == 409, out)
        check("...named as gone, not as a failure",
              out is not None and out[1].get("owner_check") == "gone", out)
        check("...with the exact plain sentence the owner reads",
              out is not None and out[1].get("error") == LATE_WORDS, out)
        check("...and the card is withdrawn then, not silently expired",
              state_of(G, row["id"]) == "expired" and G.pending() == [],
              (state_of(G, row["id"]), G.pending()))


def t_a_decision_inside_the_window_is_still_accepted():
    d, why = built()
    if d is None:
        return skip(why)
    G = load_module("jarvis_gate", d)
    OC = load_module("jarvis_owner_check", d)
    box = {}
    with simulated_clock(G):
        t = ask(G, "send_email", box)
        row = wait_for_row(G, box)
        if row is None:
            return check("the routine card was raised", False, "no row")
        check("a live card has a request still waiting",
              G.still_waiting(row["id"]) is True)
        OC.stamp(row["id"], row["action"])
        check("decide(approve) accepts it while the request waits",
              G.decide(row["id"], True, by="the test") is True)
        t.join(timeout=10)
        v = box.get("v")
        check("...and the caller reads approved",
              v is not None and v.allowed is True and v.outcome == "approved", v)


def t_a_deny_still_clears_a_card_whose_request_has_gone():
    d, why = built()
    if d is None:
        return skip(why)
    G = load_module("jarvis_gate", d)
    with simulated_clock(G) as clock:
        box = {}
        t = ask(G, "send_email", box)
        row = wait_for_row(G, box)
        if row is None:
            return check("the routine card was raised", False, "no row")
        clock.advance(MINUTES_15 + 1)
        t.join(timeout=10)
        check("a late DENY is accepted - refusing is the safe direction",
              G.decide(row["id"], False, by="the test") is True)
        check("...and the card leaves the list", G.pending() == [], G.pending())
        check("...recorded as denied, never as a lapse",
              state_of(G, row["id"]) == "denied", state_of(G, row["id"]))


# ---------------------------------------------------------------------------
# 3. The 2026-10-23 ceremonies are not narrowed by this
# ---------------------------------------------------------------------------

def t_the_four_ceremonies_still_wait_with_no_number_at_all():
    d, why = built()
    if d is None:
        return skip(why)
    G = load_module("jarvis_gate", d)
    OC = load_module("jarvis_owner_check", d)
    box = {}
    with simulated_clock(G) as clock:
        t = ask(G, "restore_backup", box)
        row = wait_for_row(G, box)
        if row is None:
            return check("the restore card was raised", False, "no row")
        clock.advance(4 * MINUTES_15)
        time.sleep(0.4)
        check("a restore card is still waiting hours later",
              t.is_alive() and any(r["id"] == row["id"] for r in G.pending()),
              {"alive": t.is_alive(), "state": state_of(G, row["id"])})
        check("...and its request is still able to act on a yes",
              G.still_waiting(row["id"]) is True)
        check("...with no expires_in to count", "expires_in" not in row, row)
        OC.stamp(row["id"], row["action"])
        check("...so a decision hours later is accepted",
              G.decide(row["id"], True, by="the test") is True)
        t.join(timeout=10)
        v = box.get("v")
        check("...and the caller reads approved",
              v is not None and v.allowed is True and v.outcome == "approved", v)


def t_a_card_the_pc_withdrew_is_still_gone():
    d, why = built()
    if d is None:
        return skip(why)
    G = load_module("jarvis_gate", d)
    box = {}
    with simulated_clock(G):
        t = ask(G, "pair_device", box)
        row = wait_for_row(G, box)
        if row is None:
            return check("the pairing card was raised", False, "no row")
        check("withdraw takes it off the list",
              G.withdraw(row["id"], "the pairing was cancelled") is True)
        check("...the list is empty", G.pending() == [], G.pending())
        check("...it is not answerable any more", G.still_waiting(row["id"]) is False)
        check("...and a late yes changes nothing",
              G.decide(row["id"], True, by="the test") is False)
        t.join(timeout=10)
        v = box.get("v")
        check("...and the waiter is refused, not told it was denied",
              v is not None and v.allowed is False and v.outcome == "timed_out", v)
        check("withdrawing it again changes nothing",
              G.withdraw(row["id"], "again") is False)


# ---------------------------------------------------------------------------
# 4. A dead process's rows are still settled, and never swallow a request
# ---------------------------------------------------------------------------

def t_a_row_left_by_a_dead_process_is_settled_at_start_up():
    d, why = built()
    if d is None:
        return skip(why)
    G = load_module("jarvis_gate", d)
    G.pending()                       # create the tables and settle nothing
    now = time.time()
    lapsed = seed(G, "send_email", now - 120.0)      # its request is long gone
    old = seed(G, "search_the_web", None)            # a row from before the patch
    ceremony = seed(G, "restore_backup", None)       # no window at all
    justlapsed = seed(G, "run_shell_on_host", now - 5.0)   # inside the grace
    G._inited = False
    G._init()
    states = {r["id"]: r["state"] for r in G.history(20) if r.get("id") in
              {lapsed, old, ceremony, justlapsed}}
    check("a routine row whose request is gone is settled at start-up",
          states.get(lapsed) == "expired", states)
    check("...and a row from before the patch, which cannot be approved",
          states.get(old) == "expired", states)
    check("...but a ceremony row with no window is left alone",
          states.get(ceremony) == "pending", states)
    check("...and the 60-second grace is still given to a row that only just lapsed",
          states.get(justlapsed) == "pending", states)


def t_a_lapsed_card_does_not_swallow_a_new_identical_request():
    d, why = built()
    if d is None:
        return skip(why)
    G = load_module("jarvis_gate", d)
    G.pending()
    lapsed = seed(G, "send_email", time.time() - 120.0)
    with closing(G._connect()) as c:
        check("a lapsed card is not what 'the same request is already waiting "
              "for you' matches",
              G._pending_card_id(c, "send_email", {}, "") != lapsed)
    live = seed(G, "send_email", time.time() + 600.0)
    with closing(G._connect()) as c:
        check("...while a card with a request still waiting IS the card a "
              "duplicate is told about",
              G._pending_card_id(c, "send_email", {}, "") == live)


if __name__ == "__main__":
    for fn in (t_the_stack_is_the_published_base_plus_both_patches,
               t_a_routine_card_is_still_pending_after_the_old_fifteen_minutes,
               t_a_late_approval_is_refused_with_the_reason_and_the_card_leaves,
               t_a_decision_inside_the_window_is_still_accepted,
               t_a_deny_still_clears_a_card_whose_request_has_gone,
               t_the_four_ceremonies_still_wait_with_no_number_at_all,
               t_a_card_the_pc_withdrew_is_still_gone,
               t_a_row_left_by_a_dead_process_is_settled_at_start_up,
               t_a_lapsed_card_does_not_swallow_a_new_identical_request):
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
