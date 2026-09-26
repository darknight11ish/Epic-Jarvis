"""jarvis_mcp.py - the MCP bridge, and the promises it makes about the gate.

Every test here runs against a REAL child process (fake_mcp_server.py) over
real pipes, not a mocked transport - the tree-kill, the framing and the
server-initiated requests are only worth testing for real.

    python3 test_mcp.py

Runs on Linux (the dev container). Written to run on Windows too, but NOT
yet run there. On Linux the Windows job-object code is exercised only against
a fake kernel32 (t_windows_code_paths_against_a_fake_kernel32).
"""
import inspect
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import tokenize
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jarvis_mcp as M  # noqa: E402

FAKE = str(HERE / "fake_mcp_server.py")
FAILED, PASSED = [], []
TMP = tempfile.mkdtemp(prefix="mcp-test-")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class NoNetwork:
    """Any socket connect or bind in this block is a failure."""

    def __enter__(self):
        self.c, self.b = socket.socket.connect, socket.socket.bind

        def boom(*a, **k):
            raise AssertionError("a socket was opened")
        socket.socket.connect = boom
        socket.socket.bind = boom
        return self

    def __exit__(self, *a):
        socket.socket.connect, socket.socket.bind = self.c, self.b
        return False


class V:
    """Shaped like jarvis_gate.Verdict after gate-outcome.patch."""

    def __init__(self, allowed, tier, action, outcome, request_id=None, reason=""):
        self.allowed, self.tier, self.action = allowed, tier, action
        self.outcome, self.request_id, self.reason = outcome, request_id, reason


class Gate:
    """Records every check. `mode` decides the answer."""

    def __init__(self, mode="approve"):
        self.mode, self.calls, self.n = mode, [], 0

    def __call__(self, action, detail, prompt=""):
        self.calls.append((action, detail, prompt))
        self.n += 1
        m = self.mode(action) if callable(self.mode) else self.mode
        if m == "approve":
            return V(True, "ask", action, "approved", request_id=f"r{self.n}")
        if m == "notify":
            return V(True, "notify", action, "notify")
        if m == "auto":
            return V(True, "auto", action, "auto")
        if m == "timeout":
            return V(False, "ask", action, "timed_out", request_id=f"r{self.n}")
        return V(False, "ask", action, "denied", request_id=f"r{self.n}", reason="denied by a human")


def section(*extra, tools=None, below=(), env=None, timeout=5, enabled=True, cmd=None):
    return {"enabled": enabled, "servers": {"fake": {
        "command": cmd or sys.executable, "args": [FAKE, *extra],
        "tools": tools or {}, "below_ask_ok": list(below), "env": env or {},
        "timeout_sec": timeout, "start_timeout_sec": 10}}}


def bridge(*extra, gate=None, clock=None, **kw):
    servers = M.parse_config(section(*extra, **{k: v for k, v in kw.items()
                                                 if k in ("tools", "below", "env", "timeout")}))
    b = M.Bridge(servers, gate_check=gate or Gate(), work_root=TMP,
                 clock=clock or time.monotonic,
                 **{k: v for k, v in kw.items() if k in ("on_outside_text", "max_line_bytes")})
    return b


_PINS = {}


def pins():
    """The real pins of the fake server's tools, read by listing them."""
    if not _PINS:
        b = bridge()
        b.start("fake")
        for t in b.list_tools_raw("fake"):
            _PINS[t["name"]] = M.pin_of(t)
        b.shutdown()
    return _PINS


def tools(*names, **overrides):
    p = pins()
    out = {n: {"pin": p[n]} for n in names}
    for n, extra in overrides.items():
        out.setdefault(n, {"pin": p.get(n, "sha256:" + "0" * 64)}).update(extra)
    return out


def alive(pid):
    if os.name == "nt":
        # os.kill(pid, 0) on Windows sends CTRL_C_EVENT - never use it here.
        import ctypes
        k32 = ctypes.WinDLL("kernel32")
        h = k32.OpenProcess(0x1000, False, pid)      # QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        try:
            k32.GetExitCodeProcess(h, ctypes.byref(code))
        finally:
            k32.CloseHandle(h)
        return code.value == 259                     # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        with open(f"/proc/{pid}/status") as f:
            return "\nState:\tZ" not in f.read()
    except OSError:
        return True


def wait_for(cond, secs=5.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


def logged(path):
    try:
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []


# ---------------------------------------------------------------------------

def t_config_only_lists_what_the_owner_wrote():
    check("no [mcp] enabled = true means no servers at all",
          M.parse_config({"servers": section()["servers"]}) == {})
    check("enabled = false means no servers", M.parse_config(section(enabled=False)) == {})

    def refused(sec, needle):
        try:
            M.parse_config(sec)
        except M.ConfigError as exc:
            return needle.lower() in str(exc).lower()
        return False
    s = section()
    s["servers"]["fake"]["command"] = "python"
    check("a bare program name is refused - no PATH search", refused(s, "full path"))
    s = section()
    s["servers"]["fake"]["transport"] = "http"
    check("a network transport is refused", refused(s, "stdio"))
    check("a secret written in plain text is refused",
          refused(section(env={"GITHUB_TOKEN": "ghp_abc"}), "Credential Manager"))
    check("a secret by reference is fine",
          bool(M.parse_config(section(env={"GITHUB_TOKEN": "credman:jarvis/github"}))))
    check("a tool with no pin is refused",
          refused(section(tools={"echo": {}}), "pin"))
    check("a .cmd with cmd.exe metacharacters is refused",
          refused(section("a&calc", cmd="/opt/node/npx.cmd"), "cmd.exe"))
    s = section()
    s["servers"]["Bad__Name"] = s["servers"].pop("fake")
    check("server names are constrained", refused(s, "server names"))
    npx = M.parse_config(section(cmd="/usr/bin/npx"))["fake"]
    node = M.parse_config(section(cmd="/usr/bin/node"))["fake"]
    check("npx is recognised as downloading code", npx.downloads and not node.downloads)


def t_planning_starts_nothing_and_opens_nothing():
    os.environ["JARVIS_TEST_SECRET"] = "hunter2-do-not-show"
    cfg = M.parse_config(section(env={"MY_API_TOKEN": "env:JARVIS_TEST_SECRET"}))["fake"]
    real = subprocess.Popen

    def no_spawn(*a, **k):
        raise AssertionError("a process was started")
    subprocess.Popen = no_spawn
    try:
        with NoNetwork():
            p = M.plan_start(cfg, TMP)
            card = M.describe_start(p)
    finally:
        subprocess.Popen = real
    check("the start card prints the whole command", FAKE in card and sys.executable in card)
    check("it names the setting passed in", "MY_API_TOKEN" in card, card)
    check("but never its value", "hunter2" not in card and "hunter2" not in repr(p))
    check("it says what refusing costs", "If you say no" in card)
    check("it says Jarvis cannot limit the program", "cannot see or limit" in card)
    check("the start action is its own gate action", p.action == "mcp_start__fake")


def t_starting_is_gated_and_needs_a_human():
    spawned = []
    real = subprocess.Popen

    class Spy(real):
        def __init__(self, *a, **k):
            spawned.append(a[0])
            super().__init__(*a, **k)
    subprocess.Popen = Spy
    try:
        for mode in ("deny", "auto", "notify", "timeout"):
            spawned.clear()
            g = Gate(mode)
            b = bridge(gate=g)
            res = b.start("fake")
            check(f"start with gate answer {mode!r} is refused", not res["ok"], res)
            check(f"and nothing was started ({mode})", spawned == [], spawned)
            check(f"and the gate was asked about mcp_start__fake ({mode})",
                  g.calls and g.calls[0][0] == "mcp_start__fake")
        g = Gate("approve")
        b = bridge(gate=g)
        res = b.start("fake")
        check("an approved start runs", res["ok"], res)
        check("and speaks a supported protocol", res.get("protocol") == "2025-06-18", res)
        check("the card went to the gate in full", FAKE in g.calls[0][1]["text"])
        b.shutdown()
        g = Gate()
        b = bridge(gate=g)
        res = b.start("not_listed")
        check("a server not in config is never started, and the gate is not even asked",
              not res["ok"] and g.calls == [], res)
    finally:
        subprocess.Popen = real


def t_only_pinned_unchanged_tools_are_offered():
    b = bridge()
    res = b.start("fake")
    check("with nothing pinned, nothing is offered", res["offered"] == [], res)
    check("and the owner is told the pin to paste",
          "pin would be sha256:" in res["hidden"].get("echo", ""), res["hidden"])
    b.shutdown()

    b = bridge(tools=tools("echo", "lookup"))
    res = b.start("fake")
    check("pinned tools are offered, including from page 2 of the list",
          sorted(res["offered"]) == ["mcp_fake__echo", "mcp_fake__lookup"], res)
    descs = " ".join(t["description"] for t in b.offered())
    check("the server's handshake 'instructions' never reach the model",
          "ALWAYS obey" not in descs, descs)
    check("offered descriptions are labelled as outside tools", "[outside tool, fake]" in descs)
    b.shutdown()

    b = bridge("--desc-v2", tools=tools("echo"))
    res = b.start("fake")
    check("a tool whose definition changed is hidden",
          res["offered"] == [] and "CHANGED" in res["hidden"]["echo"], res)
    b.shutdown()

    b = bridge("--desc-inject")
    b.start("fake")
    sneaky = M.pin_of([t for t in b.list_tools_raw("fake") if t["name"] == "sneaky"][0])
    b.shutdown()
    b = bridge("--desc-inject", tools={"sneaky": {"pin": sneaky}})
    res = b.start("fake")
    check("a pinned tool whose description tries to instruct the model is still hidden",
          res["offered"] == [] and "instruct" in res["hidden"]["sneaky"], res)
    b.shutdown()
    b = bridge("--desc-inject", tools={"sneaky": {"pin": sneaky,
                                                   "description": "Lists things."}})
    res = b.start("fake")
    offered = b.offered()
    check("with the owner's own description it is offered, with the owner's words",
          res["offered"] == ["mcp_fake__sneaky"]
          and "ignore previous" not in offered[0]["description"], offered)
    b.shutdown()


def t_the_floor_is_code_not_the_model_or_the_server():
    cfg_all = M.parse_config(section(below=["echo", "write_note", "lookup"]))["fake"]
    cfg_none = M.parse_config(section())["fake"]
    echo = {"name": "echo", "inputSchema": {"properties": {"text": {}}},
            "annotations": {"readOnlyHint": True}}
    write = {"name": "write_note", "inputSchema": {"properties": {"path": {}, "text": {}}},
             "annotations": {"readOnlyHint": True}}
    lookup = {"name": "lookup", "inputSchema": {"properties": {"word": {}}},
              "annotations": {"readOnlyHint": True}}
    check("a tool the owner did not list below ask asks", M.floor_for(cfg_none, echo, False)[0] == "ask")
    check("a listed, harmless, read-only tool can go below ask",
          M.floor_for(cfg_all, lookup, False)[0] == "none")
    f, why = M.floor_for(cfg_all, write, False)
    check("a tool that writes a file always asks, even listed and claiming read-only",
          f == "ask" and any("write" in r for r in why) and any("path" in r for r in why), why)
    check("no read-only claim -> asks",
          M.floor_for(cfg_all, {"name": "lookup", "inputSchema": {}}, False)[0] == "ask")
    check("destructiveHint raises", "destroy" in " ".join(M.risky_reasons(
        {"name": "lookup", "annotations": {"readOnlyHint": True, "destructiveHint": True}})))
    check("the rush latch raises", M.floor_for(cfg_all, lookup, True)[0] == "ask")
    check("camelCase names are split before checking",
          M.risky_reasons({"name": "sendEmail", "annotations": {"readOnlyHint": True}}) != [])
    check("the description is NOT read (a server could word it to dodge the check)",
          M.risky_reasons({"name": "lookup", "description": "deletes everything",
                           "annotations": {"readOnlyHint": True}}) == [])


def t_a_call_needs_the_right_verdict_once():
    b = bridge(tools=tools("echo", "lookup"), below=["lookup"])
    b.start("fake")
    p = b.plan_call("mcp_fake__echo", {"text": "hi"})
    check("echo was not listed below ask, so it asks", p.floor == "ask")
    r = b.run(p, verdict=V(True, "notify", p.action, "notify"))
    check("a notify verdict does not satisfy an ask floor", not r["ok"] and "ask" in r["error"], r)
    p = b.plan_call("mcp_fake__echo", {"text": "hi"})
    r = b.run(p, verdict=None)
    check("no verdict at all is refused", not r["ok"], r)
    p = b.plan_call("mcp_fake__echo", {"text": "hi"})
    r = b.run(p, verdict=V(True, "ask", "mcp__fake__lookup", "approved", "x1"))
    check("a verdict for another action is refused", not r["ok"] and "different" in r["error"], r)
    p = b.plan_call("mcp_fake__echo", {"text": "hi"})
    good = V(True, "ask", p.action, "approved", "x2")
    r = b.run(p, verdict=good)
    check("an approved verdict runs it", r.get("ok") and r["content"] == "echo: hi", r)
    check("the result is marked untrusted", r.get("untrusted") and r.get("source") == "mcp:fake/echo")
    r = b.run(p, verdict=V(True, "ask", p.action, "approved", "x3"))
    check("a plan runs once", not r["ok"] and "already run" in r["error"], r)
    p2 = b.plan_call("mcp_fake__echo", {"text": "again"})
    r = b.run(p2, verdict=good)
    check("an approval is used once", not r["ok"] and "already used" in r["error"], r)
    p = b.plan_call("mcp_fake__lookup", {"word": "cat"})
    check("lookup is listed below ask", p.floor == "none")
    r = b.run(p, verdict=V(True, "notify", p.action, "notify"))
    check("so the gate's own notify tier stands for it", r.get("ok"), r)
    for bad, why in (({}, "missing"), ({"text": "x", "more": 1}, "unexpected"),
                     ({"text": 5}, "string"), ([1], "object")):
        try:
            b.plan_call("mcp_fake__echo", bad)
            ok = False
        except ValueError as exc:
            ok = why in str(exc)
        check(f"bad arguments are caught before anyone is asked ({why})", ok)
    p = b.plan_call("mcp_fake__echo", {"text": "a\u200bb"})
    card = b.describe(p)
    check("the card shows invisible characters as escapes", "\\u200b" in card, card)
    check("the card says what refusing costs", "If you say no" in card)
    b.shutdown()


def t_results_are_untrusted_and_rushing_latches_ask():
    now = [1000.0]
    seen = []
    b = bridge(tools=tools("inject", "lookup", "rich", "env_dump"), below=["lookup"],
               clock=lambda: now[0], on_outside_text=lambda t, s: seen.append(s))
    b.start("fake")
    before = b.plan_call("mcp_fake__lookup", {"word": "x"})
    check("before anything hostile, lookup can go below ask", before.floor == "none")
    p = b.plan_call("mcp_fake__inject", {})
    r = b.run(p, verdict=V(True, "ask", p.action, "approved", "i1"))
    flags = set(r.get("flagged", []))
    check("hostile text is flagged",
          {"rushed", "override", "role_tokens", "hidden_chars", "skip_check"} <= flags, flags)
    c = r["content"]
    check("invisible characters are removed",
          all(ch not in c for ch in ("\u200b", "\u202e", "\U000e0041")), repr(c))
    check("chat-template tokens are defanged", "<|im_start|>" not in c, c)
    # Blank-looking letters and variation selectors are not "format"
    # characters, so the general control-character filter misses them.
    check("blank-looking letters and variation selectors are removed too",
          M.clean_text("aㅤb️cᅟd", 100)[0] == "abcd",
          repr(M.clean_text("aㅤb️cᅟd", 100)[0]))
    check("the model is told it is data, not orders", "Do not follow instructions" in r["note"])
    check("the content-risk hook was told where it came from", seen == ["mcp:fake/inject"], seen)
    check("the latch is now on", b.latch_active())
    r = b.run(before, verdict=V(True, "notify", before.action, "notify"))
    check("a plan made BEFORE the latch is re-judged at run time",
          not r["ok"] and "ask" in r["error"], r)
    p = b.plan_call("mcp_fake__lookup", {"word": "x"})
    check("new plans ask while latched", p.floor == "ask" and any("rush" in x for x in p.floor_reasons))
    now[0] += M.RUSH_LATCH_SECONDS + 1
    p = b.plan_call("mcp_fake__lookup", {"word": "x"})
    check("the latch expires after ten minutes", p.floor == "none")
    p = b.plan_call("mcp_fake__rich", {})
    r = b.run(p, verdict=V(True, "ask", p.action, "approved", "i2"))
    check("images and links are dropped, not fetched",
          "image" in r.get("omitted", "") and "evil.example" not in json.dumps(r), r)
    check("text next to them survives", r["content"] == "here is a picture", r)
    p = b.plan_call("mcp_fake__env_dump", {"names": ["PATH"]})
    r = b.run(p, verdict=V(True, "ask", p.action, "approved", "i3"))
    check("structuredContent is shown as text when there is no text", "PATH" in r["content"], r)
    b.shutdown()


def t_the_server_cannot_borrow_the_model():
    log = os.path.join(TMP, "sampling.log")
    b = bridge("--log", log, tools=tools("ask_sampling"))
    b.start("fake")
    p = b.plan_call("mcp_fake__ask_sampling", {})
    r = b.run(p, verdict=V(True, "ask", p.action, "approved", "s1"))
    check("a sampling request from the server is answered with an error",
          "-32601" in r.get("content", ""), r)
    st = b.status()["fake"]
    check("and counted, by method name only",
          st["refused_server_requests"].get("sampling/createMessage") == 1, st)
    msgs = logged(log)
    init = [m for m in msgs if m.get("method") == "initialize"][0]
    check("initialize declares no client capabilities (no sampling, roots, elicitation)",
          init["params"]["capabilities"] == {}, init)
    check("the server's ping was answered",
          any(m.get("id") == "srv-ping-1" and m.get("result") == {} for m in msgs), msgs[:5])
    b.shutdown()


def t_a_slow_tool_is_cancelled_and_never_retried():
    log = os.path.join(TMP, "slow.log")
    b = bridge("--log", log, tools=tools("slow"), timeout=1)
    b.start("fake")
    p = b.plan_call("mcp_fake__slow", {})
    t0 = time.monotonic()
    r = b.run(p, verdict=V(True, "ask", p.action, "approved", "t1"))
    check("it gives up at the timeout", time.monotonic() - t0 < 4, time.monotonic() - t0)
    check("and says it may have happened anyway, and was not retried",
          not r["ok"] and "may already" in r["error"] and "NOT retried" in r["error"], r)
    wait_for(lambda: any(m.get("method") == "notifications/cancelled" for m in logged(log)))
    msgs = logged(log)
    check("it sent notifications/cancelled",
          any(m.get("method") == "notifications/cancelled" for m in msgs))
    calls = [m for m in msgs if m.get("method") == "tools/call"]
    check("exactly one tools/call was sent", len(calls) == 1, calls)
    b.shutdown()


def t_protocol_abuse():
    b = bridge("--banner", tools=tools("echo"))
    res = b.start("fake")
    check("a stray banner line on stdout is survived", res["ok"], res)
    check("and counted", b.status()["fake"]["bad_lines"] == 1, b.status())
    b.shutdown()
    b = bridge(tools=tools("huge"), max_line_bytes=64 * 1024)
    b.start("fake")
    p = b.plan_call("mcp_fake__huge", {})
    r = b.run(p, verdict=V(True, "ask", p.action, "approved", "h1"))
    check("an oversized message stops the server", not r["ok"], r)
    check("and it is not running any more", not b.status()["fake"]["running"], b.status())
    p = b.plan_call("mcp_fake__huge", {})
    r = b.run(p, verdict=V(True, "ask", p.action, "approved", "h2"))
    check("and it is not restarted on its own", not r["ok"] and "does not restart" in r["error"], r)
    b.shutdown()
    b = bridge("--modern-only")
    res = b.start("fake")
    check("a 2026-07-28-only server fails with a message that says why",
          not res["ok"] and "2026-07-28" in res["error"], res)
    b.shutdown()


def t_the_whole_tree_dies():
    b = bridge(tools=tools("spawn_child"))
    b.start("fake")
    p = b.plan_call("mcp_fake__spawn_child", {})
    r = b.run(p, verdict=V(True, "ask", p.action, "approved", "k1"))
    pid = int(r["content"])
    check("the grandchild is running", alive(pid))
    b.shutdown()
    check("stopping the server kills what it started", wait_for(lambda: not alive(pid)), pid)

    # CONTROL: the shutdown the MCP Python SDK does (close stdin, wait, kill
    # the group only if the leader did not exit in time) leaves this one
    # running. Proves this test can see the failure it guards against.
    pidfile = os.path.join(TMP, "orphan-control.pid")
    p = subprocess.Popen([sys.executable, FAKE, "--orphan", pidfile], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, start_new_session=True)
    wait_for(lambda: os.path.exists(pidfile) and open(pidfile).read().strip())
    opid = int(open(pidfile).read())
    p.stdin.close()
    p.wait(timeout=5)
    check("CONTROL: a polite exit leaves the grandchild alive", alive(opid))
    try:
        os.kill(opid, 9)                 # TerminateProcess on Windows
    except OSError:
        pass

    pidfile = os.path.join(TMP, "orphan.pid")
    b = bridge("--orphan", pidfile)
    b.start("fake")
    wait_for(lambda: os.path.exists(pidfile) and open(pidfile).read().strip())
    opid = int(open(pidfile).read())
    b.shutdown()
    check("Jarvis kills it even when the server exits politely",
          wait_for(lambda: not alive(opid)), opid)


def t_the_server_gets_only_what_it_was_given():
    os.environ["HUD_TOKEN"] = "pairing-secret"
    os.environ["JARVIS_GITHUB_TOKEN"] = "ghp_parent"
    os.environ["JARVIS_TEST_SECRET"] = "hunter2-do-not-show"
    b = bridge(tools=tools("env_dump"), env={"MY_API_TOKEN": "env:JARVIS_TEST_SECRET"})
    b.start("fake")
    p = b.plan_call("mcp_fake__env_dump",
                    {"names": ["HUD_TOKEN", "JARVIS_GITHUB_TOKEN", "MY_API_TOKEN", "PATH"]})
    r = b.run(p, verdict=V(True, "ask", p.action, "approved", "e1"))
    seen = json.loads(r["content"])
    check("the pairing token is not passed to the server", seen["HUD_TOKEN"] is None, seen)
    check("nor Jarvis's own GitHub token", seen["JARVIS_GITHUB_TOKEN"] is None, seen)
    check("the one key the owner assigned it is", seen["MY_API_TOKEN"] == "hunter2-do-not-show")
    check("PATH is", bool(seen["PATH"]))
    check("the key is not in status()", "hunter2" not in json.dumps(b.status()))
    b.shutdown()
    b = bridge(env={"OTHER_TOKEN": "credman:x"})
    res = b.start("fake")
    if os.name != "nt":
        check("credman: refuses cleanly off Windows", not res["ok"] and "Windows" in res["error"], res)


def t_no_socket_is_ever_opened():
    try:
        with NoNetwork():
            b = bridge(tools=tools("echo"))
            b.start("fake")
            p = b.plan_call("mcp_fake__echo", {"text": "x"})
            b.run(p, verdict=V(True, "ask", p.action, "approved", "n1"))
            b.shutdown()
        ok = True
    except AssertionError as exc:
        ok = False
        print(exc)
    check("start, list, call and stop open no socket", ok)


class _FakeDLL:
    """Records calls; each function answers from `answers`. Accepts the
    argtypes/restype assignments the real code makes."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __getattr__(self, name):
        dll = self

        class Fn:
            argtypes = restype = None

            def __call__(self, *a):
                dll.calls.append((name, a))
                ans = dll.answers.get(name, 1)
                return ans(*a) if callable(ans) else ans
        f = Fn()
        object.__setattr__(self, name, f)
        return f


def t_windows_code_paths_against_a_fake_kernel32():
    """Not proof it works on Windows - proof the Windows-only code runs
    end to end, in the right order, with the right constants, and fails
    closed. Run this AND the real suite on Windows before trusting it."""
    import ctypes
    import threading
    import types
    real_windll, real_popen, real_os = getattr(ctypes, "WinDLL", None), subprocess.Popen, M.os

    class FakePopen:
        def __init__(self, argv, creationflags=0, **k):
            self.argv, self.creationflags, self.pid, self.killed = argv, creationflags, 4242, False

        def poll(self):
            return None if not self.killed else 1

        def kill(self):
            self.killed = True

        def wait(self, timeout=None):
            return 1

    def thread_first(snap, ref):
        te = ref._obj
        te.th32OwnerProcessID, te.th32ThreadID = 4242, 7
        return 1

    def run(assign_ok):
        k32 = _FakeDLL({"CreateJobObjectW": 1234, "OpenProcess": 55,
                        "AssignProcessToJobObject": 1 if assign_ok else 0,
                        "CreateToolhelp32Snapshot": 77, "Thread32First": thread_first,
                        "Thread32Next": 0, "OpenThread": 88, "ResumeThread": 1})
        ctypes.WinDLL = lambda name, use_last_error=False: k32
        subprocess.Popen = FakePopen
        tree = object.__new__(M._ProcessTree)
        tree.proc, tree._job, tree._klock = None, None, threading.Lock()
        err = None
        try:
            M.os = types.SimpleNamespace(name="nt", **{k: getattr(real_os, k) for k in
                                                        ("path", "environ", "getpid")})
            tree._spawn_windows(["C:\\x\\node.exe", "s.js"], {}, 512)
        except M.BridgeError as exc:
            err = exc
        finally:
            M.os = real_os
        return k32, tree, err

    try:
        k32, tree, err = run(True)
        names = [c[0] for c in k32.calls]
        check("windows: no error on the happy path", err is None, err)
        check("windows: job made and configured BEFORE the process is created",
              names.index("SetInformationJobObject") < names.index("OpenProcess"), names)
        check("windows: the process is created suspended, windowless, own group",
              tree.proc.creationflags == 0x4 | 0x08000000 | 0x200, hex(tree.proc.creationflags))
        info_call = [c for c in k32.calls if c[0] == "SetInformationJobObject"][0]
        info = info_call[1][2]._obj
        check("windows: kill-on-close + die-on-exception + memory limit are set",
              info.BasicLimitInformation.LimitFlags == 0x2000 | 0x400 | 0x200
              and info.JobMemoryLimit == 512 * 1024 * 1024 and info_call[1][1] == 9)
        check("windows: it is assigned to the job, THEN resumed",
              names.index("AssignProcessToJobObject") < names.index("ResumeThread"), names)
        check("windows: only the child's own thread is resumed",
              [c for c in k32.calls if c[0] == "OpenThread"][0][1][2] == 7)
        M.os = types.SimpleNamespace(name="nt")
        try:
            tree.kill_tree()
            tree.kill_tree()
        finally:
            M.os = real_os
        terms = [c for c in k32.calls if c[0] == "TerminateJobObject"]
        check("windows: stopping terminates the job exactly once, even if called twice",
              len(terms) == 1 and terms[0][1][0] == 1234, terms)

        k32, tree, err = run(False)
        names = [c[0] for c in k32.calls]
        check("windows: if it cannot be put in the job, start is REFUSED",
              isinstance(err, M.BridgeError) and "refused" in str(err), err)
        check("windows: and the half-started process is killed, never resumed",
              "TerminateJobObject" in names and "ResumeThread" not in names, names)

        def cred_read(target, typ, flags, ref):
            ptr = ref._obj
            cred = ptr._type_()
            blob = (ctypes.c_ubyte * 10)(*"s3cr3".encode("utf-16-le"))
            cred.CredentialBlobSize, cred.CredentialBlob = 10, ctypes.cast(
                blob, ctypes.POINTER(ctypes.c_ubyte))
            keep.append((cred, blob))
            ptr.contents = cred
            return 1 if target == "jarvis/mcp/x" and typ == 1 else 0
        keep = []
        adv = _FakeDLL({"CredReadW": cred_read, "CredFree": None})
        ctypes.WinDLL = lambda name, use_last_error=False: adv
        M.os = types.SimpleNamespace(name="nt")
        try:
            got = M._credman_read("jarvis/mcp/x")
            try:
                M._credman_read("missing")
                missing_ok = False
            except M.BridgeError as exc:
                missing_ok = "no Windows Credential Manager entry" in str(exc)
        finally:
            M.os = real_os
        check("windows: a generic credential is read as UTF-16 and freed",
              got == "s3cr3" and any(c[0] == "CredFree" for c in adv.calls), got)
        check("windows: a missing credential is a clear refusal", missing_ok)
    finally:
        subprocess.Popen = real_popen
        M.os = real_os
        if real_windll is None:
            del ctypes.WinDLL
        else:
            ctypes.WinDLL = real_windll


def t_there_is_no_approve_all_and_run_has_no_default():
    sig = inspect.signature(M.Bridge.run)
    check("run() has no default verdict",
          sig.parameters["verdict"].default is inspect.Parameter.empty)
    names = set()
    with open(M.__file__, "rb") as f:
        for tok in tokenize.tokenize(f.readline):
            if tok.type == tokenize.NAME:
                names.add(tok.string.lower())
    bad = {n for n in names if "approve_all" in n or "auto_approve" in n
           or "approveall" in n or "autoapprove" in n}
    check("no identifier anywhere is an approve-all", not bad, bad)


if __name__ == "__main__":
    for fn in (t_config_only_lists_what_the_owner_wrote,
               t_planning_starts_nothing_and_opens_nothing,
               t_starting_is_gated_and_needs_a_human,
               t_only_pinned_unchanged_tools_are_offered,
               t_the_floor_is_code_not_the_model_or_the_server,
               t_a_call_needs_the_right_verdict_once,
               t_results_are_untrusted_and_rushing_latches_ask,
               t_the_server_cannot_borrow_the_model,
               t_a_slow_tool_is_cancelled_and_never_retried,
               t_protocol_abuse,
               t_the_whole_tree_dies,
               t_the_server_gets_only_what_it_was_given,
               t_no_socket_is_ever_opened,
               t_windows_code_paths_against_a_fake_kernel32,
               t_there_is_no_approve_all_and_run_has_no_default):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
