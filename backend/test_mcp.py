"""jarvis_mcp.py - the plug-in bridge (MCP), and the promises it makes
about the gate.

Every test here runs against a REAL child process (fake_mcp_server.py) over
real pipes, not a mocked transport - the tree-kill, the framing and the
server-initiated requests are only worth testing for real. Moved here from
docs/designs/mcp-draft-2026-09-23/ (feasibility audit I07) so CI runs it,
and extended for version 1's rules: stdio only, nothing fetched at start,
read-only tools only, every call asks a person, jarvis_child_env's
environment, and a start card when a server is added or changes.

    python3 test_mcp.py

Runs on Linux (CI and the dev container). Written to run on Windows too, but
NOT yet run there. On Linux the Windows job-object code is exercised only
against a fake kernel32 (t_windows_code_paths_against_a_fake_kernel32).
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
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_mcp.py", "jarvis_child_env.py")
import jarvis_mcp as M  # noqa: E402

# The fake server is a test file: always this repository's copy.
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


def section(*extra, tools=None, env=None, timeout=5, enabled=True, cmd=None):
    return {"enabled": enabled, "servers": {"fake": {
        "command": cmd or sys.executable, "args": [FAKE, *extra],
        "tools": tools or {}, "env": env or {},
        "timeout_sec": timeout, "start_timeout_sec": 10}}}


def bridge(*extra, gate=None, clock=None, **kw):
    servers = M.parse_config(section(*extra, **{k: v for k, v in kw.items()
                                                 if k in ("tools", "env", "timeout")}))
    b = M.Bridge(servers, gate_check=gate or Gate(), work_root=TMP,
                 clock=clock or time.monotonic,
                 **{k: v for k, v in kw.items() if k in ("on_outside_text", "max_line_bytes",
                                                         "approvals", "audit")})
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


#: The fake server's tools that do not say they are read-only: the tests
#: that call them vouch for them, as the owner would with read_only = true.
_UNCLAIMED = ("inject", "background_helper", "slow", "ask_sampling", "env_dump", "rich",
              "huge")


def tools(*names, **overrides):
    p = pins()
    out = {n: dict({"pin": p[n]}, **({"read_only": True} if n in _UNCLAIMED else {}))
           for n in names}
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
    check("copying one of Jarvis's own settings is refused (it could be the pairing key)",
          refused(section(env={"THING": "env:HUD_TOKEN"}), "never gets those"))
    check("a plain, not-secret setting is fine",
          bool(M.parse_config(section(env={"GIT_PAGER": "cat"}))))
    s = section()
    s["servers"]["fake"]["below_ask_ok"] = ["echo"]
    check("below_ask_ok is refused in version 1 - every call asks", refused(s, "every time"))
    s = section()
    s["servers"]["fake"]["transprot"] = "stdio"
    check("a misspelt setting is refused, not ignored", refused(s, "unknown setting"))
    check("a tool with no pin is refused",
          refused(section(tools={"echo": {}}), "pin"))
    check("a .cmd with cmd.exe metacharacters is refused",
          refused(section("a&calc", cmd="/opt/node/server.cmd"), "cmd.exe"))
    s = section()
    s["servers"]["Bad__Name"] = s["servers"].pop("fake")
    check("server names are constrained", refused(s, "server names"))
    check("npx - which downloads code each time it starts - is refused",
          refused(section(cmd="/usr/bin/npx"), "downloads code"))
    check("so is uvx", refused(section(cmd="/usr/bin/uvx"), "downloads code"))
    s = section()
    s["servers"]["fake"]["command"] = "/usr/bin/npm"
    s["servers"]["fake"]["args"] = ["exec", "some-server"]
    check("and npm exec", refused(s, "downloads code"))
    node = M.parse_config(section(cmd="/usr/bin/node"))["fake"]
    check("a plain program is not treated as downloading", not node.downloads)


def t_planning_starts_nothing_and_opens_nothing():
    os.environ["JARVIS_TEST_SECRET"] = "hunter2-do-not-show"
    cfg = M.parse_config(section(env={"MY_API_TOKEN": "credman:jarvis/test"}))["fake"]
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
    check("it says when it will ask again (a new or changed program)",
          "until the program, its settings or its version change" in card, card)
    check("the start action is its own gate action", p.action == "mcp_start__fake")
    check("the plan carries a fingerprint", p.fingerprint.startswith("sha256:"))


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
    b = bridge("--desc-inject", tools={"sneaky": {"pin": sneaky, "read_only": True,
                                                   "description": "Lists things."}})
    res = b.start("fake")
    offered = b.offered()
    check("with the owner's own description it is offered, with the owner's words",
          res["offered"] == ["mcp_fake__sneaky"]
          and "ignore previous" not in offered[0]["description"], offered)
    b.shutdown()


def t_only_read_only_tools_are_offered():
    b = bridge(tools=tools("echo", "lookup", "write_note", "env_dump") |
               {"inject": {"pin": pins()["inject"]}})
    res = b.start("fake")
    check("tools the program says only read are offered",
          {"mcp_fake__echo", "mcp_fake__lookup"} <= set(res["offered"]), res)
    check("a tool whose NAME says it writes is never offered, even pinned and 'read-only'",
          "mcp_fake__write_note" not in res["offered"]
          and "changes something" in res["hidden"].get("write_note", ""), res["hidden"])
    check("a tool nobody says is read-only is not offered, and the owner is told how",
          "read_only = true" in res["hidden"].get("inject", ""), res["hidden"])
    check("the owner's read_only = true lets a checked tool in",
          "mcp_fake__env_dump" in res["offered"], res)
    b.shutdown()
    r = M.ToolRule(pin="sha256:" + "0" * 64, read_only=True)
    check("the program saying it is NOT read-only wins over the owner",
          M.read_only_problem({"name": "look", "annotations": {"readOnlyHint": False}}, r))
    check("destructive: never", M.read_only_problem(
        {"name": "look", "annotations": {"destructiveHint": True}}, r))
    check("reaches outside systems: never", M.read_only_problem(
        {"name": "look", "annotations": {"openWorldHint": True}}, r))
    for name in ("git_commit", "git_add", "git_reset", "git_checkout", "git_create_branch",
                 "git_init", "sendEmail", "run_query"):
        check(f"{name}: not offered in version 1",
              M.read_only_problem({"name": name, "annotations": {"readOnlyHint": True}}, r))
    for name in ("git_status", "git_diff_unstaged", "git_diff_staged", "git_log", "git_show",
                 "git_branch", "git_diff"):
        check(f"{name}: may be offered (reads)",
              not M.read_only_problem({"name": name, "annotations": {"readOnlyHint": True}},
                                      r))


def t_every_call_asks_a_person():
    cfg = M.parse_config(section())["fake"]
    lookup = {"name": "lookup", "inputSchema": {"properties": {"word": {}}},
              "annotations": {"readOnlyHint": True}}
    check("even a harmless read-only tool asks", M.floor_for(cfg, lookup, False)[0] == "ask")
    f, why = M.floor_for(cfg, {"name": "write_note", "inputSchema": {
        "properties": {"path": {}, "text": {}}}, "annotations": {"readOnlyHint": True}}, False)
    check("the card says why, in words the owner can read",
          any("write" in r for r in why) and any("path" in r for r in why), why)
    check("destructiveHint is named", "destroy" in " ".join(M.risky_reasons(
        {"name": "lookup", "annotations": {"readOnlyHint": True, "destructiveHint": True}})))
    check("the rush latch is named on the card",
          any("rush" in r for r in M.floor_for(cfg, lookup, True)[1]))
    check("camelCase names are split before checking",
          M.risky_reasons({"name": "sendEmail", "annotations": {"readOnlyHint": True}}) != [])
    check("the description is NOT read (a server could word it to dodge the check)",
          M.risky_reasons({"name": "lookup", "description": "deletes everything",
                           "annotations": {"readOnlyHint": True}}) == [])


def t_a_call_needs_the_right_verdict_once():
    b = bridge(tools=tools("echo", "lookup"))
    b.start("fake")
    p = b.plan_call("mcp_fake__echo", {"text": "hi"})
    check("every call's floor is ask", p.floor == "ask")
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
    r = b.run(p, verdict=V(True, "auto", p.action, "auto"))
    check("a tier that lets it through with nobody asked is refused", not r["ok"], r)
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
    b = bridge(tools=tools("inject", "lookup", "rich", "env_dump"),
               clock=lambda: now[0], on_outside_text=lambda t, s: seen.append(s))
    b.start("fake")
    before = b.plan_call("mcp_fake__lookup", {"word": "x"})
    check("before anything hostile, the card gives no rush reason",
          not any("rush" in x for x in before.floor_reasons))
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
    check("a notify verdict is refused at run time", not r["ok"] and "ask" in r["error"], r)
    p = b.plan_call("mcp_fake__lookup", {"word": "x"})
    check("while latched, the card says text tried to rush Jarvis",
          p.floor == "ask" and any("rush" in x for x in p.floor_reasons))
    now[0] += M.RUSH_LATCH_SECONDS + 1
    p = b.plan_call("mcp_fake__lookup", {"word": "x"})
    check("the latch expires after ten minutes; it still asks",
          p.floor == "ask" and not any("rush" in x for x in p.floor_reasons))
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
    b = bridge(tools=tools("background_helper"))
    b.start("fake")
    p = b.plan_call("mcp_fake__background_helper", {})
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
    os.environ["JARVIS_TOKEN"] = "pairing-secret-2"
    os.environ["JARVIS_GITHUB_TOKEN"] = "ghp_parent"
    os.environ["SOME_API_KEY"] = "sk-parent"
    os.environ["JARVIS_IMAP_PASSWORD"] = "mail-pw"
    names = ["HUD_TOKEN", "JARVIS_TOKEN", "JARVIS_GITHUB_TOKEN", "SOME_API_KEY",
             "JARVIS_IMAP_PASSWORD", "GIT_PAGER", "PATH"]
    b = bridge(tools=tools("env_dump"), env={"GIT_PAGER": "cat"})
    b.start("fake")
    p = b.plan_call("mcp_fake__env_dump", {"names": names})
    r = b.run(p, verdict=V(True, "ask", p.action, "approved", "e1"))
    seen = json.loads(r["content"])
    check("the pairing token is not passed to the server",
          seen["HUD_TOKEN"] is None and seen["JARVIS_TOKEN"] is None, seen)
    check("nor Jarvis's own GitHub token, API keys or passwords",
          seen["JARVIS_GITHUB_TOKEN"] is None and seen["SOME_API_KEY"] is None
          and seen["JARVIS_IMAP_PASSWORD"] is None, seen)
    check("the plain setting the owner gave it is", seen["GIT_PAGER"] == "cat", seen)
    check("PATH is", bool(seen["PATH"]))
    import jarvis_child_env
    check("the base is jarvis_child_env's allow-list",
          set(M._child_env(M.parse_config(section())["fake"]))
          == set(jarvis_child_env.inherited()))
    b.shutdown()
    b = bridge(env={"OTHER_TOKEN": "credman:x"})
    res = b.start("fake")
    if os.name != "nt":
        check("credman: refuses cleanly off Windows", not res["ok"] and "Windows" in res["error"], res)


def t_a_card_when_added_and_again_when_changed():
    store = M.ApprovalStore(os.path.join(TMP, "approved-1.json"))
    audit = []
    g = Gate()
    b = bridge(gate=g, approvals=store, audit=lambda e, d: audit.append((e, d)))
    res = b.start("fake")
    check("a new server asks first", res["ok"] and len(g.calls) == 1, res)
    got = store.get("fake")
    check("the approval is remembered: its fingerprint and version",
          got and got["fingerprint"].startswith("sha256:") and got["version"] == "1.0", got)
    b.shutdown()

    g = Gate()
    b = bridge(gate=g, approvals=store, audit=lambda e, d: audit.append((e, d)))
    res = b.start("fake")
    check("the same program again: started with no card", res["ok"] and g.calls == []
          and res.get("remembered"), res)
    check("and written to the audit log", audit and audit[-1][0] == "mcp.start.remembered",
          audit)
    b.shutdown()

    real = M.CARD_EVERY_START
    M.CARD_EVERY_START = True
    try:
        g = Gate()
        b = bridge(gate=g, approvals=store)
        res = b.start("fake")
        check("CARD_EVERY_START = True (one line): every start asks",
              res["ok"] and len(g.calls) == 1, res)
        check("and its card does not promise not to ask again",
              "without asking" not in g.calls[0][1]["text"])
        b.shutdown()
    finally:
        M.CARD_EVERY_START = real

    g = Gate()
    b = bridge("--banner", gate=g, approvals=store)
    res = b.start("fake")
    check("a changed argument asks again", res["ok"] and len(g.calls) == 1, res)
    check("and the card says it changed", "have changed since then" in g.calls[0][1]["text"],
          g.calls[0][1]["text"])
    b.shutdown()

    # The same fingerprint, a different version (an update inside a package
    # the command does not name).
    real_fp = M.fingerprint_of
    M.fingerprint_of = lambda cfg, cwd: "sha256:" + "1" * 64
    try:
        store2 = M.ApprovalStore(os.path.join(TMP, "approved-2.json"))
        b = bridge(gate=Gate(), approvals=store2)
        b.start("fake")
        b.shutdown()
        g = Gate()
        b = bridge("--version", "2.0", gate=g, approvals=store2)
        res = b.start("fake")
        check("a new version asks again", res["ok"] and len(g.calls) == 1, res)
        check("the card names both versions",
              "2.0" in g.calls[0][1]["text"] and "1.0" in g.calls[0][1]["text"],
              g.calls[0][1]["text"])
        check("and the new version is what is remembered now",
              store2.get("fake")["version"] == "2.0")
        b.shutdown()
        g = Gate("deny")
        store3 = M.ApprovalStore(os.path.join(TMP, "approved-3.json"))
        b = bridge(gate=g, approvals=store3)
        res = b.start("fake")
        check("a refused start remembers nothing", not res["ok"] and store3.get("fake") is None)
        b.shutdown()
    finally:
        M.fingerprint_of = real_fp

    a = M.parse_config(section(env={"GIT_PAGER": "cat"}))["fake"]
    b2 = M.parse_config(section(env={"GIT_PAGER": "less"}))["fake"]
    check("a changed plain setting is a changed fingerprint (it asks again)",
          M.fingerprint_of(a, TMP) != M.fingerprint_of(b2, TMP))
    c = M.parse_config(section(env={"A_TOKEN": "credman:jarvis/x"}))["fake"]
    # Reading Credential Manager off Windows raises, so a fingerprint made
    # here proves the key was not read to make it.
    check("a Credential Manager entry counts by its name - the key is never read",
          M.fingerprint_of(c, TMP).startswith("sha256:"))

    open(os.path.join(TMP, "approved-4.json"), "w").write("{not json")
    g = Gate()
    b = bridge(gate=g, approvals=M.ApprovalStore(os.path.join(TMP, "approved-4.json")))
    res = b.start("fake")
    check("a damaged approvals file asks again", res["ok"] and len(g.calls) == 1, res)
    b.shutdown()


def t_an_idle_server_is_stopped():
    now = [100.0]
    b = bridge(tools=tools("echo"), clock=lambda: now[0])
    b.start("fake")
    check("running after start", b.running() == ["fake"])
    now[0] += M.IDLE_STOP_SECONDS - 1
    check("not stopped before the idle time", b.stop_idle() == [] and b.running() == ["fake"])
    now[0] += 2
    check("stopped once idle", b.stop_idle() == ["fake"] and b.running() == [])
    b.shutdown()


def t_the_shared_bridge_reads_the_settings():
    real_load, real_dir = M._load_section, M._config_dir
    M._config_dir = lambda: TMP
    try:
        M._load_section = lambda: {}
        check("no [mcp]: not configured", not M.configured())
        check("and no bridge", M.shared_bridge() is None)
        got = M.turn_tools(object, start=True)
        check("turn_tools says why there is nothing", got["tools"] == {} and got["problems"])
        M._load_section = lambda: {"enabled": True, "servers": {"x": {
            "command": "/usr/bin/npx", "args": ["some-server"]}}}
        check("a bad [mcp] section is not configured", not M.configured())
        st = M.reach_status()
        check("and the reason is there for the reach list",
              "downloads code" in st["problem"] and st["servers"] == [], st)
        sec = section(tools=tools("echo"))
        M._load_section = lambda: sec

        class T:
            def __init__(self, name, description, parameters, prepare, execute,
                         gate_lookup_name=None):
                self.name, self.description, self.parameters = name, description, parameters
                self.prepare, self.execute = prepare, execute
                self.gate_lookup_name = gate_lookup_name
        check("configured", M.configured())
        got = M.turn_tools(T, start=False)
        check("without start, nothing is started", got["tools"] == {}
              and M.reach_status()["running"] == [], got)
        g = Gate()
        got = M.turn_tools(T, start=True, gate_check=g)
        check("with start, the server starts through this turn's gate",
              "mcp_fake__echo" in got["tools"] and g.calls
              and g.calls[0][0] == "mcp_start__fake", got)
        t = got["tools"]["mcp_fake__echo"]
        check("its tool is marked as from an outside program", t.outside_program is True)
        check("with its own gate action", t.gate_lookup_name({}) == "mcp__fake__echo")
        check("the reach list sees it running", M.reach_status()["running"] == ["fake"])
        g2 = Gate()
        got = M.turn_tools(T, start=True, gate_check=g2)
        check("already running: no second card", g2.calls == [] and "mcp_fake__echo"
              in got["tools"])
        approved = json.load(open(os.path.join(TMP, M.APPROVALS_FILE)))
        check("the start was remembered in the config folder", "fake" in approved, approved)
        M._load_section = lambda: {}
        check("settings removed: the bridge and its servers go", M.shared_bridge() is None
              and M.reach_status()["running"] == [])
    finally:
        M._load_section, M._config_dir = real_load, real_dir
        M.shared_bridge()


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
               t_only_read_only_tools_are_offered,
               t_every_call_asks_a_person,
               t_a_call_needs_the_right_verdict_once,
               t_results_are_untrusted_and_rushing_latches_ask,
               t_the_server_cannot_borrow_the_model,
               t_a_slow_tool_is_cancelled_and_never_retried,
               t_protocol_abuse,
               t_the_whole_tree_dies,
               t_the_server_gets_only_what_it_was_given,
               t_a_card_when_added_and_again_when_changed,
               t_an_idle_server_is_stopped,
               t_the_shared_bridge_reads_the_settings,
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
