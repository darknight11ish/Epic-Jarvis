"""The approval gate must not post private content to a public broker.

jarvis_gate._redact exists because, in its own words, the gate "is handed
exactly the sensitive part - the recipient of the email, the path of the file,
the body of the shell command - so writing `detail` verbatim would turn the
audit trail into the leak it exists to detect."

The local audit log honoured that. The ntfy push, 130 lines below, sent the
identical dict verbatim to https://ntfy.sh/<topic> - a URL with no
authentication, where the topic name is the only secret and it travels in the
path. On tier `notify` that fires with no human in the loop at all.

    python3 test_gate_push.py

Runs against a stubbed network and a stubbed framework module. No requests are
made and no approvals database is touched.
"""
import ast, copy, json, re, sys, types, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# BACKEND is where the modules under test actually live - this folder
# in the dev container, $JARVIS_BACKEND on a real install. REPO is this
# repository. They used to be the same path and are not on the machine
# that runs Jarvis.
from _where import BACKEND, REPO, missing, explain

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


# A framework stub: redaction ON, which is the default the real one uses.
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = HERE / "_cfg"
fw.LOG_DIR = HERE / "_cfg"
fw.load_framework = lambda: {"logging": {"redact_private_content_in_logs": True}}
fw.audit_log = lambda *a, **k: None
sys.modules["jarvis_framework"] = fw

import jarvis_gate as G

SENSITIVE = {
    "command": "grep -r 'password' /home/mario/.env",
    "cwd": "/home/mario",
    "recipient": "dr.okafor@clinic.example",
    "note": "Lucia peanut allergy - reschedule Thursday 4pm",
}
SECRETS = ["password", "/home/mario", "dr.okafor@clinic.example", "Lucia", "peanut"]


def captured(body, *, tainted=False):
    """Run _push with the network and the latch stubbed, return what was sent."""
    sent = []
    real_open, real_topic, real_taint = None, G.NTFY_TOPIC, G.taint_active
    import urllib.request
    real_open = urllib.request.urlopen

    class Fake:
        def __init__(self, req): sent.append(req)
        def close(self): pass

    urllib.request.urlopen = lambda req, timeout=None: Fake(req)
    G.NTFY_TOPIC = "jarvis-test-topic"
    G.taint_active = lambda: tainted
    try:
        G._push("Jarvis wants to: send_email", body)
        for t in list(getattr(G, "threading").enumerate()):
            if t.name != "MainThread" and t.is_alive():
                t.join(timeout=2)
    finally:
        urllib.request.urlopen = real_open
        G.NTFY_TOPIC = real_topic
        G.taint_active = real_taint
    return [r.data.decode("utf-8", "replace") for r in sent]


def t_redact_keeps_shape_drops_values():
    out = G._redact(SENSITIVE)
    blob = json.dumps(out)
    leaked = [s for s in SECRETS if s in blob]
    check("_redact drops every sensitive value", not leaked, f"leaked: {leaked}")
    check("CONTROL _redact keeps the keys, so the alert still means something",
          set(out) == set(SENSITIVE), f"got {sorted(out)}")


def t_push_sends_only_what_it_was_given():
    body = json.dumps(G._redact(SENSITIVE))
    got = captured(body)
    check("a redacted body reaches the broker unchanged", got == [body], f"{got}")
    leaked = [s for s in SECRETS if any(s in g for g in got)]
    check("nothing sensitive is on the wire", not leaked, f"leaked: {leaked}")


def t_push_refuses_while_tainted():
    got = captured(json.dumps(G._redact(SENSITIVE)), tainted=True)
    check("no push at all while the conversation is latched local", got == [],
          f"sent {len(got)} message(s) during a taint window")


def t_the_push_redaction_does_not_ride_the_logging_switch():
    """_redact is the wrong function for this path, and it took a review to see it.

    _redact opens by consulting [logging].redact_private_content_in_logs and
    returning `detail` verbatim if it is false. That key is named for LOGS -
    someone might reasonably turn it off while debugging on their own machine -
    and it would then also switch off redaction on a path that POSTs to a
    public unauthenticated broker. An on-disk log is behind the file system;
    an ntfy.sh topic is behind a guess. They are not the same decision and
    must not share a switch.
    """
    out = G._safe_detail(SENSITIVE, 400)
    leaked = [s for s in SECRETS if s in out]
    check("_safe_detail leaks nothing", not leaked, f"leaked: {leaked} in {out!r}")
    check("CONTROL: it still names the fields, so the alert means something",
          all(k in out for k in SENSITIVE), out)

    # The point of the test: flip the logging switch off and it must not care.
    import types as _t
    real = G.fw.load_framework
    G.fw.load_framework = lambda *a, **k: {
        "logging": {"redact_private_content_in_logs": False}}
    try:
        off = G._safe_detail(SENSITIVE, 400)
        leaked = [s for s in SECRETS if s in off]
        check("turning the LOGGING switch off does not un-redact the PUSH",
              not leaked, f"leaked: {leaked}")
        # CONTROL: prove the switch is real and that _redact does obey it, so
        # this test is measuring a difference rather than a no-op.
        loose = json.dumps(G._redact(SENSITIVE))
        check("CONTROL: _redact DOES obey it, which is why it is the wrong "
              "function here", any(s in loose for s in SECRETS),
              "the switch did nothing - this test proves nothing")
    finally:
        G.fw.load_framework = real

    check("a detail that will not serialise cannot raise on this path",
          isinstance(G._safe_detail({"x": object()}, 100), str))
    check("an empty detail says so rather than sending '{}'",
          G._safe_detail({}, 100) == "(no details)", G._safe_detail({}, 100))


# Every source a _push argument is allowed to be built from, and why each one
# is safe by CONSTRUCTION rather than by having been checked:
#
#   _safe_detail(...)  the redactor. Keeps the shape, drops the values, and
#                      does not consult the logging switch.
#   notice_for(...)    reads the action NAME and one boolean, and nothing
#                      else on the row. See approval-notice.patch.
#   _note[...]         the dict notice_for just returned.
#   risk_for(...)      the tier table, keyed by action name.
#   action             an action name out of that same table - never text
#                      anyone typed, and never text a web page supplied.
#
# This list grew when approval-notice.patch replaced `_safe_detail(detail, 400)`
# at both sites with strictly SAFER text: a notice built from the action name
# is not a redacted payload, it never touched the payload. The old assertion
# ("_safe_detail is in the expression") then failed on code that leaks less
# than the code it was written to protect - so the rule is stated as what it
# always meant, and the control below is what actually holds the line.
_SAFE_SOURCES = ("_safe_detail", "notice_for", "_note", "risk_for", "action")

#: Never, in any argument. These are the three locals in jarvis_gate that hold
#: the payload: the request's own detail dict, the prompt text, and the quoted
#: outside text behind `raised`. `detail` is permitted inside a _safe_detail()
#: call, which is why _redacted_names() exists.
_NEVER = ("detail", "prompt", "raised")


def _mask_redacted(node):
    """A copy of the expression with every `_safe_detail(...)` call replaced.

    Not "subtract the names that appear inside a _safe_detail call from the
    names in the whole argument" - that was the first version and it laundered
    a name for the ENTIRE expression. One mention anywhere made the raw name
    free everywhere, so

        _safe_detail(detail, 300) + json.dumps(detail)[:400]

    passed: the second half is the pre-patch line gate-push.patch was written
    to delete, sitting beside the redacted copy. Masking the call and reading
    what is left cannot do that.
    """
    class Mask(ast.NodeTransformer):
        def visit_Call(self, n):
            if getattr(n.func, "id", "") == "_safe_detail":
                return ast.copy_location(ast.Name(id="_REDACTED",
                                                  ctx=ast.Load()), n)
            return self.generic_visit(n)
    return Mask().visit(copy.deepcopy(node))


def _leaks(node):
    """Which payload names this expression reaches, by any route.

    A SOURCE scan over the masked expression, not a walk of Name nodes. The
    node walk missed every indirect route, and they are the likely ones:
    `row['prompt']` is an ast.Constant, `getattr(req, 'prompt')` is a string,
    and an f-string hides both. All three passed a Name-based check while
    putting the request text on an unauthenticated ntfy.sh topic.
    """
    src = ast.unparse(_mask_redacted(node))
    return sorted({w for w in _NEVER if re.search(rf"\b{w}\b", src)})


def t_call_sites_redact():
    """CONTROL. The rule lives at the call sites; _push cannot enforce it."""
    src = (BACKEND / "jarvis_gate.py").read_text()
    calls = [n for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_push"]
    check("both _push call sites are present", len(calls) == 2, f"found {len(calls)}")
    for i, call in enumerate(calls):
        where = f"line {call.lineno}"
        # KEYWORDS TOO. _push is `def _push(title, body)` today, and a check
        # that reads only call.args would be blind to the day it grows a third
        # field - `_push(title, body, extra=prompt)` passed everything.
        args = [(f"arg {j + 1}", a) for j, a in enumerate(call.args)]
        args += [(f"keyword {k.arg}", k.value) for k in call.keywords]
        for label, arg in args:
            leaked = _leaks(arg)
            check(f"call site {i + 1} {label} carries no payload name",
                  not leaked,
                  f"{where}: {ast.unparse(arg)[:90]} reaches {leaked}")
        body_src = ast.unparse(call.args[1]) if len(call.args) > 1 else ""
        check(f"call site {i + 1} builds its body from a safe source",
              any(t in body_src for t in _SAFE_SOURCES),
              f"{where}: {body_src[:90]} is none of {list(_SAFE_SOURCES)}")


def t_the_call_site_check_can_actually_fail():
    """CONTROL ON THE CONTROL. A guard nobody has watched fail is a guess.

    Every expression below leaks, and an earlier version of the check above
    passed four of the six. They are run here rather than described.
    """
    leaky = [
        '_push("t", prompt)',
        '_push("t", json.dumps(detail))',
        '_push("t", raised["quote"])',
        '_push(_note["title"], _note["body"] + f"(id {rid}) {row[\'prompt\']}")',
        '_push("t", getattr(req, "prompt"))',
        '_push("t", _safe_detail(detail, 300) + json.dumps(detail)[:400])',
        '_push("t", _safe_detail(prompt, 300) or prompt[:300])',
    ]
    for code in leaky:
        call = ast.parse(code).body[0].value
        args = list(call.args) + [k.value for k in call.keywords]
        check(f"REJECTED: {code[:58]}", any(_leaks(a) for a in args),
              "this leaks and the check let it through")

    kw = ast.parse('_push(_note["title"], _note["body"], extra=prompt)').body[0].value
    check("REJECTED: a payload smuggled in as a keyword",
          any(_leaks(k.value) for k in kw.keywords))

    # And the three shapes that are SAFE must still pass, or the check is
    # merely strict rather than correct.
    for code in ('_push(f"Jarvis did: {action}", risk_for(action)["why"])',
                 '_push(_note["title"], _note["body"] + f"(id {rid})")',
                 '_push(f"Jarvis wants to: {action}", _safe_detail(detail, 400))'):
        call = ast.parse(code).body[0].value
        args = list(call.args) + [k.value for k in call.keywords]
        body = ast.unparse(call.args[1])
        check(f"ACCEPTED: {code[:58]}",
              not any(_leaks(a) for a in args)
              and any(t in body for t in _SAFE_SOURCES))


if __name__ == "__main__":
    for fn in (t_redact_keeps_shape_drops_values, t_push_sends_only_what_it_was_given,
               t_the_push_redaction_does_not_ride_the_logging_switch,
               t_push_refuses_while_tainted, t_call_sites_redact,
               t_the_call_site_check_can_actually_fail):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    sys.exit(1 if FAILED else 0)
