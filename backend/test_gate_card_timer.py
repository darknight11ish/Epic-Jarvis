"""The timer on every card with a limited time, and nothing else changed.

    python3 test_gate_card_timer.py

WHY THIS EXISTS

The owner's ruling of 2026-10-30: **"if there is a card with a limited time of
any kind, be sure to put the timer on it."** It came from the same day twice
over: his app-builder card ran out while he was reading it, and no screen had
counted it down. The 2026-10-28 ruling ("if there doesn't need to be a time
limit don't have one") is not reversed - it stays true of the CARD. What was
missing is that the REQUEST's own wait was hidden.

WHAT THE PUBLISHED BASE DOES NOW (the 2026-10-30 timer; `show-card-timer.patch`
was retired into the base on 2026-11-26, after `no-deadline-cards.patch` in the
old stack):

  * a ROUTINE card whose request is still waiting carries `expires_in`, the
    whole seconds left until the row's own `waited_until` - the same moment the
    read-time sweep and the late-approval 409 already use, so the clock on the
    screen and the refusal behind it are the same moment;
  * NEVER 0 and never negative (both apps read 0 as "expired now"), rounded UP
    so a part-second left reads 1;
  * NOTHING for a ceremony card (`waited_until` NULL: pairing a device, an
    approval key, a restore) and nothing for a request that has already ended;
  * the 60-second grace is NOT counted down: no request can act on the card in
    it, so a clock there would promise what the gate refuses;
  * `waited_until` itself is never sent - the screens are told how long is
    left, never this PC's clock reading;
  * DISPLAY ONLY. No card gains a deadline of its own, nothing is refused
    because a countdown reached zero, nothing auto-approves, a Deny always
    works, and the read-time sweep, `still_waiting()` and the 409 are exactly
    what the 2026-10-28 patch left.

WHAT THIS PROVES

  1. t_the_base_carries_the_timer
     The published base itself carries the timer block, together with the
     2026-10-28 request-bounding model it sits on: `pending()` still sweeps
     before its SELECT, and the file this suite drives is the base byte for
     byte.
  2. t_a_waiting_routine_card_counts_the_request_down
     A raised routine card carries `expires_in` inside its request's window; the
     number is the request's own seconds left, and it goes DOWN as the clock
     moves.
  2b. t_the_timer_counts_from_the_request_moment_not_from_created
     The formula, distinguished: a caller-bounded request (`timeout=120`) has
     `waited_until` 780 seconds earlier than `created` + the action's 900, and
     the timer follows `waited_until`, not `created`.
  2c. t_a_stopped_request_shows_no_grace_on_the_card
     The 60-second grace is not counted down: a card whose request has ended is
     still pending inside it and carries no timer, and the read after the grace
     takes it off.
  3. t_a_ceremony_card_and_an_ended_request_carry_no_timer
     The four ceremonies carry none; a row whose request has ended carries none
     (while it is still inside the grace); an unreadable `waited_until` carries
     none rather than a wrong one; `waited_until` itself is never in the row.
  4. t_the_field_is_never_zero_or_negative
     Driven across the whole window and past it: every value is a positive
     whole number, and the field is absent exactly when no request is waiting.
  5. t_nothing_expires_or_is_refused_because_of_the_field
     Reading the queue does not settle a live card, the row stays 'pending',
     and a decision inside the window still goes through.
  6. t_a_deny_still_clears_the_card_and_a_late_approve_still_409s
     A Deny always works; an Approve after `waited_until` is refused by the
     gate and by the owner's own route, with the same plain sentence, and the
     card is taken off the list - unchanged from 2026-10-28.
  7. t_the_timer_is_in_the_base_and_not_an_earlier_layer
     THE BITE PROOF. The published base with EXACTLY the timer block cut out of
     `pending()` sends no `expires_in` at all for the same waiting card, so
     every assertion above comes from that block and nowhere else.

HOW THE GATE IS LOADED. The published base in `jarvis-backend/` is copied to a
scratch folder as it is - since 2026-11-26 it carries all three retired
patches' content, so no patch is applied and `git` is not needed - and the
result is imported with its own approvals database. Needs nothing from the
owner's PC and no network.
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

BASE = REPO / "jarvis-backend"
BACKEND = REPO / "backend"
TOML = BASE / "jarvis-framework.toml"

#: Where the 2026-10-30 timer block starts and ends in the published base. The
#: bite proof removes exactly this slice, so "without the timer" is made from
#: the base itself now that `show-card-timer.patch` is retired.
TIMER_BLOCK_START = "        # THE TIMER ON A CARD WITH A LIMITED TIME (2026-10-30)."
TIMER_BLOCK_END = "        # Why this is being asked about at all"

#: The shipped `approval_timeout_seconds` #378 left on 2026-10-13: 15 minutes.
MINUTES_15 = 15 * 60
WINDOW = MINUTES_15

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
# The published base, plus the patches, as a module
# ---------------------------------------------------------------------------

_BUILT: dict = {}


def built(timer: bool = True) -> tuple:
    """(folder holding the base gate, why not). One folder per variant.

    `timer=False` is the bite proof's copy: the published base with EXACTLY the
    timer block cut out of `pending()`. That is the same "without this change"
    question the two-patch stack used to answer, asked of the file that now
    carries the change.
    """
    key = bool(timer)
    if key in _BUILT:
        return _BUILT[key], ""
    base_gate = BASE / "jarvis_gate.py"
    if not base_gate.is_file():
        return None, f"{base_gate} is missing"
    text = base_gate.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    if not timer:
        try:
            start = text.index(TIMER_BLOCK_START)
            end = text.index(TIMER_BLOCK_END, start)
        except ValueError:
            return None, ("the timer block this suite cuts out is not in the "
                          "published base any more - re-anchor the slice")
        text = text[:start] + text[end:]
    d = Path(tempfile.mkdtemp(prefix="jarvis-card-timer-"))
    d.joinpath("jarvis_gate.py").write_bytes(text.encode("utf-8"))
    # The two SHIPPED modules the owner's route needs, from this repository's
    # own copies (the base twins must equal them; check_stale_twins.py says so).
    for name in ("jarvis_owner_check.py", "jarvis_devices.py"):
        src = BACKEND / name
        if not src.is_file():
            return None, f"{src} is missing"
        d.joinpath(name).write_bytes(src.read_bytes().replace(b"\r\n", b"\n"))
    _BUILT[key] = d
    return d, ""


def load_module(name: str, folder: Path, **env):
    """Import `name` out of `folder`, freshly, with its own approvals DB."""
    cfg = Path(tempfile.mkdtemp(prefix="jarvis-card-timer-state-"))
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
    # THIS FOLDER GOES FIRST, EVERY TIME (measured while writing this file). The
    # bite test loads a DIFFERENT, older stack out of a second scratch folder,
    # and its own `sys.path.insert(0, ...)` put it in front of the three-patch
    # one for the rest of the run - so the last test re-imported the TWO-patch
    # module and read a card with no timer, which looked exactly like the patch
    # not working. `if folder not in sys.path: insert` cannot fix that: the
    # folder IS already there, just behind another one.
    if str(folder) in sys.path:
        sys.path.remove(str(folder))
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


def row_of(gate, rid: str):
    for r in gate.pending():
        if r["id"] == rid:
            return r
    return None


def ceil_seconds(seconds: float) -> int:
    """Whole seconds, rounded UP - the rule `pending()` sends the field by."""
    whole = int(seconds)
    return whole + 1 if seconds > whole else whole


# ---------------------------------------------------------------------------
# 1. The stack's own footing
# ---------------------------------------------------------------------------

def t_the_base_carries_the_timer():
    text = TOML.read_text(encoding="utf-8")
    m = re.search(r"^\s*approval_timeout_seconds\s*=\s*(\d+)\s*$", text, re.M)
    check("the shipped settings declare approval_timeout_seconds", m is not None)
    check("...and it is still 900 - the window the REQUEST keeps",
          m is not None and int(m.group(1)) == WINDOW,
          m.group(1) if m else None)

    d, why = built()
    if d is None:
        return check("the published base carries the timer", False, why)
    # The base carries the block: the bite proof's own slice (below) finds its
    # start and end markers and only then builds its "without" copy.
    check("the published base itself carries the 2026-10-30 timer block",
          built(timer=False)[0] is not None,
          "the bite proof's slice could not find the block in the base")

    G = load_module("jarvis_gate", d)
    after = Path(G.__file__).read_text(encoding="utf-8")
    # The EXACT def line, not a bare "def pending": the queue builder must be
    # the function this reads, and a helper whose name starts with the same
    # seven characters would otherwise be picked first. PR 2's `pending_text()`
    # (the deny-note feature) is exactly such a helper - measured 2026-11-06:
    # `after.split("def pending")` landed inside it and every check below read
    # the wrong body. The old split was always ambiguous; it is now precise.
    pending_body = after.split("def pending() -> list[dict]:")[1].split("def decide(")[0]
    check("the base module imports (it compiles)", True)
    check("the file this suite drives is the published base, byte for byte",
          Path(G.__file__).read_bytes()
          == (BASE / "jarvis_gate.py").read_bytes())
    check("pending() emits expires_in", 'd["expires_in"]' in pending_body)
    check("...from the row's own request end, not from `created` + a timeout",
          'float(_waited) - time.time()' in pending_body
          and 'float(d.get("created"))' not in pending_body,
          "the field is still measured against the CARD's own created moment")
    check("...and the row is read with the column it needs",
          "SELECT id,action,tier,detail,prompt,created,raised,waited_until" in pending_body)
    check("...and `waited_until` itself is dropped before the row is returned",
          'd.pop("waited_until", None)' in pending_body)
    check("#965's read-time sweep is untouched, and still runs BEFORE the SELECT",
          "_expire_overdue(c)" in pending_body
          and pending_body.index("_expire_overdue(c)") < pending_body.index("rows = c.execute"))
    check("the sweep's own key is untouched (waited_until + the 60s grace)",
          "waited_until < ?" in after and "now - 60" in after)
    for action in NEVER_EXPIRES:
        check(f"{action}: its REQUEST still waits for its own flow",
              G.timeout_for(action) is None, G.timeout_for(action))
    for action in ROUTINE:
        check(f"{action}: its REQUEST still keeps the shipped 900",
              G.timeout_for(action) == float(WINDOW), G.timeout_for(action))
    # The two shipped modules are byte-identical twins (the rule in CLAUDE.md).
    for name in ("jarvis_owner_check.py", "jarvis_devices.py"):
        a = (BACKEND / name).read_bytes().replace(b"\r\n", b"\n")
        b = (BASE / name).read_bytes().replace(b"\r\n", b"\n")
        check(f"{name}: backend/ and jarvis-backend/ are byte-identical", a == b)


# ---------------------------------------------------------------------------
# 2. A waiting routine card counts the request down
# ---------------------------------------------------------------------------

def t_a_waiting_routine_card_counts_the_request_down():
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
        with closing(G._connect()) as c:
            waited = c.execute("SELECT waited_until FROM approvals WHERE id=?",
                               (row["id"],)).fetchone()["waited_until"]
        check("the card carries a countdown at all", "expires_in" in row, row)
        check("...and it is the request's whole remaining wait",
              row.get("expires_in") == WINDOW, row.get("expires_in"))
        check("...which is the row's own `waited_until`, to the second",
              isinstance(waited, float)
              and row.get("expires_in") == ceil_seconds(waited - clock.now),
              {"waited_until": waited, "now": clock.now,
               "expires_in": row.get("expires_in")})
        check("...and the row does NOT hand the screens the PC's clock reading",
              "waited_until" not in row, sorted(row))

        first = row["expires_in"]
        for seconds in (1, 59, 60, 300):
            clock.advance(seconds)
            row = row_of(G, row["id"])
            check(f"after {seconds}s more waiting the timer has gone down",
                  row is not None and row.get("expires_in") is not None
                  and row["expires_in"] < first,
                  row.get("expires_in") if row else "gone")
            check(f"...and it still matches the request's own seconds left "
                  f"(after {seconds}s)",
                  row is not None
                  and row.get("expires_in") == ceil_seconds(waited - clock.now),
                  {"expires_in": row.get("expires_in") if row else None,
                   "left": waited - clock.now})
        # The request is still the one that raised it, and it is still alive.
        check("the request is still waiting (the timer is not a refusal)",
              t.is_alive() and state_of(G, row["id"]) == "pending",
              {"alive": t.is_alive(), "state": state_of(G, row["id"])})
        t.join(timeout=10)      # it ends when the window does; quiet the thread


# ---------------------------------------------------------------------------
# 2b. WHICH MOMENT THE TIMER COUNTS FROM, AND THE GRACE IT MUST NOT SHOW
# ---------------------------------------------------------------------------

def t_the_timer_counts_from_the_request_moment_not_from_created():
    """Test A: a caller-bounded request, where the two formulas disagree.

    `check()` writes `created` and `waited_until` from the same clock reading,
    so a request whose wait is the action's own 900 has
    `waited_until == created + 900` - and a timer that counted from `created`
    would print the same number. That is why the ordinary seed cannot tell the
    two formulas apart.

    A caller that passes its OWN `timeout=` is the real, producible case where
    the two moments differ: `waited = timeout`, so
    `waited_until == created + timeout` while
    `created + the action's window` is still 900. The gate cannot make a
    request "start waiting late" - the moment is written at the INSERT and the
    wait begins there - so this is the closest real card the harness can
    raise, and nothing is written into the database by hand.

    The shipped timer must read `waited_until`. Counting from `created`
    instead would answer ~900 here, which is what makes this test bite.
    """
    d, why = built()
    if d is None:
        return skip(why)
    G = load_module("jarvis_gate", d)
    with simulated_clock(G) as clock:
        box = {}
        t = ask(G, "send_email", box, timeout=120)
        row = wait_for_row(G, box)
        if row is None:
            return check("the caller-bounded card was raised", False,
                         box.get("no_row", "no pending row"))
        with closing(G._connect()) as c:
            r = c.execute("SELECT created,waited_until FROM approvals WHERE id=?",
                          (row["id"],)).fetchone()
        created, waited = float(r["created"]), float(r["waited_until"])
        check("the card's request is bounded at 120, not the action's 900",
              round(waited - created) == 120, (created, waited))
        shipped = row.get("expires_in")
        from_waited = ceil_seconds(waited - clock.now)
        from_created = ceil_seconds(created + WINDOW - clock.now)
        check("the timer counts the request's own 120 seconds left",
              shipped == from_waited and shipped <= 120, (shipped, from_waited))
        check("... and NOT the 900 a `created` + action-window count would give",
              isinstance(shipped, int) and abs(from_created - shipped) > 600,
              (shipped, from_created))
        clock.advance(60)
        later = row_of(G, row["id"])
        check("... and it still follows `waited_until` a minute later",
              later is not None
              and later.get("expires_in") == ceil_seconds(waited - clock.now),
              None if later is None else (later.get("expires_in"),
                                          waited - clock.now))
        clock.advance(61)                 # past the caller's own bound
        t.join(timeout=10)


def t_a_stopped_request_shows_no_grace_on_the_card():
    """Test B: the 60-second grace is never counted down.

    A routine card whose request has ENDED is still 'pending' for the sweep's
    grace (the 2026-10-28 rule), but no request can act on it any more. If the
    timer added the grace to the seconds it shows, the card would promise time
    the gate refuses. The field must be ABSENT there - both apps read 0 as
    "expired now" - and the next read after the grace must take the card off
    the queue. A grace-carrying implementation would show ~59 seconds above.
    """
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
        with closing(G._connect()) as c:
            waited = float(c.execute(
                "SELECT waited_until FROM approvals WHERE id=?",
                (row["id"],)).fetchone()["waited_until"])
        clock.advance(WINDOW + 1)         # the request stops waiting
        t.join(timeout=10)
        inside = row_of(G, row["id"])
        check("inside the grace the card is still pending (setup)",
              inside is not None and state_of(G, row["id"]) == "pending",
              None if inside is None else state_of(G, row["id"]))
        grace_if_shown = ceil_seconds(waited + 60 - clock.now)
        check("... the grace is still running, so a grace-carrying timer would show it",
              grace_if_shown >= 1, grace_if_shown)
        check("... and the card carries NO timer: the grace is not counted down",
              inside is not None and "expires_in" not in inside,
              None if inside is None else sorted(inside))
        clock.advance(62)
        gone = row_of(G, row["id"])
        check("... and after the 60-second grace the read sweep takes it off",
              gone is None and state_of(G, row["id"]) == "expired",
              (gone, state_of(G, row["id"])))


# ---------------------------------------------------------------------------
# 3. Who carries no timer at all
# ---------------------------------------------------------------------------

def t_a_ceremony_card_and_an_ended_request_carry_no_timer():
    d, why = built()
    if d is None:
        return skip(why)
    G = load_module("jarvis_gate", d)
    G.pending()
    now = time.time()

    # The four ceremonies: their rows have no request-side moment at all.
    ids = {a: seed(G, a, None) for a in NEVER_EXPIRES}
    listed = {r["id"]: r for r in G.pending()}
    for action, rid in ids.items():
        check(f"{action}: a ceremony card carries no countdown",
              rid in listed and "expires_in" not in listed[rid],
              listed.get(rid))

    # A routine card whose request has already ended, inside the grace: still
    # drawn (with its buttons), and with no clock - nothing is waiting on it.
    ended = seed(G, "send_email", now - 5.0)
    inside = {r["id"]: r for r in G.pending()}
    check("a request that has ended carries no countdown, even inside the grace",
          ended in inside and "expires_in" not in inside[ended], inside.get(ended))

    # A `waited_until` that is not a number is no countdown, never a wrong one.
    bad = seed(G, "search_the_web", "tomorrow-ish")
    rows = {r["id"]: r for r in G.pending()}
    check("an unreadable `waited_until` draws no countdown (and does not raise)",
          bad in rows and "expires_in" not in rows[bad], rows.get(bad))

    # A row from before the patch (no `waited_until` at all) is not given one.
    old = seed(G, "run_shell_on_host", None)
    rows = {r["id"]: r for r in G.pending()}
    check("a routine row with no `waited_until` (an old row) carries none",
          old not in rows or "expires_in" not in rows[old], rows.get(old))

    # `waited_until` is never leaked on any of them.
    every = G.pending()
    check("not one row in the queue carries `waited_until` to a client",
          every and all("waited_until" not in r for r in every),
          [sorted(r) for r in every][:1])


# ---------------------------------------------------------------------------
# 4. Never 0, never negative, and absent exactly when nothing is waiting
# ---------------------------------------------------------------------------

def t_the_field_is_never_zero_or_negative():
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
        with closing(G._connect()) as c:
            waited = c.execute("SELECT waited_until FROM approvals WHERE id=?",
                               (row["id"],)).fetchone()["waited_until"]
        seen: list = []
        # Walk the whole window second by second near both edges, and in chunks
        # through the middle: every read must carry a positive whole number.
        steps = [1] * 20 + [60] * 13 + [1] * 10
        for step in steps:
            clock.advance(step)
            got = row_of(G, row["id"])
            if got is not None and "expires_in" in got:
                seen.append(got["expires_in"])
        t.join(timeout=10)
        check("the window was actually walked", len(seen) > 30, len(seen))
        check("no read ever carried 0 or a negative number",
              all(isinstance(v, int) and v >= 1 for v in seen),
              [v for v in seen if not (isinstance(v, int) and v >= 1)][:5])
        check("every value is a whole number, and none is longer than the window",
              all(v <= WINDOW for v in seen), max(seen) if seen else None)
        check("the numbers only ever go down as the clock moves",
              all(a >= b for a, b in zip(seen, seen[1:])), seen[:6] + ["..."])

        # Past the window the field is simply absent - never 0, which both
        # clients read as "expired now".
        clock.advance(max(2, int(waited - clock.now) + 1))
        rows = {r["id"]: r for r in G.pending()}
        check("past the request's end the field is absent, not 0",
              row["id"] in rows and "expires_in" not in rows[row["id"]],
              rows.get(row["id"]))


# ---------------------------------------------------------------------------
# 5. Display only: nothing expires because the field is there
# ---------------------------------------------------------------------------

def t_nothing_expires_or_is_refused_because_of_the_field():
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
        # Ten reads, a third of the way through the window: the field changes,
        # nothing else does.
        clock.advance(WINDOW // 3)
        for _ in range(10):
            got = row_of(G, row["id"])
            if got is None:
                break
        check("ten reads did not settle the card", state_of(G, row["id"]) == "pending",
              state_of(G, row["id"]))
        check("...and the sweep had nothing to settle on a clean read",
              _no_overdue(G), "the read settled something")
        check("...and the card is still in the queue",
              row_of(G, row["id"]) is not None)
        check("...and its request is still waiting", G.still_waiting(row["id"]) is True)
        # A decision inside the window still goes through, exactly as before.
        OC.stamp(row["id"], row["action"])
        check("an Approve inside the window is still accepted",
              G.decide(row["id"], True, by="the test") is True)
        check("...and the row is recorded as approved", state_of(G, row["id"]) == "approved")
        t.join(timeout=10)
        check("...and the waiting request was told, not left hanging",
              box.get("v") is not None
              and getattr(box["v"], "allowed", None) is True
              and getattr(box["v"], "outcome", None) == "approved",
              box.get("v"))


def _no_overdue(gate) -> bool:
    with closing(gate._connect()) as c:
        return gate._expire_overdue(c) == 0


# ---------------------------------------------------------------------------
# 6. A Deny always works; a late Approve still 409s
# ---------------------------------------------------------------------------

def t_a_deny_still_clears_the_card_and_a_late_approve_still_409s():
    d, why = built()
    if d is None:
        return skip(why)
    G = load_module("jarvis_gate", d)
    OC = load_module("jarvis_owner_check", d)

    # (a) A Deny, while the request waits.
    with simulated_clock(G):
        box = {}
        t = ask(G, "send_email", box)
        row = wait_for_row(G, box)
        if row is None:
            return check("the routine card was raised", False, "no row")
        check("a Deny on a card with a timer still works",
              G.decide(row["id"], False, by="the test") is True)
        check("...and is recorded as a denial, not a lapse",
              state_of(G, row["id"]) == "denied", state_of(G, row["id"]))
        t.join(timeout=10)

    # (b) An Approve after the request ended: the gate refuses it, the owner's
    #     route answers 409 with the one sentence, and the card is withdrawn.
    with simulated_clock(G) as clock:
        box = {}
        t = ask(G, "send_email", box)
        row = wait_for_row(G, box)
        if row is None:
            return check("the second routine card was raised", False, "no row")
        clock.advance(WINDOW + 1)
        t.join(timeout=10)
        check("the request ended at the shipped window, refused as timed_out",
              box.get("v") is not None
              and getattr(box["v"], "outcome", None) == "timed_out", box.get("v"))
        check("inside the grace the gate refuses an Approve",
              G.still_waiting(row["id"]) is False
              and G.decide(row["id"], True, by="the test") is False)
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
        clock.advance(61)
        check("#965's sweep took the lapsed row off the queue",
              row["id"] not in [r["id"] for r in G.pending()])


# ---------------------------------------------------------------------------
# 7. THE BITE PROOF: the base with that block cut out carries no timer
# ---------------------------------------------------------------------------

def t_the_timer_is_in_the_base_and_not_an_earlier_layer():
    """The base with EXACTLY the timer block cut out sends NO timer.

    This is what makes the rest of this file bite: if `expires_in` were coming
    from the base's 2026-10-28 layer or from an earlier patch, the assertions
    above would pass without the timer block and this test would be measuring
    nothing.
    """
    without, why = built(timer=False)
    if without is None:
        return skip(why)
    G2 = load_module("jarvis_gate", without)
    with simulated_clock(G2) as clock:
        box = {}
        t = ask(G2, "send_email", box)
        row = wait_for_row(G2, box)
        if row is None:
            return check("the routine card was raised without the timer block",
                         False, "no row")
        check("WITHOUT the timer block the same card carries NO expires_in",
              "expires_in" not in row, sorted(row))
        clock.advance(60)
        listed = row_of(G2, row["id"])
        check("...and it still carries none a minute later",
              listed is not None and "expires_in" not in listed,
              listed and sorted(listed))
        check("...so every countdown assertion in this file comes from that block",
              'd["expires_in"]' not in Path(G2.__file__).read_text(encoding="utf-8"),
              "the cut-out copy already emits the field - it cannot be the timer block")
        t.join(timeout=10)

    full, why = built()
    if full is None:
        return skip(why)
    G3 = load_module("jarvis_gate", full)
    with simulated_clock(G3):
        box = {}
        t = ask(G3, "send_email", box)
        row = wait_for_row(G3, box)
        check("WITH the block the same card carries it (the difference is the block)",
              row is not None and row.get("expires_in") == WINDOW,
              {"row": row, "error": box.get("error"), "no_row": box.get("no_row"),
               "file": G3.__file__})
        t.join(timeout=10)


if __name__ == "__main__":
    for fn in (t_the_base_carries_the_timer,
               t_a_waiting_routine_card_counts_the_request_down,
               t_the_timer_counts_from_the_request_moment_not_from_created,
               t_a_stopped_request_shows_no_grace_on_the_card,
               t_a_ceremony_card_and_an_ended_request_carry_no_timer,
               t_the_field_is_never_zero_or_negative,
               t_nothing_expires_or_is_refused_because_of_the_field,
               t_a_deny_still_clears_the_card_and_a_late_approve_still_409s,
               t_the_timer_is_in_the_base_and_not_an_earlier_layer):
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
