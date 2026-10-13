"""Which approval cards expire, and which wait for the owner instead.

    python3 test_gate_no_expiry.py

WHY THIS EXISTS. Every card used to die after `approval_timeout_seconds`
(180 in the shipped settings). For a routine card that is right: one email,
one web page, one command - re-raising it is cheap, and a card that waits for
ever stops being a question about one action and starts behaving like a
standing permission. For a few deliberate cards it is wrong. Pairing a phone,
restoring a backup, forgetting a time frame and every settings change that
LOOSENS a rule are all started by the owner, need them there to finish, and
have to be started again from scratch when the card lapses - so an owner who
stepped away for four minutes came back to nothing (the owner's decision of
2026-10-10: these wait, everything routine keeps its window, and deliberately
NOT "every card").

WHAT THIS PROVES, and each of these is a way the change could be wrong:

  * timeout_for names the real action ids - the ones the modules pass to
    check() and jarvis-framework.toml declares - and not a tool name, a
    spelling nobody uses, or an id invented to suit the list. Every name in
    APPROVAL_NEVER_EXPIRES has a line in the shipped settings file.
  * a routine card still expires exactly as it did, and is still refused with
    outcome "timed_out" - not a new answer.
  * a card with no deadline does NOT become a refusal when the clock moves
    past the timeout. The clock is simulated (see _Clock): no test sleeps 180
    seconds, and the wait loop is driven by the same code it drives in
    production.
  * a card with no deadline is still only answerable while it is THE live
    card: answered, it returns approved; denied, denied; and withdrawn - the
    job it asked about is gone - it stops waiting and refuses, which is what
    cancelling a pairing does today.
  * `/api/pending` sends no `expires_in` for these, which is the whole of what
    both apps' countdowns read. A 0 there would have said "expired now" and
    both clients would have refused a card that is still perfectly
    answerable; a 180 would have drawn a countdown that ends in a refusal that
    never comes.
  * jarvis_owner_check, which decides whether a risky approval may be stamped
    after Windows Hello, does not refuse these either. That module is the
    second half of the same promise and the easier half to forget: it used to
    treat a missing `expires_in` as "the shipped 180 seconds", so a pairing
    card would have been refused at the Hello prompt even though the gate was
    still waiting.
  * the startup sweep in `_init()` does not expire a deliberate card by age.
    Without that, the whole change would be undone by the back door: the sweep
    marks anything older than the timeout plus a grace period as 'expired',
    and a card left waiting on purpose is exactly that.

HOW THE GATE IS LOADED. `jarvis_gate.py` is the owner's file; this repository
holds a copy in `jarvis-backend/` (the published base - see
jarvis-backend/README.md and backend/test_base_matches_repo.py). This suite
copies that base into a scratch folder and applies `no-expiry-cards.patch` to
it with `git apply`, so what it exercises is the patch's real output on the
file the patch is published against - not a copy typed to suit the test, and
not `_stack`'s stand-in, which is built for jarvis_hud.py and cannot be
imported as Python. `test_approval_contract.py` checks the same patch from the
other side: that its context is the text the stack above it wrote.

Needs nothing from the owner's PC and no network. Runs anywhere git does.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _gitapply  # noqa: E402  (beside this file; its docstring says why)
from _where import REPO  # noqa: E402

PATCH = HERE / "no-expiry-cards.patch"
BASE = REPO / "jarvis-backend"
TOML = BASE / "jarvis-framework.toml"
PATCHED = ("jarvis_gate.py", "jarvis_owner_check.py", "jarvis_devices.py")

#: The shipped `approval_timeout_seconds`, and the value every check below
#: runs with. Small enough that the simulated clock reaches it at once, and
#: the same number the owner's settings file ships with.
TIMEOUT = 180

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: counted on its own, never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


# ---------------------------------------------------------------------------
# The shipped backend: the published base with this patch applied to it
# ---------------------------------------------------------------------------

_BUILT: dict = {}


def _base_copy(folder: Path, name: str, git: str) -> str:
    """Put the BASE's copy of `name` into `folder`. Returns "" or a reason.

    `jarvis_gate.py` comes from the commit, not the working tree, and that is
    the point of this suite: it has to build the file by APPLYING the patch to
    the text the patch was written against, so what it exercises is the
    patch's real output. A working-tree copy would already carry the change
    (this is the commit that makes it), and applying the patch on top would
    fail - which is a test that proves nothing about the patch.

    The other two modules are shipped whole rather than patched, so their
    working-tree copy is the shipped one; `git show HEAD:` is tried first for
    them too, so the suite reads the patch against the same commit either way.
    """
    r = subprocess.run([git, "show", f"HEAD:jarvis-backend/{name}"], cwd=str(REPO),
                       capture_output=True)
    if r.returncode == 0 and r.stdout:
        folder.joinpath(name).write_bytes(r.stdout.replace(b"\r\n", b"\n"))
        return ""
    # Not a git checkout, or the file is not in that commit yet (a suite run
    # before the first commit of this change): fall back to the working tree,
    # and say which shape was used so a failure can be read correctly.
    src = BASE / name
    if not src.is_file():
        return f"{name} is neither in HEAD nor in {BASE}"
    folder.joinpath(name).write_bytes(src.read_bytes().replace(b"\r\n", b"\n"))
    _BUILT.setdefault("working_tree", []).append(name)
    return ""


def built() -> tuple:
    """(folder holding the patched modules, why it could not be built)."""
    if "dir" in _BUILT:
        return _BUILT["dir"], ""
    git = shutil.which("git")
    if not git:
        return None, "git is not installed, so the patch cannot be applied"
    if not PATCH.is_file():
        return None, f"{PATCH.name} is missing"
    d = Path(tempfile.mkdtemp(prefix="jarvis-no-expiry-"))
    for name in PATCHED:
        why = _base_copy(d, name, git)
        if why:
            return None, why
    # Inside a work tree, `git apply` resolves the patch's paths against the
    # repository root and would apply nothing while exiting 0. _gitapply is
    # the module the rest of these suites use for exactly that.
    env = _gitapply.env_for(git, d)
    r = subprocess.run([git, "-c", "core.autocrlf=false", "-c", "core.eol=lf",
                        "apply", str(PATCH)], cwd=str(d), capture_output=True,
                       text=True, env=env)
    if r.returncode != 0:
        return None, (f"git apply refused {PATCH.name}: "
                      f"{(r.stderr or r.stdout).strip().splitlines()[:1]}")
    _BUILT["dir"] = d
    return d, ""


def load_module(name: str, folder: Path, **env):
    """Import `name` out of `folder`, freshly, with the environment its module
    reads at import time.

    FRESH EVERY TIME, and that is not tidiness either. `jarvis_gate` reads
    `JARVIS_APPROVALS_DB` and `JARVIS_APPROVAL_TIMEOUT` at import and its
    `_init()` runs once per process, so a module left in `sys.modules` from an
    earlier check carries that check's database and its `_inited` flag into
    the next one - and every gate instance then shares one stale approvals.db.
    That is not a hypothetical: it is how this suite first failed, with a card
    raised into a database nobody was watching.

    `jarvis_framework` is replaced before each import too: it is the gate's
    only module-level import, it reads the owner's settings file, and
    `CONFIG_DIR` has to be a Path (the gate writes `CONFIG_DIR / "approvals.db"`).
    """
    cfg = Path(tempfile.mkdtemp(prefix="jarvis-no-expiry-state-"))
    os.environ["JARVIS_APPROVALS_DB"] = str(cfg / "approvals.db")
    os.environ["JARVIS_APPROVAL_TIMEOUT"] = str(TIMEOUT)
    os.environ["JARVIS_NTFY_TOPIC"] = ""      # never a socket, said explicitly
    for k, v in env.items():
        os.environ[k] = str(v)
    fw = types.ModuleType("jarvis_framework")
    fw.CONFIG_DIR = cfg
    fw.LOG_DIR = cfg
    # A real tier table, and a real one is the point: `check()` treats an
    # EMPTY table as "the policy could not be read" and refuses everything
    # before it ever raises a card, so a stub with `tiers: {}` makes every
    # check below read "autonomy policy could not be read" - the gate
    # failing closed, and a test proving nothing (the lesson
    # test_gate_outcome.py's own comment records, learned the same way).
    # Every action this suite asks about is "ask", which is what the shipped
    # jarvis-framework.toml says for all of them.
    fw.load_framework = lambda: {
        "logging": {"redact_private_content_in_logs": True},
        "autonomy": {"unknown_action_tier": "ask",
                     "tiers": {a: "ask" for a in DELIBERATE + ROUTINE}},
    }
    fw.audit_log = lambda *a, **k: None
    sys.modules["jarvis_framework"] = fw
    for mod in [n for n in sys.modules if n.startswith(name)]:
        del sys.modules[mod]
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    return __import__(name)


class _Clock:
    """A clock the test moves, standing in for the gate's `time` module.

    Two ways to use it, and the difference matters:

      * `advance(seconds)`, frozen (the default): the test decides exactly how
        much time passes. Every check that asks a question about a deadline
        uses this, because it is the only version whose arithmetic is not a
        race - a waiter in another thread polls through the same clock and
        would otherwise move it under the assertion, at a rate that depends on
        how busy the machine is (measured here: 0.25 s a poll, and a slow suite
        runs the poll thousands of times a second).
      * `sleep_advances = False` and a small `poll` (see `polling_clock`): the
        wait loop's own `time.sleep(POLL_SECONDS)` moves the clock, so a
        routine card reaches its real deadline in a moment of wall time. That
        is the one shape a frozen clock cannot produce, and exactly one test
        uses it.
    """

    def __init__(self, start: float = None):
        # Real time, not a fixed date: the gate's own `_init()` sweeps rows
        # older than the timeout, and a clock starting anywhere in the past
        # would make every routine card born expired - a test failure that
        # says nothing about the change.
        self.now = float(time.time() if start is None else start)
        self.slept = 0.0
        self.sleep_advances = True
        self.poll = None       # None: advance by whatever the gate asks for

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept += float(seconds)
        if self.sleep_advances:
            self.now += float(self.poll if self.poll is not None else seconds)

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


class simulated_clock:
    """`with simulated_clock(G) as clock:` - the gate's clock, moved by hand.

    Frozen: nothing but `clock.advance()` moves it, so an assertion about
    `expires_in` or about a deadline is arithmetic rather than a race."""

    def __init__(self, module, start: float = None, poll: float = None):
        self.module = module
        self.clock = _Clock(start)
        self.clock.sleep_advances = False
        self.clock.poll = poll

    def __enter__(self):
        self.module.time = self.clock
        return self.clock

    def __exit__(self, *exc):
        self.module.time = time
        return False


class polling_clock(simulated_clock):
    """The same clock, with the gate's own poll moving it - one poll's worth of
    simulated time per poll, so a routine card reaches its real 180-second
    deadline in a few thousand of them rather than in three real minutes."""

    def __init__(self, module, start: float = None):
        super().__init__(module, start)
        self.clock.sleep_advances = True


def ask(gate, action: str, box: dict, **kw):
    """`check()` on its own thread, so the test can decide the card while it
    waits. A thread rather than a timeout: the whole point of the no-deadline
    case is that it does not come back on its own."""
    box["at"] = time.time()

    def run():
        try:
            box["v"] = gate.check(action, {"why": "a test"}, prompt=f"a test {action}",
                                  **kw)
        except Exception:
            box["v"] = None
            box["error"] = traceback.format_exc()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def wait_for_row(gate, box, seconds: float = 10.0, why: str = ""):
    """The pending row `ask()` raised, as soon as it is there. `why` is kept
    for the failure message: a check that only says "no row" cannot be acted
    on, and this suite has already been debugged once through exactly that."""
    end = time.time() + seconds
    while time.time() < end:
        rows = gate.pending()
        if rows:
            return rows[0]
        time.sleep(0.02)
    box["no_row"] = (f"{why}: nothing pending in {gate.DB_PATH} "
                     f"(exists={getattr(gate.DB_PATH, 'exists')()}); "
                     f"history={gate.history(5)}")
    return None


def kinds(actions, gate):
    return {a: gate.timeout_for(a) for a in actions}


# ---------------------------------------------------------------------------
# The names
# ---------------------------------------------------------------------------

#: What the owner's decision exempts: the deliberate, hard-to-repeat cards.
#: Every entry is checked against the shipped settings file below, so a name
#: that is not a real action id fails here rather than sitting in the set.
DELIBERATE = (
    # pairing a device
    "pair_device", "unretire_shared_key", "register_approval_key",
    # restoring a backup
    "restore_backup",
    # forgetting a time frame
    "memory_forget_range",
    # settings changes that LOOSEN a rule
    "loosen_what_asks_first", "enable_reading_tool", "watch_notifications_enable",
    "web_search_enable", "stop_asking_before_every_web_search", "topic_loosen",
    "learning_enable", "learning_auto_enable", "learning_sensitive_enable",
    "history_enable", "screen_picture_enable", "obscura_enable",
    "raise_api_limit", "raise_attention_budget", "raise_a_limit",
    "lower_the_voice_check_bar", "handoff_keep_offering",
    "handoff_bring_to_front",
)

#: What KEEPS its window: everything routine and reversible. Not an exemption
#: list - it is the control, and it is what makes the one above a decision
#: rather than a blanket "no card expires".
ROUTINE = (
    "send_email", "draft_email", "tidy_inbox", "search_the_web", "read_web_page",
    "run_shell_on_host", "delete_file", "write_notes_after_outside_text",
    "control_computer", "control_phone", "home_control", "spend_money",
    "schedule_repeat", "chatbot_session", "support_chat", "support_offer",
    "quiz_cloud_grade", "referee_tick", "chat_tag_suggest", "youtube_captions_read",
)

#: The three names `check()` gives an action it could not map to anything in
#: the settings file (jarvis_gate._classify_prompt / action_for_tool). They are
#: not declared anywhere, by design - being undeclared IS what makes them
#: "ask" - so they are checked for their timeout and not against the file.
FALLBACK = ("unclassified_tool", "unclassified_action", "unclassified_side_effect")


def t_the_patch_is_the_base_plus_this_change():
    """The suite's own footing: the base is there, the patch applies to it,
    and what comes out is not what went in."""
    d, why = built()
    if d is None:
        return skip(why)
    check("the published base's jarvis_gate.py is there", (BASE / "jarvis_gate.py").is_file())
    check("no-expiry-cards.patch applies to it with git", True)
    git = shutil.which("git")
    before = subprocess.run([git, "show", "HEAD:jarvis-backend/jarvis_gate.py"],
                            cwd=str(REPO), capture_output=True).stdout.decode("utf-8")
    after = (d / "jarvis_gate.py").read_text(encoding="utf-8")
    check("...and the file it produces is not the file it started from",
          after != before.replace("\r\n", "\n"))
    check("...and it is the whole file, not an empty one", len(after) > 100_000, len(after))
    check("...and the other two files it changes are shipped modules the repository "
          "publishes whole",
          (d / "jarvis_owner_check.py").is_file() and (d / "jarvis_devices.py").is_file())
    check("...and those two are byte for byte the published ones (the patch must not "
          "carry a second copy of a shipped module)",
          (d / "jarvis_owner_check.py").read_bytes()
          == (BASE / "jarvis_owner_check.py").read_bytes().replace(b"\r\n", b"\n")
          if "jarvis_owner_check.py" not in _BUILT.get("working_tree", []) else True)


def t_every_exempted_name_is_a_real_gate_action():
    """No invented ids. Each is an action `jarvis-framework.toml` declares -
    the file the gate reads its tiers from - and the modules pass that exact
    string to check().

    A name that is not there would be dead weight in the set: it would exempt
    nothing, and the card it was meant to be would still lapse.
    """
    d, why = built()
    if d is None:
        return skip(why)
    toml = TOML.read_text(encoding="utf-8")
    declared = set(re.findall(r"^\s*([a-z_][a-z0-9_]*)\s*=\s*\"(?:ask|auto|never|notify)\"",
                              toml, re.M))
    for name in DELIBERATE:
        check(f"{name} is a real action in jarvis-framework.toml", name in declared,
              f"not declared; {len(declared)} actions are")
    for name in ROUTINE:
        check(f"{name} (routine) is a real action too", name in declared)
    for name in FALLBACK:
        check(f"{name} is one of the names check() itself can produce",
              f'"{name}"' in (BASE / "jarvis_gate.py").read_text(encoding="utf-8"))
    # And the two lists cannot overlap: an action is exempt or it is not.
    check("no action is in both lists",
          not (set(DELIBERATE) & (set(ROUTINE) | set(FALLBACK))),
          sorted(set(DELIBERATE) & (set(ROUTINE) | set(FALLBACK))))


def t_timeout_for_returns_no_deadline_for_deliberate_cards_only():
    d, why = built()
    if d is None:
        return skip(why)
    G = load_module("jarvis_gate", d)
    for name, got in kinds(DELIBERATE, G).items():
        check(f"timeout_for({name!r}) is None - the card waits", got is None, got)
    for name, got in kinds(ROUTINE, G).items():
        check(f"timeout_for({name!r}) is {TIMEOUT} - the card still expires",
              got == TIMEOUT, got)
    check("an action nobody thought to classify keeps its window",
          G.timeout_for("some_action_added_next_year") == TIMEOUT)
    check("...and an empty action name is not accidentally exempt",
          G.timeout_for("") == TIMEOUT)
    check("the set and timeout_for agree, name for name",
          set(G.APPROVAL_NEVER_EXPIRES) == set(DELIBERATE),
          sorted(set(G.APPROVAL_NEVER_EXPIRES) ^ set(DELIBERATE)))


# ---------------------------------------------------------------------------
# The clock
# ---------------------------------------------------------------------------

def t_a_clock_past_the_timeout_does_not_refuse_a_deliberate_card():
    """The whole change, in one check: pair the phone, walk away for an hour,
    come back. The card is still waiting, and the call that raised it has not
    been refused."""
    d, why = built()
    if d is None:
        return skip(why)
    G = load_module("jarvis_gate", d)
    OC = load_module("jarvis_owner_check", d)
    box = {}
    with simulated_clock(G) as clock:
        t = ask(G, "pair_device", box)
        row = wait_for_row(G, box)
        if row is None:
            return check("the pairing card was raised", False, box.get("no_row", "no pending row"))
        clock.advance(3600.0)          # an hour later
        # Nothing to wait for: the waiter never returns on its own, which is
        # the point. Give the poll loop the same wall-clock moment it would
        # have had, so a card that WAS going to give up has every chance to.
        time.sleep(0.4)
        still = G.pending()
        check("an hour on, the card is still waiting",
              [r["id"] for r in still] == [row["id"]], still)
        check("...and it carries no expiry", "expires_in" not in still[0], still[0])
        check("...and the code that raised it is still waiting, not refused",
              t.is_alive() and "v" not in box, box)
        # Answer it, an hour late - which is the point. Stamped the way a real
        # approval is (jarvis_owner_check.stamp, the same call POST
        # /api/approve makes): an approval nothing stamped is refused, which
        # the check at the end of the answer-and-deny test proves is still so.
        OC.stamp(still[0]["id"], still[0]["action"])
        G.decide(still[0]["id"], True, by="the test")
        t.join(timeout=10)
        v = box.get("v")
        check("answered an hour late, it is approved", v is not None and v.allowed is True,
              f"{v} / {box.get('error', '')}")
        check("...with outcome 'approved', from a person's yes",
              v is not None and v.outcome == "approved", v)


def t_the_same_clock_still_expires_a_routine_card():
    """CONTROL. If nothing expired, the check above would pass on a gate that
    had stopped refusing anything at all.

    The one test that lets the gate's own poll move the clock: it is the only
    way to reach a real 180-second deadline without sleeping for three
    minutes. `ask()` cannot help here - the check has to return a verdict on
    its own - so this calls it directly, on the test's own thread.
    """
    d, why = built()
    if d is None:
        return skip(why)
    G = load_module("jarvis_gate", d)
    before = time.time()
    with polling_clock(G) as clock:
        v = G.check("send_email", {"to": "someone"}, prompt="send an email")
    took = time.time() - before
    check("a routine card refuses when its window passes", v.allowed is False, v)
    check("...as timed_out, not denied - nobody decided anything",
          v.outcome == "timed_out", v)
    check("...and it was the simulated clock that got there, not a real wait",
          took < 30, f"took {took:.1f}s (clock moved {clock.now - before:.0f}s)")
    check("...and the row is left 'expired', as it always was",
          [r["state"] for r in G.history(5)] == ["expired"], G.history(5))


def t_a_clock_past_the_timeout_does_not_expire_the_deliberate_row():
    """The back door: `_init()` sweeps anything older than the timeout plus a
    grace period to 'expired', because a process that died mid-wait leaves its
    row behind. A card left waiting ON PURPOSE is exactly that shape, so
    without the sweep's exclusion the change holds for a few minutes and then
    quietly undoes itself.

    The control runs in the same database, with the same sweep, on a routine
    card of exactly the same age.
    """
    d, why = built()
    if d is None:
        return skip(why)
    G = load_module("jarvis_gate", d)
    with simulated_clock(G) as clock:
        box = {}
        t = ask(G, "restore_backup", box)
        row = wait_for_row(G, box)
        if row is None:
            return check("the restore card was raised", False, box.get("no_row", "no pending row"))
        clock.advance(TIMEOUT + 600.0)         # past the sweep's grace period
        # What a later start-up of Jarvis does - the same database, the same
        # sweep, no new rows.
        G._inited = False
        G._init()
        rows = G.pending()
        check("the sweep leaves a deliberate card alone",
              [r["id"] for r in rows] == [row["id"]], rows)
        check("...and it is still 'pending' in the record, not 'expired'",
              [r["state"] for r in G.history(5) if r["id"] == row["id"]] == ["pending"],
              G.history(5))
        check("...and the code that raised it is still waiting", t.is_alive())
        G.decide(row["id"], False, by="the test")
        t.join(timeout=10)
    with simulated_clock(G) as clock:
        # A routine card, same age, same database, same sweep.
        box2 = {}
        t2 = ask(G, "send_email", box2)
        wait_for_row(G, box2)
        clock.advance(TIMEOUT + 600.0)
        t2.join(timeout=10)
        G._inited = False
        G._init()
        check("CONTROL: a routine card of the same age IS swept, and is gone "
              "from the list",
              all(r["action"] != "send_email" for r in G.pending()), G.pending())
        check("...and the record says 'expired'",
              [r["state"] for r in G.history(5) if r["action"] == "send_email"]
              == ["expired"], G.history(5))


# ---------------------------------------------------------------------------
# Still only the live card
# ---------------------------------------------------------------------------

def t_a_deliberate_card_can_still_be_answered_and_denied():
    """Answering is not weakened by there being no deadline.

    An "approved" row is only believed when THIS process stamped it, through
    the same `jarvis_owner_check.take_stamp` that `POST /api/approve` uses
    (owner-check.patch). The test stamps it the same way a real approval is
    stamped rather than reaching round that check: an unstamped approve is
    refused, which is the protection, and the check at the end proves it is
    still there for a card with no deadline.
    """
    d, why = built()
    if d is None:
        return skip(why)
    for answer, want, outcome in ((True, True, "approved"), (False, False, "denied")):
        G = load_module("jarvis_gate", d)
        OC = load_module("jarvis_owner_check", d)
        box = {}
        with simulated_clock(G):
            t = ask(G, "memory_forget_range", box)
            row = wait_for_row(G, box)
            if row is None:
                check(f"'forget a time frame' card raised ({want=})", False, "no row")
                continue
            if answer:
                OC.stamp(row["id"], row["action"])
            check(f"decide({answer}) is accepted on a card with no deadline",
                  G.decide(row["id"], answer, by="the test") is True)
            t.join(timeout=10)
            v = box.get("v")
            check(f"...and the caller reads {outcome}", v is not None and v.outcome == outcome,
                  f"{v} / {box.get('error', '')}")
            check("...and a second decision on the same card changes nothing",
                  G.decide(row["id"], not answer, by="the test") is False)
    # The stamp check itself, on a card with no deadline: refuse, never grant.
    G = load_module("jarvis_gate", d)
    box = {}
    with simulated_clock(G):
        t = ask(G, "pair_device", box)
        row = wait_for_row(G, box)
        if row is None:
            return check("the pairing card was raised", False, "no row")
        G.decide(row["id"], True, by="a program that is not the backend")
        t.join(timeout=10)
        v = box.get("v")
        check("an approval nothing stamped is still refused, deadline or none",
              v is not None and v.allowed is False and v.outcome == "refused", v)


def t_a_deliberate_card_can_still_be_withdrawn():
    """Cancelling a pairing, or starting a new one, abandons the card. With no
    clock to run out, nothing else would ever take it off the list - so
    `withdraw` does, and the wait it wakes is a refusal that is NOT a denial:
    nobody said no, and a denial would propose a memory rule."""
    d, why = built()
    if d is None:
        return skip(why)
    G = load_module("jarvis_gate", d)
    box = {}
    with simulated_clock(G):
        t = ask(G, "pair_device", box)
        row = wait_for_row(G, box)
        if row is None:
            return check("the pairing card was raised", False, box.get("no_row", "no pending row"))
        check("withdraw takes the card off the list",
              G.withdraw(row["id"], "the pairing was cancelled") is True)
        check("...and the list is empty", G.pending() == [], G.pending())
        t.join(timeout=10)
        v = box.get("v")
        check("...and the wait ends as a refusal, not a denial",
              v is not None and v.allowed is False and v.outcome == "timed_out", v)
        check("...and its state in history is 'expired', as a lapse is",
              [r["state"] for r in G.history(5) if r["id"] == row["id"]] == ["expired"],
              G.history(5))
        check("withdrawing an id that is gone changes nothing",
              G.withdraw(row["id"], "again") is False)


def t_pending_sends_no_deadline_for_a_card_that_has_none():
    """What both apps' countdowns read.

    Absent means "no countdown" to the phone (PendingRows.kt computes
    expires_at_ms only from a real number) and to the desktop (stream.rs
    stamps one only from a real number, and expiryWords returns "" without
    one). 0 would have meant "expired now" to both - they would have refused a
    card that is still answerable - and the timeout would have drawn a
    countdown that ends in a refusal that never comes.
    """
    d, why = built()
    if d is None:
        return skip(why)
    G = load_module("jarvis_gate", d)
    with simulated_clock(G):
        box = {}
        t = ask(G, "pair_device", box)
        row = wait_for_row(G, box)
        if row is None:
            return check("the pairing card was raised", False, box.get("no_row", "no pending row"))
        check("no expires_in on a card with no deadline", "expires_in" not in row, row)
        check("...and the notice is still there, so the card still has its words",
              bool(row.get("notice", {}).get("title")), row)
        G.decide(row["id"], False, by="the test")
        t.join(timeout=5)
    # A module of its own for the routine half: `check()`'s wait loop holds a
    # read connection, and two cards in one process share one approvals.db -
    # the second half gets a clean instance rather than relying on what a
    # connection opened for the first card can see. (This is not tidiness: it
    # is how this suite first failed, with the routine card raised into a
    # database the new waiter could not read.)
    G2 = load_module("jarvis_gate", d)
    with simulated_clock(G2) as clock:
        box2 = {}
        t2 = ask(G2, "send_email", box2)
        row2 = wait_for_row(G2, box2)
        if row2 is None:
            return check("the routine card was raised", False,
                         box2.get("no_row", "no pending row"))
        # The whole window, to the second: `expires_in` is a whole number of
        # seconds, so a card raised at time T reads TIMEOUT, or one less if
        # the fraction of a second between the row's `created` and this read
        # has already carried it over.
        left = row2.get("expires_in")
        check("a routine card still carries its seconds left - the whole window, "
              "as it always did",
              left in (TIMEOUT, TIMEOUT - 1), left)
        before = G2.pending()[0].get("expires_in")
        check("...and with the clock standing still it does not move",
              before == G2.pending()[0].get("expires_in"), before)
        clock.advance(60.0)
        after = G2.pending()[0].get("expires_in")
        check("...and it counts down by exactly a minute when a minute passes",
              after == before - 60, f"{before} then {after}")
        G2.decide(row2["id"], False, by="the test")
        t2.join(timeout=5)


# ---------------------------------------------------------------------------
# The other half: the Windows Hello check
# ---------------------------------------------------------------------------

def t_owner_check_gives_a_row_with_a_deadline_its_own_seconds():
    """`jarvis_owner_check._time_left`, on its own, for the four shapes a row
    can arrive in. The function is lifted out of the patched module's text so
    this suite does not need a Windows Hello verifier to ask it."""
    d, why = built()
    if d is None:
        return skip(why)
    text = (d / "jarvis_owner_check.py").read_text(encoding="utf-8")
    fn = re.search(r"def _time_left\(row: dict\).*?(?=\ndef |\n# ---)", text, re.S)
    if fn is None:
        return check("_time_left is in the patched module", False, "not found")
    ns = {"Optional": __import__("typing").Optional, "DEFAULT_TIME_LEFT": 180.0}
    exec(compile(fn.group(0), "jarvis_owner_check.py:_time_left", "exec"), ns)
    _time_left = ns["_time_left"]
    check("a card with 30 seconds left reads 30", _time_left({"expires_in": 30}) == 30)
    check("a card past its deadline reads 0 or less", _time_left({"expires_in": 0}) == 0
          and _time_left({"expires_in": -5}) == -5)
    check("NO expires_in at all is the shipped timeout, NOT None: a row from a "
          "backend without approval-expiry.patch still has a window",
          _time_left({}) == 180.0, _time_left({}))
    check("an explicit null is None - the gate's own 'no deadline', which is what "
          "the patch writes by leaving the field off a JSON row",
          _time_left({"expires_in": None}) is None)
    for bad in ("yesterday", "", [1], float("nan")):
        check(f"expires_in={bad!r} falls back to the shipped timeout",
              _time_left({"expires_in": bad}) == 180.0, _time_left({"expires_in": bad}))


def t_owner_check_does_not_refuse_a_card_with_no_deadline():
    """The same promise, asked of the decision path itself.

    `approve_check` is what stands between a risky card and its stamp. With no
    Windows Hello verifier, a card with no deadline must reach the verifier
    rather than be refused first - the bug this half exists for is that the
    old code read a missing `expires_in` as "180 seconds left" and answered
    409 GONE for a card the gate was still waiting on.
    """
    d, why = built()
    if d is None:
        return skip(why)
    OC = load_module("jarvis_owner_check", d)
    row = {"id": "r1", "action": "pair_device", "tier": "ask",
           "detail": {"text": "words"}, "prompt": "connect a new device",
           "notice": {"title": "Jarvis wants to connect a new device", "body": "check the words"},
           "risk": {"reversible": "yes", "reach": "local", "why": "a test",
                    "swipe_ok": True, "classified": True}}
    asked = []
    OC.set_verifier(lambda message, timeout: asked.append(timeout) or OC.CONFIRMED)
    try:
        # From this PC, so the Windows Hello branch is the one that runs. The
        # pending function is handed in, which is the seam that module already
        # has: no gate, no database, no Windows.
        out = OC.approve_check({"id": "r1"}, peer="127.0.0.1", local="127.0.0.1",
                               own=lambda: frozenset({"127.0.0.1"}),
                               pending=lambda: [row])
        check("a deliberate card with no deadline is not refused", out is None, out)
        check("...and Windows Hello was actually asked", asked != [], asked)
        check("...with a bounded prompt (a Hello dialog left open for ever helps "
              "nobody), the shipped timeout", asked == [180.0], asked)
        # CONTROL: the same row with a deadline in the past is still refused.
        gone = dict(row, expires_in=0)
        out2 = OC.approve_check({"id": "r1"}, peer="127.0.0.1", local="127.0.0.1",
                                own=lambda: frozenset({"127.0.0.1"}),
                                pending=lambda: [gone])
        check("CONTROL: a card whose window HAS passed is still refused",
              out2 is not None and out2[0] == 409 and out2[1].get("owner_check") == "gone",
              out2)
        # And the re-read after the prompt still refuses a card that is no
        # longer the live one - the protection that has to survive no expiry.
        answers = [row, None]
        out3 = OC.approve_check({"id": "r1"}, peer="127.0.0.1", local="127.0.0.1",
                                own=lambda: frozenset({"127.0.0.1"}),
                                pending=lambda: [answers.pop(0)] if answers[0] else [])
        check("...and a card that is no longer pending after the prompt is refused",
              out3 is not None and out3[0] == 409 and out3[1].get("owner_check") == "gone",
              out3)
    finally:
        OC.set_verifier(None)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    for fn in (t_the_patch_is_the_base_plus_this_change,
               t_every_exempted_name_is_a_real_gate_action,
               t_timeout_for_returns_no_deadline_for_deliberate_cards_only,
               t_a_clock_past_the_timeout_does_not_refuse_a_deliberate_card,
               t_the_same_clock_still_expires_a_routine_card,
               t_a_clock_past_the_timeout_does_not_expire_the_deliberate_row,
               t_a_deliberate_card_can_still_be_answered_and_denied,
               t_a_deliberate_card_can_still_be_withdrawn,
               t_pending_sends_no_deadline_for_a_card_that_has_none,
               t_owner_check_gives_a_row_with_a_deadline_its_own_seconds,
               t_owner_check_does_not_refuse_a_card_with_no_deadline):
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
