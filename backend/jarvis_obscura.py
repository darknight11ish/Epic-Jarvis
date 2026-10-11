"""jarvis_obscura.py - the DRIVER for Obscura, the headless browser (no window)
that Jarvis can use for plain reading and quick lookups on the web.

NEW MODULE, shipped whole (apply-patches.ps1 copies it beside jarvis_hud.py).
It holds no permission logic at all: whether Obscura may run, and what each step
asks, is jarvis_browser_engine.py's job (the switch, the approval card, the
mode rule) and the existing browser control's (one card listing every step).
This file only starts the program, talks to it, and keeps it inside limits.

WHAT OBSCURA IS (checked by reading a copy of its source, 2026-09-29; nothing
from it was run where this was written)
  Obscura (github.com/h4ckf0r0day/obscura, Apache-2.0) is a headless browser
  written in Rust: it runs a page's JavaScript with V8, but draws no window.
  `obscura mcp` is a small server, speaking the Model Context Protocol over
  STANDARD INPUT AND OUTPUT (one JSON message per line), that offers about 40
  tools (navigate, snapshot, click, fill, cookies, evaluate, ...). Its
  `--stealth` flag makes it present an ordinary Chrome's TLS fingerprint and
  browser profile, and blocks a list of tracker domains.

WHY STANDARD INPUT/OUTPUT AND NOT ITS WEB-SOCKET (CDP) OR HTTP SERVER
  Over stdin/stdout the program opens NO NETWORK PORT AT ALL. So "bound to this
  PC only" is not a setting that could be got wrong: there is nothing to bind,
  nothing for another program (or another device on the home network, or
  Tailscale) to connect to, and no token to keep. Its HTTP mode and its CDP
  server both listen on a port; neither is ever started here (a test proves the
  command line has no `--http`, `--host` or `--port`).

WHAT THIS FILE ALWAYS DOES
  * `--stealth` is on for everything Obscura runs (the owner's decision,
    2026-09-29). It is not a setting; `command()` has it and a test checks it.
  * Obscura's own guard against reaching private addresses stays ON: this
    computer (127.x), the home network (192.168.x, 10.x, 172.16-31.x), link-local,
    and the 100.64.0.0/10 block Tailscale and NordVPN Meshnet use. `--allow-
    private-network` and OBSCURA_ALLOW_PRIVATE_NETWORK are never passed, and
    the environment says `0` for it explicitly.
  * NO PROXY. There is no proxy setting anywhere in Jarvis for it: nothing the
    owner browses would pass through a company that sells proxies. (It ignores
    HTTP_PROXY on its own; `--proxy` and OBSCURA_PROXY are never passed.)
  * Nothing is remembered between sessions: `--storage-dir` is never passed, so
    no cookie or local storage is ever written, and it is never "signed in".
  * Only a short allow-list of its tools may be called (ALLOWED_TOOLS). Running
    the page's own script (`browser_evaluate`), cookies and storage, tabs, the
    network log, key presses and PDF export are not on it: `call()` refuses them
    before anything is sent. (They would need their own switch and card; none
    is built.)
  * ONE program at a time, a hard time limit (SESSION_MAX_S), an idle limit
    (IDLE_MAX_S), a page-load cap (PAGE_CALLS_MAX) and a time limit on every
    single call (CALL_TIMEOUT_S). Past any of them the program is stopped and
    the caller is told in words; it is never left running. A small watchdog
    thread (`_watch`) calls `Driver.tick()` between sleeps, which enforces the
    idle and session limits ON ITS OWN, so a program nobody is talking to is
    stopped after IDLE_MAX_S (3 minutes) even
    if no further call ever comes (a page stays open between two plans, which
    is what lets a click follow a read, but never longer than that). An idle
    or old program met by the NEXT call is simply replaced by a fresh one on
    a blank page - never a refusal at the owner's next task.
  * A program is STARTED only while the owner's switch is on: the engine hands
    its Driver a `start_gate` (jarvis_browser_engine._start_gate) that is asked
    before every start, so turning the switch off between two steps of a plan
    cannot be undone by the next step quietly starting it again.
  * The program's environment is an allow-list (jarvis_child_env.py): none of
    Jarvis's own settings, keys or tokens reach it.

WHAT IT CANNOT DO (said plainly)
  It has no window, so a captcha or a sign-in page cannot be handed to the owner
  in it - the task goes to the visible browser instead (jarvis_browser_engine.py
  says so). `--stealth` makes it look like an ordinary Chrome to simple checks;
  it does NOT solve captchas or get past interactive challenges, and a site can
  still block it. That is why the chatbot driver, which the owner must be able
  to take over, keeps using the visible browser.

INSTALL AND CHECK
  The owner pastes ONE PowerShell line (install_line()). It downloads Obscura's
  Windows release archive of ONE named release (RELEASE_TAG - never "latest",
  so a later release cannot arrive unannounced), unpacks it into <settings
  folder>\\obscura, and PRINTS the SHA-256 of the archive and of obscura.exe for
  the owner to compare with the release page. The line does NOT run the
  program: nothing of it runs before the owner has had that chance. The owner's
  SECOND step (printed by the line) is `py -3 jarvis_obscura.py --check`, which
  runs it for the first time, and remembers its checksum; `--accept-new` is
  added only when replacing a file that was remembered before, and only after
  comparing. The backend never downloads it. PINNED_DIGEST is EMPTY: nobody
  could read a real release checksum from where this was written. Until one is
  put here, the first checked file's SHA-256 is remembered (obscura-check.json)
  and a later file with any other checksum is refused until the owner runs the
  second step with `--accept-new` on purpose.
  obscura.log (the program's own error output) is kept as PLAIN TEXT beside the
  settings; it holds what Obscura prints about its own errors, never a typed
  value (nothing is typed to it on the command line).

UNVERIFIED (said plainly): a real Obscura binary was never run for this
(the build machine is not Windows and the release could not be downloaded), so
the exact output of its tools is what its source says, not what was seen. The
tests use a stand-in program that speaks the same protocol
(test_obscura.py). `tools/check_obscura.py` is the owner's real check.

Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

try:
    import jarvis_child_env
except Exception:  # pragma: no cover - shipped beside it on the PC
    jarvis_child_env = None  # type: ignore

# --------------------------------------------------------------------------
#   Names and limits
# --------------------------------------------------------------------------

NAME = "Obscura"
LICENCE = "Apache-2.0"
PROJECT_URL = "https://github.com/h4ckf0r0day/obscura"
#: The Windows archive with rendering AND stealth (Obscura's release workflow
#: names its archives obscura-x86_64-windows[-stealth|-no-render].zip).
ASSET = "obscura-x86_64-windows-stealth.zip"
#: The release the install line downloads: v0.2.3, the newest release on
#: https://github.com/h4ckf0r0day/obscura/releases (dated 2026-09-20, marked
#: Latest, read 2026-09-29), whose asset list carries this archive by this exact
#: name (read through a page reader, not by downloading it).
RELEASE_TAG = "v0.2.3"
DOWNLOAD_URL = PROJECT_URL + "/releases/download/" + RELEASE_TAG + "/" + ASSET
#: The SHA-256 of that archive as the release page LISTS it next to the file
#: (read 2026-09-29 through a page reader, NOT by downloading the file and
#: hashing it here - the owner compares it once with the page on their own
#: screen). The install line refuses to unpack a download that differs.
RELEASE_ZIP_SHA256 = "4d7311c69c3263bb8376055f9cb846968b75c77c444d4b5efa74b1018b456fb9"

#: SHA-256 of obscura.exe to pin the download to, or "" while nobody has been
#: able to read one from a real release. See "INSTALL AND CHECK" above.
PINNED_DIGEST = ""

#: The one flag that is always on. Not a setting.
STEALTH_FLAG = "--stealth"

#: Hard limits (seconds unless said). A limit reached stops the program.
SESSION_MAX_S = 600.0        # one run of the program, start to stop
IDLE_MAX_S = 180.0           # nobody asked it anything for this long
CALL_TIMEOUT_S = 45.0        # one call, and the start-up handshake
START_TIMEOUT_S = 30.0
SEND_TIMEOUT_S = 10.0        # writing one request to the program's input
WATCH_POLL_S = 5.0           # how often the watchdog looks at the clock
PAGE_CALLS_MAX = 15          # navigations and clicks/back/forward/reload per run
MAX_LINE_BYTES = 12_000_000  # one reply line (a screenshot is the biggest)
MAX_TEXT_CHARS = 250_000     # one call's text, kept

#: The MCP tools that may be called - only the ones something here really uses.
ALLOWED_TOOLS = frozenset({
    "browser_navigate", "browser_snapshot", "browser_links",
    "browser_interactive_elements", "browser_click", "browser_fill",
    "browser_select_option", "browser_get_attribute", "browser_detect_forms",
    "browser_extract", "browser_screenshot",
})
#: The ones that change which page is showing (counted against the page cap).
PAGE_CALLS = frozenset({"browser_navigate", "browser_click"})
#: A tool that runs a little script inside the page - `browser_extract` - may be
#: called ONLY with exactly this argument, which Jarvis wrote (a fixed list of
#: CSS selectors; no word from the model or from a page is in it). Any other
#: argument is refused before anything is sent, so it can never become
#: "run this script" (browser_evaluate stays off the list).
HIDDEN_SELECTORS = (
    '[hidden], [aria-hidden="true"], template, [inert], '
    '[style*="display:none"], [style*="display: none"], '
    '[style*="visibility:hidden"], [style*="visibility: hidden"], '
    '[style*="opacity:0"], [style*="opacity: 0"], '
    '[style*="font-size:0"], [style*="font-size: 0"]')
FIXED_ARGS = {
    "browser_extract": {"schema": {"text": "body", "hidden[]": HIDDEN_SELECTORS}},
}
#: What is NOT on the list, kept as words so a test can prove each is refused.
REFUSED_TOOLS = (
    "browser_evaluate", "browser_get_cookies", "browser_set_cookie",
    "browser_clear_cookies", "browser_storage_state", "browser_set_storage_state",
    "browser_tab_new", "browser_tab_list", "browser_tab_switch", "browser_tab_close",
    "browser_network_requests", "browser_console_messages", "browser_press_key",
    "browser_type", "browser_fill_form", "browser_pdf", "browser_reload",
    "browser_forward", "browser_scroll", "browser_search",
    "browser_count", "browser_wait_for", "browser_markdown", "browser_back",
    "browser_wait_for_text", "browser_close",
)

#: What the owner sees for each reason a run did not go ahead. Words only.
WHY = {
    "not_installed": ("Obscura (the windowless browser) is not installed on this PC yet. "
                      "Settings shows the one line that installs it."),
    "not_checked": ("Obscura is installed but not checked yet, so Jarvis will not start it. "
                    "The install line printed a long code (a checksum, a fingerprint of the "
                    "file). Check it matches the one on the release page. Then run the check "
                    "command the line printed."),
    "changed": ("Obscura's file is not the one Jarvis checked, so Jarvis will not start it. "
                "If you did not update it yourself, delete it. If you did, run the install "
                "line again, then the check command with --accept-new."),
    "start_failed": ("The windowless browser (Obscura) could not start. Nothing was opened. "
                     "Ask again with the visible browser, or run the check command the install "
                     "line printed to see why."),
    "slow": ("The windowless browser (Obscura) took too long, so it was stopped. Try again, "
             "or ask for the visible browser."),
    "died": ("The windowless browser (Obscura) stopped unexpectedly. Try again, or ask for "
             "the visible browser."),
    "limit_time": ("The windowless browser (Obscura) reached its time limit, so it was "
                   "stopped. Try again, or ask for the visible browser."),
    "limit_pages": ("The windowless browser (Obscura) reached its limit of pages for one "
                    "run, so it was stopped. Try again with a smaller job, or ask for the "
                    "visible browser."),
    "refused_tool": "Jarvis refused a step that this browser is not allowed to do.",
    "switched_off": "The windowless browser is switched off, so Obscura was not started",
    "error": ("The windowless browser (Obscura) ran into an error. Try again, or ask for "
              "the visible browser."),
    "not_windows": "Obscura's Windows program can only be started on Windows.",
}


class ObscuraError(Exception):
    """`code` is a WHY key; `detail` is a short plain-words extra."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail

    def words(self) -> str:
        base = WHY.get(self.code, WHY["error"])
        return base + (f" ({self.detail})" if self.detail else "")


# --------------------------------------------------------------------------
#   Files
# --------------------------------------------------------------------------


def _config_dir() -> Path:
    mod = sys.modules.get("jarvis_framework") or fw
    if mod is not None:
        try:
            return Path(mod.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def install_dir() -> Path:
    return _config_dir() / "obscura"


def exe_name() -> str:
    return "obscura.exe" if os.name == "nt" else "obscura"


def exe_path() -> Path:
    """Where the program is: `[obscura] path` in jarvis-framework.toml if it is
    a full path to a file, else <settings folder>/obscura/obscura(.exe)."""
    mod = sys.modules.get("jarvis_framework") or fw
    if mod is not None:
        try:
            p = str((mod.load_framework().get("obscura") or {}).get("path") or "").strip()
            if p and Path(p).is_absolute():
                return Path(p)
        except Exception:
            pass
    return install_dir() / exe_name()


def check_path() -> Path:
    return _config_dir() / "obscura-check.json"


def log_path() -> Path:
    return _config_dir() / "obscura.log"


def _audit(event: str, detail: dict) -> None:
    try:
        mod = sys.modules.get("jarvis_framework") or fw
        if mod is not None:
            mod.audit_log(event, detail)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   What is installed, and is it the file that was checked
# --------------------------------------------------------------------------

_DIGEST_CACHE: dict = {"key": None, "digest": ""}


def digest_of(path: Path) -> str:
    """SHA-256 of the file, "" if it cannot be read. Cached by size and time."""
    try:
        st = path.stat()
    except OSError:
        return ""
    key = (str(path), st.st_size, st.st_mtime_ns)
    if _DIGEST_CACHE["key"] == key:
        return _DIGEST_CACHE["digest"]
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
    except OSError:
        return ""
    _DIGEST_CACHE.update(key=key, digest=h.hexdigest())
    return _DIGEST_CACHE["digest"]


def checked() -> Optional[dict]:
    """What the owner's last check recorded, or None: {"version", "digest",
    "at", "stealth_ok", "private_refused"}. A damaged file is "not checked"."""
    try:
        doc = json.loads(check_path().read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or doc.get("v") != 1:
            return None
        return {"version": str(doc.get("version") or ""), "digest": str(doc.get("digest") or ""),
                "at": float(doc.get("at") or 0), "stealth_ok": doc.get("stealth_ok"),
                "private_refused": doc.get("private_refused")}
    except Exception:
        return None


def save_check(doc: dict) -> Path:
    doc = dict(doc, v=1)
    p = check_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    os.replace(tmp, p)
    return p


def problem() -> str:
    """"" when the installed program may be started, else a WHY key:
    "not_installed" (no file), "not_checked" (the owner's check has never
    passed) or "changed" (its checksum is not the pinned one, or not the one
    the owner's check remembered)."""
    p = exe_path()
    if not p.is_file():
        return "not_installed"
    d = digest_of(p)
    if not d:
        return "start_failed"
    if PINNED_DIGEST:
        return "" if d == PINNED_DIGEST else "changed"
    c = checked()
    if c and c["digest"]:
        return "" if d == c["digest"] else "changed"
    return "not_checked"        # never checked: fail closed


def status() -> dict:
    """What a settings screen may say about the install - numbers and words,
    never a word from a web page: {"installed", "problem", "version", "checked_at",
    "digest_pinned"}."""
    p = exe_path()
    prob = problem()
    c = checked()
    return {"installed": p.is_file(), "problem": prob,
            "version": (c or {}).get("version", "") if c else "",
            "checked_at": (c or {}).get("at", 0) if c else 0,
            "checked": bool(c),
            "digest_pinned": bool(PINNED_DIGEST)}


# --------------------------------------------------------------------------
#   Starting it: the command line and the environment
# --------------------------------------------------------------------------


def command(exe: Optional[str] = None) -> list:
    """The exact command line. `--stealth` first, always; then `mcp` - the
    standard-input/output server. Nothing else: no `--http`, `--host`, `--port`,
    `--proxy`, `--allow-private-network`, `--storage-dir`, `--user-agent`."""
    return [str(exe or exe_path()), STEALTH_FLAG, "mcp"]


def child_env(base: Optional[dict] = None) -> dict:
    """The environment for the program: an allow-list (nothing of Jarvis's), the
    private-network guard held ON in words, and its own time limits set."""
    if jarvis_child_env is not None:
        env = jarvis_child_env.inherited(base)
    else:  # pragma: no cover - shipped beside it on the PC
        env = {k: v for k, v in (base if base is not None else os.environ).items()
               if k.upper() in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE", "HOME")}
    for k in list(env):
        if k.upper().startswith("OBSCURA_") or k.upper() in (
                "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
            env.pop(k, None)
    env.update({
        # The guard against reaching this PC's own network. Held ON.
        "OBSCURA_ALLOW_PRIVATE_NETWORK": "0",
        # Its own time limits, inside ours.
        "OBSCURA_NAV_TIMEOUT_MS": "25000",
        "OBSCURA_FETCH_TIMEOUT_MS": "15000",
        "OBSCURA_SCRIPT_DEADLINE_MS": "15000",
        "OBSCURA_NAV_CHAIN_LIMIT": "5",
    })
    return env


_popen = subprocess.Popen


def _taskkill(pid: int) -> bool:
    """Windows' own tree-kill, and its OWN answer: True only when it worked.

    The answer is the point. This used to be a bare `subprocess.run(...)` whose
    return code nobody read, so a REFUSED taskkill - no rights over the
    process, or an environment that denies the call - was indistinguishable
    from a successful one, and the caller then waited out the full timeout on a
    program that was still running. The measured symptom (2026-10-08) is a
    suite that hangs to its ceiling with one failure, "stop kills it", and
    nothing else wrong. Split out so a test can hand back a refusal without
    needing one."""
    r = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, timeout=10)
    return r.returncode == 0


def _kill_tree(p) -> None:
    gone = False
    try:
        if os.name == "nt":
            gone = _taskkill(p.pid)
        else:
            import signal
            try:
                pgid = os.getpgid(p.pid)
                # NEVER signal a group this process is in. The program is
                # started with its own session (the Popen kwargs above), so its
                # group is normally its own - but a caller whose child shares
                # the caller's group would otherwise have killpg take the
                # caller down with it, and under run_suites.py that is the whole
                # sweep: the step dies with no output and the job is cancelled
                # half an hour later, which is exactly what CI showed on
                # 2026-10-08. Fall through and kill the one process instead.
                if pgid != os.getpgrp():
                    os.killpg(pgid, signal.SIGKILL)
                    gone = True
                else:
                    gone = False
            except Exception:
                gone = False
    except Exception:
        gone = False
    if not gone:
        # A refused taskkill, or no process group to signal: kill the process
        # we started. Its own children may outlive it - but a program that is
        # still running is worse than one whose children are, and before this
        # the refusal fell through to a five-second wait and nothing else.
        try:
            p.kill()
        except Exception:
            pass
    # A killed program is gone a moment later, not at that instant: wait (a few
    # seconds at most) so that "stopped" means stopped when this returns.
    try:
        p.wait(timeout=5)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   The driver: one program, one conversation over stdin/stdout
# --------------------------------------------------------------------------


def _watch_thread(drv: "Driver", gen: int) -> None:
    """Starts the watchdog thread for one run of the program."""
    threading.Thread(target=drv._watch, args=(gen,),
                     name="jarvis-obscura-watchdog", daemon=True).start()


#: How the watchdog thread is started. A test that proves the idle and session
#: limits sets this to a no-op and drives `Driver.tick()` with its OWN clock:
#: then whether the program is stopped does not depend on a background thread
#: being scheduled inside the test's own real-time window (the shape
#: `_reset_for_tests` has elsewhere in the backend). The real thread is what
#: production uses, and `t_...` in the suites still starts it to prove it runs.
WATCH_THREAD: Callable[["Driver", int], None] = _watch_thread


class Driver:
    """The one Obscura process, or none. All methods are safe to call from any
    thread; calls are one at a time.

    `start_gate() -> str`, when given, is asked before every START: a plain
    reason means "do not start it" (the engine passes one that says no while
    the owner's switch is off). It is what keeps a plan whose switch was turned
    off half-way from quietly starting the program again."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic,
                 popen: Optional[Callable] = None,
                 command_fn: Optional[Callable] = None, verify: bool = True,
                 start_gate: Optional[Callable[[], str]] = None) -> None:
        self.verify = verify
        self.start_gate = start_gate
        self.lock = threading.RLock()
        self.clock = clock
        self._popen_fn = popen
        self._command_fn = command_fn
        self.proc = None
        self.lines: "queue.Queue" = queue.Queue()
        self.started = 0.0
        self.last_used = 0.0
        self.pages = 0
        self.next_id = 0
        self.gen = 0
        self.busy = 0                 # calls in flight (the watchdog waits for them)
        self.version = ""
        self.last_stop_why = ""

    # ---- state ----------------------------------------------------------

    def alive(self) -> bool:
        p = self.proc
        try:
            return p is not None and p.poll() is None
        except Exception:
            return False

    def view(self) -> dict:
        """What a settings screen may show. Reads plain numbers WITHOUT the lock a
        running call holds (a call can wait up to CALL_TIMEOUT_S), so asking never
        hangs behind a slow page."""
        return {"running": self.alive(), "pages": self.pages, "version": self.version,
                "why_stopped": self.last_stop_why}

    # ---- starting and stopping ------------------------------------------

    def _reader(self, proc, gen: int) -> None:
        """Reads the program's output one line at a time into the queue. A
        line longer than MAX_LINE_BYTES ends the run (never held in memory)."""
        out = proc.stdout
        try:
            while True:
                line = out.readline(MAX_LINE_BYTES + 1)
                if not line:
                    break
                if len(line) > MAX_LINE_BYTES:
                    self.lines.put((gen, None, "too_long"))
                    break
                self.lines.put((gen, line, ""))
        except Exception:
            pass
        self.lines.put((gen, None, "eof"))

    def tick(self, gen: Optional[int] = None) -> bool:
        """One look by the watchdog: stops a program nobody is using
        (IDLE_MAX_S) or that has run for SESSION_MAX_S, without waiting for
        another call to notice. True while the run it was asked about should
        still be watched, False when it is over (a newer run has its own
        watchdog).

        Public, and named `tick`, on purpose: the same shape jarvis_focus.py
        and jarvis_schedule.py use. The tests drive this with their own clock
        instead of waiting for the background thread to wake up on a busy
        machine, so "the watchdog stops it" is proved without racing real
        elapsed time. Nothing here waits, so a test never blocks - and it takes
        no lock, so a program hung on a call still gets stopped."""
        gen = self.gen if gen is None else gen
        if self.gen != gen or not self.alive():
            return False
        now = self.clock()
        if now - self.started > SESSION_MAX_S:
            self.stop("time limit")
            return False
        if not self.busy and now - self.last_used > IDLE_MAX_S:
            self.stop("idle")
            return False
        return True

    def _watch(self, gen: int) -> None:
        """The watchdog thread: sleeps WATCH_POLL_S between ticks, and ends when
        that program is gone."""
        while True:
            time.sleep(WATCH_POLL_S)
            if not self.tick(gen):
                return

    def start(self) -> None:
        with self.lock:
            if self.alive():
                return
            self._drop()
            # The owner's switch first: never start it while it is off.
            if self.start_gate is not None:
                try:
                    why = str(self.start_gate() or "")
                except Exception:
                    why = "the switch could not be read"
                if why:
                    raise ObscuraError("switched_off", why.rstrip("."))
            # Tests hand in their own command; the real one is checked first.
            prob = problem() if (self._command_fn is None and self.verify) else ""
            if prob:
                raise ObscuraError(prob)
            cmd = (self._command_fn or command)()
            kwargs: dict = {"stdin": subprocess.PIPE, "stdout": subprocess.PIPE,
                            "env": child_env()}
            log = None
            try:
                log_path().parent.mkdir(parents=True, exist_ok=True)
                log = open(log_path(), "wb")
                kwargs["stderr"] = log
            except OSError:
                kwargs["stderr"] = subprocess.DEVNULL
            if os.name == "nt":
                kwargs["creationflags"] = 0x08000000 | 0x00000200   # no console, own group
            else:
                kwargs["start_new_session"] = True
            try:
                self.proc = (self._popen_fn or _popen)(cmd, **kwargs)
            except Exception as exc:
                self.proc = None
                raise ObscuraError("start_failed", type(exc).__name__)
            finally:
                if log is not None:
                    try:
                        log.close()
                    except Exception:
                        pass
            self.gen += 1
            self.lines = queue.Queue()
            threading.Thread(target=self._reader, args=(self.proc, self.gen),
                             name="jarvis-obscura-reader", daemon=True).start()
            WATCH_THREAD(self, self.gen)
            self.started = self.last_used = self.clock()
            self.pages = 0
            self.next_id = 0
            self.last_stop_why = ""
        try:
            info = self._rpc("initialize", {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "jarvis", "version": "1"}}, timeout=START_TIMEOUT_S)
            si = (info or {}).get("serverInfo") or {}
            self.version = str(si.get("version") or "")[:40]
            self._notify("notifications/initialized")
        except ObscuraError:
            self.stop("start_failed")
            raise
        _audit("obscura.started", {"version": self.version})

    def _drop(self) -> None:
        p, self.proc = self.proc, None
        if p is None:
            return
        try:
            if p.poll() is None:
                _kill_tree(p)
        except Exception:
            pass
        for stream in (getattr(p, "stdin", None), getattr(p, "stdout", None)):
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass

    def stop(self, why: str = "stopped") -> None:
        """Stops the program AT ONCE, even while another thread is waiting on a
        call: the program is killed first, without waiting for the lock a call
        holds (a call can wait up to CALL_TIMEOUT_S), so turning the switch off
        or pressing Stop everything is never held up. The waiting call then sees
        the program gone and ends with "died"."""
        p = self.proc
        if p is not None:
            try:
                if p.poll() is None:
                    _kill_tree(p)
            except Exception:
                pass
        with self.lock:
            self._drop()
            self.gen += 1
            self.last_stop_why = why
        _audit("obscura.stopped", {"why": why})

    # ---- talking --------------------------------------------------------

    def _send(self, msg: dict) -> None:
        """Writes one request. The write happens in a helper thread with its own
        time limit: a program that has stopped reading its input (hung) would
        otherwise block a large write for ever while this thread holds the lock."""
        data = (json.dumps(msg) + "\n").encode("utf-8")
        proc = self.proc
        if proc is None:
            raise ObscuraError("died")
        failed: list = []

        def write() -> None:
            try:
                proc.stdin.write(data)
                proc.stdin.flush()
            except Exception as exc:
                failed.append(exc)

        t = threading.Thread(target=write, name="jarvis-obscura-writer", daemon=True)
        t.start()
        t.join(SEND_TIMEOUT_S)
        if t.is_alive():
            self.stop("slow")          # kills the program, which frees the writer
            raise ObscuraError("slow")
        if failed:
            raise ObscuraError("died")

    def _notify(self, method: str) -> None:
        self._send({"jsonrpc": "2.0", "method": method})

    def _rpc(self, method: str, params: dict, *, timeout: float) -> dict:
        self.next_id += 1
        rid = self.next_id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        gen = self.gen
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise ObscuraError("slow")
            try:
                g, line, why = self.lines.get(timeout=min(left, 0.5))
            except queue.Empty:
                if not self.alive():
                    raise ObscuraError("died")
                continue
            if g != gen:
                continue
            if line is None:
                raise ObscuraError("died", "it sent something too large" if why == "too_long" else "")
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if not isinstance(msg, dict) or msg.get("id") != rid:
                continue
            if isinstance(msg.get("error"), dict):
                raise ObscuraError("error", str(msg["error"].get("message") or "")[:160])
            res = msg.get("result")
            return res if isinstance(res, dict) else {}

    def _check_limits(self) -> None:
        """Called by a call that finds the program still running. A program left
        idle too long, or run for its time limit while NOBODY was using it, is
        replaced quietly - the next call starts a fresh one on a blank page - so
        the owner's next task is never refused for something that happened
        between tasks. Only a program that was in use right up to the limit is
        stopped with a reason."""
        now = self.clock()
        if now - self.last_used > IDLE_MAX_S:
            self.stop("idle")
            return
        if now - self.started > SESSION_MAX_S:
            self.stop("time limit")
            raise ObscuraError("limit_time")

    def call(self, tool: str, args: Optional[dict] = None, *,
             timeout: Optional[float] = None) -> dict:
        """One MCP tool call. Returns {"text": str, "image": bytes|None,
        "error": bool}. A tool not on ALLOWED_TOOLS is refused before anything is
        sent, and so is a tool with fixed arguments (FIXED_ARGS) given any other.
        Starts the program when it is not running - unless the start gate says
        the owner's switch is off."""
        if tool not in ALLOWED_TOOLS:
            raise ObscuraError("refused_tool", tool)
        if tool in FIXED_ARGS and (args or {}) != FIXED_ARGS[tool]:
            raise ObscuraError("refused_tool", tool + " with other arguments")
        with self.lock:
            if self.alive():
                self._check_limits()
            if not self.alive():
                self.start()
            if tool in PAGE_CALLS:
                if self.pages >= PAGE_CALLS_MAX:
                    self.stop("page limit")
                    raise ObscuraError("limit_pages")
                self.pages += 1
            self.busy += 1
            try:
                res = self._rpc("tools/call", {"name": tool, "arguments": dict(args or {})},
                                timeout=timeout or CALL_TIMEOUT_S)
            except ObscuraError as exc:
                if exc.code in ("slow", "died"):
                    if exc.code == "died" and self.last_stop_why == "time limit":
                        raise ObscuraError("limit_time") from None
                    self.stop(exc.code)
                raise
            finally:
                self.busy -= 1
            self.last_used = self.clock()
        return _content(res)

    def close_browser(self) -> None:
        """Ends the run the polite way, then makes sure it is gone."""
        with self.lock:
            if self.alive():
                try:
                    self._rpc("tools/call", {"name": "browser_close", "arguments": {}},
                              timeout=5.0)
                except ObscuraError:
                    pass
            self.stop("closed")


def _content(res: dict) -> dict:
    """The text and the picture in one tool result, capped."""
    import base64
    text_parts, image = [], None
    for item in res.get("content") or []:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "text":
            text_parts.append(str(item.get("text") or ""))
        elif kind == "image" and image is None:
            try:
                image = base64.b64decode(str(item.get("data") or ""), validate=False)
            except Exception:
                image = None
    text = "\n".join(text_parts)
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + "\n...(cut: too long)"
    return {"text": text, "image": image, "error": bool(res.get("isError"))}


DRIVER = Driver()


def stop_all(why: str = "switched off") -> None:
    """Stops the program if it is running. Called when the switch goes off and
    by Stop everything."""
    DRIVER.stop(why)


# --------------------------------------------------------------------------
#   The owner's install line and check
# --------------------------------------------------------------------------


def install_line() -> str:
    """The ONE PowerShell line the owner pastes. Downloads the archive of the ONE
    named release (RELEASE_TAG), unpacks it into Jarvis's own folder, and COMPARES
    the archive's SHA-256 with RELEASE_ZIP_SHA256 (the value the release page
    lists) BEFORE unpacking - a different file is deleted, not unpacked - and
    PRINTS both checksums. It does NOT run the program and does not tell Jarvis to
    trust it: the owner compares first, then runs the check command the line
    prints (`--accept-new` only when replacing a file checked before). Jarvis's
    backend never downloads it. One line, kept to what Windows PowerShell 5.1
    has (no `??`, no `&&`)."""
    here = str(Path(__file__).resolve().parent).replace("'", "''")
    # The folder Jarvis really looks in (its own settings folder's `obscura`),
    # so the line is right even when the settings folder is not the default.
    dest = str(install_dir()).replace("'", "''")
    page = f"{PROJECT_URL}/releases/tag/{RELEASE_TAG}"
    return (
        "$ProgressPreference = 'SilentlyContinue'; "
        f"$d = '{dest}'; New-Item -ItemType Directory -Force -Path $d | Out-Null; "
        f"Invoke-WebRequest -ErrorAction Stop -Uri '{DOWNLOAD_URL}' -OutFile \"$d\\obscura.zip\"; "
        "$z = (Get-FileHash -Algorithm SHA256 -LiteralPath \"$d\\obscura.zip\").Hash; "
        f"$w = '{RELEASE_ZIP_SHA256}'; "
        "if ($z -ne $w) { Remove-Item -LiteralPath \"$d\\obscura.zip\"; "
        "throw \"STOP: the download's SHA-256 ($z) is not the one expected ($w). Nothing was unpacked or run.\" }; "
        "Expand-Archive -ErrorAction Stop -Force -LiteralPath \"$d\\obscura.zip\" -DestinationPath $d; "
        "Remove-Item -LiteralPath \"$d\\obscura.zip\"; "
        "$e = (Get-FileHash -Algorithm SHA256 -LiteralPath \"$d\\obscura.exe\").Hash; "
        f"$h = '{here}'; "
        f"Write-Host \"Downloaded Obscura {RELEASE_TAG}. Nothing has been run yet.\"; "
        "Write-Host \"SHA-256 of the zip: $z\"; Write-Host \"SHA-256 of obscura.exe: $e\"; "
        "Write-Host \"The zip matched the checksum this line expected ($w). Compare it ONCE with the "
        f"SHA-256 GitHub shows for that file on {page} . "
        "If they are the same, run this second command to check the program: "
        "Set-Location -LiteralPath '$h'; py -3 .\\jarvis_obscura.py --check   "
        "(add --accept-new only if you are replacing a file you checked before)\"")


def _self_test_page() -> str:
    return "data:text/html,<title>Jarvis check</title><h1>Hello from a test page</h1>" \
           "<a href='https://example.com/'>a link</a><input name='q' aria-label='Search'>"


def check(say: Callable[[str], None] = print, *, accept_new: bool = False,
          driver: Optional[Driver] = None, run_cli: Optional[Callable] = None,
          serve_local: Optional[Callable] = None) -> int:
    """The owner's check: run on the PC, prints what it did. Exit 0 = every
    step passed. `run_cli(args) -> (code, text)` and `serve_local()` are for
    tests; the real ones run the program's own command line and a tiny local
    page server (to prove Obscura REFUSES to visit it)."""
    say("Obscura check: this starts Obscura, loads a made-up page that is inside the check "
        "itself, and prints what happened. It visits no real website.")
    exe = exe_path()
    if not exe.is_file():
        say(f"  Stopped: {WHY['not_installed']}\n  Looked for: {exe}")
        return 1
    d = digest_of(exe)
    say(f"  File: {exe}")
    say(f"  SHA-256: {d}")
    ok = True
    if PINNED_DIGEST:
        if d == PINNED_DIGEST:
            say("  Checksum: matches the one this Jarvis was built for.")
        else:
            say("  Stopped: the checksum is NOT the one this Jarvis was built for.")
            return 1
    else:
        rem = checked()
        if rem and rem["digest"] and rem["digest"] != d and not accept_new:
            say("  Stopped: this file is not the one that was checked before (its checksum "
                "differs). If you updated it yourself on purpose, run the install line again.")
            return 1
        say("  Checksum: Jarvis has no official fingerprint for this file to compare with, "
            "so it will remember this one. If the file ever changes, Jarvis will refuse it.")
    run = run_cli or _run_cli
    code, text = run([str(exe), "--version"])
    version = text.strip().splitlines()[0][:60] if text.strip() else ""
    say(f"  Version: {version or 'could not be read'}")
    ok &= code == 0 and bool(version)
    code, text = run([str(exe), STEALTH_FLAG, "fetch", _self_test_page(), "--eval",
                      "navigator.webdriver", "--quiet"])
    wd = text.strip().splitlines()[-1].strip().lower() if text.strip() else ""
    stealth_ok = code == 0 and wd == "false"
    say(f"  Stealth on: navigator.webdriver reads {wd or 'nothing'} "
        f"({'as an ordinary Chrome does' if stealth_ok else 'NOT what was expected'}).")
    ok &= stealth_ok
    drv = driver or Driver(verify=False)   # this check IS the verifying
    private_refused = None
    try:
        local = (serve_local or _serve_local)()
        drv.start()
        say(f"  The MCP program starts and answers (its own version: {drv.version or '?'}). "
            f"It listens on no port: it talks over standard input and output.")
        nav = drv.call("browser_navigate", {"url": _self_test_page()})
        page = drv.call("browser_snapshot", {"max_chars": 500})
        seen = "Hello from a test page" in page["text"]
        say(f"  Loaded the test page: {'its words were read' if seen else 'its words were NOT read'}.")
        ok &= seen and not nav["error"]
        els = drv.call("browser_interactive_elements", {"limit": 20})
        found = "Search" in els["text"]
        say(f"  Listed the page's boxes and links: {'found the search box' if found else 'search box NOT found'}.")
        ok &= found
        if local is not None:
            got = drv.call("browser_navigate", {"url": local["url"]})
            refused = got["error"] or "check-page-marker" not in (
                drv.call("browser_snapshot", {"max_chars": 500})["text"])
            private_refused = bool(refused)
            say(f"  Asked to visit a page on THIS PC ({local['url']}): "
                f"{'refused, as it should be (its private-address guard is on)' if refused else 'it VISITED it - the guard is NOT on'}.")
            ok &= bool(refused)
            local["stop"]()
        shot = drv.call("browser_screenshot", {})
        has_png = bool(shot["image"] and shot["image"][:8] == b"\x89PNG\r\n\x1a\n")
        say(f"  Screenshot: {'a picture came back' if has_png else 'no picture (this may be a build without drawing)'}.")
    except ObscuraError as exc:
        say("  Stopped: " + exc.words())
        ok = False
    finally:
        drv.stop("check finished")
    if ok:
        where = save_check({"version": version, "digest": d, "at": time.time(),
                            "stealth_ok": stealth_ok, "private_refused": private_refused})
        say(f"Result: every step passed. Saved in {where} - Settings now shows it.")
        return 0
    say("Result: something did not pass, so nothing was saved. Read the lines above.")
    return 1


def _run_cli(args: list) -> tuple:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=60, env=child_env(),
                           stdin=subprocess.DEVNULL)
        return r.returncode, (r.stdout or "") + (r.stderr if r.returncode else "")
    except Exception as exc:
        return 1, type(exc).__name__


def _serve_local() -> Optional[dict]:
    """A one-page web server on 127.0.0.1, for the check to prove Obscura will
    not visit it. Its page holds a marker no other page has."""
    import http.server
    import socketserver

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = b"<title>x</title><p>check-page-marker</p>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    try:
        srv = socketserver.TCPServer(("127.0.0.1", 0), H)
    except OSError:
        return None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return {"url": f"http://127.0.0.1:{srv.server_address[1]}/",
            "stop": lambda: (srv.shutdown(), srv.server_close())}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--check" in argv:
        return check(accept_new="--accept-new" in argv)
    if "--status" in argv:
        print(json.dumps(status(), indent=2))
        return 0
    if "--line" in argv:
        print(install_line())
        return 0
    print(__doc__.split("\n\n")[0])
    print("  py -3 jarvis_obscura.py --check     start it, load a made-up page, print what happened")
    print("  py -3 jarvis_obscura.py --status    what Settings shows about the install")
    print("  py -3 jarvis_obscura.py --line      the one line that installs it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
