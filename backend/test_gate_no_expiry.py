"""Which approval cards expire, and the four doors that may wait for the owner.

    python3 test_gate_no_expiry.py

WHY THIS EXISTS, AND WHY IT IS NARROW

`rescue/card-expiry-never-expires` (6900be0ac) rescued work that made 23 gate
actions' cards wait for ever. The owner's ruling of 2026-10-23 (Q1) refused
that scope: only the three interactive ceremonies - pairing a device, an
approval key for a phone, and restoring a backup - may have no deadline.
Every other card keeps the 15-minute window `#378` shipped, including every
setting that LOOSENS a rule and "forget a time frame".

So this suite proves FOUR things, and the file is organised around them:

  1. t_an_ordinary_session_still_expires_after_fifteen_minutes
     The shipped `approval_timeout_seconds` is 900 (15 minutes), the patched
     gate's default is that same 900 (not the 180 the rescued work was written
     against), and a routine card actually ends at 15 minutes - refused as
     `timed_out`, with its row `expired`.
  2. t_only_pairing_approval_key_and_restore_may_never_expire
     `APPROVAL_NEVER_EXPIRES` is EXACTLY the four action ids of those three
     flows. The other 19 actions the rescued work exempted are named here and
     held to 900, so a re-widening fails this suite by name. Each exempted id
     is a real action in `jarvis-framework.toml`, raised by the module that
     owns it - no invented, misspelt or tool names.
  3. t_never_expires_cannot_be_reached_by_omission_zero_negative_malformed_or_unknown_flow
     The only way in is the exact action id. None, "", 0, a negative number,
     a flow name ("pairing", "approval_key", ...), the wrong case, a padded or
     truncated name, an unknown name, bytes, a list, a dict - every one is an
     ordinary 900-second card. There is no "flow" argument to forge and no
     caller-supplied value that reaches the set; a caller's own `timeout=`
     still wins over it, in the safe (shorter) direction.
  4. t_the_patch_is_the_base_plus_this_change
     The suite's own footing: `no-expiry-cards.patch` applies to the published
     base with `git apply` (no fuzz), produces a different, complete,
     compilable module, that module is anchored on #378's 900 seconds, and the
     patch touches only `jarvis_gate.py` - never a second copy of a module the
     repository ships whole.

The other tests here are the supporting half: a card with no deadline can
still be approved, denied and withdrawn; the start-up sweep does not age it
out (and still sweeps a routine row); `/api/pending` carries no `expires_in`
for it (never 0); `jarvis_owner_check` - the Windows Hello gate - does not
refuse it; and the pairing/approval-key modules withdraw a cancelled card
instead of leaving a permanent ghost.

The last three drive the real pairing and approval-key code against the real
patched gate (audit 2026-10-24, B-1 and B-2): Cancel and the 600-second expiry
must take the waiting pair_device card off the list so a later Approve cannot
report success while minting nothing, and a retry of the SAME approval key
must join the one card already waiting instead of orphaning the waiter that
will store it. They replaced a source-text pin that passed while both bugs
were live.

HOW THE GATE IS LOADED. `jarvis_gate.py` is the owner's file; this repository
holds the published base in `jarvis-backend/` (see jarvis-backend/README.md
and backend/test_base_matches_repo.py). This suite copies that base into a
scratch folder and applies `no-expiry-cards.patch` to it with `git apply`, so
what it exercises is the patch's real output on the file the patch is
published against - not a copy typed to suit the test. The two SHIPPED
modules it uses (`jarvis_owner_check.py`, `jarvis_devices.py`) are the
repository's own copies, and the twin check proves the base's copies are
byte-identical to them.

Needs nothing from the owner's PC and no network. Runs anywhere git does.
"""
from __future__ import annotations

import inspect
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
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _gitapply  # noqa: E402  (beside this file; its docstring says why)
from _where import REPO  # noqa: E402

PATCH = HERE / "no-expiry-cards.patch"
BASE = REPO / "jarvis-backend"
BACKEND = REPO / "backend"
TOML = BASE / "jarvis-framework.toml"

#: The shipped `approval_timeout_seconds` #378 left on 2026-10-13: 15 minutes.
#: Read out of the config below as well, so these two cannot drift apart.
MINUTES_15 = 15 * 60

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
# The published base, plus this patch, as a module
# ---------------------------------------------------------------------------

_BUILT: dict = {}

#: The actions the owner's ruling does NOT exempt. Every one was in the rescued
#: work's 23-name list and must stay on the 15-minute window; named one by one
#: so a re-widening fails a check that says which name came back.
DROPPED_FROM_THE_RESCUE = (
    "memory_forget_range",
    "loosen_what_asks_first", "enable_reading_tool",
    "watch_notifications_enable",
    "web_search_enable", "stop_asking_before_every_web_search",
    "topic_loosen",
    "learning_enable", "learning_auto_enable", "learning_sensitive_enable",
    "history_enable",
    "screen_picture_enable", "obscura_enable",
    "raise_api_limit", "raise_attention_budget", "raise_a_limit",
    "lower_the_voice_check_bar",
    "handoff_keep_offering", "handoff_bring_to_front",
)

#: The four that ARE exempt: pairing (its card, and bringing the old shared key
#: back), the approval-key registration, and the restore. Kept as a tuple so
#: the expected set below is written out rather than derived from the module.
NEVER_EXPIRES = ("pair_device", "unretire_shared_key", "register_approval_key",
                 "restore_backup")

#: Everything routine and reversible. The control: these MUST keep their window.
ROUTINE = (
    "send_email", "draft_email", "tidy_inbox", "search_the_web", "read_web_page",
    "run_shell_on_host", "delete_file", "control_computer", "control_phone",
    "home_control", "spend_money", "schedule_repeat", "chatbot_session",
    "support_chat", "support_offer", "quiz_cloud_grade", "youtube_captions_read",
    "unclassified_action",
)


def built() -> tuple:
    """(folder holding the patched gate and the two SHIPPED copies, why not).

    The base is read from THIS CHECKOUT's `jarvis-backend/` - the file
    `no-expiry-cards.patch` is published against. `git apply` is used rather
    than a text substitution so a patch whose context no longer matches the
    base fails here instead of passing on a hand-made copy.
    """
    if "dir" in _BUILT:
        return _BUILT["dir"], ""
    git = shutil.which("git")
    if not git:
        return None, "git is not installed, so the patch cannot be applied"
    if not PATCH.is_file():
        return None, f"{PATCH.name} is missing"
    base_gate = BASE / "jarvis_gate.py"
    if not base_gate.is_file():
        return None, f"{base_gate} is missing"
    d = Path(tempfile.mkdtemp(prefix="jarvis-no-expiry-"))
    d.joinpath("jarvis_gate.py").write_bytes(
        base_gate.read_bytes().replace(b"\r\n", b"\n"))
    # The two SHIPPED modules: this repository's own copies, which the base
    # twins must equal (test_the_patch_... checks that, and
    # tools/check_stale_twins.py checks it in a second at the desk).
    for name in ("jarvis_owner_check.py", "jarvis_devices.py"):
        src = BACKEND / name
        if not src.is_file():
            return None, f"{src} is missing"
        d.joinpath(name).write_bytes(src.read_bytes().replace(b"\r\n", b"\n"))
    env = _gitapply.env_for(git, d)
    r = subprocess.run([git, "-c", "core.autocrlf=false", "-c", "core.eol=lf",
                        "apply", str(PATCH)], cwd=str(d), capture_output=True,
                       text=True, env=env)
    if r.returncode != 0:
        return None, (f"git apply refused {PATCH.name}: "
                      f"{(r.stderr or r.stdout).strip().splitlines()[:2]}")
    _BUILT["dir"] = d
    return d, ""


def load_module(name: str, folder: Path, **env):
    """Import `name` out of `folder`, freshly, with the environment its module
    reads at import time.

    FRESH EVERY TIME: `jarvis_gate` reads `JARVIS_APPROVALS_DB` at import and
    its `_init()` runs once per process, so a module left in `sys.modules`
    carries an earlier check's database and `_inited` flag into the next one.
    `jarvis_framework` is replaced before each import: it is the gate's only
    module-level import, it reads the owner's settings file, and `CONFIG_DIR`
    has to be a Path.
    """
    cfg = Path(tempfile.mkdtemp(prefix="jarvis-no-expiry-state-"))
    os.environ["JARVIS_APPROVALS_DB"] = str(cfg / "approvals.db")
    os.environ.pop("JARVIS_APPROVAL_TIMEOUT", None)
    os.environ["JARVIS_NTFY_TOPIC"] = ""      # never a socket, said explicitly
    os.environ["JARVIS_NTFY_SERVER"] = ""
    for k, v in env.items():
        os.environ[k] = str(v)
    fw = types.ModuleType("jarvis_framework")
    fw.CONFIG_DIR = cfg
    fw.LOG_DIR = cfg
    # A real tier table: `check()` treats an EMPTY one as "the policy could not
    # be read" and refuses before a card is ever raised, which would make every
    # check below prove nothing. Every action asked about is "ask", which is
    # what the shipped jarvis-framework.toml says for all of them.
    tiers = {a: "ask" for a in NEVER_EXPIRES + DROPPED_FROM_THE_RESCUE + ROUTINE}
    fw.load_framework = lambda: {
        "logging": {"redact_private_content_in_logs": True},
        "autonomy": {"unknown_action_tier": "ask",
                     "approval_timeout_seconds": 900,
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
    """A clock the test moves, standing in for the gate's `time` module.

    Frozen by default: nothing but `advance()` moves it, so an assertion about
    a deadline is arithmetic rather than a race against a waiter's poll.
    """

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
    """`with simulated_clock(G) as clock:` - the gate's clock, moved by hand."""

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
    """`check()` on its own thread, so the test can answer or withdraw the card
    while it waits. A thread rather than a short timeout: the whole point of
    the no-deadline case is that it does not come back on its own."""
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
    """The pending row `ask()` raised, as soon as it is there."""
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


# ---------------------------------------------------------------------------
# 1. THE ORDINARY CARD KEEPS #378's FIFTEEN MINUTES
# ---------------------------------------------------------------------------

def t_an_ordinary_session_still_expires_after_fifteen_minutes():
    """#378's window, read from the shipped settings and then driven.

    Three ways this could be wrong and all three are checked: the shipped
    number could change, the patched module's default could go back to the 180
    the rescued work was written against, or the patch could accidentally stop
    a routine card from expiring at all.
    """
    text = TOML.read_text(encoding="utf-8")
    m = re.search(r"^\s*approval_timeout_seconds\s*=\s*(\d+)\s*$", text, re.M)
    check("the shipped settings declare approval_timeout_seconds", m is not None)
    shipped = int(m.group(1)) if m else None
    check("it is 900 - the fifteen minutes #378 shipped", shipped == MINUTES_15,
          shipped)
    check("and 900 really is 15 minutes", MINUTES_15 == 15 * 60)

    d, why = built()
    if d is None:
        return skip(why)
    G = load_module("jarvis_gate", d)
    check("the patched gate's own default is the shipped 900, not 180",
          G.APPROVAL_TIMEOUT == float(MINUTES_15), G.APPROVAL_TIMEOUT)
    for action in ROUTINE:
        check(f"{action}: an ordinary card gets 900 seconds",
              G.timeout_for(action) == float(MINUTES_15), G.timeout_for(action))

    with simulated_clock(G) as clock:
        box = {}
        t = ask(G, "send_email", box)
        row = wait_for_row(G, box)
        if row is None:
            return check("the routine card was raised", False,
                         box.get("no_row", "no pending row"))
        # Read, don't assume: `expires_in` is a whole number of seconds and the
        # fraction between the row's `created` and this read can carry it over.
        check("a routine card carries its seconds left - the whole window",
              row.get("expires_in") in (MINUTES_15, MINUTES_15 - 1),
              row.get("expires_in"))
        clock.advance(MINUTES_15 - 1)
        time.sleep(0.4)          # let the waiter poll with the clock moved
        check("one second before the window ends, it is still waiting",
              t.is_alive() and any(r["id"] == row["id"] for r in G.pending()),
              {"alive": t.is_alive(), "state": state_of(G, row["id"])})
        clock.advance(2)
        t.join(timeout=10)
        v = box.get("v")
        check("fifteen minutes after it was raised, the card ends",
              v is not None and v.allowed is False, v)
        check("...as 'timed_out' - nobody answered, nobody decided",
              v is not None and v.outcome == "timed_out",
              v.outcome if v is not None else box.get("error"))
        check("...and its row is 'expired', exactly as before this change",
              state_of(G, row["id"]) == "expired", state_of(G, row["id"]))


# ---------------------------------------------------------------------------
# 2. THE ALLOW-LIST IS THE THREE FLOWS, AND NOTHING ELSE
# ---------------------------------------------------------------------------

def t_only_pairing_approval_key_and_restore_may_never_expire():
    """Q1's narrowing, by name: four are exempt, nineteen came back out.

    The rescued work's set had 23 names. This checks the set is EXACTLY the
    four device/backup ones (so a fifth cannot creep in), that each is a real
    action id declared in the shipped settings, that each is raised by the
    module that owns it, and that every one of the other nineteen is back on
    the 15-minute window with a check that names it.
    """
    d, why = built()
    if d is None:
        return skip(why)
    G = load_module("jarvis_gate", d)
    got = set(G.APPROVAL_NEVER_EXPIRES)
    check("APPROVAL_NEVER_EXPIRES is exactly the four Q1 allows",
          got == set(NEVER_EXPIRES), sorted(got))
    check("...and it is a frozenset, so no caller can add to it",
          isinstance(G.APPROVAL_NEVER_EXPIRES, frozenset),
          type(G.APPROVAL_NEVER_EXPIRES))
    for action in NEVER_EXPIRES:
        check(f"{action}: its card has no deadline", G.timeout_for(action) is None,
              G.timeout_for(action))

    # Real action ids, not invented ones: each is declared in the shipped
    # settings file - the file the gate reads its tiers from - with a real tier.
    declared = set(re.findall(
        r'^\s*([a-z_][a-z0-9_]*)\s*=\s*"(?:ask|auto|never|notify)"', text_of(TOML), re.M))
    for action in NEVER_EXPIRES:
        check(f"{action} is a real action in jarvis-framework.toml",
              action in declared, f"not declared; {len(declared)} actions are")

    # ...and each is the action the owning module passes to check(), read from
    # that module's own source rather than restated here.
    devices = text_of(BACKEND / "jarvis_devices.py")
    for const, action in (("ACTION", "pair_device"),
                          ("UNRETIRE_ACTION", "unretire_shared_key"),
                          ("KEY_ACTION", "register_approval_key")):
        check(f"jarvis_devices.py raises {action} (its {const})",
              f'{const} = "{action}"' in devices, const)
    backup = text_of(BASE / "jarvis_backup.py")
    check("jarvis_backup.py raises restore_backup (its RESTORE_ACTION)",
          'RESTORE_ACTION = "restore_backup"' in backup)

    # The nineteen that came back out of the set, each named.
    for action in DROPPED_FROM_THE_RESCUE:
        check(f"{action}: NOT exempt - still the ordinary 900 seconds",
              action not in got and G.timeout_for(action) == float(MINUTES_15),
              G.timeout_for(action))

    with simulated_clock(G) as clock:
        box = {}
        t = ask(G, "pair_device", box)
        row = wait_for_row(G, box)
        if row is None:
            return check("the pairing card was raised", False,
                         box.get("no_row", "no pending row"))
        clock.advance(4 * MINUTES_15)
        time.sleep(0.4)
        check("an exempt card is still pending an hour later, and still waiting",
              t.is_alive() and any(r["id"] == row["id"] for r in G.pending()),
              {"alive": t.is_alive(), "state": state_of(G, row["id"])})
        check("with no deadline there is no expires_in to count",
              "expires_in" not in row, row)
        G.withdraw(row["id"], "the test's pairing was cancelled")
        t.join(timeout=10)


# ---------------------------------------------------------------------------
# 3. NO BYPASS: OMISSION, 0, NEGATIVE, MALFORMED, UNKNOWN FLOW
# ---------------------------------------------------------------------------

#: Every shape a value could arrive in if it were asked to select "never
#: expire", and none of them may. The flow names are here because a wider
#: design could have taken a flow argument - this one has none, and even the
#: exact spelling of a flow is still just an unknown action name.
BAD_VALUES = (
    None, "", 0, 0.0, -1, -900, -0.0, False, True,
    "0", "-1", "1",
    "pairing", "pairing_flow", "approval_key", "approval-key",
    "backup_restore", "restore", "device-pairing", "never_expires",
    "__never_expires__", "APPROVAL_NEVER_EXPIRES",
    "PAIR_DEVICE", "Pair_Device", "pair_devices", "pair-device",
    "pair_device ", " pair_device", "pair_device\n", "pair_device\x00",
    "pair_devic", "pair_device_", "unknown", "unknown_action", "unknown_flow",
    "unclassified", "*", "%", "None",
    b"pair_device", ["pair_device"], ("pair_device",),
    {"action": "pair_device"}, {"flow": "pairing"},
)


def t_never_expires_cannot_be_reached_by_omission_zero_negative_malformed_or_unknown_flow():
    """The one door is an exact action id, so nothing else may open it.

    A design that took a "flow" argument could be handed "pairing", nothing, a
    number or a name nobody defined; this one has no such argument at all, and
    `timeout_for()` treats every non-exact value as an ordinary card. Both
    halves are checked: the signature (nothing to forge) and the behaviour
    (every bad value gets 900).
    """
    d, why = built()
    if d is None:
        return skip(why)
    G = load_module("jarvis_gate", d)

    sig = inspect.signature(G.timeout_for)
    params = list(sig.parameters.values())
    check("timeout_for takes exactly one argument: the action",
          [p.name for p in params] == ["action"], sig)
    check("...with no **kwargs, so there is no second channel to pass a flow",
          not any(p.kind == p.VAR_KEYWORD for p in params), sig)
    check("check() takes no flow/never_expires argument for a caller to set",
          not ({"flow", "never_expires", "no_expiry"} & set(
              inspect.signature(G.check).parameters)))

    for value in BAD_VALUES:
        got = G.timeout_for(value)
        label = repr(value)
        if len(label) > 40:
            label = label[:37] + "..."
        check(f"omission/bad value {label}: an ordinary 900-second card",
              got == float(MINUTES_15), got)

    # The four exact ids are the only values that open it, and even a caller's
    # own `timeout=` cannot make a routine card wait for ever: it can only
    # shorten the wait (0 or negative ends it at once, the safe direction).
    for action in NEVER_EXPIRES:
        check(f"CONTROL: the exact id {action!r} is the one exemption",
              G.timeout_for(action) is None)
    for action in NEVER_EXPIRES:
        v = G.check(action, {"why": "a test"}, prompt="a test", timeout=0)
        check(f"CONTROL: even an exempt action with timeout=0 ends at once "
              f"({action})", v.allowed is False and v.outcome == "timed_out", v)
        row = [r for r in G.history(10) if r["action"] == action]
        check(f"...and its row is expired, not left waiting ({action})",
              bool(row) and row[0]["state"] == "expired", row[:1])

    # And the three places a deadline is decided all read that one function, so
    # there is no second, laxer path to the same set.
    src = Path(G.__file__).read_text(encoding="utf-8")
    check("check() takes its wait from timeout_for",
          "waited = timeout_for(action) if timeout is None else timeout" in src)
    check("pending() takes expires_in from the same function",
          'left = timeout_for(d.get("action"))' in src)
    check("the start-up sweep exempts the same set, not a copy of it",
          "_forever = sorted(APPROVAL_NEVER_EXPIRES)" in src)


# ---------------------------------------------------------------------------
# 4. THE PATCH IS THE PUBLISHED BASE PLUS THIS ONE CHANGE
# ---------------------------------------------------------------------------

def t_the_patch_is_the_base_plus_this_change():
    """The suite's own footing, and the re-anchoring #378 made necessary.

    The rescued patch was written against the 180-second gate; it did not
    apply to main of 2026-10-13, and it does not apply to this one either. A
    patch that only applied because the base had been edited by hand would
    prove nothing, so this checks the base is untouched, that `git apply`
    accepts the patch as written, and that the result carries #378's 900.
    """
    d, why = built()
    if d is None:
        return check("no-expiry-cards.patch applies to the published base", False, why)
    check("no-expiry-cards.patch applies to the published base with git", True)
    check("...and the base has not been edited to make it fit",
          'def timeout_for(' not in text_of(BASE / "jarvis_gate.py"),
          "the base already contains the change - re-anchor the patch instead")

    before = text_of(BASE / "jarvis_gate.py")
    after = text_of(d / "jarvis_gate.py")
    check("...and the file it produces is not the file it started from",
          after != before)
    check("...and it is the whole file, not an empty one", len(after) > 100_000,
          len(after))
    try:
        compile(after, "jarvis_gate.py (patched)", "exec")
        compiles = True
    except SyntaxError as exc:
        compiles = False
        check("the patched module compiles", False, exc)
    if compiles:
        check("the patched module compiles", True)

    # Anchored on main's gate, not the 180-second text the rescue was written
    # against: the default is #378's 900, and no stale timeout literal was
    # carried in by the patch.
    check("the patched module keeps #378's 900-second default",
          '_cfg("autonomy", "approval_timeout_seconds", 900)' in after)
    added = [l[1:] for l in text_of(PATCH).splitlines()
             if l.startswith("+") and not l.startswith("+++")]
    check("no added line puts the timeout back to the old 180 or 600",
          not any(re.search(r"approval_timeout_seconds\",\s*(180|600)\b", l)
                  for l in added), [l for l in added if "180" in l or "600" in l])

    # One file, and only one: a patch that also carried a copy of a SHIPPED
    # module would be a second, silently different version of it.
    touched = set(re.findall(r"^\+\+\+ b/(.+)$", text_of(PATCH), re.M))
    check("the patch changes exactly one file - jarvis_gate.py",
          touched == {"jarvis_gate.py"}, sorted(touched))
    check("...and it does not carry jarvis_owner_check.py or jarvis_devices.py",
          not ({"jarvis_owner_check.py", "jarvis_devices.py"} & touched),
          sorted(touched))

    # The two SHIPPED modules ARE changed, as whole files, and their twins are
    # byte-identical (the rule in CLAUDE.md; this is the in-suite half).
    for name in ("jarvis_owner_check.py", "jarvis_devices.py"):
        a = (BACKEND / name).read_bytes().replace(b"\r\n", b"\n")
        b = (BASE / name).read_bytes().replace(b"\r\n", b"\n")
        check(f"{name}: backend/ and jarvis-backend/ are byte-identical", a == b)


# ---------------------------------------------------------------------------
# The supporting half: a card with no deadline is still a card
# ---------------------------------------------------------------------------

def t_a_never_card_is_still_only_the_live_card():
    """Answered, denied, and never approved without a stamp.

    Having no deadline must not weaken the three things an ordinary card
    already guarantees: an approval is believed only when THIS process stamped
    it, a denial is a denial, and a second decision changes nothing.
    """
    d, why = built()
    if d is None:
        return skip(why)
    for answer, outcome in ((True, "approved"), (False, "denied")):
        G = load_module("jarvis_gate", d)
        OC = load_module("jarvis_owner_check", d)
        box = {}
        with simulated_clock(G) as clock:
            t = ask(G, "restore_backup", box)
            row = wait_for_row(G, box)
            if row is None:
                check("the restore card was raised", False, "no row")
                continue
            clock.advance(5 * MINUTES_15)     # far past any ordinary window
            if answer:
                OC.stamp(row["id"], row["action"])
            check(f"decide({answer}) is accepted on a card with no deadline",
                  G.decide(row["id"], answer, by="the test") is True)
            t.join(timeout=10)
            v = box.get("v")
            check(f"...and the caller reads {outcome}",
                  v is not None and v.allowed is answer and v.outcome == outcome,
                  f"{v} / {box.get('error', '')}")
            check("...and a second decision on the same card changes nothing",
                  G.decide(row["id"], not answer, by="the test") is False)

    # A program that is not the backend writes "approved": still refused.
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


def t_a_never_card_can_still_be_withdrawn():
    """Cancelling a pairing has to take its card off the list.

    With no clock to run out, nothing else ever would - so `withdraw()` does,
    and the waiter it wakes is a refusal that is NOT a denial: nobody said no,
    and a denial would propose a standing rule.
    """
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
        check("withdraw takes the card off the list",
              G.withdraw(row["id"], "the pairing was cancelled") is True)
        check("...and the list is empty", G.pending() == [], G.pending())
        t.join(timeout=10)
        v = box.get("v")
        check("...and the wait ends as a refusal, not a denial",
              v is not None and v.allowed is False and v.outcome == "timed_out", v)
        check("...and its state is 'expired', as a lapse is",
              state_of(G, row["id"]) == "expired", state_of(G, row["id"]))
        check("withdrawing an id that is gone changes nothing",
              G.withdraw(row["id"], "again") is False)


def t_the_start_up_sweep_does_not_age_out_a_never_card():
    """The back door: `_init()` sweeps stale pending rows on every start-up.

    A never-expiring card older than the timeout would be expired by that
    sweep, silently undoing the whole change - so the sweep excludes exactly
    the same set. The control is a routine row of the same age, which is
    still swept.
    """
    d, why = built()
    if d is None:
        return skip(why)
    G = load_module("jarvis_gate", d)
    G.pending()                     # create the tables, run _init once
    now = time.time()
    old = now - (G.APPROVAL_TIMEOUT + 600.0)   # past timeout + the 60 s grace
    rows = (("never-1", "pair_device"), ("never-2", "restore_backup"),
            ("routine-1", "send_email"), ("unknown-1", "some_unknown_action"))
    with sqlite3.connect(str(G.DB_PATH)) as c:
        for rid, action in rows:
            c.execute("INSERT INTO approvals (id,action,tier,detail,prompt,state,"
                      "created,raised,target_digest) VALUES (?,?,?,?,?,?,?,?,?)",
                      (rid, action, "ask", "{}", "a test", "pending", old, None, None))
    G._inited = False
    G._init()
    states = {r["id"]: r["state"] for r in
              G.history(20) if r["id"] in {x[0] for x in rows}}
    check("the sweep leaves a pairing card of any age waiting",
          states.get("never-1") == "pending", states)
    check("...and a restore card too", states.get("never-2") == "pending", states)
    check("CONTROL: a routine card of the same age IS swept",
          states.get("routine-1") == "expired", states)
    check("CONTROL: an action nobody classified IS swept (nothing widened by "
          "accident)", states.get("unknown-1") == "expired", states)


def t_pending_sends_no_deadline_for_a_never_card():
    """What both apps' countdowns read.

    Absent means "no countdown" to the phone and the desktop. 0 would have
    meant "expired now" to both - they would have refused a card that is still
    answerable - and the timeout would have drawn a countdown that ends in a
    refusal that never comes.
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
            return check("the pairing card was raised", False, "no row")
        check("no expires_in on a card with no deadline", "expires_in" not in row, row)
        check("...and its notice is still there, so the card still has words",
              bool(row.get("notice", {}).get("title")), row)
        G.decide(row["id"], False, by="the test")
        t.join(timeout=5)

    # A module of its own for the routine half: one process shares one
    # approvals.db, and the first card's read connection would otherwise be
    # asked about the second card's row.
    G2 = load_module("jarvis_gate", d)
    box2 = {}
    with simulated_clock(G2):
        t2 = ask(G2, "send_email", box2)
        row2 = wait_for_row(G2, box2)
        if row2 is None:
            return check("the routine card was raised", False, "no row")
        check("CONTROL: a routine card still carries its whole window",
              row2.get("expires_in") in (MINUTES_15, MINUTES_15 - 1),
              row2.get("expires_in"))
        G2.decide(row2["id"], False, by="the test")
        t2.join(timeout=5)


def t_owner_check_does_not_refuse_a_card_with_no_deadline():
    """The Windows Hello half, on its own, through the seam that module has.

    `jarvis_owner_check._time_left` used to read an absent `expires_in` as
    "900 seconds left" and then, once those seconds were up, answer 409 GONE
    for a card the gate was still waiting on. With no verifier this suite asks
    the decision path directly: no deadline must reach the verifier, not a
    refusal.
    """
    d, why = built()
    if d is None:
        return skip(why)
    OC = load_module("jarvis_owner_check", d)
    check("the shipped default is still 900, not the old 180",
          OC.DEFAULT_TIME_LEFT == float(MINUTES_15), OC.DEFAULT_TIME_LEFT)
    check("a row with no field whose action has no deadline reads None",
          OC._time_left({"action": "pair_device"}) is None,
          OC._time_left({"action": "pair_device"}))
    check("a row with no field whose action IS routine still reads 900",
          OC._time_left({"action": "send_email"}) == float(MINUTES_15),
          OC._time_left({"action": "send_email"}))
    check("an unknown action is NOT given a deadline of its own",
          OC._time_left({"action": "some_unknown_action"}) == float(MINUTES_15))

    row = {"id": "r1", "action": "pair_device", "tier": "ask",
           "detail": {"text": "words"}, "prompt": "connect a new device",
           "notice": {"title": "Jarvis wants to connect a new device",
                      "body": "check the words"},
           "risk": {"reversible": "yes", "reach": "local", "why": "a test",
                    "swipe_ok": True, "classified": True}}
    asked = []
    OC.set_verifier(lambda message, timeout: asked.append(timeout) or OC.CONFIRMED)
    try:
        out = OC.approve_check({"id": "r1"}, peer="127.0.0.1", local="127.0.0.1",
                               own=lambda: frozenset({"127.0.0.1"}),
                               pending=lambda: [row])
        check("a deliberate card with no deadline is not refused", out is None, out)
        check("...and Windows Hello was actually asked", asked != [], asked)
        # 2026-10-26: the prompt is capped at 180 s, because its own deadline
        # is its only cancel - a no-deadline card therefore reaches the prompt
        # with the cap, not the shipped 900. The card itself is not used up: it
        # keeps waiting, and Approve can be pressed again.
        check("...with a bounded prompt (the 180 s cap), never 'for ever'",
              asked == [OC._PROMPT_MAX] and OC._PROMPT_MAX == 180.0, asked)

        # The row's OWN number wins over the allow-list: an exempt action that
        # somehow carries a deadline (an old row, a foreign backend) is still
        # refused once it has run out. The allow-list narrows what the GATE
        # emits; it cannot make a stated deadline disappear.
        gone = dict(row, expires_in=0)
        out2 = OC.approve_check({"id": "r1"}, peer="127.0.0.1", local="127.0.0.1",
                                own=lambda: frozenset({"127.0.0.1"}),
                                pending=lambda: [gone])
        check("CONTROL: a row carrying 0 seconds left is still refused, "
              "exempt action or not",
              out2 is not None and out2[0] == 409
              and out2[1].get("owner_check") == "gone", out2)

        # ...and a row carrying a REAL deadline is asked with that number, not
        # silently replaced by the shipped one.
        asked.clear()
        soon = dict(row, expires_in=5)
        out4 = OC.approve_check({"id": "r1"}, peer="127.0.0.1", local="127.0.0.1",
                                own=lambda: frozenset({"127.0.0.1"}),
                                pending=lambda: [soon])
        check("...and a row with 5 seconds left reaches the prompt with 5",
              out4 is None and asked == [5.0], (out4, asked))

        answers = [row, None]
        out3 = OC.approve_check(
            {"id": "r1"}, peer="127.0.0.1", local="127.0.0.1",
            own=lambda: frozenset({"127.0.0.1"}),
            pending=lambda: [answers.pop(0)] if answers[0] else [])
        check("...and a card that is no longer the live one after the prompt "
              "is refused", out3 is not None and out3[0] == 409
              and out3[1].get("owner_check") == "gone", out3)
    finally:
        OC.set_verifier(None)


# ---------------------------------------------------------------------------
# B-1 / B-2: the pairing card's life, and a duplicate approval-key retry
# ---------------------------------------------------------------------------
#
# These replace a source-text pin ("_take_off(...)" appears in _decide). The
# pin could not fail for the reason that matters: it passed while the wrong id
# was withdrawn and while a cancelled session's card stayed on the list for
# ever (audit B-1). What follows drives the real pairing code against the real
# patched gate and asks the gate itself what is pending.

#: A mesh address that is not this PC. `own` is passed explicitly everywhere,
#: so nothing here has to know the build machine's own addresses.
PEER_MESH = "100.101.2.3"


def ask_tier(_action):
    return "ask"


def _devices_and_gate():
    """(gate module, devices module, the folder, why not). Fresh modules.

    The gate is the one `built()` makes - the published base with
    no-expiry-cards.patch applied - and `jarvis_devices.py` is this
    repository's own copy. So what runs is the real `cancel()`/`_tick()`/
    `register_key()` calling the real `jarvis_gate.check()`, not stand-ins for
    either.
    """
    d, why = built()
    if d is None:
        return None, None, None, why
    G = load_module("jarvis_gate", d)
    D = load_module("jarvis_devices", d)
    D._reset_for_tests()
    return G, D, d, ""


def card_of(gate, action: str, seconds: float = 10.0):
    """The pending card for `action`, as /api/pending would show it, or None."""
    end = time.time() + seconds
    while time.time() < end:
        for row in gate.pending():
            if row.get("action") == action:
                return row
        time.sleep(0.02)
    return None


def card_gone(gate, rid: str, seconds: float = 10.0) -> bool:
    """True once `rid` is no longer among the waiting cards."""
    end = time.time() + seconds
    while time.time() < end:
        if not any(row.get("id") == rid for row in gate.pending()):
            return True
        time.sleep(0.02)
    return False


class Pairing:
    """One real QR pairing, driven by hand, with the clock under the test.

    `jarvis_devices._now` is the clock `SESSION_SECONDS` is measured on (both
    `_tick` and `_decide` read it), so moving it is exactly what the ten-minute
    window sees - no sleeping for ten minutes.
    """

    def __init__(self, G, D):
        self.G, self.D = G, D
        self.now = 1_000_000.0
        self._real_now = D._now
        D._now = lambda: self.now
        self.code, self.out = D.start({"address": "jarvis-pc.tail1234.ts.net", "port": 4719},
                                      here=True, tier_of=ask_tier, armed=lambda: True)
        if self.code != 200:
            raise RuntimeError(f"start refused: {self.out}")
        q = D.parse_qr(self.out["qr"])
        nonce = D._b64u(bytes(range(16)))
        self.k, self.nonce = q["secret"], nonce
        t = D.transcript("qr", q["pair_id"], nonce, "Pixel 9")
        self.body = {"method": "qr", "pair_id": q["pair_id"], "phone_nonce": nonce,
                     "name": "Pixel 9", "proof": D.claim_proof(self.k, t)}

    def claim(self):
        code, ans = self.D.claim(self.body, peer=PEER_MESH, own=lambda: frozenset(),
                                 gate=self.G.check, tier_of=ask_tier, spawn=self.D._spawn)
        if code != 202:
            raise RuntimeError(f"claim refused: {ans}")
        return card_of(self.G, self.D.ACTION)

    def advance(self, seconds):
        self.now += seconds

    def close(self):
        """Leave no blocked waiter behind for the next test."""
        try:
            self.D.cancel(here=True)
        except Exception:
            pass
        for row in self.G.pending():
            try:
                self.G.decide(row["id"], False, by="the test")
            except Exception:
                pass
        self.D._now = self._real_now


def t_a_cancelled_pairing_takes_its_card_off_the_list():
    """BUG B-1, first trigger: Cancel ends the session while the card waits.

    `_decide` is blocked inside check(), and a pair_device card has no deadline,
    so before this fix the row stayed on /api/pending for ever - on both apps,
    across backend restarts - and a later Approve ran Windows Hello, was
    recorded as approved, and minted nothing.
    """
    G, D, d, why = _devices_and_gate()
    if G is None:
        return skip(why)
    P = Pairing(G, D)
    try:
        card = P.claim()
        check("the pairing card is waiting while the phone waits",
              card is not None and card["action"] == D.ACTION, card)
        if card is None:
            return
        code, out = D.cancel(here=True)
        check("Cancel ends the session", code == 200 and out["was"] == "waiting_for_card", out)
        check("...and its card leaves /api/pending", card_gone(G, card["id"]))
        check("...and a late Approve is refused, never reported as a success",
              G.decide(card["id"], True, by="the test") is False)
        check("...so no device was made by that Approve",
              not D.registry_path().exists())
    finally:
        P.close()


def t_an_expired_pairing_takes_its_card_off_the_list():
    """BUG B-1, second trigger: the SESSION expires at 600 s; the card did not.

    The session's own ten minutes still run out even though the card never
    does. When they do, the card must go with the session: otherwise the owner
    presses Approve on a card whose session is dead, /api/approve answers 200
    approved, and no key is minted and no device exists.
    """
    G, D, d, why = _devices_and_gate()
    if G is None:
        return skip(why)
    P = Pairing(G, D)
    try:
        card = P.claim()
        check("the pairing card is waiting while the session is live", card is not None)
        if card is None:
            return
        P.advance(D.SESSION_SECONDS + 1)
        code, view = D.session_view(here=True)     # this is what runs _tick()
        check("the 600 seconds end the session", view["state"] == "expired", view)
        check("...and the card leaves /api/pending with it", card_gone(G, card["id"]))
        check("...and a late Approve is refused, never reported as a success",
              G.decide(card["id"], True, by="the test") is False)
        code, ans = D.collect({"pair_id": P.out["pair_id"],
                               "proof": D.collect_proof(P.k, P.out["pair_id"], P.nonce)},
                              peer=PEER_MESH, own=lambda: frozenset())
        check("...and collect says expired, so the phone is told the truth",
              code == 410 and ans["state"] == "expired", ans)
        check("...and no device exists", not D.registry_path().exists())
    finally:
        P.close()


def t_a_duplicate_approval_key_retry_keeps_the_one_card():
    """BUG B-2: a retry of the SAME public key must not orphan the waiter.

    The gate raises ONE card for one identical request. The old code replaced
    `_AK[you]` before that card existed, so the retry's waiter met the
    "already waiting" refusal next to its own id, deleted the slot, and the
    original waiter then found the slot gone when the owner approved the card:
    the Windows Hello yes was discarded and no key was stored.
    """
    G, D, d, why = _devices_and_gate()
    if G is None:
        return skip(why)
    crypto = D._crypto()
    if crypto is None:
        return skip("cryptography is not installed, so no key can be parsed")
    # Loaded BEFORE anything writes the device registry: `load_module` installs
    # a fresh `jarvis_framework`, and `jarvis_devices._config_dir()` reads that
    # module's CONFIG_DIR at call time - loading it after a registry write
    # would move the registry out from under the flow under test.
    OC = load_module("jarvis_owner_check", d)
    D._reset_for_tests()
    try:
        device_id, _token = D._mint("Pixel 9")
        der = crypto.ec.generate_private_key(crypto.ec.SECP256R1()).public_key().public_bytes(
            crypto.serialization.Encoding.DER,
            crypto.serialization.PublicFormat.SubjectPublicKeyInfo)
        text = D._b64u(der)
        spki, problem = D.parse_public_key(text)
        if spki is None:
            return skip(f"the generated key was not accepted: {problem}")

        def register():
            return D.register_key({"public_key": text}, you=device_id, gate=G.check,
                                  tier_of=ask_tier, spawn=D._spawn, armed=lambda: True)

        code, first = register()
        card = card_of(G, D.KEY_ACTION)
        check("the first registration is 202 waiting",
              code == 202 and first == {"waiting": True} and card is not None, first)
        if card is None:
            return
        slot = D._AK.get(device_id)
        check("the first request owns the waiting slot", slot is not None)

        code2, second = register()          # the retry, same key
        check("the retry is answered 202 waiting too (that card covers it)",
              code2 == 202 and second == {"waiting": True}, second)
        check("...and it did NOT replace the waiting slot", D._AK.get(device_id) == slot,
              (slot, D._AK.get(device_id)))
        rows = [r for r in G.pending() if r.get("action") == D.KEY_ACTION]
        check("...and there is still exactly one card", len(rows) == 1, rows)
        # The gate believes an approval only when THIS process stamped it -
        # i.e. when it came through POST /api/approve on the PC after Windows
        # Hello. A test that just wrote `approved` into the row would be
        # refused as unstamped (and rightly), so the stamp is taken here the
        # way the approve route takes it.
        OC.stamp(card["id"], D.KEY_ACTION)
        check("the owner's single yes is accepted once",
              G.decide(card["id"], True, by="the test") is True)
        end = time.time() + 10
        stored = None
        while time.time() < end:
            stored = D.approval_key_of(device_id)
            if stored:
                break
            time.sleep(0.02)
        check("...and THAT approval stored the key - the yes was not discarded",
              stored == spki, stored)
    finally:
        for row in G.pending():
            try:
                G.decide(row["id"], False, by="the test")
            except Exception:
                pass
        D._reset_for_tests()


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def text_of(path: Path) -> str:
    return path.read_text(encoding="utf-8")


if __name__ == "__main__":
    for fn in (t_the_patch_is_the_base_plus_this_change,
               t_an_ordinary_session_still_expires_after_fifteen_minutes,
               t_only_pairing_approval_key_and_restore_may_never_expire,
               t_never_expires_cannot_be_reached_by_omission_zero_negative_malformed_or_unknown_flow,
               t_a_never_card_is_still_only_the_live_card,
               t_a_never_card_can_still_be_withdrawn,
               t_the_start_up_sweep_does_not_age_out_a_never_card,
               t_pending_sends_no_deadline_for_a_never_card,
               t_owner_check_does_not_refuse_a_card_with_no_deadline,
               t_a_cancelled_pairing_takes_its_card_off_the_list,
               t_an_expired_pairing_takes_its_card_off_the_list,
               t_a_duplicate_approval_key_retry_keeps_the_one_card):
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
