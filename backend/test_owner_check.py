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
CASES = REPO / "jarvis-desktop" / "tests" / "fixtures" / "risky-approval-cases.json"
RULES_RS = REPO / "jarvis-desktop" / "src-tauri" / "src" / "lock" / "rules.rs"
SECURITY_KT = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis"
               / "client" / "data" / "Security.kt")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _case_rows() -> dict:
    return {c["name"]: c for c in json.loads(CASES.read_text(encoding="utf-8"))["cases"]}


def _risky_row(rid="r1", expires_in=150):
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
           ("", None), ("not an address", None), (None, None)]   # cannot be placed: asks
    no = [("100.101.102.103", "100.64.0.5"),    # the phone over Tailscale
          ("192.168.1.44", "192.168.1.20"),     # another device at home
          ("fe80::1%eth0", "fe80::2%eth0")]
    for peer, local in yes:
        if not OC.from_this_pc(peer, local, own=own):
            check(f"{peer!r} -> {local!r} counts as this PC", False)
    for peer, local in no:
        if OC.from_this_pc(peer, local, own=own):
            check(f"{peer!r} -> {local!r} counts as another device", False)
    check("the rule, all cases", True)
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
    row = _risky_row("r4")
    _fresh_stamps()
    OC.set_verifier(None)
    got = OC.approve_check({"id": "r4"}, peer="127.0.0.1", pending=lambda: [row], own=())
    if sys.platform == "win32":
        check("(on Windows the real check runs; skipped)", True)
        return
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
    call = text[i:i + 200]
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
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
