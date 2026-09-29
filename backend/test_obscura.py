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
  - install state: not installed, never checked (refused), changed since checked
    (refused), pinned checksum; the install line is ONE line and the backend never
    downloads anything; PINNED_DIGEST is empty (said plainly);
  - the owner's check: prints what it did, refuses a changed file unless told,
    fails when the stand-in visits a private address (guard off), and saves only
    when every step passed.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
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
        clock.t += OB.SESSION_MAX_S + 1
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
    check("the install line is ONE line", "\n" not in line and "\r" not in line and len(line) < 1400)
    check("it downloads the stealth Windows archive from Obscura's own releases",
          OB.DOWNLOAD_URL in line and line.count("Invoke-WebRequest") == 1
          and "windows-stealth.zip" in OB.DOWNLOAD_URL
          and OB.DOWNLOAD_URL.startswith("https://github.com/h4ckf0r0day/obscura/releases/"))
    check("it unpacks into the folder Jarvis really looks in and then runs the check",
          f"$d = '{OB.install_dir()}'" in line and "jarvis_obscura.py --check --accept-new" in line)
    check("... whatever the settings folder is", str(fresh()) in OB.install_line())
    check("no proxy, no key and no other host in it",
          "proxy" not in line.lower() and line.count("http") == 1)
    src = (HERE / "jarvis_obscura.py").read_text()
    import re
    check("the backend never downloads anything itself (no urllib/requests/urlopen in the driver)",
          not re.search(r"urllib|import requests|urlopen|http\.client|socket\.socket|create_connection", src.split('"""', 2)[2]),
          [m.group(0) for m in re.finditer(r"urllib|import requests|urlopen|http\.client|socket\.socket",
                                            src.split('"""', 2)[2])][:3])


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
