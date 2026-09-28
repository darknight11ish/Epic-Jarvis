"""jarvis_chatbot_gemini.py - the Gemini adapter for the chatbot driver:
Jarvis types into gemini.google.com in a browser window the owner can see.

NEW MODULE, shipped whole (like jarvis_chatbot.py, which it plugs into).
STEP 2 OF THE CHATBOT DRIVER. Still not reachable from either app: the
routes and screens are a later step (docs/JARVIS-API.md section 60).

THE OWNER'S DECISIONS (CLAUDE.md, 2026-09-28; docs/CHATBOT-DRIVER-DESIGN.md,
"The owner's answers (2026-09-28)")
  * Gemini first, through its WEBSITE, driven OPENLY. The owner chose this
    knowing Google's terms forbid automated access and that the account
    could be closed.
  * A SPARE Google account used only by Jarvis, so a ban cannot touch the
    owner's Gmail, and the owner's email and Gemini's memory of them stay
    out of these chats.
  * A request for "tactics that help avoid bans" was declined: getting round
    a site's bot protection is not something this project builds.

WHAT "OPENLY" MEANS HERE, IN CODE (test_chatbot_gemini.py checks each one)
  * A real, VISIBLE browser window (Playwright's Chromium, or Microsoft
    Edge), launched with `headless=False` and Playwright's own defaults.
    Nothing hides that a program is driving it: the browser's own
    "controlled by automated test software" signs stay as they are, and the
    browser identifies itself exactly as it normally would.
  * No stealth plug-in, no change to how the browser presents itself, no
    script injected into the page, no proxy, no captcha solving, no retrying
    to get past a limit.
  * A person's pace: a plain, fixed pause after every typed character (the
    point is not to overload the site - not to look like a person).
  * At a captcha, a sign-in page, an "unusual activity" / "verify it's you"
    page, a notice over the page, or anything else it does not recognise,
    status() says "needs_owner" and the adapter does NOTHING else. The
    driver (jarvis_chatbot.py) pauses and asks the owner, who deals with it
    in the visible window.

WHAT IT TOUCHES AND READS
  * One browser profile folder used ONLY for this:
    <Jarvis settings folder>/chatbot/gemini-profile (normally
    %USERPROFILE%\\.openjarvis\\chatbot\\gemini-profile). The owner signs in
    to the spare Google account once, by hand, with
        py -3 jarvis_chatbot_gemini.py sign-in
    Jarvis never types, sees or stores the password: Google's sign-in cookie
    lives in that profile folder, as it would in any browser.
  * A NEW chat every conversation (it opens gemini.google.com/app fresh),
    never an old one. It never reads the sidebar, the chat list or any other
    chat: only the newest reply that appeared AFTER its own message.
  * It clicks exactly two things: the message box and the send button. It
    never clicks, opens or follows a link in a reply.
  * The only address it ever opens by itself is gemini.google.com/app.
    _navigate() refuses any other host. Google's sign-in page is reached only
    by the OWNER clicking "Sign in" in the window.

WHEN THE SITE CHANGES
Every selector (how the adapter finds the message box, the send button, the
reply, the stop button and the warning pages) is in ONE table, SELECTORS,
below, with fallbacks, role/aria-label based where possible. They were
written without access to gemini.google.com (the container this was built
in cannot reach it, and must not automate it). The owner checks them on the
PC with one line, which sends one harmless fixed question and prints PASS or
FAIL per step:
    py -3 jarvis_chatbot_gemini.py check

IF PLAYWRIGHT IS NOT INSTALLED
open() raises GeminiUnavailable with the one-line install command, and
ready() says the same before any approval card is raised:
    py -3 -m pip install playwright; py -3 -m playwright install chromium

THREADS
Playwright's objects must be used from the thread that made them, and the
driver may call close() from another thread (a Stop pressed while paused).
So every browser call runs on this adapter's own thread (_Worker), and the
public methods hand work to it and wait.

    python3 test_chatbot_gemini.py
"""
from __future__ import annotations

import importlib.util
import os
import queue
import re
import sys
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Callable, Optional

import jarvis_chatbot as CB

ID = "gemini_web"
NAME = "Gemini"
HOST = "gemini.google.com"
#: The one address this adapter opens by itself: a new, empty chat.
START_URL = "https://gemini.google.com/app"
#: Google's sign-in pages. Reached only when the OWNER clicks "Sign in".
SIGN_IN_HOSTS = ("accounts.google.com",)

#: A plain, fixed pause after every typed character, in milliseconds. A
#: person's pace, so the site is not flooded - not a disguise.
TYPE_DELAY_MS = 45
#: A reply is complete when the "stop" control is gone AND its text has not
#: changed for this many seconds.
SETTLE_SECONDS = 3.0
#: How often the reply is looked at while waiting.
POLL_SECONDS = 0.25
#: How long open() waits for the message box after the page loads.
OPEN_WAIT = 30.0
#: How long send() waits for the site to take the message.
SENT_WAIT = 20.0
#: Playwright's own wait for any one browser step, in milliseconds.
STEP_TIMEOUT_MS = 10000
#: The sign-in helper gives up after this long.
SIGN_IN_WAIT = 30 * 60
#: Which browser: "chromium" (Playwright's own, the default) or "msedge" /
#: "chrome" (the one already on the PC). JARVIS_GEMINI_BROWSER picks.
BROWSERS = ("chromium", "msedge", "chrome")

INSTALL_LINE = "py -3 -m pip install playwright; py -3 -m playwright install chromium"
SIGN_IN_LINE = "py -3 jarvis_chatbot_gemini.py sign-in"
CHECK_LINE = "py -3 jarvis_chatbot_gemini.py check"

NOT_INSTALLED = ("Playwright (the program Jarvis uses to work a browser window) is not "
                 "installed on this PC. To install it, run this one line in PowerShell in "
                 "Jarvis's folder: " + INSTALL_LINE)
NO_BROWSER = ("Playwright is installed, but its browser is not. Run this one line in "
              "PowerShell: py -3 -m playwright install chromium")
NOT_SIGNED_IN = ("Jarvis's Gemini window has never been signed in. Sign in once, by hand, "
                 "to the spare Google account used only by Jarvis: run this one line in "
                 "PowerShell in Jarvis's folder: " + SIGN_IN_LINE)
PROFILE_BUSY = ("Jarvis's Gemini window is already open (the sign-in window, or a check). "
                "Close that window first, then try again.")


# ============================================================================
#   THE SELECTORS - everything that depends on how gemini.google.com looks
# ============================================================================
#
# One table. Each role lists Playwright selectors in the order they are tried;
# the first one that finds something VISIBLE wins. Role and aria-label based
# first (they change least), then Gemini's own element names, then plain
# fallbacks. NOT VERIFIED against the live site from here - the owner's
# `py -3 jarvis_chatbot_gemini.py check` prints which one matched for each
# role. When Gemini changes its page, this table is the one place to edit.
#
#   role           what it finds                              used by
#   input          the box the message is typed into          send(), status()
#   send           the button that sends it                   send()
#   stop           "stop response", shown while it writes      read_reply(), send()
#   reply          ONE reply from Gemini (the newest is last)  read_reply()
#   reply_text     the words inside one reply                 read_reply()
#   sign_in_form   an email or password box: a sign-in page   status()
#   signed_out     a "Sign in" button: nobody is signed in    status()
#   captcha        a "prove you are a person" check            status()
#   warning        a heading or alert that may say "unusual"  status() (text below)
#   notice         anything laid over the page (a dialog)     status()
SELECTORS: dict = {
    "input": (
        'div[role="textbox"][aria-label*="prompt" i]',
        'rich-textarea div[contenteditable="true"]',
        'div.ql-editor[contenteditable="true"]',
        '[contenteditable="true"][role="textbox"]',
        'textarea[aria-label*="prompt" i]',
    ),
    "send": (
        'button[aria-label="Send message"]',
        'button[aria-label*="Send" i]',
        'button.send-button',
    ),
    "stop": (
        'button[aria-label="Stop response"]',
        'button[aria-label*="Stop" i]',
        'button.stop',
    ),
    "reply": (
        'model-response',
        '[data-test-id="model-response"]',
        'div.model-response',
    ),
    "reply_text": (
        'message-content .markdown',
        'message-content',
        '.markdown',
    ),
    "sign_in_form": (
        'input[type="email"]',
        'input[type="password"]',
        'input[name="identifier"]',
    ),
    "signed_out": (
        'a[aria-label="Sign in" i]',
        'a[href*="accounts.google.com/ServiceLogin"]',
        'button[aria-label="Sign in" i]',
    ),
    "captcha": (
        'iframe[src*="recaptcha"]',
        'iframe[title*="captcha" i]',
        '#captcha-form',
        '.g-recaptcha',
    ),
    "warning": (
        'h1',
        'h2',
        '[role="alert"]',
        '[role="alertdialog"]',
    ),
    "notice": (
        '[role="alertdialog"]',
        '[role="dialog"]',
    ),
}

#: status()'s reason when the chat page shows no message box (still loading,
#: or the selectors need updating - the self-check says which).
NO_BOX = "no message box on the page"
#: Words in a heading, alert or dialog that mean Google wants a person.
UNUSUAL_WORDS = re.compile(
    r"unusual (?:traffic|activity)|verify (?:it'?s|it’s) you|confirm (?:it'?s|it’s) you"
    r"|automated (?:queries|requests)|are you a robot|not a robot",
    re.IGNORECASE)
#: Words that mean the page wants a sign-in.
SIGN_IN_WORDS = re.compile(r"^\s*(?:sign in|choose an account|use your google account)\b",
                           re.IGNORECASE)
#: Where the warning check never looks: inside a reply, inside one of
#: Jarvis's own messages, or in the sidebar.
_SKIP_JS = ("e => !!e.closest('" + ", ".join(SELECTORS["reply"])
            + ", message-content, user-query, nav, [role=\"navigation\"]')")
#: Google's "unusual traffic" page lives at google.<tld>/sorry/...
_SORRY_PATH = re.compile(r"^/sorry(?:/|$)")


class GeminiUnavailable(RuntimeError):
    """The Gemini window cannot be opened. `owner_words` is the plain-words
    reason, with the one line to fix it; jarvis_chatbot.run() shows it."""

    def __init__(self, owner_words: str):
        super().__init__(owner_words)
        self.owner_words = owner_words


# ============================================================================
#   Where things live
# ============================================================================

def _config_dir() -> Path:
    try:
        import jarvis_framework as fw
        return Path(fw.CONFIG_DIR)
    except Exception:
        pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def profile_dir() -> Path:
    """The browser profile used ONLY for Jarvis's Gemini window."""
    return _config_dir() / "chatbot" / "gemini-profile"


def check_report_path() -> Path:
    return _config_dir() / "chatbot" / "gemini-check.txt"


def _browser_name() -> str:
    b = (os.environ.get("JARVIS_GEMINI_BROWSER") or "chromium").strip().lower()
    return b if b in BROWSERS else "chromium"


def _import_playwright() -> Callable:
    """sync_playwright, or GeminiUnavailable in plain words."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        raise GeminiUnavailable(NOT_INSTALLED) from None
    return sync_playwright


def playwright_installed() -> bool:
    """Is Playwright there? Looked up, not loaded (cheap: both apps' status
    asks this)."""
    try:
        return importlib.util.find_spec("playwright.sync_api") is not None
    except (ImportError, ValueError):
        return False


def ready() -> str:
    """"" when a conversation can start; otherwise the plain-words reason and
    the one line that fixes it. Opens nothing. jarvis_chatbot.plan() asks
    this BEFORE any approval card, so a card is never raised for something
    that cannot run."""
    if not playwright_installed():
        return NOT_INSTALLED
    if not profile_dir().is_dir():
        return NOT_SIGNED_IN
    return ""


def _host_path(url: str) -> tuple:
    try:
        u = urllib.parse.urlsplit(str(url or ""))
        return (u.hostname or "").lower().rstrip("."), u.path or "/"
    except ValueError:
        return "", "/"


def _is_google_sorry(host: str, path: str) -> bool:
    return bool(_SORRY_PATH.match(path)) and (host == "google.com" or host.startswith("www.google.")
                                             or host.startswith("google."))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace(" ", " ")).strip()


# ============================================================================
#   One thread owns the browser
# ============================================================================

class _Worker:
    """Runs every browser call on one thread, in order."""

    def __init__(self):
        self._q: "queue.Queue" = queue.Queue()
        self._t = threading.Thread(target=self._loop, name="jarvis-gemini", daemon=True)
        self._t.start()

    def _loop(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                return
            fn, box, done = item
            try:
                box["value"] = fn()
            except BaseException as exc:  # handed back to the caller
                box["error"] = exc
            done.set()

    def call(self, fn: Callable, timeout: float):
        if threading.current_thread() is self._t:
            return fn()
        box: dict = {}
        done = threading.Event()
        self._q.put((fn, box, done))
        if not done.wait(timeout):
            raise TimeoutError("the Gemini window did not answer in time")
        if "error" in box:
            raise box["error"]
        return box.get("value")

    def stop(self) -> None:
        self._q.put(None)

    def alive(self) -> bool:
        return self._t.is_alive()


# ============================================================================
#   The adapter
# ============================================================================

class GeminiWeb(CB.Adapter):
    """Gemini through its website, in a window the owner can see.

    The keyword arguments exist for test_chatbot_gemini.py, which points the
    adapter at a fake page on 127.0.0.1. The registry's factory uses none of
    them, so the real adapter only ever opens START_URL."""
    id = ID
    name = NAME
    host = HOST

    def __init__(self, *, start_url: str = START_URL, chat_hosts: tuple = (HOST,),
                 sign_in_hosts: tuple = SIGN_IN_HOSTS, profile: Optional[Path] = None,
                 type_delay_ms: int = TYPE_DELAY_MS, settle_seconds: float = SETTLE_SECONDS,
                 open_wait: float = OPEN_WAIT, browser: Optional[str] = None):
        self.start_url = str(start_url)
        self.chat_hosts = tuple(h.lower() for h in chat_hosts)
        self.sign_in_hosts = tuple(h.lower() for h in sign_in_hosts)
        self.profile = Path(profile) if profile is not None else None
        self.type_delay_ms = int(type_delay_ms)
        self.settle_seconds = float(settle_seconds)
        self.open_wait = float(open_wait)
        self.browser = browser or _browser_name()
        #: Which selector matched, per role: {role: (number, selector)}. For
        #: the owner's self-check; holds no page text.
        self.matched: dict = {}
        self._worker: Optional[_Worker] = None
        self._pw = None
        self._ctx = None
        self._page = None
        self._closed = False
        self._before: dict = {}      # reply selector -> how many replies before our message
        self._waiting = False        # a message was sent and its reply not yet handed back
        self._last_text = ""
        self._last_change = 0.0
        self._sent = 0               # messages this adapter has sent
        self._chat_path = ""         # the chat's address once Gemini gave it one

    # ---- the interface ---------------------------------------------------

    def open(self) -> None:
        if self._closed:
            raise GeminiUnavailable("This Gemini window was already closed.")
        sync_playwright = _import_playwright()
        if self._worker is None:
            self._worker = _Worker()
        self._worker.call(lambda: self._open_here(sync_playwright), self.open_wait + 90)

    def send(self, text: str) -> None:
        text = str(text or "")
        if not text.strip():
            raise ValueError("nothing to send")
        budget = len(text) * self.type_delay_ms / 1000.0 + SENT_WAIT + 60
        self._call(lambda: self._send_here(text), budget)

    def read_reply(self, timeout: float) -> Optional[str]:
        t = max(0.0, float(timeout))
        return self._call(lambda: self._read_here(t), t + 30)

    def status(self) -> CB.Status:
        if self._closed or self._worker is None:
            return CB.Status("gone")
        try:
            return self._call(self._status_here, 30)
        except Exception:
            return CB.Status("gone")

    def close(self) -> None:
        """Close the window. Never raises; safe from any thread, twice."""
        if self._closed:
            return
        self._closed = True
        w, self._worker = self._worker, None
        if w is None:
            return
        try:
            w.call(self._close_here, 30)
        except Exception:
            pass
        w.stop()

    # ---- for the tests and the self-check ----------------------------------

    def _navigate(self, url: str) -> None:
        """Open `url` in the window - refused for any host but Gemini's."""
        self._call(lambda: self._goto_here(url), 60)

    def _call(self, fn: Callable, timeout: float):
        if self._closed or self._worker is None:
            raise RuntimeError("the Gemini window is not open")
        return self._worker.call(fn, timeout)

    # ---- everything below runs on the worker thread ------------------------

    def _open_here(self, sync_playwright) -> None:
        folder = self.profile if self.profile is not None else profile_dir()
        folder.mkdir(parents=True, exist_ok=True)
        pw = sync_playwright().start()
        try:
            opts = {}
            if self.browser != "chromium":
                opts["channel"] = self.browser
            # headless=False: a real window on the owner's screen. Playwright's
            # own launch defaults are kept as they are. no_viewport lets the
            # page follow the window's size, like any browser window.
            ctx = pw.chromium.launch_persistent_context(
                str(folder), headless=False, no_viewport=True, **opts)
        except Exception as exc:
            pw.stop()
            msg = str(exc)
            if "Executable doesn't exist" in msg or "playwright install" in msg:
                raise GeminiUnavailable(NO_BROWSER) from None
            if "ProcessSingleton" in msg or "user data directory is already in use" in msg \
                    or "SingletonLock" in msg:
                raise GeminiUnavailable(PROFILE_BUSY) from None
            raise
        self._pw, self._ctx = pw, ctx
        ctx.set_default_timeout(STEP_TIMEOUT_MS)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        self._page = page
        self._goto_here(self.start_url)
        # Wait for the message box (the page builds it after loading), or
        # for a page that needs the owner. Either way open() returns:
        # status() says which.
        end = time.monotonic() + self.open_wait
        while time.monotonic() < end:
            st = self._status_here()
            if st.state == "gone" or st.reason != NO_BOX:
                break
            page.wait_for_timeout(250)
        self._before = self._reply_counts()
        self._waiting = False

    def _goto_here(self, url: str) -> None:
        host, _ = _host_path(url)
        if host not in self.chat_hosts:
            raise PermissionError(f"Jarvis's Gemini window only opens {', '.join(self.chat_hosts)}"
                                  f" by itself, not {host or 'that address'}")
        self._page.goto(url, wait_until="domcontentloaded")

    def _close_here(self) -> None:
        ctx, pw = self._ctx, self._pw
        self._ctx = self._pw = self._page = None
        try:
            if ctx is not None:
                ctx.close()
        finally:
            if pw is not None:
                pw.stop()

    def _page_alive(self) -> bool:
        p = self._page
        if p is None or self._ctx is None:
            return False
        try:
            return not p.is_closed()
        except Exception:
            return False

    def _visible(self, selector: str):
        """The first VISIBLE element for `selector`, or None. Never waits."""
        try:
            loc = self._page.locator(selector)
            n = loc.count()
        except Exception:
            return None
        for i in range(min(n, 20)):
            el = loc.nth(i)
            try:
                if el.is_visible():
                    return el
            except Exception:
                continue
        return None

    def _find(self, role: str):
        for i, sel in enumerate(SELECTORS[role], 1):
            el = self._visible(sel)
            if el is not None:
                self.matched[role] = (i, sel)
                return el
        return None

    def _texts(self, role: str, most: int = 12) -> list:
        """Short texts of VISIBLE headings/alerts/dialogs - for the warning
        check only. Never kept, never handed on. Anything inside a reply, a
        message of Jarvis's, or the sidebar is skipped: a reply that talks
        about "unusual activity" is not a warning page, and the sidebar
        (the account's other chats) is never read."""
        out = []
        for sel in SELECTORS[role]:
            try:
                loc = self._page.locator(sel)
                n = min(loc.count(), most)
            except Exception:
                continue
            for i in range(n):
                el = loc.nth(i)
                try:
                    if not el.is_visible() or el.evaluate(_SKIP_JS):
                        continue
                    out.append(el.inner_text(timeout=2000)[:300])
                except Exception:
                    continue
        return out

    def _status_here(self) -> CB.Status:
        if not self._page_alive():
            return CB.Status("gone")
        try:
            url = self._page.url
        except Exception:
            return CB.Status("gone")
        host, path = _host_path(url)
        if host in self.sign_in_hosts:
            return CB.Status("needs_owner", "login")
        if _is_google_sorry(host, path):
            return CB.Status("needs_owner", "unusual")
        if host not in self.chat_hosts:
            return CB.Status("needs_owner", f"a page on {host or 'no address'}"[:60])
        if self._chat_path and path != self._chat_path:
            start = _host_path(self.start_url)[1].rstrip("/")
            if self._chat_path.rstrip("/") == start and path.startswith(start + "/"):
                # Gemini gave this new chat its own address (/app/<id>).
                self._chat_path = path
            else:
                # Someone opened another chat in the window: never read it.
                return CB.Status("needs_owner", "a different chat is showing")
        if self._find("captcha") is not None:
            return CB.Status("needs_owner", "captcha")
        texts = self._texts("warning")
        if any(UNUSUAL_WORDS.search(t) for t in texts):
            return CB.Status("needs_owner", "unusual")
        if self._find("sign_in_form") is not None or self._find("signed_out") is not None \
                or any(SIGN_IN_WORDS.search(t) for t in texts):
            return CB.Status("needs_owner", "login")
        if self._find("notice") is not None:
            return CB.Status("needs_owner", "a notice is open over the page")
        if self._find("input") is None:
            return CB.Status("needs_owner", NO_BOX)
        return CB.OK

    def _reply_counts(self) -> dict:
        out = {}
        for sel in SELECTORS["reply"]:
            try:
                out[sel] = self._page.locator(sel).count()
            except Exception:
                out[sel] = 0
        return out

    def _newest_reply(self):
        """The newest reply that appeared AFTER our message, or None. Older
        replies and anything outside the reply elements are never read."""
        for i, sel in enumerate(SELECTORS["reply"], 1):
            try:
                loc = self._page.locator(sel)
                n = loc.count()
            except Exception:
                continue
            if n > self._before.get(sel, 0):
                self.matched["reply"] = (i, sel)
                return loc.nth(n - 1)
        return None

    def _reply_text(self, reply) -> str:
        for i, sel in enumerate(SELECTORS["reply_text"], 1):
            try:
                inner = reply.locator(sel)
                if inner.count():
                    self.matched["reply_text"] = (i, sel)
                    return inner.last.inner_text(timeout=3000)
            except Exception:
                continue
        try:
            self.matched["reply_text"] = (0, "the whole reply element")
            return reply.inner_text(timeout=3000)
        except Exception:
            return ""

    def _input_text(self, box) -> str:
        try:
            v = box.evaluate("e => ('value' in e && e.tagName === 'TEXTAREA') ? e.value "
                             ": e.innerText")
            return str(v or "")
        except Exception:
            return ""

    def _type_message(self, box, text: str) -> None:
        """Click the message box and type `text` at a fixed pace. A line
        break is Shift+Enter, because Enter alone would send half a message."""
        kb = self._page.keyboard
        box.click()
        if _norm(self._input_text(box)):
            kb.press("Control+A")
            kb.press("Backspace")
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        for i, line in enumerate(lines):
            if i:
                kb.press("Shift+Enter")
            if line:
                kb.type(line, delay=self.type_delay_ms)

    def _press_send(self) -> None:
        btn = self._find("send")
        if btn is None:
            raise RuntimeError("Gemini's send button was not found (its selector may need "
                               "updating: run the self-check)")
        end = time.monotonic() + 5
        while not btn.is_enabled() and time.monotonic() < end:
            self._page.wait_for_timeout(100)
        btn.click()

    def _send_here(self, text: str) -> None:
        st = self._status_here()
        if st.state != "ok":
            # The driver looks first; this is a second lock, not a retry.
            raise RuntimeError(f"not sending: the page needs you ({st.reason or st.state})")
        if self._waiting:
            raise RuntimeError("not sending: the last reply has not been read yet")
        if self._sent == 0 and _host_path(self._page.url)[1] != _host_path(self.start_url)[1]:
            # The first message always goes into a NEW chat: if the window
            # shows anything else by now (the owner signed in, or looked at
            # something), open a fresh one first.
            self._goto_here(self.start_url)
            end = time.monotonic() + self.open_wait
            while self._find("input") is None and time.monotonic() < end:
                self._page.wait_for_timeout(250)
            st = self._status_here()
            if st.state != "ok":
                raise RuntimeError(f"not sending: the page needs you ({st.reason or st.state})")
        box = self._find("input")
        if box is None:
            raise RuntimeError("Gemini's message box was not found")
        self._before = self._reply_counts()
        self._type_message(box, text)
        typed = self._input_text(box)
        if _norm(typed) != _norm(text):
            # Never send anything but exactly the checked words.
            self._page.keyboard.press("Control+A")
            self._page.keyboard.press("Backspace")
            raise RuntimeError("the message box did not hold exactly the message, so nothing "
                               "was sent")
        self._press_send()
        # Taken: the box empties, a reply starts, or the stop control shows.
        end = time.monotonic() + SENT_WAIT
        while time.monotonic() < end:
            if self._find("stop") is not None or self._newest_reply() is not None:
                break
            if self._status_here().state != "ok":
                # The page changed under it (a captcha, another page): the
                # message may have gone. status() now says what the page is.
                break
            box2 = self._find("input")
            if box2 is not None and not _norm(self._input_text(box2)):
                break
            self._page.wait_for_timeout(200)
        else:
            raise RuntimeError("Gemini did not take the message")
        self._waiting = True
        self._sent += 1
        self._last_text = ""
        self._last_change = time.monotonic()

    def _read_here(self, timeout: float) -> Optional[str]:
        if not self._waiting:
            return None
        end = time.monotonic() + timeout
        while True:
            if not self._page_alive():
                raise RuntimeError("the Gemini window was closed")
            reply = self._newest_reply()
            if reply is not None:
                text = self._reply_text(reply)
                now = time.monotonic()
                if text != self._last_text:
                    self._last_text, self._last_change = text, now
                writing = self._find("stop") is not None
                if (not writing and _norm(text)
                        and now - self._last_change >= self.settle_seconds):
                    self._waiting = False
                    self._before = self._reply_counts()
                    if not self._chat_path:
                        self._chat_path = _host_path(self._page.url)[1]
                    out, self._last_text = text.strip(), ""
                    return out
            if time.monotonic() >= end:
                return None
            self._page.wait_for_timeout(int(POLL_SECONDS * 1000))


def _factory() -> CB.Adapter:
    """The registry's factory: the real site, the real profile. Opens
    nothing until the driver calls open()."""
    return GeminiWeb()


CB.register_adapter(CB.AdapterInfo(
    ID, NAME, HOST, _factory, built=True,
    how=("through its website, in a browser window you can see, signed in with the "
         "spare Google account used only by Jarvis"),
    card_note=("Jarvis types at a person's pace and never hides that it is a program, "
               "never changes how the browser looks to Google, and never solves or skips "
               "a captcha - at a captcha, a sign-in or an \"unusual activity\" page it stops "
               "and asks you. It opens a new chat and reads only the replies to its own "
               "messages. Google's terms forbid automated use of its services, so the "
               "spare account could be closed."),
    ready=ready))


# ============================================================================
#   The owner's two commands: sign in once, and check the selectors
# ============================================================================

def sign_in(*, out=print, adapter: Optional[GeminiWeb] = None,
            wait: float = SIGN_IN_WAIT) -> int:
    """Open Jarvis's Gemini window and wait while the owner signs in, by
    hand, to the spare Google account. Jarvis types nothing and reads no
    password; it only watches whether the message box has appeared."""
    try:
        _import_playwright()
    except GeminiUnavailable as exc:
        out(exc.owner_words)
        return 1
    a = adapter if adapter is not None else GeminiWeb(open_wait=5)
    out("Opening Jarvis's own Gemini window (a profile used only for this, in "
        f"{profile_dir()}).")
    out("In that window: click Sign in, and sign in to the SPARE Google account used only by "
        "Jarvis - not your main one. Jarvis does not see or keep the password.")
    out("When Gemini's message box shows, close the window. Waiting up to 30 minutes.")
    try:
        a.open()
    except GeminiUnavailable as exc:
        out(exc.owner_words)
        a.close()
        return 1
    signed = False
    end = time.monotonic() + wait
    try:
        while time.monotonic() < end:
            try:
                alive = a._call(a._page_alive, 30)
                st = a._call(a._status_here, 30) if alive else CB.Status("gone")
            except Exception:
                break
            if st.state == "gone":
                break
            if st.state == "ok" and not signed:
                signed = True
                out("Signed in: Gemini's message box is showing. You can close the window now.")
            time.sleep(1.0)
    finally:
        a.close()
    if signed:
        out("Done. Jarvis's Gemini window stays signed in. To check it works, run: "
            + CHECK_LINE)
        return 0
    out("The window closed before Gemini's message box showed, so it may not be signed in. "
        "Run this again to finish: " + SIGN_IN_LINE)
    return 1


CHECK_QUESTION = "What is 2 plus 2?"


def self_check(*, out=print, adapter: Optional[GeminiWeb] = None,
               report: Optional[Path] = None, reply_wait: float = 120.0) -> int:
    """Send ONE harmless fixed question and print PASS or FAIL per step, with
    which selector matched - so the selectors are proved on the owner's PC
    before any real conversation. Stops at any page that needs the owner."""
    lines: list = []

    def step(ok: bool, what: str, detail: str = "") -> bool:
        line = f"{'PASS' if ok else 'FAIL'}  {what}" + (f" - {detail}" if detail else "")
        lines.append(line)
        out(line)
        return ok

    def sel(role: str) -> str:
        m = a.matched.get(role)
        return f"selector {m[0]} of {len(SELECTORS[role])}: {m[1]}" if m else "no selector matched"

    a = adapter
    report = report or check_report_path()
    try:
        _import_playwright()
        step(True, "Playwright is installed")
    except GeminiUnavailable as exc:
        step(False, "Playwright is installed", exc.owner_words)
        return _finish(lines, report, out)
    if a is None:
        if not profile_dir().is_dir():
            step(False, "Jarvis's Gemini window has been signed in once", NOT_SIGNED_IN)
            return _finish(lines, report, out)
        a = GeminiWeb()
    try:
        _check_steps(a, step, sel, reply_wait)
    finally:
        a.close()
        step(True, "Closed the window")
    return _finish(lines, report, out)


def _check_steps(a: "GeminiWeb", step: Callable, sel: Callable, reply_wait: float) -> None:
    """The self-check's steps with the window open. Returns at the first
    step that cannot go on; self_check() closes the window either way."""
    try:
        a.open()
        step(True, "The browser window opened (you can see it)")
    except Exception as exc:
        step(False, "The browser window opened",
             getattr(exc, "owner_words", "") or type(exc).__name__)
        return
    st = a.status()
    if not step(st.state == "ok", "Gemini's chat page is showing (no sign-in, captcha or "
                "warning page)", "" if st.state == "ok" else
                f"{st.state}: {st.reason} - deal with it in the window, then run this again"):
        return
    step("input" in a.matched, "Found the message box", sel("input"))
    try:
        a.send(CHECK_QUESTION)
        step(True, f"Typed and sent \"{CHECK_QUESTION}\"", sel("send"))
    except Exception as exc:
        step(False, f"Typed and sent \"{CHECK_QUESTION}\"", f"{exc} ({sel('send')})")
        return
    reply, started, saw_stop = None, time.monotonic(), False
    while reply is None and time.monotonic() - started < reply_wait:
        reply = a.read_reply(2.0)
        saw_stop = saw_stop or "stop" in a.matched
    step(reply is not None, "A complete reply came back",
         f"{sel('reply')}; words: {sel('reply_text')}" if reply is not None
         else f"nothing within {int(reply_wait)} seconds ({sel('reply')})")
    step(saw_stop, "Saw the \"stop response\" button while it wrote", sel("stop")
         if saw_stop else "not seen - replies are still read, but only by waiting for the "
                          "text to stop changing")
    if reply is not None:
        step(bool(re.search(r"\b4\b|\bfour\b", reply, re.IGNORECASE)),
             "The reply answers the question (it says 4)", _norm(reply)[:120])
    st = a.status()
    step(st.state == "ok", "The page is still the normal chat afterwards",
         "" if st.state == "ok" else f"{st.state}: {st.reason}")


def _finish(lines: list, report: Path, out) -> int:
    failed = sum(1 for l in lines if l.startswith("FAIL"))
    summary = f"{len(lines) - failed} pass, {failed} fail"
    lines.append(summary)
    out(summary)
    try:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        out(f"These results are also saved in {report}")
    except OSError:
        pass
    return 1 if failed else 0


def main(argv: list) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "sign-in":
        return sign_in()
    if cmd == "check":
        return self_check()
    print("Jarvis's Gemini window. Two commands, run in Jarvis's folder:\n"
          f"  {SIGN_IN_LINE}   sign in once, by hand, to the spare Google account\n"
          f"  {CHECK_LINE}     send one harmless question and print PASS/FAIL per step")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
