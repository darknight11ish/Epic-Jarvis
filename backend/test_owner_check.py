"""test_owner_check.py - the approval gap, step 1 (docs/APPROVAL-GAP-DESIGN.md).

    python3 backend/test_owner_check.py

The owner's decisions of 2026-09-25 (CLAUDE.md): the PC's backend asks
Windows Hello itself before it accepts a RISKY approval that comes from the
PC, stamps every approval it accepts so "approved" written straight into
approvals.db does not count, and refuses a risky approval on a PC with no
Windows Hello ("no lock, no risky approval").

What is proved here, with no Windows and no owner's files:

  * the risky rule, and the prompt's words, against the shared cases the
    desktop and the phone are tested with (tools/gen_risky_approval_cases.py);
  * telling this PC from another device by the connection;
  * the stamp: once, per card and action, and never for a row nobody stamped;
  * POST /api/approve's check, with a stand-in for Windows Hello: every
    outcome, a card that stopped waiting while the prompt was open, a phone
    approval, a card that is not risky, and Deny never held;
  * the prompt cannot outlive its card (2026-10-26): a card with no written
    words is refused before the prompt, the prompt's seconds are re-read
    after the one-at-a-time wait and capped at three minutes, a card that is
    withdrawn or expires WHILE the prompt is up closes it within a quarter of
    a second (the watcher), a request that never gets its turn is refused
    rather than waiting for ever, and a clean backend shutdown asks a live
    prompt to close;
  * the `--hello` child refuses an empty stdin line (the cardless 900 s prompt
    the old code allowed) and clamps any timeout it is given to the cap;
  * the wrapper round the server's POST handler, on a fake handler;
  * owner-check.patch in the whole stack's stand-in (backend/_stack.py): the
    gate's two "approved" branches ask for the stamp, the helpers lifted and
    run, and the server wraps its handler before anything listens;
  * /api/version's capabilities.owner_check;
  * the Windows side's arithmetic (the interface id) and that it fails
    closed off Windows.

The end-to-end check - a real gate, a real approvals.db, a row set to
"approved" by hand and refused - runs on the owner's PC, in
test_gate_outcome.py (it needs the owner's jarvis_gate.py).
"""
from __future__ import annotations

import ast
import importlib
import io
import json
import re
import subprocess
import sys
import threading
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_owner_check.py", "rebuilt/jarvis_events.py")

import jarvis_owner_check as OC  # noqa: E402
import _stack  # noqa: E402

PASSED, FAILED = [], []
SKIPPED = []
CASES = REPO / "jarvis-desktop" / "tests" / "fixtures" / "risky-approval-cases.json"
RULES_RS = REPO / "jarvis-desktop" / "src-tauri" / "src" / "lock" / "rules.rs"
SECURITY_KT = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis"
               / "client" / "data" / "Security.kt")


def _block(src, marker):
    """The block `marker` opens, delimited by INDENTATION, not by a count.

    `call = text[i:i + 200]` counted characters from the install call and
    hoped the three guards were inside the next 200 of them - a promise about
    how long the call stays, which has to be re-measured by hand whenever it
    grows (2026-10-03). The call ends where the indentation comes back to its
    own level.

    The text here is a fragment of jarvis_hud.py assembled by the patch stack,
    so it is not a parseable module and ast cannot be used on it; indentation
    is the structure that is available, and unlike a character count it is the
    same structure the Python parser reads.
    """
    at = src.find(marker)
    if at < 0:
        return ""
    start = src.rfind("\n", 0, at) + 1
    head = src[start:at]
    indent = len(head) - len(head.lstrip())
    lines = src[start:].split("\n")
    out = [lines[0]]
    for line in lines[1:]:
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        out.append(line)
    return "\n".join(out)


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass. (It used to be check("(on Windows the real check runs;
    skipped)", True) - a condition of the constant True, so it printed as a
    pass and was counted as one.)"""
    SKIPPED.append(why)
    print(f"skip  {why}")


def _case_rows() -> dict:
    return {c["name"]: c for c in json.loads(CASES.read_text(encoding="utf-8"))["cases"]}


def _risky_row(rid="r1", expires_in=150, action=None):
    """A risky row with WRITTEN words (app_merge_change is in the card words).

    The old version used the "not in the gate's table" fixture row, which is
    exactly the action with no written words - so it is now the UNLABELLED
    case, `_unlabelled_row` below, and must not be used where a prompt is
    expected (2026-10-26)."""
    row = dict(_case_rows()["adding a change to an app: stays on this PC, no Undo yet - risky"]["row"])
    row["id"] = rid
    row["expires_in"] = expires_in
    if action is not None:
        row["action"] = action
    return row


def _unlabelled_row(rid="u1", expires_in=150):
    """The fixture row the review quoted: an action nobody wrote words for."""
    row = dict(_case_rows()["not in the gate's table: unclassified"]["row"])
    row["id"] = rid
    row["expires_in"] = expires_in
    return row


def _safe_row(rid="s1"):
    row = dict(_case_rows()["stays on this PC and can be undone"]["row"])
    row["id"] = rid
    return row


class Verifier:
    """A stand-in for Windows Hello: answers `outcome`, and remembers what
    the prompt said."""

    def __init__(self, outcome="confirmed", then=None):
        self.outcome, self.then, self.asked = outcome, then, []

    def __call__(self, message, timeout):
        self.asked.append((message, timeout))
        if self.then:
            self.then()
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class FakeChild:
    """A stand-in for the Windows Hello child PROCESS: it records what the
    backend writes to its stdin, and finishes when its pipe is closed.

    This is how the shutdown hook is proved without raising a real prompt:
    `jarvis_owner_check._SPAWN` is replaced with one of these, so no process
    starts and no dialog can appear. Its stdin is itself, like a file."""

    def __init__(self, answer="cancelled"):
        self.written = []
        self.closed = False
        self.returncode = None
        self.answered = threading.Event()
        self.stdout = io.StringIO(json.dumps({"outcome": answer}) + "\n")
        self.stdin = self

    def write(self, text):
        self.written.append(text)
        return len(text)

    def flush(self):
        pass

    def close(self):
        self.closed = True
        self.answered.set()

    def wait(self, timeout=None):
        if not self.answered.wait(timeout):
            raise subprocess.TimeoutExpired("jarvis_owner_check.py --hello", timeout)
        self.returncode = 0
        return 0


def _fresh_stamps():
    with OC._STAMPS_LOCK:
        OC._STAMPS.clear()


# ------------------------------------------------------------ the rule --

def t_the_shared_cases_are_what_the_backend_says_today():
    r = subprocess.run([sys.executable, str(REPO / "tools" / "gen_risky_approval_cases.py"),
                        "--check"], capture_output=True, text=True)
    check("risky-approval-cases.json (the desktop's and the phone's copy) equals a fresh run",
          r.returncode == 0, r.stdout + r.stderr)
    cases = _case_rows()
    check("there are cases on both sides of the rule",
          any(c["risky"] for c in cases.values()) and any(not c["risky"] for c in cases.values()))
    for c in cases.values():
        if OC.is_risky(c["row"]) != c["risky"] or OC.approval_message(c["row"]) != c["message"]:
            check(f"case {c['name']!r}", False, c)


def t_the_rule_is_the_phones():
    check("local and undoable is not risky", not OC.is_risky(_safe_row()))
    check("a row that is not a dict is risky", OC.is_risky(None) and OC.is_risky("x"))
    row = _safe_row()
    for raised in (True, {"code": "rushed"}, '{"code":"rushed"}', "anything", 0, []):
        row["raised"] = raised
        if not OC.is_risky(row):
            check(f"raised={raised!r} is risky (toward caution, as the desktop reads it)", False)
    for raised in (None, False):
        row["raised"] = raised
        check(f"raised={raised!r} is not raised", not OC.is_risky(row))
    row = _safe_row()
    row["risk"] = dict(row["risk"], reach=None)
    check("a reach that is not text is outbound", OC.is_risky(row))


def t_the_prompt_names_the_card_never_the_payload():
    row = _risky_row()
    row["detail"] = '{"to": "someone@example.com", "body": "SECRET WORDS"}'
    row["prompt"] = "SECRET WORDS"
    said = OC.approval_message(row)
    check("it starts with the card's own title",
          said.startswith(row["notice"]["title"] + "\n"), said)
    check("and never quotes the detail or the prompt",
          "SECRET" not in said and "example.com" not in said, said)
    check("at most 300 characters", len(OC.approval_message({"notice": {"title": "x" * 999}})) == 300)


# ---------------------------------------------------- this PC, or not --

def t_this_pc_is_told_from_another_device_by_the_connection():
    own = ("100.64.0.5", "192.168.1.20")
    yes = [("127.0.0.1", None), ("::1", None), ("::ffff:127.0.0.1", None),
           ("100.64.0.5", "100.64.0.5"),        # the PC calling its own Tailscale address
           ("192.168.1.20", "100.64.0.5"),      # one of the PC's own addresses
           (None, None)]                        # no request to place: in-process
    # FAIL CLOSED (SECPRIV audit N8, 2026-10-18): a NETWORK peer that cannot
    # be placed is NOT this PC. None is the documented in-process convention
    # (a direct call with no network request behind it), not a peer string.
    no = [("100.101.102.103", "100.64.0.5"),    # the phone over Tailscale
          ("192.168.1.44", "192.168.1.20"),     # another device at home
          ("fe80::1%eth0", "fe80::2%eth0"),
          ("", None), ("not an address", None),  # unparsable network peers
          ("0.0.0.0", None)]                    # the unspecified address
    wrong = []
    for peer, local in yes:
        if not OC.from_this_pc(peer, local, own=own):
            wrong.append(f"{peer!r} -> {local!r} should count as this PC")
            check(f"{peer!r} -> {local!r} counts as this PC", False)
    for peer, local in no:
        if OC.from_this_pc(peer, local, own=own):
            wrong.append(f"{peer!r} -> {local!r} should count as another device")
            check(f"{peer!r} -> {local!r} counts as another device", False)
    # Was `check("the rule, all cases", True)`: the condition was the constant
    # True, so it printed ok even on a run where one of the cases above had
    # just printed FAIL - a summary that could not fail. It now asserts the
    # same thing the per-case reports say, so the two cannot disagree.
    check("the rule, all cases", not wrong, "; ".join(wrong))
    check("this PC's own addresses are read without raising",
          isinstance(OC.own_addresses(), frozenset))


# ------------------------------------------------------------ the stamp --

def t_a_stamp_counts_once_for_its_own_card_and_action():
    _fresh_stamps()
    check("nothing stamped: no approval", OC.take_stamp("appr_1", "send_email") is False)
    OC.stamp("appr_1", "send_email")
    check("another action does not match", OC.take_stamp("appr_1", "run_shell_on_host") is False)
    OC.stamp("appr_1", "send_email")
    check("the stamped card and action: yes", OC.take_stamp("appr_1", "send_email") is True)
    check("and only once", OC.take_stamp("appr_1", "send_email") is False)
    OC.stamp(12, "x")
    check("an id that is a number matches its text", OC.take_stamp("12", "x") is True)


def t_a_stamp_from_another_run_is_worth_nothing():
    """A new start makes a new secret: what an old process stamped - or what
    any other program computed - does not match."""
    _fresh_stamps()
    OC.stamp("appr_2", "send_email")
    kept = dict(OC._STAMPS)
    old_secret = OC._SECRET
    OC._SECRET = b"\x00" * 32
    try:
        with OC._STAMPS_LOCK:
            OC._STAMPS.update(kept)
        check("a stamp made with another secret is refused",
              OC.take_stamp("appr_2", "send_email") is False)
    finally:
        OC._SECRET = old_secret
    check("the secret is 32 random bytes, made at import", len(OC._SECRET) == 32)
    src = (HERE / "jarvis_owner_check.py").read_text(encoding="utf-8")
    check("and it is never written anywhere",
          not re.search(r"_SECRET[^\n]*(write|open|dump|print)", src))


def t_old_stamps_are_dropped_and_the_table_is_bounded():
    _fresh_stamps()
    for i in range(OC._MAX_STAMPS + 20):
        OC.stamp(f"a{i}", "x")
    check("at most _MAX_STAMPS are kept", len(OC._STAMPS) == OC._MAX_STAMPS)
    check("the oldest went first", OC.take_stamp("a0", "x") is False
          and OC.take_stamp(f"a{OC._MAX_STAMPS + 19}", "x") is True)
    _fresh_stamps()
    OC.stamp("old", "x")
    with OC._STAMPS_LOCK:
        mac, _ = OC._STAMPS["old"]
        OC._STAMPS["old"] = (mac, time.monotonic() - OC._STAMP_TTL - 1)
    check("a stamp older than any card waits is refused", OC.take_stamp("old", "x") is False)


# ------------------------------------------------------ /api/approve --

def _run(body, rows, verifier, peer="127.0.0.1", local="127.0.0.1"):
    _fresh_stamps()
    OC.set_verifier(verifier)
    try:
        return OC.approve_check(body, peer=peer, local=local, pending=rows, own=())
    finally:
        OC.set_verifier(None)


def t_a_risky_approval_from_this_pc_asks_windows_hello_first():
    row = _risky_row("r1")
    v = Verifier("confirmed")
    got = _run({"id": "r1"}, lambda: [row], v)
    check("confirmed: the owner's handler goes ahead", got is None, got)
    check("one prompt, with the card's title and why",
          len(v.asked) == 1 and v.asked[0][0] == OC.approval_message(row), v.asked)
    check("the prompt may stay up for the card's time left", v.asked and v.asked[0][1] == 150)
    check("and the approval is stamped", OC.take_stamp("r1", row["action"]))


def t_no_windows_hello_no_risky_approval():
    row = _risky_row("r2")
    got = _run({"id": "r2"}, lambda: [row], Verifier("unavailable"))
    check("refused with 403", got is not None and got[0] == 403, got)
    check("with the sentence that says how to set it up",
          got and got[1]["error"] == OC.NOT_SET_UP and "Sign-in options" in got[1]["error"], got)
    check("nothing stamped", not OC.take_stamp("r2", row["action"]))


def t_every_other_outcome_refuses_too():
    row = _risky_row("r3")
    for outcome, want in (("cancelled", OC.CANCELLED), ("failed", OC.FAILED),
                          ("nonsense", OC.FAILED), (RuntimeError("boom"), OC.FAILED)):
        got = _run({"id": "r3"}, lambda: [row], Verifier(outcome))
        check(f"{outcome!r}: 403, said plainly, nothing stamped",
              got and got[0] == 403 and got[1]["error"] == want
              and not OC.take_stamp("r3", row["action"]), got)


def t_off_windows_there_is_no_windows_hello_so_it_fails_closed():
    """Off Windows there is no Windows Hello, so the REAL path (no stand-in)
    refuses. On Windows this test must not reach that path: it would raise a
    real Windows Hello dialog, and no test may do that.

    The old order called `approve_check` FIRST and only then skipped on
    Windows - so on the owner's PC the suite did exactly that, and the test
    that was reported as "runs no real prompt" ran the real child (found
    2026-10-26 while timing this suite: it sat for the card's full 150 s in
    two runs). The skip now comes before the call."""
    if sys.platform == "win32":
        skip("off Windows there is no Windows Hello so a risky approval fails closed: on "
             "Windows the real check would raise a real prompt, so this test does not run it. "
             "It did NOT run, and it did NOT pass.")
        return
    row = _risky_row("r4")
    _fresh_stamps()
    OC.set_verifier(None)
    got = OC.approve_check({"id": "r4"}, peer="127.0.0.1", pending=lambda: [row], own=())
    check("no stand-in, not Windows: refused as not set up",
          got and got[0] == 403 and got[1]["owner_check"] == "not_set_up", got)


def t_a_card_that_stopped_waiting_while_the_prompt_was_open_is_refused():
    row = _risky_row("r5")
    state = {"rows": [row]}

    def deny_meanwhile():
        state["rows"] = []                 # denied on the phone, or timed out
    got = _run({"id": "r5"}, lambda: list(state["rows"]), Verifier("confirmed", then=deny_meanwhile))
    check("gone meanwhile: 409, which both apps read as no longer waiting",
          got and got[0] == 409 and got[1]["error"] == OC.GONE, got)
    check("nothing stamped", not OC.take_stamp("r5", row["action"]))
    check("and the sentence says neither 'already' nor anything the apps misread",
          "already" not in OC.GONE.lower())

    expired = _risky_row("r6", expires_in=150)

    def run_out():
        expired["expires_in"] = 0
    got = _run({"id": "r6"}, lambda: [expired], Verifier("confirmed", then=run_out))
    check("ran out of time meanwhile: 409", got and got[0] == 409, got)


def t_one_prompt_at_a_time():
    row_a, row_b = _risky_row("ra"), _risky_row("rb", expires_in=0.3)
    started, release = threading.Event(), threading.Event()

    def slow(message, timeout):
        started.set()
        release.wait(5)
        return "confirmed"
    OC.set_verifier(slow)
    box = {}
    t = threading.Thread(target=lambda: box.setdefault(
        "a", OC.approve_check({"id": "ra"}, peer="127.0.0.1", pending=lambda: [row_a, row_b], own=())))
    t.start()
    started.wait(5)
    try:
        got = OC.approve_check({"id": "rb"}, peer="127.0.0.1", pending=lambda: [row_a, row_b], own=())
        check("a second card waits for the first prompt, and is refused when its time runs out",
              got and got[0] == 409, got)
    finally:
        release.set()
        t.join(5)
        OC.set_verifier(None)
    check("the first one went through", box.get("a") is None, box)


# --------------------------------------- a prompt that cannot outlive its card --
#
# Measured 2026-10-26 (.dsh-scratch/WINDOWS-HELLO-2026-10-26/FINDINGS.md): the
# seconds were read BEFORE the one-prompt-at-a-time wait, so a queued card
# could be given its full 900 s even with 2 s left, and nothing asked a live
# prompt to close when the backend stopped. These tests use the fake verifier
# and a fake child process; no real Windows Hello dialog is raised.


def _hold_the_prompt(rows, rid):
    """Open a prompt that holds the one-at-a-time lock, and hand back the
    controls to end it: (release, thread, box).

    `started` is set from inside the stand-in, so the caller knows the first
    prompt is really open - and therefore holding the lock - before it sends
    the next card."""
    started, release = threading.Event(), threading.Event()

    def slow(message, timeout):
        started.set()
        release.wait(10)
        return "confirmed"

    OC.set_verifier(slow)
    box = {}
    t = threading.Thread(target=lambda: box.setdefault(
        "out", OC.approve_check({"id": rid}, peer="127.0.0.1",
                                pending=lambda: list(rows), own=())))
    t.start()
    started.wait(10)
    return release, t, box


def _watched_prompt(rows, rid):
    """Open a prompt through the REAL child path (`_verify_windows`) on a
    FAKE child process, so the watcher's cancel travels the route a real
    prompt's would, and hand back (fake child, thread, box, real spawn).

    `_SPAWN` is replaced before the prompt starts, so no process is started
    and no dialog can appear. The fake child does not answer until its pipe is
    closed, which is what a real child waiting for an answer does."""
    _fresh_stamps()
    fake = FakeChild("cancelled")
    real_spawn = OC._SPAWN
    OC._SPAWN = lambda *a, **k: fake
    OC.set_verifier(OC._verify_windows)
    box = {}
    thread = threading.Thread(target=lambda: box.setdefault(
        "out", OC.approve_check({"id": rid}, peer="127.0.0.1",
                                pending=lambda: list(rows), own=())))
    thread.start()
    for _ in range(500):
        with OC._LIVE_LOCK:
            live = len(OC._LIVE_PROMPTS)
        if live and fake.written:
            break
        time.sleep(0.01)
    return fake, thread, box, real_spawn


def _watch_prompt_then(change, rid, row):
    """Open that fake-child prompt on `row`, make `change(rows, row)` happen
    under it, and report (seconds until it ended, answer, what the child was
    written, alive).

    `written` is snapshotted BEFORE the cleanup cancels anything, so the
    "the watcher told the child" check cannot be satisfied by the cleanup."""
    rows = [row]
    fake, thread, box, real_spawn = _watched_prompt(rows, rid)
    started = time.monotonic()
    written = []
    try:
        change(rows, row)
        thread.join(5)
        written = list(fake.written)
    finally:
        rows.clear()
        OC._cancel_live_prompts()          # a regression must not leave one up
        thread.join(5)
        OC._SPAWN = real_spawn
        OC.set_verifier(None)
        with OC._LIVE_LOCK:
            OC._LIVE_PROMPTS.clear()
    return time.monotonic() - started, box.get("out"), written, thread.is_alive()


def t_only_an_action_with_written_words_may_prompt():
    """The fixture row the review quoted - an action nobody wrote words for -
    is refused BEFORE the verifier is called. The actions that DO have words
    still prompt, so this is a guard, not a blanket refusal (2026-10-26)."""
    row = _unlabelled_row("u1")
    v = Verifier(RuntimeError("no prompt may be shown"))
    got = _run({"id": "u1"}, lambda: [row], v)
    check("unlabelled: 403 with its own owner_check",
          got is not None and got[0] == 403 and got[1]["owner_check"] == "unlabelled", got)
    check("the sentence is plain and says nothing was approved",
          got is not None and got[1]["error"] == OC.UNLABELLED
          and "written words" in OC.UNLABELLED
          and "Nothing was approved" in OC.UNLABELLED, got)
    check("the verifier was never called", not v.asked, v.asked)
    check("nothing stamped", not OC.take_stamp("u1", row["action"]))

    for action in ("app_merge_change", "unclassified_tool", "send_email"):
        row = _risky_row(f"c_{action}", action=action)
        v = Verifier("confirmed")
        got = _run({"id": row["id"]}, lambda: [row], v)
        check(f"{action} has written words and still prompts",
              got is None and len(v.asked) == 1, (action, got, v.asked))

    # The guard belongs to THIS PC's prompt. A phone approval checks its own
    # fingerprint and is untouched, which is the documented split (the phone
    # is not changed by this fix).
    row = _unlabelled_row("u2")
    v = Verifier(RuntimeError("no prompt on the PC for another device"))
    got = _run({"id": "u2"}, lambda: [row], v, peer="100.101.102.103", local="100.64.0.5")
    check("a card from another device is not this guard's business",
          got is None and not v.asked, got)


def t_a_queued_prompt_gets_the_time_its_card_has_left_now():
    """The measured defect: the card had 2 s left by its turn, but the
    seconds had been read before the wait, so the prompt got 900."""
    first = _risky_row("q1", expires_in=900)
    queued = _risky_row("q2", expires_in=900)
    release, t, box = _hold_the_prompt([first, queued], "q1")
    v2 = Verifier("confirmed")
    timer = threading.Timer(0.5, release.set)
    try:
        queued["expires_in"] = 2       # what a fresh /api/pending read says now
        timer.start()
        got = _run({"id": "q2"}, lambda: [first, queued], v2)
    finally:
        release.set()
        timer.cancel()
        t.join(10)
        OC.set_verifier(None)
    check("the queued prompt opens and the card is approved", got is None, got)
    check("with the 2 s the card has NOW, not the 900 s it joined the queue with",
          bool(v2.asked) and v2.asked[0][1] == 2, v2.asked)
    check("the first prompt went through", box.get("out") is None, box)


def t_a_card_that_ran_out_while_it_waited_gets_409_and_no_prompt():
    first = _risky_row("x1", expires_in=900)
    queued = _risky_row("x2", expires_in=900)
    release, t, box = _hold_the_prompt([first, queued], "x1")
    v2 = Verifier(RuntimeError("no prompt for a card that has already gone"))
    timer = threading.Timer(0.5, release.set)
    try:
        queued["expires_in"] = 0       # a fresh read says it has run out
        timer.start()
        got = _run({"id": "x2"}, lambda: [first, queued], v2)
    finally:
        release.set()
        timer.cancel()
        t.join(10)
        OC.set_verifier(None)
    check("409: the answer both apps read as no longer waiting",
          got is not None and got[0] == 409 and got[1]["owner_check"] == "gone", got)
    check("and no prompt was shown", not v2.asked, v2.asked)
    check("nothing stamped", not OC.take_stamp("x2", queued["action"]))
    check("the first prompt went through", box.get("out") is None, box)


def t_no_prompt_may_stay_up_longer_than_three_minutes():
    """The prompt's only cancel is its own deadline, so the deadline is
    capped: a 900 s card gets at most 180 s of prompt, and the card itself
    keeps waiting (the owner can press Approve again)."""
    row = _risky_row("m1", expires_in=900)
    v = Verifier("confirmed")
    got = _run({"id": "m1"}, lambda: [row], v)
    check("the prompt is really given 180 s - a literal, not one constant "
          "compared with itself",
          bool(v.asked) and v.asked[0][1] == 180, v.asked)
    check("...and the cap constant itself is pinned at three minutes",
          OC._PROMPT_MAX == 180, OC._PROMPT_MAX)
    # The cap is applied where the child is spawned too, so a future caller
    # that passes 900 cannot hand Windows a quarter-hour dialog. Proved on a
    # FAKE child that answers at once: no process starts, no dialog appears.
    fake = FakeChild("confirmed")
    fake.answered.set()
    real_spawn = OC._SPAWN
    OC._SPAWN = lambda *a, **k: fake
    try:
        out = OC._verify_windows("a card", 900)
    finally:
        OC._SPAWN = real_spawn
    asked = [line for line in fake.written if "timeout" in line]
    check("a caller that asks for 900 s still gives Windows 180 s",
          out == "confirmed" and bool(asked)
          and json.loads(asked[0]).get("timeout") == 180, (out, fake.written))
    v150 = Verifier("confirmed")
    got150 = _run({"id": "m2"}, lambda: [_risky_row("m2", expires_in=150)], v150)
    check("a card with 150 s left is unchanged (the smaller number wins)",
          got150 is None and bool(v150.asked) and v150.asked[0][1] == 150, v150.asked)
    check("and the 900 s card is still approved", got is None, got)


def t_a_card_that_stops_waiting_while_the_prompt_is_up_closes_it():
    """The other half of the measured defect (2026-10-26 review): a dialog
    that is ALREADY up used to wait out its number even after its card was
    denied, withdrawn or had expired - three minutes of a prompt for nothing.
    `_PromptWatch` polls the card four times a second and asks the child to
    close, and the answer becomes the 409 both apps read as "no longer
    waiting".

    Proved through the real child path (`_verify_windows`) on a FAKE child
    process: `_SPAWN` is replaced, so nothing starts and no dialog appears."""
    # Measured, not read off the constant: start a watcher on a card that stays
    # waiting and count its polls over a second.
    poll_rows = [_risky_row("pc1", expires_in=150)]
    w = OC._PromptWatch(lambda: list(poll_rows), "pc1").start()
    time.sleep(1.0)
    polls = w.reads
    poll_rows.clear()
    w.gone.wait(5)
    w.stop()
    check("the watcher really looks about four times a second (measured)",
          2 <= polls <= 6, polls)
    check("...with a quarter of a second as the interval it uses",
          OC._WATCH_INTERVAL == 0.25, OC._WATCH_INTERVAL)

    row = _risky_row("wd1", expires_in=900)
    elapsed, out, written, alive = _watch_prompt_then(lambda rows, r: rows.clear(),
                                                      "wd1", row)
    check("a card withdrawn while the prompt is up closes it at once",
          not alive and elapsed < 3.0, (alive, round(elapsed, 2)))
    check("...the answer is 409, not 'the owner dismissed it'",
          out is not None and out[0] == 409 and out[1]["owner_check"] == "gone", out)
    check("...the child is told in words, down its own pipe",
          any(w.strip() == "cancel" for w in written), written)
    check("...and nothing is stamped", not OC.take_stamp("wd1", row["action"]))

    row = _risky_row("ex1", expires_in=900)
    elapsed, out, written, alive = _watch_prompt_then(
        lambda rows, r: r.update(expires_in=0), "ex1", row)
    check("a card that expires while the prompt is up closes it too",
          not alive and elapsed < 3.0, (alive, round(elapsed, 2)))
    check("...with the same 409",
          out is not None and out[0] == 409 and out[1]["owner_check"] == "gone", out)
    check("...and nothing is stamped", not OC.take_stamp("ex1", row["action"]))


def t_the_watcher_leaves_a_card_that_is_still_waiting_alone():
    """A watcher that cancelled every prompt would be worse than none: the
    owner could never approve anything. Shown on a stand-in live prompt."""
    class Live:
        def __init__(self):
            self.cancels = 0

        def cancel(self):
            self.cancels += 1

    live = Live()
    rows = [_risky_row("wt1", expires_in=150)]
    with OC._LIVE_LOCK:
        OC._LIVE_PROMPTS.add(live)
    try:
        watch = OC._PromptWatch(lambda: list(rows), "wt1", interval=0.02).start()
        time.sleep(0.2)                    # ten polls with the card still there
        while_waiting = live.cancels
        rows.clear()
        for _ in range(200):
            if watch.gone.is_set() and live.cancels:
                break
            time.sleep(0.01)
        watch.stop()
    finally:
        with OC._LIVE_LOCK:
            OC._LIVE_PROMPTS.discard(live)
    check("a card that is still waiting: its prompt is not touched",
          while_waiting == 0, while_waiting)
    check("a card that stops waiting: the live prompt is asked to close",
          watch.gone.is_set() and live.cancels >= 1, (watch.gone.is_set(), live.cancels))
    check("...and the watcher ends when the prompt is over", not watch._thread.is_alive())

    # A queue that cannot be read is not a card that went away: a locked
    # database must not close a prompt the owner is looking at.
    def broken():
        raise OSError("database is locked")

    fresh = Live()
    with OC._LIVE_LOCK:
        OC._LIVE_PROMPTS.add(fresh)
    try:
        watch = OC._PromptWatch(broken, "wt1", interval=0.02).start()
        time.sleep(0.15)
        watch.stop()
    finally:
        with OC._LIVE_LOCK:
            OC._LIVE_PROMPTS.discard(fresh)
    check("a queue that cannot be read does not close the prompt",
          not watch.gone.is_set() and fresh.cancels == 0, fresh.cancels)


def t_a_stale_watcher_closes_only_its_own_prompt():
    """`stop()` joins for two seconds; a queue read can outlive that. By the
    time the stale read returns the prompt lock is released, so the NEXT card's
    prompt can be the one on screen - and a global cancel would close it
    (2026-10-26 review). The watcher is token-scoped, so it cannot.

    No prompt is raised: `_LIVE_PROMPTS` holds two stand-ins and the queue is a
    function, so no child process, no dialog and no database are involved."""
    entered, release = threading.Event(), threading.Event()

    def slow_pending():
        entered.set()
        release.wait(10)
        return []                  # by now THIS watcher's card really is gone

    class Live:
        def __init__(self, token):
            self.token = token
            self.cancels = 0

        def cancel(self):
            self.cancels += 1

    mine_token = object()
    mine, next_card = Live(mine_token), Live(object())
    with OC._LIVE_LOCK:
        OC._LIVE_PROMPTS.add(mine)
    watch = OC._PromptWatch(slow_pending, "s1", interval=0.01,
                            cancel=lambda: OC._cancel_prompts_for(mine_token)).start()
    try:
        check("the slow queue read started", entered.wait(5))
        watch.stop()               # two-second join, and the read is slower
        check("the watcher thread really can outlive stop()",
              watch._thread.is_alive(), watch._thread.is_alive())
        with OC._LIVE_LOCK:        # the next card's prompt is live by now
            OC._LIVE_PROMPTS.add(next_card)
        release.set()
        watch._thread.join(5)
        check("the stale watcher closes the prompt it was made for",
              mine.cancels >= 1, mine.cancels)
        check("...and never the NEXT card's prompt, which is the whole point",
              next_card.cancels == 0, next_card.cancels)
    finally:
        release.set()
        watch.stop()
        with OC._LIVE_LOCK:
            OC._LIVE_PROMPTS.discard(mine)
            OC._LIVE_PROMPTS.discard(next_card)


def t_a_wait_for_the_prompt_is_bounded_and_refuses_after_it():
    """`_PROMPT.acquire(-1)` waited for ever: one child that never answered
    held every later approval until the backend restarted. The wait is now
    bounded by `_PROMPT_WAIT_MAX` (a whole prompt, the ten seconds its child
    gets to answer, and the cancel that follows - thirty seconds of slack in
    all), and a card that never gets its turn is a 409 (2026-10-26 review)."""
    check("a card with no deadline waits the whole worst-case hold",
          OC._wait_for_prompt(None) == OC._PROMPT_WAIT_MAX, OC._wait_for_prompt(None))
    check("a card with 150 s waits its own 150 s",
          OC._wait_for_prompt(150) == 150, OC._wait_for_prompt(150))
    check("a 900 s card waits the whole hold, NOT the 30 s shorter prompt cap "
          "(the bug this fixes)",
          OC._wait_for_prompt(900) == OC._PROMPT_WAIT_MAX, OC._wait_for_prompt(900))
    row = _risky_row("bw1", expires_in=900)
    v = Verifier(RuntimeError("no prompt when the wait ran out"))
    saved = OC._PROMPT_WAIT_MAX
    OC._PROMPT.acquire()                   # stand in for a prompt that is stuck
    try:
        OC._PROMPT_WAIT_MAX = 0.05         # the whole wait, so the test is quick
        started = time.monotonic()
        got = _run({"id": "bw1"}, lambda: [row], v)
        elapsed = time.monotonic() - started
    finally:
        OC._PROMPT.release()
        OC._PROMPT_WAIT_MAX = saved
    check("the whole-hold ceiling is the prompt cap plus thirty seconds of slack",
          saved == OC._PROMPT_MAX + 30.0, saved)
    check("a request that never gets its turn is refused, not left hanging",
          got is not None and got[0] == 409 and got[1]["owner_check"] == "gone"
          and elapsed < 2.0, (got, round(elapsed, 2)))
    check("...and no prompt was shown", not v.asked, v.asked)


def t_the_live_row_is_checked_again_after_the_wait():
    """A same-id action can change while the prompt queues (the gate raises a
    fresh card under the same id for some actions). The label and the stamp
    must be the LIVE row's, not the row read before the wait (2026-10-26
    review).

    Each scenario gets its OWN read counter: a shared one (as this test first
    had) would hand the second scenario's first read the row under test, so the
    pre-wait guard would refuse it and the post-wait re-check would never be
    exercised - the test would pass on the unfixed code."""
    before = _risky_row("lr1", expires_in=900)
    after = _risky_row("lr1", expires_in=900, action="send_email")
    after["notice"] = dict(after["notice"], title="Jarvis wants to send an email")

    def labelled_first_then(row):
        """The pre-wait read sees `before`; every later read sees `row`."""
        reads = []

        def pending():
            reads.append(1)
            return [before] if len(reads) == 1 else [row]
        return pending, reads

    pending, reads = labelled_first_then(after)
    v = Verifier("confirmed")
    got = _run({"id": "lr1"}, pending, v)
    check("a labelled action that changed under the same id still prompts",
          got is None and len(v.asked) == 1, (got, v.asked))
    check("...with the LIVE row's title, not the one read before the wait",
          bool(v.asked) and v.asked[0][0] == OC.approval_message(after), v.asked)
    check("...and the stamp is for the live action, which is what the gate asks for",
          OC.take_stamp("lr1", after["action"]) is True)
    check("...not for the action read before the wait",
          OC.take_stamp("lr1", before["action"]) is False)

    pending, reads = labelled_first_then(_unlabelled_row("lr1", expires_in=900))
    v = Verifier(RuntimeError("no prompt for a row with no written words"))
    got = _run({"id": "lr1"}, pending, v)
    check("an action that LOST its written words is refused before the prompt",
          got is not None and got[0] == 403 and got[1]["owner_check"] == "unlabelled", got)
    check("...refused on the SECOND read (the one after the wait), which is the "
          "re-check this test exists for",
          len(reads) == 2, (len(reads), got))
    check("...the verifier was never called", not v.asked, v.asked)
    check("...and nothing was stamped", not OC.take_stamp("lr1", before["action"]))


def t_the_hello_child_refuses_an_empty_line_and_clamps_the_timeout():
    """Blocker 2 of the 2026-10-26 review: the child read an empty stdin line
    as `{}` and then gave the prompt the 900 s default, so a `--hello` with no
    card at all could still raise a quarter-hour dialog.

    Proved on the PARSER ONLY, never by running the child: if this guard
    regressed, running the child on the owner's PC would raise a REAL Windows
    Hello prompt. The wiring is checked on the syntax tree, not by starting
    anything."""
    for line in ("", "\n", "   \n"):
        try:
            OC._hello_ask(line)
        except ValueError:
            refused = True
        else:
            refused = False
        check(f"an empty --hello line ({line!r}) is refused, not read as a request",
              refused)
    check("a request with no timeout gets the cap, not the shipped 900",
          OC._hello_ask('{"message": "x"}') == ("x", OC._PROMPT_MAX))
    check("a request that ASKS for 900 gets the cap",
          OC._hello_ask('{"timeout": 900}')[1] == OC._PROMPT_MAX)
    check("a request with less time keeps it",
          OC._hello_ask('{"message": "m", "timeout": 2}') == ("m", 2.0))
    check("a nonsense timeout cannot make the prompt longer",
          OC._hello_ask('{"timeout": "soon"}')[1] == OC._PROMPT_MAX)
    try:
        OC._hello_ask("5")
    except ValueError:
        refused = True
    else:
        refused = False
    check("a line that is not an object is refused", refused)

    tree = ast.parse((HERE / "jarvis_owner_check.py").read_text(encoding="utf-8"))
    main = [n for n in tree.body if isinstance(n, ast.If)
            and isinstance(n.test, ast.Compare)
            and isinstance(n.test.left, ast.Name) and n.test.left.id == "__name__"]
    calls = [n for n in ast.walk(main[0]) if isinstance(n, ast.Call)] if main else []
    asks = [c for c in calls if isinstance(c.func, ast.Name) and c.func.id == "_hello_ask"]
    prompts = [c for c in calls if isinstance(c.func, ast.Name) and c.func.id == "_hello_child"]
    check("the --hello block parses its one line with the tested rule",
          len(asks) == 1, len(asks))
    check("...and only then asks Windows",
          bool(asks) and bool(prompts) and asks[0].lineno < prompts[0].lineno,
          [(c.func.id, c.lineno) for c in asks + prompts])


def t_shutdown_cancels_a_live_prompt():
    """A clean backend exit asks the child to close the prompt, through the
    pipe the child watches. Proved on a FAKE child: no process, no dialog."""
    fake = FakeChild("cancelled")
    real_spawn = OC._SPAWN
    OC._SPAWN = lambda *a, **k: fake
    box = {}
    thread = threading.Thread(target=lambda: box.setdefault(
        "out", OC._verify_windows("Approve?", 30)))
    asked = None
    try:
        thread.start()
        live = 0
        for _ in range(500):
            with OC._LIVE_LOCK:
                live = len(OC._LIVE_PROMPTS)
            if live and fake.written:
                break
            time.sleep(0.01)
        check("the prompt is registered while it waits, and has its question",
              live == 1 and bool(fake.written), (live, fake.written))
        asked = OC._cancel_live_prompts()
        thread.join(10)
    finally:
        OC._SPAWN = real_spawn
        if thread.is_alive():
            OC._cancel_live_prompts()
            thread.join(10)
        with OC._LIVE_LOCK:
            OC._LIVE_PROMPTS.clear()
    check("the shutdown hook asks every live prompt to close", asked == 1, asked)
    check("the child is told in words, and its pipe is shut",
          any("cancel" in w for w in fake.written) and fake.closed, fake.written)
    check("the check then reads the child's own answer", box.get("out") == "cancelled", box)
    check("and nothing is left registered", not OC._LIVE_PROMPTS, OC._LIVE_PROMPTS)
    check("the hook is what atexit runs", OC._SHUTDOWN_HOOK is OC._cancel_live_prompts)


def t_a_prompt_that_answers_on_its_own_is_read_as_before():
    """The ordinary path, on the same fake: the question goes down the pipe,
    the answer comes back, and nothing is cancelled."""
    fake = FakeChild("confirmed")
    fake.answered.set()                  # the fake answers straight away
    real_spawn = OC._SPAWN
    OC._SPAWN = lambda *a, **k: fake
    try:
        got = OC._verify_windows("Approve?", 30)
    finally:
        OC._SPAWN = real_spawn
        with OC._LIVE_LOCK:
            OC._LIVE_PROMPTS.clear()
    check("the child's answer is read as before", got == "confirmed", got)
    check("the question was sent as one JSON line",
          len(fake.written) == 1 and json.loads(fake.written[0])["message"] == "Approve?",
          fake.written)
    check("and no cancel was written", not any("cancel" in w for w in fake.written))


def t_the_child_stops_when_its_parent_says_cancel_or_closes_the_pipe():
    for text, why in (("cancel\n", "the cancel line"), ("", "the pipe closing")):
        stop = threading.Event()
        OC._watch_for_stop(io.StringIO(text), stop)
        check(f"{why} stops the prompt", stop.is_set())

    # The loop that ACTS on that flag, through its own seam: a fake operation
    # records whether Windows was asked to cancel. No Windows, no prompt.
    class Op:
        def __init__(self, statuses, answer=7):
            self.statuses, self.answer = list(statuses), answer
            self.cancels = 0

        def status(self):
            return self.statuses.pop(0) if self.statuses else 0

        def cancel(self):
            self.cancels += 1

        def value(self):
            return self.answer

    stop = threading.Event()
    op = Op([0, 0])
    got = OC._wait_async(op.status, op.cancel, op.value, stop,
                         time.monotonic() + 60, tick=stop.set)
    check("the flag cancels the prompt, and the wait ends as stopped",
          got is OC._STOPPED and op.cancels == 1, (got, op.cancels))

    op = Op([1])
    check("a finished operation still returns its own result, nothing cancelled",
          OC._wait_async(op.status, op.cancel, op.value, None,
                         time.monotonic() + 60) == 7 and op.cancels == 0)
    op = Op([2])
    check("a cancelled or failed operation returns no result",
          OC._wait_async(op.status, op.cancel, op.value, None,
                         time.monotonic() + 60) is None)
    op = Op([None])
    check("a status that cannot be read returns no result",
          OC._wait_async(op.status, op.cancel, op.value, None,
                         time.monotonic() + 60) is None and op.cancels == 0)
    op = Op([0, 0])
    check("a deadline ends the wait by cancelling, not by waiting for ever",
          OC._wait_async(op.status, op.cancel, op.value, None,
                         time.monotonic() - 1) is None and op.cancels == 1)

    # The Windows-only wiring: the child's wait() is handed that flag, the
    # --hello block starts the stdin watcher, and it passes the flag in.
    # Walked as SYNTAX (ast), never as source text, so a rename or a reformat
    # cannot make it lie.
    tree = ast.parse((HERE / "jarvis_owner_check.py").read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    waits = [c for c in calls if isinstance(c.func, ast.Name) and c.func.id == "_wait_async"]
    check("the child's wait loop is handed the stop flag",
          any(any(isinstance(a, ast.Name) and a.id == "should_stop" for a in c.args)
              for c in waits), len(waits))
    check("the child starts a thread reading its stdin for cancel",
          any(isinstance(c.func, ast.Attribute) and c.func.attr == "Thread"
              and any(k.arg == "target" and isinstance(k.value, ast.Name)
                      and k.value.id == "_watch_for_stop" for k in c.keywords)
              for c in calls))
    check("...and passes that flag into the check",
          any(isinstance(c.func, ast.Name) and c.func.id == "_hello_child"
              and any(k.arg == "should_stop" for k in c.keywords) for c in calls))


def t_the_phone_checks_its_own_fingerprint_so_no_prompt_here():
    row = _risky_row("r7")
    v = Verifier(RuntimeError("must not be asked"))
    got = _run({"id": "r7"}, lambda: [row], v, peer="100.101.102.103", local="100.64.0.5")
    check("from another device: no prompt on the PC", got is None and not v.asked, got)
    check("but it is stamped", OC.take_stamp("r7", row["action"]))


def t_a_card_that_is_not_risky_asks_nothing():
    row = _safe_row("s2")
    v = Verifier(RuntimeError("must not be asked"))
    check("not risky, from this PC: no prompt", _run({"id": "s2"}, lambda: [row], v) is None
          and not v.asked)
    check("stamped", OC.take_stamp("s2", row["action"]))


def t_what_this_backend_cannot_find_it_leaves_to_the_owners_handler():
    v = Verifier(RuntimeError("must not be asked"))
    check("unknown id: passed on (the owner's handler answers 409), not stamped",
          _run({"id": "nope"}, lambda: [_risky_row("r8")], v) is None
          and not OC.take_stamp("nope", "send_email") and not v.asked)
    for body in (None, {}, {"id": ""}, [1, 2]):
        check(f"body {body!r}: passed on", _run(body, lambda: [], v) is None)

    def broken():
        raise OSError("database is locked")
    got = _run({"id": "r8"}, broken, v)
    check("a queue that cannot be read: 503, nothing approved",
          got and got[0] == 503 and "Nothing was approved" in got[1]["error"], got)


# ------------------------------------------------- the server wrapper --

class FakeHandler:
    """Just enough of jarvis_hud.Handler: a path, a body, who is asking."""
    decided: list = []

    def __init__(self, path, body, peer="127.0.0.1", token=True):
        raw = json.dumps(body).encode()
        self.path = path
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = io.BytesIO(raw)
        self.client_address = (peer, 50000)
        self.connection = types.SimpleNamespace(getsockname=lambda: ("127.0.0.1", 4719))
        self.token = token
        self.sent = None

    def do_POST(self):          # the owner's handler: reads the body itself
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        FakeHandler.decided.append((self.path, body))
        return self._send(200, {"ok": True})

    def _send(self, code, payload):
        self.sent = (code, payload)


def _read_body(h):
    return h.rfile.read(int(h.headers.get("Content-Length") or 0))


def t_the_wrapper_holds_approve_and_never_deny():
    cls = type("H", (FakeHandler,), {})
    OC._ARMED = False
    line = OC.install(cls, origin_ok=lambda h: True, token_ok=lambda h: h.token,
                      read_body=_read_body)
    check("install says what it did", "Windows Hello" in line, line)
    check("and /api/version can say so", OC.armed() is True)
    again = OC.install(cls, origin_ok=lambda h: True, token_ok=lambda h: h.token,
                       read_body=_read_body)
    check("installing twice does not wrap twice", "already on" in again, again)

    row = _risky_row("w1")
    rows = [row]
    real_pending = OC._pending_rows
    OC._pending_rows = lambda: list(rows)
    FakeHandler.decided.clear()
    try:
        OC.set_verifier(Verifier(RuntimeError("Deny must never ask")))
        h = cls("/api/deny", {"id": "w1"})
        h.do_POST()
        check("Deny goes straight to the owner's handler, never held",
              FakeHandler.decided == [("/api/deny", {"id": "w1"})] and h.sent[0] == 200, h.sent)

        _fresh_stamps()
        FakeHandler.decided.clear()
        OC.set_verifier(Verifier("confirmed"))
        h = cls("/api/approve", {"id": "w1", "by": "desktop_spotlight"})
        kept = h.rfile
        h.do_POST()
        check("a confirmed approve reaches the owner's handler with the same body",
              FakeHandler.decided == [("/api/approve", {"id": "w1", "by": "desktop_spotlight"})],
              FakeHandler.decided)
        check("stamped for the gate", OC.take_stamp("w1", row["action"]))
        check("and the connection's own reader is put back", h.rfile is kept)

        FakeHandler.decided.clear()
        OC.set_verifier(Verifier("unavailable"))
        h = cls("/api/approve/?x=1", {"id": "w1"})
        h.do_POST()
        check("a refused approve never reaches the owner's handler",
              FakeHandler.decided == [] and h.sent[0] == 403
              and h.sent[1]["error"] == OC.NOT_SET_UP, h.sent)

        v = Verifier(RuntimeError("no prompt for a stranger"))
        OC.set_verifier(v)
        FakeHandler.decided.clear()
        h = cls("/api/approve", {"id": "w1"}, token=False)
        h.do_POST()
        check("a request without the token raises no prompt: the owner's handler refuses it",
              not v.asked and FakeHandler.decided == [("/api/approve", {"id": "w1"})])

        FakeHandler.decided.clear()
        h = cls("/api/chat", {"message": "hi"})
        h.do_POST()
        check("every other route is untouched", FakeHandler.decided == [("/api/chat", {"message": "hi"})])
    finally:
        OC._pending_rows = real_pending
        OC.set_verifier(None)
        OC._ARMED = False


# ------------------------------------------------ the patch, in place --

def _gate():
    text, log = _stack.stand_in("jarvis_gate.py")
    return text, log


def t_the_gate_believes_no_approved_row_without_a_stamp():
    text, log = _gate()
    if text is None:
        check("the gate's stand-in builds", False, log)
        return
    check("owner-check.patch needed none of the owner's lines it had not already seen",
          not [l for l in log if l.startswith("owner-check.patch")], log)
    lines = text.splitlines()
    branches = [i for i, l in enumerate(lines) if re.search(r'row\["state"\] == "approved"', l)]
    check("both of the gate's approved branches are there", len(branches) == 2, branches)
    for i in branches:
        after = "\n".join(lines[i + 1:i + 6])
        check(f"line {i + 1}: the stamp is asked before gate.approved is recorded",
              after.find("_approval_stamped(rid, action)") != -1
              and after.find("_approval_stamped") < after.find('_audit("gate.approved"'), after)

    ns = {"_audit": lambda *a, **k: ns.setdefault("audits", []).append(a)}

    class Verdict:
        def __init__(self, allowed, tier, action, reason, request_id=None, outcome="refused"):
            self.allowed, self.tier, self.action = allowed, tier, action
            self.reason, self.request_id, self.outcome = reason, request_id, outcome
    ns["Verdict"] = Verdict
    for name in ("_approval_stamped", "_unstamped_approval"):
        src = _stack.function_text(text, name)
        check(f"{name} is in the patched gate", src is not None)
        exec(compile(src, f"owner-check.patch:{name}", "exec"), ns)
    _fresh_stamps()
    check("a row nobody stamped: not approved", ns["_approval_stamped"]("g1", "send_email") is False)
    OC.stamp("g1", "send_email")
    check("the stamped one: approved, once", ns["_approval_stamped"]("g1", "send_email") is True
          and ns["_approval_stamped"]("g1", "send_email") is False)
    v = ns["_unstamped_approval"]("g2", "ask", "send_email", {"decided_by": "someone"})
    check("an unstamped approved row is refused, not denied (no rule is proposed)",
          v.allowed is False and v.outcome == "refused" and v.request_id == "g2", vars(v))
    check("and the audit log says so",
          ns.get("audits") and ns["audits"][-1][0] == "gate.unstamped_approval")
    saved = sys.modules.get("jarvis_owner_check")
    sys.modules["jarvis_owner_check"] = None     # import fails
    try:
        OC.stamp("g3", "x")
        check("without jarvis_owner_check.py nothing is approved (fails closed)",
              ns["_approval_stamped"]("g3", "x") is False)
    finally:
        sys.modules["jarvis_owner_check"] = saved


def t_the_server_wraps_its_handler_before_anything_listens():
    text, log = _stack.stand_in("jarvis_hud.py")
    if text is None:
        check("the server's stand-in builds", False, log)
        return
    i = text.find("jarvis_owner_check.install(Handler")
    j = text.find("_loopback_companion(bind, HUD_PORT, Handler)\n    print(")
    k = text.find("httpd = ThreadingHTTPServer((bind, HUD_PORT), Handler)")
    check("install() is called", i != -1)
    check("before the loopback socket and the main one", -1 < i < j < k, (i, j, k))
    call = _block(text, "jarvis_owner_check.install(Handler")
    check("the install call is still there to check", bool(call))
    check("with the server's own origin, token and body readers",
          "origin_ok=_origin_ok" in call and "token_ok=_token_ok" in call
          and "read_body=_read_body" in call, call)
    check("and a missing module is said on the banner",
          "every approval is refused" in text)


def t_the_order_pins_only_what_it_needs():
    order = _stack.order()
    check("owner-check.patch is applied", "owner-check.patch" in order)
    at = order.index("owner-check.patch")
    for need in ("gate-outcome.patch", "log-scrub.patch", "bind-wildcard.patch"):
        check(f"after {need} (its context lines are that patch's output)",
              need in order and order.index(need) < at)


# --------------------------------------------------- /api/version --

def t_the_version_handshake_says_the_backend_asks():
    try:
        import jarvis_events as E
    except ImportError:
        sys.path.append(str(HERE / "rebuilt"))
        import jarvis_events as E
    OC._ARMED = False
    check("not installed: owner_check is false (the desktop keeps asking itself)",
          E._capability_probe()["owner_check"] is False)
    OC._ARMED = True
    try:
        check("installed: owner_check is \"backend\"",
              E._capability_probe()["owner_check"] == "backend")
    finally:
        OC._ARMED = False


# ------------------------------------------------ the Windows side --

def t_the_windows_side_is_arithmetic_checked_and_fails_closed():
    check("the interface id of IAsyncOperation<bool> is Windows' own",
          str(OC.winrt_iid("pinterface({9fc2b0bb-e446-44e2-aa61-9cab8f636af2};b1)"))
          == "cdb5efb3-5788-509d-9be1-71ccb8a3362a")
    check("and of IIterable<String>",
          str(OC.winrt_iid("pinterface({faa585ea-6214-4217-afda-7f46de5869b3};string)"))
          == "e2fcc7c1-3bfc-5a0b-b2b0-72e769d1cb7e")
    for code, want in ((0, None), (1, "unavailable"), (2, "unavailable"), (3, "unavailable"),
                       (4, "again"), (99, "again")):
        check(f"availability {code} -> {want}", OC.before_prompt(code) == want)
    for code, want in ((0, "confirmed"), (1, "unavailable"), (3, "unavailable"), (4, "again"),
                       (5, "cancelled"), (6, "cancelled"), (99, "again")):
        check(f"result {code} -> {want}", OC.after_prompt(code) == want)
    for rc, out, want in ((0, '{"outcome": "confirmed"}\n', "confirmed"),
                          (0, 'noise\n{"outcome": "cancelled"}', "cancelled"),
                          (0, '{"outcome": "yes please"}', "failed"),
                          (0, "", "failed"), (1, '{"outcome": "confirmed"}', "failed"),
                          (0, "not json", "failed")):
        check(f"the child's answer {out!r} (exit {rc}) -> {want}",
              OC.parse_child_answer(rc, out) == want)
    if sys.platform != "win32":
        r = subprocess.run([sys.executable, str(HERE / "jarvis_owner_check.py"), "--hello"],
                           input='{"message": "x", "timeout": 1}', capture_output=True,
                           text=True, timeout=30)
        check("the child, off Windows, answers failed rather than crash",
              OC.parse_child_answer(r.returncode, r.stdout) == "failed", r.stdout + r.stderr)


# ------------------------------------------------------- the words --

def _rust_const(name):
    src = RULES_RS.read_text(encoding="utf-8")
    m = re.search(rf'pub const {name}: &str =\s*"((?:[^"\\]|\\.)*)";', src, re.S)
    return re.sub(r"\\\n\s*", "", m.group(1)) if m else None


def t_both_apps_say_the_same_thing():
    check("the desktop's own refusal is the backend's, word for word",
          _rust_const("NO_HELLO_NO_RISKY") == OC.NOT_SET_UP, _rust_const("NO_HELLO_NO_RISKY"))
    # Kotlin writes a long sentence as pieces joined with +; read it whole.
    kt = re.sub(r'"\s*\+\s*\n\s*"', "", SECURITY_KT.read_text(encoding="utf-8"))
    check("the phone's says the same about its screen lock",
          "so Jarvis cannot check it is you, and risky approvals are refused until it has one" in kt)
    for s in (OC.NOT_SET_UP, OC.CANCELLED, OC.FAILED, OC.GONE, OC.QUEUE_UNREADABLE):
        check(f"no 'already' or '409' in {s[:40]!r}... (the desktop reads those as answered)",
              "already" not in s.lower() and "409" not in s)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
