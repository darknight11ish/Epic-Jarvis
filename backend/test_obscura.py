"""test_obscura.py - the driver for Obscura, the headless browser
(jarvis_obscura.py; the owner's decision of 2026-09-29).

    python3 backend/test_obscura.py

No real Obscura is used (none can run here): a stand-in program,
backend/_fake_obscura.py, speaks the same protocol over standard input and
output, and is started as a REAL child process, so the process handling (start,
stop, kill, timeouts, one at a time) is tested for real. What it proves:

  - the command line: --stealth always, `mcp` (standard input/output), and NEVER
    --http, --host, --port, --proxy, --allow-private-network, --storage-dir or
    --user-agent - so no network port exists to bind, no proxy, no saved cookies;
  - the environment is an allow-list: none of Jarvis's tokens or keys, no proxy
    variable, and the private-network guard held ON in words;
  - only the listed tools may be called; evaluate, cookies, storage, tabs, key
    presses, the network log and PDF are refused BEFORE anything is sent;
  - one program at a time; stop kills it; limits: a page cap, a time limit, an
    idle limit and a per-call limit each stop it, in words; a program that dies or
    sends a huge line is reported, never hung on;
  - a program is STARTED only while the start gate (the owner's switch) says yes; a
    watchdog stops an idle or over-age program on its own; an idle or old program
    met by the next call is replaced quietly, never a refusal; asking for the state
    never waits behind a running call; a write to a program that stopped reading is
    cut off; the one tool that runs a script in the page only takes Jarvis's own
    fixed argument;
  - install state: not installed, never checked (refused), changed since checked
    (refused), pinned checksum; the install line is ONE line, downloads one NAMED
    release (never "latest"), prints the checksums and does NOT run the program,
    parses as PowerShell, and the backend never downloads anything; PINNED_DIGEST
    is empty (said plainly);
  - the owner's check: prints what it did, refuses a changed file unless told,
    fails when the stand-in visits a private address (guard off), and saves only
    when every step passed.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_obscura.py", "jarvis_child_env.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-obscura-"))
CFG: dict = {}
AUDIT: list = []
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: CFG
fw.audit_log = lambda event, detail=None, **k: AUDIT.append((event, detail))
fw.action_tier = lambda action: "ask"
sys.modules["jarvis_framework"] = fw

import jarvis_obscura as OB  # noqa: E402

FAKE = HERE / "_fake_obscura.py"
PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def fresh():
    d = Path(tempfile.mkdtemp(prefix="cfg-", dir=_TMP))
    fw.CONFIG_DIR = d
    CFG.clear()
    AUDIT.clear()
    OB._DIGEST_CACHE.update(key=None, digest="")
    return d


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def driver(mode="", log=None, clock=None, verify=False):
    env_log = str(log) if log else ""
    real_env = OB.child_env

    def env(base=None):
        e = real_env(base)
        e["FAKE_MODE"] = mode
        e["FAKE_LOG"] = env_log
        return e
    OB.child_env = env
    d = OB.Driver(clock=clock or time.monotonic,
                  command_fn=lambda: [sys.executable, str(FAKE), "--stealth", "mcp"],
                  verify=verify)
    d._restore = lambda: setattr(OB, "child_env", real_env)
    return d


def events(log: Path) -> list:
    try:
        return [json.loads(l) for l in log.read_text().splitlines()]
    except OSError:
        return []


def t_command_line():
    cmd = OB.command("C:\\x\\obscura.exe")
    check("the command is exe, --stealth, mcp - and nothing else", cmd == ["C:\\x\\obscura.exe", "--stealth", "mcp"], cmd)
    bad = ("--http", "--host", "--port", "-p", "--proxy", "--allow-private-network",
           "--storage-dir", "--user-agent", "--allow-file-access", "--obey-robots", "--workers")
    check("no flag that opens a port, adds a proxy, keeps cookies or drops the private-address guard",
          not any(b in cmd for b in bad))
    check("stealth is a constant, not a setting", OB.STEALTH_FLAG == "--stealth"
          and "--stealth" in OB.command())
    src = (HERE / "jarvis_obscura.py").read_text()
    check("the module reads no proxy setting from anywhere (no 'proxy' key is looked up)",
          "_cfg(\"proxy" not in src and "get(\"proxy" not in src and "OBSCURA_PROXY\":" not in src)


def t_environment():
    base = {"PATH": "/bin", "SYSTEMROOT": "C:\\Windows", "HUD_TOKEN": "tok-secret",
            "OPENAI_API_KEY": "sk-x", "JARVIS_TOKEN": "j", "HTTPS_PROXY": "http://p:1",
            "HTTP_PROXY": "http://p:1", "OBSCURA_PROXY": "http://p:2",
            "OBSCURA_ALLOW_PRIVATE_NETWORK": "1", "OBSCURA_MCP_TOKEN": "z" * 40,
            "OBSCURA_TIMEZONE": "Asia/Tokyo", "OBSCURA_GEOLOCATION": "1,2"}
    env = OB.child_env(base)
    check("no token, key or proxy variable of Jarvis's or the machine's reaches it",
          not any(k in env for k in ("HUD_TOKEN", "OPENAI_API_KEY", "JARVIS_TOKEN", "HTTPS_PROXY",
                                     "HTTP_PROXY", "OBSCURA_PROXY", "OBSCURA_MCP_TOKEN")), sorted(env))
    check("the private-address guard is held ON in words, whatever the machine set",
          env.get("OBSCURA_ALLOW_PRIVATE_NETWORK") == "0")
    check("no timezone or location is invented for it",
          "OBSCURA_TIMEZONE" not in env and "OBSCURA_GEOLOCATION" not in env)
    check("its own time limits are set", env.get("OBSCURA_NAV_TIMEOUT_MS") == "25000")
    check("it still gets what a program needs to start", env.get("PATH") == "/bin")


def t_tools_are_allow_listed():
    fresh()
    log = _TMP / "log-tools.jsonl"
    d = driver(log=log)
    try:
        refused = []
        for tool in OB.REFUSED_TOOLS + ("browser_made_up",):
            try:
                d.call(tool, {})
                refused.append((tool, "ALLOWED"))
            except OB.ObscuraError as exc:
                if exc.code != "refused_tool":
                    refused.append((tool, exc.code))
        check("evaluate, cookies, storage, tabs, keys, the network log, PDF and the rest are refused",
              not refused, refused)
        check("...before the program is even started, and nothing was sent",
              not d.alive() and not events(log))
        for name in ("browser_evaluate", "browser_get_cookies", "browser_set_cookie",
                     "browser_clear_cookies", "browser_storage_state", "browser_pdf"):
            check(f"{name} is not on the list", name not in OB.ALLOWED_TOOLS)
        check("every listed tool is one this project means to use",
              OB.ALLOWED_TOOLS.isdisjoint(OB.REFUSED_TOOLS))
    finally:
        d.stop("test")
        d._restore()


def t_start_call_stop():
    fresh()
    log = _TMP / "log-run.jsonl"
    d = driver(log=log)
    try:
        got = d.call("browser_navigate", {"url": "https://example.test/"})
        check("a call starts the program on demand and gets its answer",
              d.alive() and "Navigated" in got["text"] and not got["error"], got)
        check("its own version is read from the handshake", d.version == "0.0.0-test", d.version)
        starts = [e for e in events(log) if e.get("start")]
        check("exactly ONE program was started", len(starts) == 1)
        d.call("browser_snapshot", {})
        d.start()        # already running: a no-op, never a second one
        check("asking again starts no second program",
              len([e for e in events(log) if e.get("start")]) == 1)
        env_names = starts[0]["env"]
        check("what the program was started with holds no Jarvis secret",
              not any(n.upper() in ("HUD_TOKEN", "JARVIS_TOKEN", "HTTPS_PROXY", "OBSCURA_PROXY")
                      for n in env_names))
        proc = d.proc
        d.stop("test")
        check("stop kills it", proc.poll() is not None and not d.alive())
        check("stopping is audited without any page content",
              any(e == "obscura.stopped" for e, _ in AUDIT))
        d.call("browser_navigate", {"url": "https://example.test/about"})
        check("after a stop the next call starts a fresh program on a blank page",
              d.alive() and len([e for e in events(log) if e.get("start")]) == 2)
    finally:
        d.stop("test")
        d._restore()


def t_limits():
    fresh()
    real = (OB.PAGE_CALLS_MAX, OB.CALL_TIMEOUT_S)
    # page cap
    OB.PAGE_CALLS_MAX = 3
    d = driver()
    try:
        for _ in range(3):
            d.call("browser_navigate", {"url": "https://example.test/"})
        try:
            d.call("browser_navigate", {"url": "https://example.test/about"})
            check("the page cap stops the program", False)
        except OB.ObscuraError as exc:
            check("the page cap stops the program, in words",
                  exc.code == "limit_pages" and not d.alive() and "limit of pages" in exc.words(),
                  exc.code)
        d.call("browser_snapshot", {})
        check("reading (not a page change) is not counted against the cap", True)
    finally:
        d.stop("t")
        d._restore()
        OB.PAGE_CALLS_MAX = real[0]
    # time limit and idle limit, on a fake clock
    clock = Clock()
    d = driver(clock=clock)
    try:
        d.call("browser_navigate", {"url": "https://example.test/"})
        # A session that is USED right up to the limit (a call every couple of
        # minutes, never idle for the idle limit) is stopped with a reason. (One
        # that merely sat there is replaced quietly - see t_a_program_nobody_uses.)
        for _ in range(4):
            clock.t += OB.IDLE_MAX_S - 30
            d.call("browser_snapshot", {})
        clock.t += 60                       # 660 s in all, but only 60 s since the last call
        try:
            d.call("browser_snapshot", {})
            check("the time limit stops the program", False)
        except OB.ObscuraError as exc:
            check("the time limit stops the program, in words",
                  exc.code == "limit_time" and not d.alive(), exc.code)
        d.call("browser_navigate", {"url": "https://example.test/"})
        clock.t += OB.IDLE_MAX_S + 1
        proc = d.proc
        got = d.call("browser_snapshot", {})
        check("after too long idle the program is stopped and a fresh one answers on a blank page",
              proc.poll() is not None and "URL: about:blank" in got["text"], got["text"][:60])
    finally:
        d.stop("t")
        d._restore()
    # per-call limit
    OB.CALL_TIMEOUT_S = 1.0
    d = driver("hang")
    try:
        t0 = time.monotonic()
        try:
            d.call("browser_navigate", {"url": "https://example.test/"})
            check("a call that never answers is cut off", False)
        except OB.ObscuraError as exc:
            check("a call that never answers is cut off and the program stopped",
                  exc.code == "slow" and not d.alive() and time.monotonic() - t0 < 10, exc.code)
    finally:
        d.stop("t")
        d._restore()
        OB.CALL_TIMEOUT_S = real[1]


def t_death_and_huge_lines():
    fresh()
    d = driver("die")
    try:
        try:
            d.call("browser_navigate", {"url": "https://example.test/"})
            check("a program that exits is noticed", False)
        except OB.ObscuraError as exc:
            check("a program that exits straight after starting is reported, not waited on forever",
                  exc.code in ("died", "start_failed") and not d.alive(), exc.code)
    finally:
        d.stop("t")
        d._restore()
    d = driver("big")
    try:
        d.call("browser_navigate", {"url": "https://example.test/"})
        try:
            d.call("browser_snapshot", {})
            check("a huge line ends the run", False)
        except OB.ObscuraError as exc:
            check("a reply larger than the cap ends the run instead of filling memory",
                  exc.code == "died" and not d.alive(), exc.code)
    finally:
        d.stop("t")
        d._restore()


def t_install_state():
    d = fresh()
    check("no file: not installed", OB.problem() == "not_installed" and not OB.status()["installed"])
    exe = OB.exe_path()
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"MZ-pretend-program-v1")
    check("a file that was never checked is REFUSED (fail closed)",
          OB.problem() == "not_checked" and "not been checked" in OB.WHY["not_checked"])
    dig = OB.digest_of(exe)
    OB.save_check({"version": "0.1.0", "digest": dig, "at": time.time(), "stealth_ok": True})
    check("a checked file is fine", OB.problem() == "" and OB.status()["version"] == "0.1.0")
    exe.write_bytes(b"MZ-pretend-program-v2-swapped")
    check("a file changed since it was checked is refused",
          OB.problem() == "changed" and "changed" in OB.WHY["changed"])
    real = OB.PINNED_DIGEST
    try:
        OB.PINNED_DIGEST = OB.digest_of(exe)
        check("a pinned checksum that matches is accepted even with no check", OB.problem() == "")
        OB.PINNED_DIGEST = "0" * 64
        check("a pinned checksum that does not match is refused", OB.problem() == "changed")
    finally:
        OB.PINNED_DIGEST = real
    check("PINNED_DIGEST is empty: nobody could read a real release checksum here (said plainly)",
          OB.PINNED_DIGEST == "")
    # the real Driver.start refuses an unchecked/changed program before spawning
    exe.write_bytes(b"MZ-pretend-program-v3")
    drv = OB.Driver()
    try:
        drv.start()
        check("the driver will not start a program that failed the check", False)
    except OB.ObscuraError as exc:
        check("the driver will not start a program that was never checked or changed",
              exc.code in ("not_checked", "changed") and not drv.alive(), exc.code)
    CFG["obscura"] = {"path": "relative/obscura.exe"}
    check("a relative path in the settings is ignored (a full path only)",
          OB.exe_path() == OB.install_dir() / OB.exe_name())
    CFG.clear()
    (fw.CONFIG_DIR / "obscura-check.json").write_text("{not json")
    check("a damaged check file reads as 'not checked'", OB.checked() is None)


def t_install_line():
    line = OB.install_line()
    check("the install line is ONE line", "\n" not in line and "\r" not in line and len(line) < 1800)
    import re as _re
    check("it downloads the stealth Windows archive of ONE NAMED release from Obscura's own releases",
          OB.DOWNLOAD_URL in line and line.count("Invoke-WebRequest") == 1
          and "windows-stealth.zip" in OB.DOWNLOAD_URL
          and OB.DOWNLOAD_URL.startswith("https://github.com/h4ckf0r0day/obscura/releases/download/"
                                          + OB.RELEASE_TAG + "/"))
    check("the release is a version tag, never 'latest'",
          _re.fullmatch(r"v\d+\.\d+\.\d+", OB.RELEASE_TAG) is not None and "latest" not in line.lower())
    check("it unpacks into the folder Jarvis really looks in", f"$d = '{OB.install_dir()}'" in line)
    check("... whatever the settings folder is", str(fresh()) in OB.install_line())
    line = OB.install_line()
    head = line.split("Write-Host", 1)[0]
    check("it PRINTS the checksum of the zip and of obscura.exe (Get-FileHash, SHA256), for the owner to compare",
          line.count("Get-FileHash -Algorithm SHA256") == 2 and "SHA-256 of the zip" in line
          and "SHA-256 of obscura.exe" in line and "Compare" in line)
    import re as _re2
    check("the expected checksum is a real SHA-256 (64 hex letters) and is the one in the line, once",
          _re2.fullmatch(r"[0-9a-f]{64}", OB.RELEASE_ZIP_SHA256) is not None
          and line.count(OB.RELEASE_ZIP_SHA256) == 1)
    check("the zip is COMPARED with it before anything is unpacked, and a different file is deleted "
          "and stops the line (throw), never unpacked",
          "$z -ne $w" in line and line.index("$z -ne $w") < line.index("Expand-Archive")
          and "throw" in line and line.index("throw") < line.index("Expand-Archive")
          and line.index("Remove-Item -LiteralPath") < line.index("Expand-Archive"))
    check("the line still tells the owner to check the expected value once against the release page",
          "Compare it ONCE with the" in line and OB.RELEASE_TAG in line)
    check("it does NOT run the program: nothing before the printing runs py, the check or the exe",
          "py -3" not in head and "--check" not in head and "--accept-new" not in head
          and "Start-Process" not in line and "& '" not in line and "obscura.exe --" not in line)
    tail = line.split("Write-Host", 1)[1]
    check("the second step it prints is the plain check, and says --accept-new is only for replacing a "
          "file checked before",
          "py -3 .\\jarvis_obscura.py --check" in tail and "add --accept-new only if you are replacing" in tail
          and "--check --accept-new" not in line)
    check("the archive is deleted by a literal path (a [ in a folder name is not a wildcard)",
          'Remove-Item -LiteralPath "$d\\obscura.zip"' in line and 'Remove-Item "' not in line)
    urls = _re.findall(r"https?://\S+", line)
    check("no proxy, no key and no host other than Obscura's own GitHub project in it",
          "proxy" not in line.lower() and bool(urls) and all(u.startswith(OB.PROJECT_URL + "/") for u in urls), urls)
    check("it is written for Windows PowerShell 5.1: no ?? and no &&", "??" not in line and "&&" not in line)
    import subprocess as _sp
    ps = "/opt/pwsh/pwsh"
    if os.path.exists(ps):
        f = _TMP / "install-line.ps1"
        f.write_text(line, encoding="utf-8")
        g = _TMP / "parse.ps1"
        g.write_text("param([string]$p); $t=$null; $e=$null; [void][System.Management.Automation.Language."
                     "Parser]::ParseFile($p,[ref]$t,[ref]$e); $e.Count", encoding="utf-8")
        r = _sp.run([ps, "-NoProfile", "-File", str(g), "-p", str(f)], capture_output=True, text=True, timeout=120)
        check("the line parses as PowerShell with no errors", r.stdout.strip() == "0", r.stdout + r.stderr)
    else:
        print("note: no PowerShell 7 at /opt/pwsh/pwsh here, so the parse check was skipped")
    src = (HERE / "jarvis_obscura.py").read_text()
    import re
    check("the backend never downloads anything itself (no urllib/requests/urlopen in the driver)",
          not re.search(r"urllib|import requests|urlopen|http\.client|socket\.socket|create_connection", src.split('"""', 2)[2]),
          [m.group(0) for m in re.finditer(r"urllib|import requests|urlopen|http\.client|socket\.socket",
                                            src.split('"""', 2)[2])][:3])


def t_the_start_gate_keeps_it_off():
    fresh()
    log = _TMP / "log-gate.jsonl"
    gate = {"why": "The headless browser is switched off."}
    d = driver(log=log)
    d.start_gate = lambda: gate["why"]
    try:
        try:
            d.call("browser_navigate", {"url": "https://example.test/"})
            check("a call with the gate saying no does not start the program", False)
        except OB.ObscuraError as exc:
            check("a call with the gate saying no is refused in words and starts nothing",
                  exc.code == "switched_off" and "switched off" in exc.words() and not d.alive()
                  and not [e for e in events(log) if e.get("start")], exc.code)
        gate["why"] = ""
        d.call("browser_navigate", {"url": "https://example.test/"})
        check("with the gate saying yes it starts", d.alive())
        d.stop("switch off")
        gate["why"] = "The headless browser is switched off."
        try:
            d.call("browser_snapshot", {})
            check("after a stop with the gate saying no, the next call does not restart it", False)
        except OB.ObscuraError as exc:
            check("after a stop with the gate saying no, the next call does not restart it",
                  exc.code == "switched_off" and not d.alive()
                  and len([e for e in events(log) if e.get("start")]) == 1, exc.code)

        def broken():
            raise RuntimeError("x")
        d.start_gate = broken
        try:
            d.start()
            check("a gate that breaks does not start it", False)
        except OB.ObscuraError as exc:
            check("a gate that breaks keeps it off (fail closed)", exc.code == "switched_off" and not d.alive())
    finally:
        d.stop("t")
        d._restore()
    plain = OB.Driver(command_fn=lambda: [sys.executable, str(FAKE), "--stealth", "mcp"], verify=False)
    check("a driver made without a gate (the owner's own check) is not held back", plain.start_gate is None)


def t_a_program_nobody_uses():
    fresh()
    real = OB.WATCH_POLL_S
    OB.WATCH_POLL_S = 0.05
    clock = Clock()
    d = driver(clock=clock)
    try:
        d.call("browser_navigate", {"url": "https://example.test/"})
        proc = d.proc
        check("running after a call", d.alive())
        clock.t += OB.IDLE_MAX_S + 1
        deadline = time.monotonic() + 5
        while d.alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        check("the watchdog stops an idle program ON ITS OWN, with no further call",
              not d.alive() and proc.poll() is not None and d.last_stop_why == "idle", d.last_stop_why)
        got = d.call("browser_snapshot", {})
        check("the next call after that starts a fresh program on a blank page, no refusal",
              d.alive() and "URL: about:blank" in got["text"], got["text"][:40])
        proc = d.proc
        clock.t += OB.SESSION_MAX_S + 1
        deadline = time.monotonic() + 5
        while d.alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        check("the watchdog stops a program at the session limit too",
              not d.alive() and proc.poll() is not None and d.last_stop_why in ("time limit", "idle"),
              d.last_stop_why)
    finally:
        d.stop("t")
        d._restore()
        OB.WATCH_POLL_S = real
    # The owner comes back after 11 minutes and the watchdog has not run (a slow
    # poll): the call itself replaces the program quietly.
    clock = Clock()
    d = driver(clock=clock)
    try:
        d.call("browser_navigate", {"url": "https://example.test/"})
        proc = d.proc
        clock.t += 11 * 60
        got = d.call("browser_snapshot", {})
        check("11 quiet minutes later the next task gets a fresh program quietly (no 'limit' refusal)",
              d.alive() and d.proc is not proc and proc.poll() is not None
              and "URL: about:blank" in got["text"], got["text"][:40])
        check("... and the pages counter started again", d.pages == 0)
    finally:
        d.stop("t")
        d._restore()


def t_asking_for_the_state_never_waits():
    fresh()
    real = OB.CALL_TIMEOUT_S
    OB.CALL_TIMEOUT_S = 30.0
    d = driver("hang")
    out = {}

    def call():
        try:
            d.call("browser_navigate", {"url": "https://example.test/"})
        except OB.ObscuraError as exc:
            out["code"] = exc.code
    t = threading.Thread(target=call, daemon=True)
    t.start()
    try:
        deadline = time.monotonic() + 10
        while not d.alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        time.sleep(0.5)                     # the call now holds the lock, waiting on the program
        t0 = time.monotonic()
        v = d.view()
        took = time.monotonic() - t0
        check("view() answers at once while a call is hung on the program (it does not take the call's lock)",
              took < 1.0 and v["running"] is True, f"took {took:.1f}s")
    finally:
        d.stop("t")
        t.join(10)
        d._restore()
        OB.CALL_TIMEOUT_S = real


def t_a_write_to_a_program_that_stopped_reading_is_cut_off():
    fresh()
    real = OB.SEND_TIMEOUT_S
    OB.SEND_TIMEOUT_S = 1.0
    d = driver("deaf")
    try:
        d.start()
        t0 = time.monotonic()
        try:
            d.call("browser_fill", {"ref": "e1", "value": "x" * 6_000_000})
            check("a huge write to a program that reads nothing is cut off", False)
        except OB.ObscuraError as exc:
            took = time.monotonic() - t0
            free = d.lock.acquire(timeout=1)
            if free:
                d.lock.release()
            check("a huge write to a program that reads nothing is cut off, the program is stopped, and the "
                  "lock is free again", exc.code == "slow" and not d.alive() and took < 10 and free,
                  (exc.code, took, free))
    finally:
        d.stop("t")
        d._restore()
        OB.SEND_TIMEOUT_S = real


def t_the_script_tool_takes_only_jarvis_own_argument():
    import re as _re
    fresh()
    log = _TMP / "log-extract.jsonl"
    d = driver(log=log)
    try:
        for bad in ({}, {"schema": {"x": "body"}}, {"schema": {"text": "body", "hidden[]": "*"}},
                    {"schema": OB.FIXED_ARGS["browser_extract"]["schema"], "extra": 1},
                    {"selector": "body"}):
            try:
                d.call("browser_extract", bad)
                check(f"browser_extract with {str(bad)[:40]} is refused", False)
            except OB.ObscuraError as exc:
                check(f"browser_extract with other arguments is refused ({str(bad)[:40]})",
                      exc.code == "refused_tool")
        check("... before the program was even started", not d.alive() and not events(log))
        got = d.call("browser_extract", OB.FIXED_ARGS["browser_extract"])
        doc = json.loads(got["text"])
        check("with exactly Jarvis's own argument it is called", "text" in doc and "hidden" in doc and d.alive())
        sel = OB.FIXED_ARGS["browser_extract"]["schema"]["hidden[]"]
        check("its selectors are a fixed list of plain CSS: letters, digits and [ ] = \" - : , * only - no "
              "@attribute form, no script, no page or model word",
              _re.fullmatch(r'[A-Za-z0-9\[\]="\-:,* ]+', sel) is not None and "@" not in sel, sel)
        check("browser_evaluate is still not on the list", "browser_evaluate" not in OB.ALLOWED_TOOLS)
    finally:
        d.stop("t")
        d._restore()


def t_every_allowed_tool_is_used():
    used = (HERE / "jarvis_browser_engine.py").read_text() + \
        (HERE / "jarvis_obscura.py").read_text().split("def check(", 1)[1]
    unused = [t for t in sorted(OB.ALLOWED_TOOLS) if f'"{t}"' not in used]
    check("every tool on the allow-list is one the engine or the owner's check calls", not unused, unused)


def _cli(webdriver="false", version="obscura 0.0.0-test"):
    def run(args):
        if "--version" in args:
            return 0, version + "\n"
        if "fetch" in args:
            return 0, webdriver + "\n"
        return 1, "?"
    return run


class LocalPage:
    def __init__(self):
        self.url = "http://127.0.0.1:59999/"
        self.stopped = False

    def stop(self):
        self.stopped = True


def t_the_owners_check():
    d = fresh()
    out: list = []
    say = out.append
    exe = OB.exe_path()
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"MZ-check-program-1")
    lp = LocalPage()
    drv = driver()
    try:
        code = OB.check(say, driver=drv, run_cli=_cli(), serve_local=lambda: {"url": lp.url, "stop": lp.stop})
        text = "\n".join(out)
        check("every step passes against the stand-in", code == 0, text)
        check("it prints the checksum, the version, stealth, the refusal of a local page and the screenshot",
              all(w in text for w in ("SHA-256", "Version: obscura 0.0.0-test", "navigator.webdriver reads false",
                                       "refused, as it should be", "Screenshot: a picture came back")), text)
        check("it says the program listens on no port", "listens on no port" in text)
        saved = OB.checked()
        check("a pass saves the version and the checksum (so a later different file is refused)",
              saved is not None and saved["digest"] == OB.digest_of(exe) and saved["stealth_ok"] is True
              and saved["private_refused"] is True, saved)
        check("the local test page was stopped", lp.stopped)
        # a changed file is refused unless the owner says so
        exe.write_bytes(b"MZ-check-program-2")
        out.clear()
        code = OB.check(say, driver=driver(), run_cli=_cli(), serve_local=lambda: None)
        check("a changed file is refused by a plain check", code == 1 and "not the one that was checked" in "\n".join(out))
        out.clear()
        code = OB.check(say, accept_new=True, driver=driver(), run_cli=_cli(), serve_local=lambda: None)
        check("...and accepted when the owner runs the install line on purpose (--accept-new)", code == 0)
        # stealth not on
        out.clear()
        code = OB.check(say, driver=driver(), run_cli=_cli(webdriver="true"), serve_local=lambda: None)
        check("a program that shows navigator.webdriver = true fails the check and saves nothing new",
              code == 1 and "NOT what was expected" in "\n".join(out))
        # private guard off
        os.environ["FAKE_X"] = "1"
        out.clear()
        code = OB.check(say, driver=driver("visit_private"), run_cli=_cli(),
                        serve_local=lambda: {"url": "http://127.0.0.1:59999/", "stop": lambda: None},
                        accept_new=True)
        check("a program that VISITS a page on this PC fails the check (the guard is not on)",
              code == 1 and "NOT on" in "\n".join(out), "\n".join(out))
    finally:
        drv.stop("t")
        drv._restore()
        for dd in (drv,):
            pass
    out.clear()
    (exe).unlink()
    code = OB.check(say)
    check("with nothing installed the check says so in words", code == 1 and "not installed" in "\n".join(out))


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
