"""jarvis_chatbot_web.py - what every chatbot WEBSITE adapter shares: Jarvis
types into a chatbot's website in a browser window the owner can see.

NEW MODULE, shipped whole (like jarvis_chatbot.py, which it plugs into).
Each website is a THIN site file that holds only what is different about
that site - its SELECTORS table, its host, its sign-in hosts and its
wording - and hands everything else to this module:

    jarvis_chatbot_gemini.py      gemini_web       gemini.google.com
    jarvis_chatbot_chatgpt.py     chatgpt_web      chatgpt.com
    jarvis_chatbot_claude.py      claude_web       claude.ai
    jarvis_chatbot_copilot.py     copilot_web      copilot.microsoft.com
    jarvis_chatbot_perplexity.py  perplexity_web   www.perplexity.ai
    jarvis_chatbot_deepseek.py    deepseek_web     chat.deepseek.com
    jarvis_chatbot_grok.py        grok_web         grok.com
    jarvis_chatbot_lechat.py      lechat_web       chat.mistral.ai
    jarvis_chatbot_metaai.py      metaai_web       www.meta.ai

jarvis_chatbot.py imports this module at its end; load_sites(), at the end
of THIS module, imports every site file in SITE_MODULES, and each one
registers itself in the driver's list. Every site is reachable from both
apps through /api/chatbot/* (jarvis_chatbot_routes.py, docs/JARVIS-API.md
section 60) once Playwright is installed and that site's window has been
signed in. NONE of them has yet been tried against its real site.

THE OWNER'S DECISIONS (CLAUDE.md, 2026-09-28; docs/CHATBOT-DRIVER-DESIGN.md)
  * Gemini first, through its WEBSITE, driven OPENLY; then "the chatbot
    driver becomes versatile": ChatGPT, Claude, Microsoft Copilot,
    Perplexity and other commonly used chatbot websites, driven openly like
    Gemini, each with its own SPARE account used only by Jarvis. The owner
    chose this knowing each company's terms restrict automated access and
    that an account could be blocked or closed.
  * A request for "tactics that help avoid bans" was declined: getting round
    a site's bot protection is not something this project builds.

WHAT "OPENLY" MEANS HERE, IN CODE (test_chatbot_gemini.py and
test_chatbot_sites.py check each one, over this file and every site file)
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
    / "verify you are human" page, a notice over the page, or anything else
    it does not recognise, status() says "needs_owner" and the adapter does
    NOTHING else. The driver (jarvis_chatbot.py) pauses and asks the owner,
    who deals with it in the visible window.

WHAT IT TOUCHES AND READS (per site)
  * One browser profile folder used ONLY for that site:
    <Jarvis settings folder>/chatbot/<site>-profile (normally
    %USERPROFILE%\\.openjarvis\\chatbot\\<site>-profile). The owner signs in
    to that site's spare account once, by hand, with
        py -3 jarvis_chatbot_<site>.py sign-in
    Jarvis never types, sees or stores the password: the site's sign-in
    cookie lives in that profile folder, as it would in any browser.
  * A NEW chat every conversation (it opens the site's new-chat address
    fresh), never an old one. It never reads the sidebar, the chat list or
    any other chat: only the newest reply that appeared AFTER its own
    message. For a site whose answers list sources (Perplexity), the links
    listed in that reply are read as TEXT - never opened, never followed.
  * It clicks exactly two things: the message box and the send button. It
    never clicks, opens or follows a link in a reply. If the send button is
    not found it stops - it does not press Enter instead.
  * The only address it opens by itself is the site's new-chat address.
    _goto_here() refuses any other host. A sign-in page is reached only by
    the OWNER clicking "Sign in" in the window.

WHEN A SITE CHANGES
Every selector is in that site's ONE table, SELECTORS, with fallbacks. They
were written without access to any of these sites (the container this was
built in cannot reach them, and must not automate them). The owner checks
them on the PC with one line per site, which sends two harmless fixed
questions in one new chat and prints PASS or FAIL per step:
    py -3 jarvis_chatbot_<site>.py check

THREADS
Playwright's objects must be used from the thread that made them, and the
driver may call close() from another thread (a Stop pressed while paused).
So every browser call runs on the adapter's own thread (_Worker), and the
public methods hand work to it and wait.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import queue
import re
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import jarvis_chatbot as CB

#: Every site file, in the order both apps list them. Gemini first (the
#: owner's first choice), then the four the owner named, then the other
#: commonly used chatbot websites.
SITE_MODULES = (
    "jarvis_chatbot_gemini",
    "jarvis_chatbot_chatgpt",
    "jarvis_chatbot_claude",
    "jarvis_chatbot_copilot",
    "jarvis_chatbot_perplexity",
    "jarvis_chatbot_deepseek",
    "jarvis_chatbot_grok",
    "jarvis_chatbot_lechat",
    "jarvis_chatbot_metaai",
)

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
#: "chrome" (the one already on the PC).
BROWSERS = ("chromium", "msedge", "chrome")
#: At most this many source links are read from one reply (as text).
MOST_SOURCES = 20

INSTALL_LINE = "py -3 -m pip install playwright; py -3 -m playwright install chromium"
NOT_INSTALLED = ("Playwright (the program Jarvis uses to work a browser window) is not "
                 "installed on this PC. To install it, run this one line in PowerShell in "
                 "Jarvis's folder: " + INSTALL_LINE)
NO_BROWSER = ("Playwright is installed, but its browser is not. Run this one line in "
              "PowerShell: py -3 -m playwright install chromium")

#: The two fixed, harmless questions every site's self-check sends, in the
#: same chat: the second one proves the conversation can carry on there
#: (a site gives a new chat its own address around the first reply, and a
#: wrong guess at that address shows only on the next message).
CHECK_QUESTION = "What is 2 plus 2?"
CHECK_QUESTION_2 = "And what is 3 plus 3?"

# ============================================================================
#   Shared selector lists a site table may reuse
# ============================================================================
#
# Plain CSS only in every table (no Playwright-only extras): the "reply" and
# "own" selectors are also handed to the page's own closest(), where anything
# but CSS would fail.

#: An email or password box: a sign-in page.
SIGN_IN_FORM = (
    'input[type="email"]',
    'input[type="password"]',
    'input[name="identifier"]',
    'input[name="username"]',
)
#: "Prove you are a person" checks the big sites are known to use.
CAPTCHA = (
    'iframe[src*="recaptcha"]',
    'iframe[src*="hcaptcha"]',
    'iframe[src*="challenges.cloudflare.com"]',
    'iframe[src*="arkoselabs"]',
    'iframe[title*="captcha" i]',
    'iframe[title*="challenge" i]',
    '.cf-turnstile',
    '#challenge-form',
    '#challenge-stage',
    '.g-recaptcha',
    '#captcha-form',
)
#: Headings and alerts that may say "unusual activity" (text below).
WARNING = (
    'h1',
    'h2',
    '[role="alert"]',
    '[role="alertdialog"]',
)
#: Anything laid over the page (a dialog, a cookie box).
NOTICE = (
    '[role="alertdialog"]',
    '[role="dialog"]',
)
#: Where the warning check never looks, on every site: the sidebar.
SIDEBAR = ('nav', '[role="navigation"]')

#: Words in a heading, alert or dialog that mean the site wants a person.
UNUSUAL_WORDS = re.compile(
    r"unusual (?:traffic|activity)|suspicious activity"
    r"|verify (?:it'?s|it’s) you|confirm (?:it'?s|it’s) you"
    r"|(?:verify|confirm) (?:that )?you are (?:a )?human"
    r"|automated (?:queries|requests)|are you a robot|not a robot"
    r"|checking (?:your browser|if the site connection is secure)",
    re.IGNORECASE)
#: Words that mean the page wants a sign-in.
SIGN_IN_WORDS = re.compile(
    r"^\s*(?:sign in|sign into|log in|log into|choose an account|use your google account)\b",
    re.IGNORECASE)
#: status()'s reason when the chat page shows no message box (still loading,
#: or the selectors need updating - the self-check says which).
NO_BOX = "no message box on the page"
#: Google's "unusual traffic" page lives at google.<tld>/sorry/...
_SORRY_PATH = re.compile(r"^/sorry(?:/|$)")


class WebUnavailable(RuntimeError):
    """The window cannot be opened. `owner_words` is the plain-words reason,
    with the one line to fix it; jarvis_chatbot.run() shows it."""

    def __init__(self, owner_words: str):
        super().__init__(owner_words)
        self.owner_words = owner_words


# ============================================================================
#   A site: everything that is different about one chatbot website
# ============================================================================

@dataclass(frozen=True)
class Site:
    """One chatbot website. The site file fills this in; nothing else in it
    decides anything.

        id            the driver's chatbot id ("chatgpt_web")
        name          what the owner calls it ("ChatGPT")
        host          the one host the window opens by itself
        start_url     the new-chat address, on `host`
        module        the site file, for the owner's command lines
        profile_name  <config>/chatbot/<profile_name>-profile
        account       what the spare account is ("OpenAI account")
        company       who runs the site, for the card ("OpenAI")
        selectors     the site's SELECTORS table
        sign_in_hosts hosts whose pages are a sign-in (reason "login"); the
                      window never opens them itself
        sign_in_paths a regex over the path: a sign-in page on `host` itself
        chat_address  a regex over the path: the address a NEW chat gets
                      once the site names it ("/c/<id>"). Empty: anything
                      under the start address (Gemini's /app -> /app/<id>)
        terms         the card's sentence about the site's terms
        card_note     the whole card note, when a site words its own
        browser_env   the environment variable that picks the browser
        blocked_page  callable(host, path) -> True for the site's own
                      "unusual traffic" page (Google's /sorry)
    """
    id: str
    name: str
    host: str
    start_url: str
    module: str
    profile_name: str
    account: str
    company: str
    selectors: dict = field(default_factory=dict, compare=False, hash=False)
    sign_in_hosts: tuple = ()
    sign_in_paths: str = ""
    chat_address: str = ""
    terms: str = ""
    card_note: str = ""
    browser_env: str = ""
    blocked_page: Optional[Callable] = field(default=None, compare=False, hash=False)

    # ---- the words and command lines, one place -------------------------

    @property
    def sign_in_line(self) -> str:
        return f"py -3 {self.module} sign-in"

    @property
    def check_line(self) -> str:
        return f"py -3 {self.module} check"

    @property
    def not_signed_in(self) -> str:
        return (f"Jarvis's {self.name} window has never been signed in. Sign in once, by "
                f"hand, to the spare {self.account} used only by Jarvis: run this one line "
                f"in PowerShell in Jarvis's folder: {self.sign_in_line}")

    @property
    def sign_in_unfinished(self) -> str:
        """The profile folder is there but no finished sign-in was recorded:
        the sign-in window was closed early, or it was set up before Jarvis
        recorded a finished sign-in (2026-09-28). Running sign-in again is
        quick when the window is in fact signed in: it sees the message box
        at once."""
        return (f"Jarvis's {self.name} window was opened, but its sign-in was never "
                f"finished (or it was set up before Jarvis kept a note of a finished "
                f"sign-in). Run this one line in PowerShell in Jarvis's folder and sign in "
                f"to the spare {self.account} used only by Jarvis - if it is already signed "
                f"in, it finishes as soon as {self.name}'s message box shows: "
                f"{self.sign_in_line}")

    @property
    def profile_busy(self) -> str:
        return (f"Jarvis's {self.name} window is already open (the sign-in window, or a "
                "check). Close that window first, then try again.")

    @property
    def how(self) -> str:
        return ("through its website, in a browser window you can see, signed in with the "
                f"spare {self.account} used only by Jarvis")

    @property
    def note(self) -> str:
        """The card note: driven openly, the terms, the spare account, and
        that the account may be blocked or closed - in plain words."""
        if self.card_note:
            return self.card_note
        return ("Driven openly: Jarvis types at a person's pace in a window you can see, "
                "never hides that it is a program, never changes how the browser looks to "
                f"{self.company}, and never solves or skips a captcha - at a captcha, a "
                "sign-in or an \"unusual activity\" page it stops and asks you. It opens a "
                "new chat and reads only the replies to its own messages. "
                + (self.terms.strip() + " " if self.terms.strip() else "")
                + f"It uses a spare {self.account} used only by Jarvis, never your own, and "
                  "that account may be blocked or closed.")


# ============================================================================
#   Where things live
# ============================================================================

def config_dir() -> Path:
    try:
        import jarvis_framework as fw
        return Path(fw.CONFIG_DIR)
    except Exception:
        pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def profile_dir(site: Site) -> Path:
    """The browser profile used ONLY for this site's window."""
    return config_dir() / "chatbot" / f"{site.profile_name}-profile"


def check_report_path(site: Site) -> Path:
    return config_dir() / "chatbot" / f"{site.profile_name}-check.txt"


#: A small file in a site's profile folder, written only when the sign-in
#: helper saw the site's message box (a sign-in that actually finished). It
#: holds the date and nothing else - no account, no cookie, no password.
#: Inside the profile folder, so deleting the folder forgets both.
SIGNED_IN_MARKER = "jarvis-signed-in.txt"


def signed_in_marker(folder: Path) -> Path:
    return Path(folder) / SIGNED_IN_MARKER


def mark_signed_in(folder: Path) -> bool:
    """Record a finished sign-in in `folder`. Never raises."""
    try:
        signed_in_marker(folder).write_text(
            "Signed in by hand with the sign-in helper on "
            + time.strftime("%Y-%m-%d") + ".\n", encoding="utf-8")
        return True
    except OSError:
        return False


def browser_name(site: Site) -> str:
    b = (os.environ.get(site.browser_env or "_") or os.environ.get("JARVIS_CHATBOT_BROWSER")
         or "chromium").strip().lower()
    return b if b in BROWSERS else "chromium"


def import_playwright() -> Callable:
    """sync_playwright, or WebUnavailable in plain words."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        raise WebUnavailable(NOT_INSTALLED) from None
    return sync_playwright


def playwright_installed() -> bool:
    """Is Playwright there? Looked up, not loaded (cheap: both apps' status
    asks this)."""
    try:
        return importlib.util.find_spec("playwright.sync_api") is not None
    except (ImportError, ValueError):
        return False


def ready(site: Site) -> str:
    """"" when a conversation can start; otherwise the plain-words reason and
    the one line that fixes it. Opens nothing. jarvis_chatbot.plan() asks
    this BEFORE any approval card, so a card is never raised for something
    that cannot run."""
    if not playwright_installed():
        return NOT_INSTALLED
    folder = profile_dir(site)
    if not folder.is_dir():
        return site.not_signed_in
    # The folder alone proves nothing: opening the sign-in window makes it.
    # Only a sign-in that finished leaves the marker.
    if not signed_in_marker(folder).is_file():
        return site.sign_in_unfinished
    return ""


def host_path(url: str) -> tuple:
    try:
        u = urllib.parse.urlsplit(str(url or ""))
        return (u.hostname or "").lower().rstrip("."), u.path or "/"
    except ValueError:
        return "", "/"


def is_google_sorry(host: str, path: str) -> bool:
    return bool(_SORRY_PATH.match(path)) and (host == "google.com" or host.startswith("www.google.")
                                             or host.startswith("google."))


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace(" ", " ")).strip()


def skip_js(site: Site) -> str:
    """The page-side test for "never look here" in the warning check:
    inside a reply, inside one of Jarvis's own messages, or the sidebar.
    So a site's "reply" and "own" selectors must stay NARROW: anything
    inside a match is skipped, and one that matched a page-wide wrapper
    would hide every warning on the page."""
    sels = list(site.selectors.get("reply", ())) + list(site.selectors.get("own", ())) \
        + list(SIDEBAR)
    return "e => !!e.closest(" + json.dumps(", ".join(sels)) + ")"


# ============================================================================
#   One thread owns the browser
# ============================================================================

class _Worker:
    """Runs every browser call on one thread, in order."""

    def __init__(self, label: str = "chatbot"):
        self._label = label
        self._q: "queue.Queue" = queue.Queue()
        self._t = threading.Thread(target=self._loop, name=f"jarvis-{label}", daemon=True)
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
            raise TimeoutError(f"the {self._label} window did not answer in time")
        if "error" in box:
            raise box["error"]
        return box.get("value")

    def stop(self) -> None:
        self._q.put(None)

    def alive(self) -> bool:
        return self._t.is_alive()


# ============================================================================
#   The adapter every website shares
# ============================================================================

class WebAdapter(CB.Adapter):
    """A chatbot website, in a window the owner can see. A site file makes a
    subclass that sets SITE (and id, name, host from it).

    The keyword arguments exist for the tests, which point the adapter at a
    fake page on 127.0.0.1. The registry's factory uses none of them, so the
    real adapter only ever opens the site's start address."""
    SITE: Site = None  # type: ignore[assignment]

    def __init__(self, *, start_url: Optional[str] = None, chat_hosts: Optional[tuple] = None,
                 sign_in_hosts: Optional[tuple] = None, profile: Optional[Path] = None,
                 type_delay_ms: int = TYPE_DELAY_MS, settle_seconds: float = SETTLE_SECONDS,
                 open_wait: float = OPEN_WAIT, browser: Optional[str] = None):
        site = self.SITE
        if site is None:
            raise TypeError("a website adapter needs its SITE")
        self.site = site
        self.start_url = str(start_url if start_url is not None else site.start_url)
        self.chat_hosts = tuple(h.lower() for h in (chat_hosts if chat_hosts is not None
                                                    else (site.host,)))
        self.sign_in_hosts = tuple(h.lower() for h in (sign_in_hosts if sign_in_hosts
                                                       is not None else site.sign_in_hosts))
        self.profile = Path(profile) if profile is not None else None
        self.type_delay_ms = int(type_delay_ms)
        self.settle_seconds = float(settle_seconds)
        self.open_wait = float(open_wait)
        self.browser = browser or browser_name(site)
        self.selectors = site.selectors
        self._skip_js = skip_js(site)
        self._chat_re = re.compile(site.chat_address) if site.chat_address else None
        self._sign_in_path_re = re.compile(site.sign_in_paths) if site.sign_in_paths else None
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
        #: The chat this conversation is in, locked at the FIRST send: the
        #: new-chat address, then - once, and only to the site's own shape of
        #: a new chat's address - the address the site gives that chat. Any
        #: other address afterwards is "a different chat is showing".
        self._chat_path = ""

    # ---- the interface ---------------------------------------------------

    def open(self) -> None:
        if self._closed:
            raise WebUnavailable(f"This {self.site.name} window was already closed.")
        sync_playwright = import_playwright()
        if self._worker is None:
            self._worker = _Worker(self.site.name)
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
        """Open `url` in the window - refused for any host but the site's."""
        self._call(lambda: self._goto_here(url), 60)

    def _call(self, fn: Callable, timeout: float):
        if self._closed or self._worker is None:
            raise RuntimeError(f"the {self.site.name} window is not open")
        return self._worker.call(fn, timeout)

    # ---- everything below runs on the worker thread ------------------------

    def _open_here(self, sync_playwright) -> None:
        folder = self.profile if self.profile is not None else profile_dir(self.site)
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
                raise WebUnavailable(NO_BROWSER) from None
            if "ProcessSingleton" in msg or "user data directory is already in use" in msg \
                    or "SingletonLock" in msg:
                raise WebUnavailable(self.site.profile_busy) from None
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
        host, _ = host_path(url)
        if host not in self.chat_hosts:
            raise PermissionError(f"Jarvis's {self.site.name} window only opens "
                                  f"{', '.join(self.chat_hosts)} by itself, not "
                                  f"{host or 'that address'}")
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
        for i, sel in enumerate(self.selectors.get(role, ()), 1):
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
        for sel in self.selectors.get(role, ()):
            try:
                loc = self._page.locator(sel)
                n = min(loc.count(), most)
            except Exception:
                continue
            for i in range(n):
                el = loc.nth(i)
                try:
                    if not el.is_visible() or el.evaluate(self._skip_js):
                        continue
                    out.append(el.inner_text(timeout=2000)[:300])
                except Exception:
                    continue
        return out

    def _is_new_chat_address(self, path: str) -> bool:
        """Is `path` the address the site gives a NEW chat (its own id)?"""
        if self._chat_re is not None:
            return bool(self._chat_re.match(path))
        start = host_path(self.start_url)[1].rstrip("/")
        return path.startswith(start + "/")

    def _status_here(self) -> CB.Status:
        if not self._page_alive():
            return CB.Status("gone")
        try:
            url = self._page.url
        except Exception:
            return CB.Status("gone")
        host, path = host_path(url)
        if host in self.sign_in_hosts:
            return CB.Status("needs_owner", "login")
        if self.site.blocked_page is not None and self.site.blocked_page(host, path):
            return CB.Status("needs_owner", "unusual")
        if host not in self.chat_hosts:
            return CB.Status("needs_owner", f"a page on {host or 'no address'}"[:60])
        if self._sign_in_path_re is not None and self._sign_in_path_re.match(path):
            return CB.Status("needs_owner", "login")
        if self._chat_path and path != self._chat_path:
            start = host_path(self.start_url)[1].rstrip("/")
            if self._chat_path.rstrip("/") == start and self._is_new_chat_address(path):
                # The site gave this new chat its own address. Accepted ONCE:
                # from now on the chat is locked to this address.
                self._chat_path = path
            else:
                # Someone opened another chat in the window (or the site gave
                # the new chat an address of a shape this site file does not
                # expect - the self-check's second question finds that):
                # never read it.
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
        for sel in self.selectors.get("reply", ()):
            try:
                out[sel] = self._page.locator(sel).count()
            except Exception:
                out[sel] = 0
        return out

    def _newest_reply(self):
        """The newest reply that appeared AFTER our message, or None. Older
        replies and anything outside the reply elements are never read."""
        for i, sel in enumerate(self.selectors.get("reply", ()), 1):
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
        for i, sel in enumerate(self.selectors.get("reply_text", ()), 1):
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

    def _sources(self, reply) -> list:
        """The source links listed INSIDE this reply, as (label, address)
        text pairs - read with get_attribute, never clicked, opened or
        followed. Only http(s) addresses, each once, at most MOST_SOURCES."""
        for i, sel in enumerate(self.selectors.get("sources", ()), 1):
            try:
                loc = reply.locator(sel)
                n = min(loc.count(), MOST_SOURCES * 2)
            except Exception:
                continue
            out, seen = [], set()
            for j in range(n):
                a = loc.nth(j)
                try:
                    href = str(a.get_attribute("href", timeout=2000) or "").strip()
                    label = norm(a.inner_text(timeout=2000))[:120]
                except Exception:
                    continue
                if not re.match(r"^https?://", href, re.IGNORECASE) or href in seen:
                    continue
                seen.add(href)
                out.append((label, href))
                if len(out) >= MOST_SOURCES:
                    break
            if out:
                self.matched["sources"] = (i, sel)
                return out
        return []

    def _whole_reply(self, reply) -> str:
        """The reply's words, and - for a site whose answers list sources -
        the listed links as plain text after them."""
        text = self._reply_text(reply)
        if not self.selectors.get("sources"):
            return text
        found = self._sources(reply)
        if not found or not norm(text):
            return text
        lines = [f"{n}. {label + ' - ' if label else ''}{href}"
                 for n, (label, href) in enumerate(found, 1)]
        return (text.rstrip() + f"\n\nSources listed by {self.site.name} (links not opened):\n"
                + "\n".join(lines))

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
        if norm(self._input_text(box)):
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
            raise RuntimeError(f"{self.site.name}'s send button was not found (its selector "
                               "may need updating: run the self-check)")
        end = time.monotonic() + 5
        while not btn.is_enabled() and time.monotonic() < end:
            self._page.wait_for_timeout(100)
        btn.click()

    def _send_here(self, text: str) -> None:
        if self._sent == 0:
            # Nothing sent yet: no chat is locked (a first send that failed
            # half-way does not leave one behind). It is locked below.
            self._chat_path = ""
        st = self._status_here()
        if st.state != "ok":
            # The driver looks first; this is a second lock, not a retry.
            raise RuntimeError(f"not sending: the page needs you ({st.reason or st.state})")
        if self._waiting:
            raise RuntimeError("not sending: the last reply has not been read yet")
        if self._sent == 0 and host_path(self._page.url)[1] != host_path(self.start_url)[1]:
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
        if self._sent == 0:
            # Lock the chat at the first send: the new-chat address it is on
            # now. Only one move from here is accepted - to this new chat's
            # own address (status()); anything else is another chat, whose
            # replies are never read.
            self._chat_path = host_path(self._page.url)[1]
        box = self._find("input")
        if box is None:
            raise RuntimeError(f"{self.site.name}'s message box was not found")
        self._before = self._reply_counts()
        self._type_message(box, text)
        typed = self._input_text(box)
        if norm(typed) != norm(text):
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
            if box2 is not None and not norm(self._input_text(box2)):
                break
            self._page.wait_for_timeout(200)
        else:
            raise RuntimeError(f"{self.site.name} did not take the message")
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
                raise RuntimeError(f"the {self.site.name} window was closed")
            # Read ONLY while the page is the normal chat this conversation
            # is in. Anything else (another chat opened in the window, a
            # captcha, a sign-in page) and nothing is read: the driver's own
            # status() look then pauses and asks the owner.
            if self._status_here().state != "ok":
                if time.monotonic() >= end:
                    return None
                self._page.wait_for_timeout(int(POLL_SECONDS * 1000))
                continue
            reply = self._newest_reply()
            if reply is not None:
                text = self._whole_reply(reply)
                now = time.monotonic()
                if text != self._last_text:
                    self._last_text, self._last_change = text, now
                writing = self._find("stop") is not None
                if (not writing and norm(text)
                        and now - self._last_change >= self.settle_seconds):
                    self._waiting = False
                    self._before = self._reply_counts()
                    out, self._last_text = text.strip(), ""
                    return out
            if time.monotonic() >= end:
                return None
            self._page.wait_for_timeout(int(POLL_SECONDS * 1000))


def register(site: Site, factory: Callable[[], CB.Adapter], ready_fn: Callable[[], str]) -> None:
    """Put a site in the driver's list, as built. Opens nothing."""
    CB.register_adapter(CB.AdapterInfo(
        site.id, site.name, site.host, factory, built=True, how=site.how,
        card_note=site.note, ready=ready_fn))


# ============================================================================
#   The owner's two commands: sign in once, and check the selectors
# ============================================================================

def sign_in(site: Site, cls: type, *, out=print, adapter: Optional[WebAdapter] = None,
            wait: float = SIGN_IN_WAIT) -> int:
    """Open Jarvis's window for `site` and wait while the owner signs in, by
    hand, to the spare account. Jarvis types nothing and reads no password;
    it only watches whether the message box has appeared."""
    try:
        import_playwright()
    except WebUnavailable as exc:
        out(exc.owner_words)
        return 1
    a = adapter if adapter is not None else cls(open_wait=5)
    out(f"Opening Jarvis's own {site.name} window (a profile used only for this, in "
        f"{profile_dir(site)}).")
    out(f"In that window: click Sign in, and sign in to the SPARE {site.account} used only by "
        "Jarvis - not your main one. Jarvis does not see or keep the password.")
    out(f"When {site.name}'s message box shows, close the window. Waiting up to 30 minutes.")
    try:
        a.open()
    except WebUnavailable as exc:
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
                folder = a.profile if a.profile is not None else profile_dir(site)
                if not mark_signed_in(folder):
                    out(f"(Jarvis could not note the finished sign-in in {folder}, so it "
                        "may still say the window is not signed in.)")
                out(f"Signed in: {site.name}'s message box is showing. You can close the "
                    "window now.")
            time.sleep(1.0)
    finally:
        a.close()
    if signed:
        out(f"Done. Jarvis's {site.name} window stays signed in. To check it works, run: "
            + site.check_line)
        return 0
    out(f"The window closed before {site.name}'s message box showed, so it may not be signed "
        "in. Run this again to finish: " + site.sign_in_line)
    return 1


def self_check(site: Site, cls: type, *, out=print, adapter: Optional[WebAdapter] = None,
               report: Optional[Path] = None, reply_wait: float = 120.0) -> int:
    """Send TWO harmless fixed questions in one new chat and print PASS or
    FAIL per step, with which selector matched - so the selectors, and the
    conversation carrying on in the same chat, are proved on the owner's PC
    before any real conversation. Stops at any page that needs the owner."""
    lines: list = []

    def step(ok: bool, what: str, detail: str = "") -> bool:
        line = f"{'PASS' if ok else 'FAIL'}  {what}" + (f" - {detail}" if detail else "")
        lines.append(line)
        out(line)
        return ok

    def note(what: str) -> None:
        line = f"NOTE  {what}"
        lines.append(line)
        out(line)

    def sel(role: str) -> str:
        m = a.matched.get(role)
        if not m:
            return "no selector matched"
        return f"selector {m[0]} of {len(site.selectors.get(role, ()))}: {m[1]}"

    a = adapter
    report = report or check_report_path(site)
    try:
        import_playwright()
        step(True, "Playwright is installed")
    except WebUnavailable as exc:
        step(False, "Playwright is installed", exc.owner_words)
        return _finish(lines, report, out)
    if a is None:
        why = ready(site)
        if why:
            step(False, f"Jarvis's {site.name} window has been signed in once", why)
            return _finish(lines, report, out)
        a = cls()
    try:
        _check_steps(site, a, step, note, sel, reply_wait)
    finally:
        a.close()
        step(True, "Closed the window")
    return _finish(lines, report, out)


def _check_steps(site: Site, a: WebAdapter, step: Callable, note: Callable, sel: Callable,
                 reply_wait: float) -> None:
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
    if not step(st.state == "ok", f"{site.name}'s chat page is showing (no sign-in, captcha "
                "or warning page)", "" if st.state == "ok" else
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
    if reply is not None:
        why = f"{sel('reply')}; words: {sel('reply_text')}"
    else:
        st = a.status()
        why = (_after_words(site, st) if st.state == "needs_owner"
               else f"nothing within {int(reply_wait)} seconds ({sel('reply')})")
    step(reply is not None, "A complete reply came back", why)
    step(saw_stop, "Saw the \"stop\" button while it wrote", sel("stop")
         if saw_stop else "not seen - replies are still read, but only by waiting for the "
                          "text to stop changing")
    if reply is not None:
        step(bool(re.search(r"\b4\b|\bfour\b", reply, re.IGNORECASE)),
             "The reply answers the question (it says 4)", norm(reply)[:120])
        if site.selectors.get("sources"):
            # Not a PASS or a FAIL: a simple sum may come back with no sources.
            note(f"Sources read as text: {sel('sources')}" if "sources" in a.matched
                 else f"No sources were listed with this reply, so how Jarvis reads "
                      f"{site.name}'s sources is not checked by this question")
    if reply is None:
        return
    # The SECOND question, in the same chat. A site gives a new chat its own
    # address around the first reply; if this site file expects the wrong
    # shape of address, it shows only now, on the next message of a real
    # conversation - so the check sends one.
    st = a.status()
    if not step(st.state == "ok", "The page is still the same chat after the first reply",
                "" if st.state == "ok" else _after_words(site, st)):
        return
    try:
        a.send(CHECK_QUESTION_2)
        step(True, f"Typed and sent a second question in the same chat, \"{CHECK_QUESTION_2}\"")
    except Exception as exc:
        step(False, f"Typed and sent a second question in the same chat, \"{CHECK_QUESTION_2}\"",
             _after_words(site, a.status()) if a.status().state == "needs_owner" else str(exc))
        return
    reply2, started = None, time.monotonic()
    while reply2 is None and time.monotonic() - started < reply_wait:
        reply2 = a.read_reply(2.0)
    if not step(reply2 is not None, "A complete second reply came back in the same chat",
                "" if reply2 is not None else
                (_after_words(site, a.status()) if a.status().state == "needs_owner"
                 else f"nothing within {int(reply_wait)} seconds")):
        return
    step(bool(re.search(r"\b6\b|\bsix\b", reply2, re.IGNORECASE)),
         "The second reply answers the second question (it says 6)", norm(reply2)[:120])
    # A site may name the chat a moment after the reply; look once more
    # after that moment.
    time.sleep(2.0)
    st = a.status()
    step(st.state == "ok", "The page is still the same chat afterwards",
         "" if st.state == "ok" else _after_words(site, st))


def _after_words(site: Site, st) -> str:
    """The self-check's words for a page that is not the normal chat."""
    if getattr(st, "reason", "") == "a different chat is showing":
        return (f"{st.state}: {st.reason} - if you did not open another chat yourself, "
                f"{site.name} gave the new chat an address this site file does not expect, "
                f"so a real conversation would stop there too: the chat_address "
                f"line in {site.module} needs updating")
    return f"{st.state}: {st.reason}"


def _finish(lines: list, report: Path, out) -> int:
    failed = sum(1 for line in lines if line.startswith("FAIL"))
    passed = sum(1 for line in lines if line.startswith("PASS"))
    summary = f"{passed} pass, {failed} fail"
    lines.append(summary)
    out(summary)
    try:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        out(f"These results are also saved in {report}")
    except OSError:
        pass
    return 1 if failed else 0


def main(site: Site, cls: type, argv: list) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "sign-in":
        return sign_in(site, cls)
    if cmd == "check":
        return self_check(site, cls)
    print(f"Jarvis's {site.name} window. Two commands, run in Jarvis's folder:\n"
          f"  {site.sign_in_line}   sign in once, by hand, to the spare {site.account}\n"
          f"  {site.check_line}     send two harmless questions and print PASS/FAIL per step")
    return 2


# ============================================================================
#   Loading every site file
# ============================================================================

#: {module name: "ExceptionName: words"} for a site file that failed to load.
#: One broken site file never takes the others (or the driver) down with it;
#: test_chatbot_sites.py fails while this is not empty.
LOAD_ERRORS: dict = {}


def load_sites() -> None:
    """Import every site file; each registers itself. A site file that is
    missing is skipped (it was not copied to this PC); one that breaks is
    recorded in LOAD_ERRORS and skipped."""
    for name in SITE_MODULES:
        try:
            importlib.import_module(name)
            LOAD_ERRORS.pop(name, None)
        except ModuleNotFoundError as exc:
            if exc.name != name:
                LOAD_ERRORS[name] = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            LOAD_ERRORS[name] = f"{type(exc).__name__}: {exc}"


# Last, once everything above exists: a site file imports this module and
# uses it at once, so this must come after every definition.
load_sites()
