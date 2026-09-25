"""A timeout is not a refusal, and the no-approve-all rule is now testable.

    python3 test_gate_outcome.py

No pytest, no network. Real sqlite approval queues in a temp dir.

TWO THINGS.

1. Verdict now carries `outcome`. The database already distinguished these -
   approvals.state is pending|approved|denied|expired - but Verdict did not,
   so by the time a caller saw the answer, "a person said no" and "nobody was
   there" differed only in the wording of a sentence. They need different
   handling: a denial is an answer and must not be retried; a timeout is the
   absence of one and is worth asking again later.

2. The claim "there is no approve-all anywhere in Jarvis" is prose about code.
   docs/PEERS.md records what happens to prose like that: cline's own docs
   still describe three auto-approve toggles their UI stopped rendering in
   June, same repo, both shipped. So the last test here reads the source and
   asserts the claim, rather than trusting this file's comments.
"""
import json, os, sys, tempfile, time, traceback, types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# BACKEND is where the modules under test actually live - this folder
# in the dev container, $JARVIS_BACKEND on a real install. REPO is this
# repository. They used to be the same path and are not on the machine
# that runs Jarvis.
from _where import BACKEND, REPO, missing, explain

# A temp home BEFORE the import: jarvis_gate opens its queue at import time.
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-gate-outcome-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP)
os.environ.setdefault("JARVIS_APPROVAL_TIMEOUT", "1")
# No push: the topic is unset, so _push returns without opening a socket. Said
# explicitly rather than relied on, because a test that quietly posted to
# ntfy.sh would be the exact leak the gate exists to prevent.
os.environ["JARVIS_NTFY_TOPIC"] = ""

# Same framework stub as test_gate_push.py: redaction on, which is the real
# default, and an audit log that goes nowhere.
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
# A real tier table. The first version of this file omitted it, and every
# check() bailed out at "autonomy policy could not be read" - which is the
# gate failing closed exactly as designed, and a test that proved nothing.
fw.load_framework = lambda: {
    "logging": {"redact_private_content_in_logs": True},
    "autonomy": {
        "unknown_action_tier": "ask",
        # Keyed on ACTION names, not tool names: _TOOL_ACTIONS maps a tool to
        # an action and is a hardcoded table in the module, not config. The
        # first version of this stub keyed on tool names, so every lookup fell
        # through to unclassified_tool and every case read as tier ask - which
        # is the gate failing safe, and a test proving nothing.
        "tiers": {
            "send_email": "ask",
            "read_files_readonly": "ask",
            "run_shell_on_host": "never",
            "post_to_external_service": "never",
            "open_public_tunnel": "never",
        },
    },
}
fw.audit_log = lambda *a, **k: None
sys.modules["jarvis_framework"] = fw

import jarvis_gate as G

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def t_the_type_fails_closed():
    """codex's `impl Default for ReviewDecision -> Denied`, in Python."""
    v = G.Verdict(False, "ask", "send_email", "because")
    check("a Verdict with no outcome defaults to refused",
          v.outcome == "refused", f"got {v.outcome!r}")

    # The one that matters: a new construction site that forgets the field
    # must not silently grant.
    v = G.Verdict(True, "ask", "send_email", "because")
    check("allowed=True with a forgotten outcome is forced to False",
          v.allowed is False,
          "a default of 'approved' would make forgetting the field a grant")

    v = G.Verdict(True, "ask", "x", "y", outcome="nonsense")
    check("an unknown outcome is coerced, not raised",
          v.outcome == "refused" and v.allowed is False, f"got {v}")

    check("timed_out is not allowed, ever",
          G.Verdict(True, "ask", "x", "y", outcome="timed_out").allowed is False)

    for good in ("auto", "notify", "approved"):
        check(f"{good} may carry allowed=True",
              G.Verdict(True, "ask", "x", "y", outcome=good).allowed is True)


def t_nobody_answered_is_timed_out_not_denied():
    """The whole point. A one-second timeout, and nobody answers."""
    started = time.time()
    v = G.check("send_email", {"to": "someone"}, prompt="send an email",
                timeout=1.0)
    took = time.time() - started

    check("it refused", v.allowed is False)
    check("and it is timed_out, not denied", v.outcome == "timed_out",
          f"got {v.outcome!r}")
    check("and the convenience property agrees", v.timed_out is True)
    check("and it did not hang", took < 20, f"took {took:.1f}s")
    check("and the id is there so the row can be found",
          bool(v.request_id))


def t_a_real_denial_is_denied():
    """CONTROL. If everything came back timed_out the test above is empty."""
    import threading
    box = {}

    def ask():
        box["v"] = G.check("send_email", {"to": "someone"},
                           prompt="send an email", timeout=20.0)

    t = threading.Thread(target=ask, daemon=True)
    t.start()
    # Wait for the row to appear, then answer it.
    rid = None
    for _ in range(200):
        time.sleep(0.05)
        pend = G.pending()
        if pend:
            rid = pend[0]["id"]
            break
    if not rid:
        check("a denial reads as denied", False, "no pending row ever appeared")
        return
    G.decide(rid, False, by="the test")
    t.join(timeout=20)
    v = box.get("v")
    check("a denial reads as denied", v is not None and v.outcome == "denied",
          f"got {v}")
    check("and it is not flagged as a timeout", v is not None and not v.timed_out)


def t_a_denial_proposes_a_constraint_never_writes_one():
    """A denial only ever PROPOSES a standing rule - propose() is the one
    choke point every fact this project learns already goes through
    (memory-safety.patch removed the sole auto-accept path that used to be
    inside it), and a denial writing to memory directly would be a second,
    unreviewed door into the same room - the shape no-auto-approve.patch
    found and fixed for tier confirmation, one module over."""
    import threading
    calls = []
    stub = types.ModuleType("jarvis_extract")

    def fake_propose(turns, **kw):
        calls.append({"turns": turns, "kwargs": kw})
        return []
    stub.propose = fake_propose
    sys.modules["jarvis_extract"] = stub

    box = {}

    def ask():
        box["v"] = G.check("send_email", {"to": "someone"},
                           prompt="send an email", timeout=20.0)
    t = threading.Thread(target=ask, daemon=True)
    t.start()
    rid = None
    for _ in range(200):
        time.sleep(0.05)
        pend = G.pending()
        if pend:
            rid = pend[0]["id"]
            break
    if not rid:
        check("a denial proposes a constraint", False, "no pending row ever appeared")
        return
    G.decide(rid, False, by="the test")
    t.join(timeout=20)

    check("propose() was called exactly once", len(calls) == 1, f"got {len(calls)} calls")
    if calls:
        check("it was tagged source=gate_denial",
              calls[0]["kwargs"].get("source") == "gate_denial", calls[0]["kwargs"])
        text = calls[0]["turns"][0]["content"]
        check("the candidate constraint names the denied action",
              "send email" in text, text)
        check("this module has no direct write path - only propose exists on the stub",
              not hasattr(stub, "add_fact") and not hasattr(stub, "_accept"))


def t_a_no_on_an_always_ask_card_proposes_nothing():
    """AP-11: second_card_enable always asks (the module acts on nothing
    else), so "I do not want Jarvis to second card enable without asking me
    first" says nothing - and every "no" used to put it in the Memory tab."""
    import threading
    calls = []
    stub = types.ModuleType("jarvis_extract")
    stub.propose = lambda *a, **k: calls.append((a, k))
    sys.modules["jarvis_extract"] = stub
    box = {}

    def ask():
        box["v"] = G.check("second_card_enable", {"text": "turn on the wiki"},
                           prompt="second card", timeout=20.0)
    t = threading.Thread(target=ask, daemon=True)
    t.start()
    rid = None
    for _ in range(200):
        time.sleep(0.05)
        pend = G.pending()
        if pend:
            rid = pend[0]["id"]
            break
    if not rid:
        check("a second-card card was raised (test setup)", False, "no pending row appeared")
        return
    G.decide(rid, False, by="the test")
    t.join(timeout=20)
    check("it was denied (test setup)", box.get("v") is not None
          and box["v"].outcome == "denied", repr(box.get("v")))
    check("denying second_card_enable proposes no memory", calls == [], repr(calls))


def t_a_timeout_never_proposes_anything():
    """Nobody decided anything here - a timeout must not seed a constraint,
    the same reason it must not be recorded as a denial."""
    calls = []
    stub = types.ModuleType("jarvis_extract")
    stub.propose = lambda *a, **k: calls.append((a, k))
    sys.modules["jarvis_extract"] = stub

    v = G.check("send_email", {"to": "someone"}, prompt="send an email", timeout=1.0)
    check("it really did time out (test setup)", v.outcome == "timed_out", v.outcome)
    check("a timeout calls propose() zero times", len(calls) == 0, f"got {len(calls)} calls")


def t_an_approval_is_approved():
    import threading
    box = {}

    def ask():
        box["v"] = G.check("send_email", {"to": "someone"},
                           prompt="send an email", timeout=20.0)

    t = threading.Thread(target=ask, daemon=True)
    t.start()
    rid = None
    for _ in range(200):
        time.sleep(0.05)
        pend = G.pending()
        if pend:
            rid = pend[0]["id"]
            break
    if not rid:
        check("an approval reads as approved", False, "no pending row appeared")
        return
    # owner-check.patch: the gate believes "approved" only when this process
    # stamped it - which POST /api/approve does after its checks. The test
    # approves through the gate directly, so it stamps as that route would.
    import jarvis_owner_check
    jarvis_owner_check.stamp(rid, "send_email")
    G.decide(rid, True, by="the test")
    t.join(timeout=20)
    v = box.get("v")
    check("an approval reads as approved",
          v is not None and v.outcome == "approved" and v.allowed is True,
          f"got {v}")


def _wait_for_card():
    import threading
    box = {}

    def ask():
        box["v"] = G.check("send_email", {"to": "someone"},
                           prompt="send an email", timeout=20.0)
    t = threading.Thread(target=ask, daemon=True)
    t.start()
    for _ in range(200):
        time.sleep(0.05)
        pend = G.pending()
        if pend:
            return t, box, pend[0]["id"]
    return t, box, None


def t_an_approval_nobody_stamped_is_refused():
    """The approval gap, step 1 (docs/APPROVAL-GAP-DESIGN.md): another
    program that calls decide() - or imports this module in a process of its
    own - has no stamp from THIS process, so its "yes" does not count."""
    t, box, rid = _wait_for_card()
    if not rid:
        check("an unstamped approval is refused", False, "no pending row appeared")
        return
    G.decide(rid, True, by="another program")
    t.join(timeout=20)
    v = box.get("v")
    check("an unstamped approval is refused, not run",
          v is not None and v.allowed is False and v.outcome == "refused", f"got {v}")
    check("and the reason says why",
          v is not None and "not through Jarvis's own approval check" in v.reason, f"got {v}")


def t_approved_written_straight_into_the_database_is_refused():
    """The cheap attack the design names: write state='approved' into
    approvals.db, no web request at all. No stamp, so refused."""
    import sqlite3
    t, box, rid = _wait_for_card()
    if not rid:
        check("a row written straight into the database is refused", False,
              "no pending row appeared")
        return
    dbs = sorted(_TMP.rglob("approvals*.db"))
    if not dbs:
        check("the approval queue's file was found", False, f"nothing under {_TMP}")
        G.decide(rid, False, by="the test")
        return
    con = sqlite3.connect(str(dbs[0]))
    try:
        con.execute("UPDATE approvals SET state='approved' WHERE id=?", (rid,))
        con.commit()
    finally:
        con.close()
    t.join(timeout=20)
    v = box.get("v")
    check("a row written straight into the database is refused",
          v is not None and v.allowed is False and v.outcome == "refused", f"got {v}")


def t_the_tool_hook_says_something_different():
    """The refusal string goes back to the MODEL. "Denied" tells it to find
    another way; for a tool the owner would have approved, that means working
    around a gate nobody answered."""
    msg = G.gate_tool("send_email", {"to": "someone"})
    check("a timed-out tool call is refused", msg is not None)
    if msg:
        check("and does not call it a refusal by a person",
              "nobody answered" in msg, f"got {msg!r}")
        check("and says nothing was decided",
              "Nothing was decided" in msg, f"got {msg!r}")


def t_the_refused_tiers_are_marked():
    v = G.check("post_to_external_service", {"url": "https://example.test"},
                prompt="post somewhere")  # an ACTION name, which check() takes
    check("a never-tier refusal is 'refused', not 'denied'",
          v.outcome == "refused" and v.allowed is False, f"got {v}")
    check("and it is not mistaken for a timeout", v.timed_out is False)


def t_the_auto_approve_flag_does_not_bypass_anything():
    """confirm_auto used to return True for tier `ask` with nobody asked.

    That is an approve-all by definition: it granted every future, unnamed
    `ask` action for the life of the process on one flag typed once. It had
    no callers, which is the only reason it never granted anything - but a
    blanket grant with no caller is still a blanket grant sitting in the
    module that enforces the rule, looking intended.

    Found by the invariant test below, on its first run.
    """
    # The shape confirm() is actually handed. `_TOOL_PROMPT` is
    # "Allow execution of tool 'x' with args {}?" - the first version of this
    # test invented "tool read_file {}", which matches nothing, classifies as
    # unclassified_action, and so falls to tier ask. It failed for the right
    # reason and told me my prompt was wrong.
    def ask(tool, args="{}"):
        return f"Allow execution of tool '{tool}' with args {args}?"

    # `calculator` is listed in _TOOL_ACTIONS as the tier literal "auto", so
    # it needs no entry in the stub table above at all.
    check("an auto-tier action still passes through it",
          G.confirm_auto(ask("calculator")) is True,
          "the flag must not make things WORSE than no flag")

    # The load-bearing one. tier `ask`, nobody answers, one-second timeout.
    started = time.time()
    got = G.confirm_auto(ask("send_email"))
    took = time.time() - started
    check("an ask-tier action is NOT granted by the flag", got is False,
          "this returning True is the approve-all")
    check("and it actually waited for a human rather than refusing instantly",
          took >= 0.5, f"returned in {took:.2f}s - it did not go through the gate")

    check("a never-tier action is still refused",
          G.confirm_auto(ask("shell_exec", "rm -rf /")) is False)


def _code_only(text: str) -> str:
    """The source with comments and docstrings removed.

    `ast.unparse` of the parsed module drops comments outright and, once the
    docstring nodes are stripped, leaves only executable code plus string
    literals that are actually used as values.
    """
    import ast
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef,
                             ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                # Replaced rather than deleted: a function whose only statement
                # is its docstring would become a syntax error.
                body[0] = ast.Pass()
    return ast.unparse(tree)


def t_there_is_still_no_approve_all():
    """The claim in docs/ARCHITECTURE.md, asserted against the source.

    Reading the file rather than trusting a comment, because a prose claim
    about code is the thing that goes stale first - see docs/PEERS.md on
    cline's docs describing three toggles their UI had already removed.
    """
    src = (BACKEND / "jarvis_gate.py")
    if not src.is_file():
        check("the gate source is readable", False, f"no {src}")
        return
    text = src.read_text(encoding="utf-8")

    # A decision is per-id. `decide` taking one id is the shape that makes a
    # bulk form impossible without a new function.
    check("decide() takes a single request id",
          "def decide(request_id" in text or "def decide(rid" in text,
          "a decide() over a list would be an approve-all by another name")

    # Identifiers, not prose. These words appear in this module's comments and
    # docstrings on purpose - describing what other projects did and what this
    # one must not do - and in docs/PEERS.md at length. What must not exist is
    # a code path.
    #
    # Comments and docstrings are removed with `ast` rather than by guessing at
    # lines: the first version of this check skipped lines containing a triple
    # quote, which missed every line in the MIDDLE of a docstring, and then
    # reported the word "approve_all" from a comment explaining why there is no
    # approve_all. A test that cannot tell code from prose about code is worse
    # than no test, because it will be silenced rather than fixed.
    code = _code_only(text)
    banned = ["approve_all", "approveAll", "allow_all", "allowAll",
              "yolo", "autoApprove", "bypass_approvals"]
    found = [b for b in banned if b in code]
    check("no blanket-grant identifier exists in the gate code",
          not found, f"found {found}")

    # confirm_auto is the one that was real. It is kept as a symbol so
    # anything wired to it still resolves, but it must delegate.
    check("confirm_auto delegates to confirm rather than returning True",
          "return confirm(prompt)" in text,
          "it used to `return True` for tier ask with nobody asked")
    check("and the old bypass is gone",
          '_audit("gate.auto_approved_by_flag"' not in text)

    # The literal that would turn every unclassified action into a pass. The
    # audit's own finding was that `allowed` is True on tier notify, so the
    # unknown default is the load-bearing one.
    check("an unclassified action defaults to ask",
          'UNKNOWN_TIER = str(_cfg("autonomy", "unknown_action_tier", "ask"))' in text,
          "the fallback tier is what an unlisted tool gets")

    # Only three outcomes may run. Asserted on the type, which is the one
    # place a fourth could be added without touching a branch.
    check("only auto, notify and approved can carry allowed=True",
          'self.outcome not in ("auto", "notify", "approved")' in text)


def main():
    for fn in (t_the_type_fails_closed, t_nobody_answered_is_timed_out_not_denied,
               t_a_real_denial_is_denied,
               t_a_denial_proposes_a_constraint_never_writes_one,
               t_a_no_on_an_always_ask_card_proposes_nothing,
               t_a_timeout_never_proposes_anything,
               t_an_approval_is_approved,
               t_an_approval_nobody_stamped_is_refused,
               t_approved_written_straight_into_the_database_is_refused,
               t_the_tool_hook_says_something_different,
               t_the_refused_tiers_are_marked,
               t_the_auto_approve_flag_does_not_bypass_anything,
               t_there_is_still_no_approve_all):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
