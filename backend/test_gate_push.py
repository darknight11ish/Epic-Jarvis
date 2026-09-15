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
import ast, json, re, sys, types, traceback
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


def t_call_sites_redact():
    """CONTROL. The rule lives at the call sites; _push cannot enforce it."""
    src = (BACKEND / "jarvis_gate.py").read_text()
    calls = [n for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_push"]
    check("both _push call sites are present", len(calls) == 2, f"found {len(calls)}")
    for i, call in enumerate(calls):
        body_src = ast.unparse(call.args[1]) if len(call.args) > 1 else ""
        check(f"call site {i + 1} redacts before sending",
              "_safe_detail" in body_src,
              f"line {call.lineno}: {body_src[:90]}")
        check(f"call site {i + 1} does not fall back to the raw prompt",
              "prompt" not in body_src,
              f"line {call.lineno}: {body_src[:90]}")


if __name__ == "__main__":
    for fn in (t_redact_keeps_shape_drops_values, t_push_sends_only_what_it_was_given,
               t_the_push_redaction_does_not_ride_the_logging_switch,
               t_push_refuses_while_tainted, t_call_sites_redact):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    sys.exit(1 if FAILED else 0)
