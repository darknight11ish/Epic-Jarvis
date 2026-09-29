"""jarvis_support_widget.py - the customer-support chat WINDOW: a company's
help page in a browser window the owner can see, and the chat widget on it.

NEW MODULE, shipped whole. The rules of a support chat (the details card,
the offer cards, "are you a bot?", identity checks, the last check before
every message) are all jarvis_support.py's; this file only works the
window. It is built ON the chatbot websites' shared base,
jarvis_chatbot_web.py: the same one visible browser launch
(WebAdapter._open_here), the same one host-checked way to open an address
(_goto_here), the same typing at a fixed pace, the same worker thread and
the same "needs the owner" words for captchas, sign-in pages and "unusual
activity" pages. Design: docs/CHATBOT-DRIVER-DESIGN.md, "Customer-support
chats", section 2.

DRIVEN OPENLY, as the base's docstring says, in code: a real, VISIBLE
window with Playwright's own defaults. No stealth plug-in, no change to how
the browser presents itself, no script injected into the page, no proxy,
no captcha solving, no retrying to get past a limit. At a captcha, a
sign-in page or an "unusual activity" page, status() says so and nothing
else happens; jarvis_support pauses and asks the owner.

WHAT IT CLICKS: the message box, the chat's Send button, and - only when
jarvis_support's driver picks one whose label is exactly on screen, after
the same last check as any message - one of the chat's own menu buttons
("Talk to an agent"). A button with offer words on it is never pressed
without its own offer card. It never clicks the page's "Chat with us"
launcher (the owner opens the chat), a link, an attachment, "email me the
transcript", or anything outside the chat.

ONE BROWSER PROFILE FOR SUPPORT CHATS, apart from the chatbot sites':
<Jarvis settings folder>/chatbot/support-profile. The owner signs in to
their OWN account there, by hand (Jarvis never types, sees or keeps a
password). `py -3 jarvis_support_widget.py forget-sign-ins` deletes it.

THE HOST LOCK, AND A CHAT IN A FRAME FROM ANOTHER HOST
The window opens only the company's help page by itself (_goto_here
refuses any other host), and any other top-level page - a sign-in on
another host, a redirect elsewhere - pauses and asks the owner. Most chat
widgets live in an IFRAME (a small page inside the page) served from the
chat maker's own host (Freshchat's wchat.freshchat.com, Salesforce's
*.my.site.com, ...). Jarvis never OPENS that host: the company's own page
loads it. Jarvis reads and types inside such a frame ONLY when BOTH are
true: (1) the frame is where that vendor's widget is known to live on the
page (its selector in VENDORS), and (2) the frame's own address is on that
vendor's host list (or the company's own hosts; a frame with no address of
its own, "about:blank" / "about:srcdoc", belongs to the page it is in). A
chat frame from any other host is never read or typed into: status() says
"a chat window from <host>, which Jarvis does not recognise" and the chat
pauses for the owner. The vendor hosts are written below and marked NOT
VERIFIED like every selector.

VENDORS (the design's list): Zendesk, Intercom, LivePerson, Gorgias,
Freshchat, Salesforce, and an unbranded fallback on standard page roles
(role="log", a text box, a Send button) - held narrow on purpose: only the
nearest part of the page around a role="log" list that also holds a text
area (never the whole page), only a text area or a textbox, and only a
button labelled Send, so a site's search box or a form's submit button is
never taken for a chat. Every selector and host is a
GUESS written without access to any of these widgets (the container this
was built in could not reach them): NOT VERIFIED. The owner checks them on
the PC with one line that reads only and sends nothing:
    py -3 jarvis_support_widget.py check groupon
Ada (named in the design as "a guess") is not in the table: nothing about
its widget could be confirmed at all.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import jarvis_chatbot as CB
import jarvis_chatbot_web as W

#: The support chats' own browser profile: <config>/chatbot/support-profile.
PROFILE_NAME = "support"
MODULE_FILE = "jarvis_support_widget.py"
CHECK_WAIT = 5 * 60.0
SIGN_IN_WAIT = 30 * 60.0
#: How long send() waits for the chat to take the message.
TAKEN_WAIT = 15.0
#: At most this many chat lines are looked at, from the newest back.
MOST_ITEMS = 200
MOST_MENU = 20

# ============================================================================
#   The vendor table - NOT VERIFIED (see the docstring)
# ============================================================================


@dataclass(frozen=True)
class Vendor:
    """One chat-widget maker.

        frame      where its chat iframe sits on the company's page ("" rows:
                   the chat is in the page itself)
        container  where its chat sits when it is IN the page
        hosts      the only hosts its chat frame may come from
        roles      selectors INSIDE the chat, tried before the shared ones:
                   input, send, item (one chat line), own (a line the
                   customer's side sent), menu (a button the chat offers)
    """
    id: str
    name: str
    frame: tuple = ()
    container: tuple = ()
    hosts: tuple = ()
    roles: dict = field(default_factory=dict, compare=False, hash=False)
    #: Its own message box and Send selectors only - never the shared,
    #: broader ones (the unbranded fallback: a page's search box or a
    #: form's submit button must never be taken for a chat's).
    strict: bool = False


VENDORS = (
    Vendor("zendesk", "Zendesk",
           frame=('iframe[title*="Messaging window" i]', 'iframe#webWidget',
                  'iframe[title*="Zendesk" i]'),
           hosts=("zendesk.com", "zdassets.com", "zopim.com", "zendesk.chat"),
           roles={"input": ('textarea[placeholder*="message" i]',),
                  "own": ('[data-testid*="primary" i]',)}),
    Vendor("intercom", "Intercom",
           frame=('iframe[name="intercom-messenger-frame"]', 'iframe#intercom-frame'),
           hosts=("intercom.io", "intercom.com", "intercomcdn.com", "intercom-messenger.com"),
           roles={"input": ('textarea[name="message"]',),
                  "own": ('[class*="user-comment" i]', '.intercom-comment-container-user')}),
    Vendor("liveperson", "LivePerson",
           container=("#lpChat", ".lp_maximized"),
           hosts=("liveperson.net", "lpsnmedia.net"),
           roles={"input": ('textarea[class*="lpview" i]',),
                  "send": ('button[class*="lp_send" i]',),
                  "own": ('[class*="consumer" i]',)}),
    Vendor("gorgias", "Gorgias",
           frame=('#gorgias-chat-container iframe#chat-window',
                  '#gorgias-chat-container iframe'),
           container=("#gorgias-chat-container",),
           hosts=("gorgias.chat", "gorgias.io", "gorgias.help"),
           roles={"own": ('[class*="customer" i]',)}),
    Vendor("freshchat", "Freshchat",
           frame=('#fc_frame iframe#fc_widget', '#fc_frame iframe'),
           hosts=("freshchat.com", "freshworks.com", "freshdesk.com"),
           roles={"own": ('[class*="user-message" i]',)}),
    Vendor("salesforce", "Salesforce",
           frame=('iframe[name="embeddedMessagingFrame"]', 'iframe#embeddedMessagingFrame'),
           container=(".embeddedServiceSidebar",),
           hosts=("salesforce.com", "force.com", "my.site.com", "salesforce-sites.com",
                  "salesforceliveagent.com", "salesforce-scrt.com"),
           roles={"own": ('[class*="outbound" i]', '[class*="chasitor" i]')}),
)
#: No maker recognised: standard page roles. The chat is the nearest part
#: of the page (at most UNBRANDED_LEVELS up from a role="log" list, never the
#: whole page) that also holds a text area; only a text area or a textbox,
#: and only a button labelled Send, are ever used there.
UNBRANDED = Vendor("unbranded", "an unbranded chat", container=('[role="log"]',), strict=True,
                   roles={"input": ('textarea', '[contenteditable="true"][role="textbox"]'),
                          "send": ('button[aria-label*="send" i]', 'button[title*="send" i]')})
UNBRANDED_LEVELS = 3

#: Shared selectors inside any chat, tried after the vendor's own.
SHARED_ROLES = {
    "input": ('textarea', '[contenteditable="true"][role="textbox"]',
              '[contenteditable="true"]', 'input[type="text"]'),
    "send": ('button[aria-label*="send" i]', 'button[title*="send" i]',
             'button[type="submit"]', 'button[class*="send" i]',
             '[role="button"][aria-label*="send" i]'),
    "item": ('[role="log"] > *', '[class*="message-list" i] > *',
             '[class*="messages" i] > *'),
    "own": ('[data-author="me"]', '[data-sender="user"]', '[class*="outgoing" i]',
            '[class*="from-me" i]', '[class*="visitor" i]'),
    "menu": ('[class*="quick-repl" i] button', '[class*="quick_repl" i] button',
             '[role="log"] button', '[role="listbox"] [role="option"]'),
    "captcha": W.CAPTCHA,
}

#: What the top page is checked for (the base's shared lists); "reply"
#: holds every widget's place on the page, so the "unusual activity" check
#: never reads a word INSIDE a chat (an agent saying "unusual activity" is
#: not a warning page).
TOP_SELECTORS = {
    "reply": tuple(s for v in VENDORS for s in v.frame + v.container) + UNBRANDED.container,
    "own": (),
    "sign_in_form": W.SIGN_IN_FORM,
    "captcha": W.CAPTCHA,
    "warning": W.WARNING,
    "signed_out": (),
    "notice": (),
    "input": (),
}


def vendor_roles(v: Vendor, role: str) -> tuple:
    if v.strict and role in ("input", "send"):
        return tuple(v.roles.get(role, ()))
    return tuple(v.roles.get(role, ())) + tuple(SHARED_ROLES.get(role, ()))


def host_allowed(host: str, allowed) -> bool:
    h = str(host or "").lower().rstrip(".")
    return any(h == a or h.endswith("." + a) for a in allowed)


# ============================================================================
#   The window
# ============================================================================

def ready() -> str:
    """"" when a support chat can start on this PC, else why and the one
    line that fixes it. Opens nothing. (Signing in is not needed first:
    a sign-in page pauses the chat and the owner signs in in the window.)"""
    if not W.playwright_installed():
        return W.NOT_INSTALLED
    return ""


def profile_dir() -> Path:
    return W.config_dir() / "chatbot" / f"{PROFILE_NAME}-profile"


def _site(name: str, help_url: str, hosts: tuple) -> W.Site:
    return W.Site(id="support", name=f"{name} support", host=hosts[0] if hosts else "",
                  start_url=help_url, module=MODULE_FILE, profile_name=PROFILE_NAME,
                  account="account", company=name, selectors=TOP_SELECTORS,
                  sign_in_hosts=(), terms="")


class SupportWidget(W.WebAdapter):
    """A company's help page and its chat. The keyword arguments beyond the
    company's own are for the tests (a fake page on 127.0.0.1, a vendor
    table of fake hosts); the real one only ever opens the help page."""

    def __init__(self, name: str, help_url: str, hosts: tuple, *,
                 vendors: Optional[tuple] = None, profile: Optional[Path] = None,
                 type_delay_ms: int = W.TYPE_DELAY_MS, open_wait: float = 20.0,
                 browser: Optional[str] = None):
        self.SITE = _site(name, help_url, tuple(hosts))
        super().__init__(chat_hosts=tuple(hosts), sign_in_hosts=(),
                         profile=profile if profile is not None else profile_dir(),
                         type_delay_ms=type_delay_ms, open_wait=open_wait,
                         browser=browser)
        self.company_hosts = tuple(h.lower() for h in hosts)
        self.vendors = tuple(vendors) if vendors is not None else VENDORS
        #: The chat found last: (vendor, how) - for status and the check.
        self.vendor: Optional[Vendor] = None
        self.frame_host = ""
        self._seen = 0
        self._item_sel = ""

    # ---- the interface jarvis_support uses --------------------------------

    def read_new(self) -> list:
        return self._call(self._read_new_here, 30) or []

    def menu(self) -> list:
        return self._call(self._menu_here, 30) or []

    def choose(self, label: str) -> None:
        label = str(label or "")
        if not label.strip():
            raise ValueError("no button named")
        self._call(lambda: self._choose_here(label), 30)

    def send(self, text: str) -> None:
        text = str(text or "")
        if not text.strip():
            raise ValueError("nothing to send")
        budget = len(text) * self.type_delay_ms / 1000.0 + TAKEN_WAIT + 60
        self._call(lambda: self._send_here(text), budget)

    def read_reply(self, timeout: float):  # the chatbot interface; not used here
        return None

    # ---- everything below runs on the worker thread ------------------------

    def _outside_widgets(self, selector: str) -> bool:
        """Is there a VISIBLE `selector` on the top page that is NOT inside
        a chat widget? (A pre-chat form's email box is not a sign-in page.)"""
        try:
            loc = self._page.locator(selector)
            n = min(loc.count(), 10)
        except Exception:
            return False
        for i in range(n):
            el = loc.nth(i)
            try:
                if el.is_visible() and not el.evaluate(self._skip_js):
                    return True
            except Exception:
                continue
        return False

    def _frame_of(self, selector: str):
        """(frame, host) for the first visible iframe matching `selector`, or
        (None, "")."""
        try:
            loc = self._page.locator(selector)
            n = min(loc.count(), 5)
        except Exception:
            return None, ""
        for i in range(n):
            el = loc.nth(i)
            try:
                if not el.is_visible():
                    continue
                frame = el.element_handle().content_frame()
            except Exception:
                continue
            if frame is None:
                continue
            host, _ = W.host_path(frame.url or "")
            return frame, host
        return None, ""

    def _scope_here(self):
        """(scope, vendor, why): where the chat is on the page - a frame or a
        part of the page - its maker, and "" when Jarvis may work in it;
        (None, None, S.NO_CHAT) when no chat is open; (None, vendor, words)
        when there is one Jarvis must not touch."""
        import jarvis_support as S
        for v in self.vendors + (UNBRANDED,):
            for fsel in v.frame:
                frame, host = self._frame_of(fsel)
                if frame is None:
                    continue
                if host and not host_allowed(host, v.hosts + self.company_hosts):
                    return None, v, (f"a chat window from {host}, which Jarvis does not "
                                     f"recognise")
                self.frame_host = host
                if self._first(frame, vendor_roles(v, "input")) is not None:
                    return frame, v, ""
            if v is UNBRANDED:
                scope = self._unbranded_scope()
                if scope is not None:
                    self.frame_host = ""
                    return scope, v, ""
                continue
            for csel in v.container:
                try:
                    loc = self._page.locator(csel)
                    if loc.count() and loc.first.is_visible():
                        scope = loc.first
                        if self._first(scope, vendor_roles(v, "input")) is not None:
                            self.frame_host = ""
                            return scope, v, ""
                except Exception:
                    continue
        return None, None, S.NO_CHAT

    def _unbranded_scope(self):
        """The nearest part of the page around a visible role="log" list that
        also holds a text area - at most UNBRANDED_LEVELS up, and never the
        page's body: a search box elsewhere on the page is not a chat."""
        try:
            loc = self._page.locator('[role="log"]')
            n = min(loc.count(), 5)
        except Exception:
            return None
        for i in range(n):
            node = loc.nth(i)
            try:
                if not node.is_visible():
                    continue
            except Exception:
                continue
            for _ in range(UNBRANDED_LEVELS):
                node = node.locator("xpath=..")
                try:
                    tag = str(node.evaluate("e => e.tagName") or "").upper()
                except Exception:
                    break
                if tag in ("BODY", "HTML", ""):
                    break
                if self._first(node, vendor_roles(UNBRANDED, "input")) is not None:
                    return node
        return None

    @staticmethod
    def _first(scope, selectors: tuple):
        for sel in selectors:
            try:
                loc = scope.locator(sel)
                n = min(loc.count(), 10)
            except Exception:
                continue
            for i in range(n):
                el = loc.nth(i)
                try:
                    if el.is_visible():
                        return el
                except Exception:
                    continue
        return None

    def _status_here(self) -> CB.Status:
        import jarvis_support as S
        if not self._page_alive():
            return CB.Status("gone")
        try:
            url = self._page.url
        except Exception:
            return CB.Status("gone")
        host, path = W.host_path(url)
        if W.is_google_sorry(host, path):
            return CB.Status("needs_owner", "unusual")
        if host not in self.chat_hosts:
            return CB.Status("needs_owner", f"a page on {host or 'no address'}"[:80])
        if self._find("captcha") is not None:
            return CB.Status("needs_owner", "captcha")
        texts = self._texts("warning")
        if any(W.UNUSUAL_WORDS.search(t) for t in texts):
            return CB.Status("needs_owner", "unusual")
        if any(self._outside_widgets(s) for s in W.SIGN_IN_FORM) \
                or any(W.SIGN_IN_WORDS.search(t) for t in texts):
            return CB.Status("needs_owner", "login")
        scope, vendor, why = self._scope_here()
        self.vendor = vendor
        if scope is None:
            return CB.Status("needs_owner", why)
        if self._first(scope, W.CAPTCHA) is not None:
            return CB.Status("needs_owner", "captcha")
        return CB.OK

    def _items(self, scope, v: Vendor) -> tuple:
        """(selector, locator) of the chat's lines."""
        for sel in vendor_roles(v, "item"):
            try:
                loc = scope.locator(sel)
                if loc.count():
                    return sel, loc
            except Exception:
                continue
        return "", None

    def _is_own(self, el, v: Vendor) -> bool:
        sels = ", ".join(vendor_roles(v, "own"))
        try:
            return bool(el.evaluate("(e, s) => e.matches(s) || !!e.querySelector(s) "
                                    "|| !!e.closest(s)", sels))
        except Exception:
            return False

    def _read_new_here(self) -> list:
        st = self._status_here()
        if st.state != "ok":
            return []
        scope, v, _ = self._scope_here()
        sel, loc = self._items(scope, v)
        if loc is None:
            return []
        if sel != self._item_sel:
            # A different list (the chat re-drew itself): everything in it
            # counts as new once.
            self._item_sel, self._seen = sel, 0
        n = loc.count()
        if n < self._seen:
            self._seen = n
        start = max(self._seen, n - MOST_ITEMS)
        out = []
        for i in range(start, n):
            el = loc.nth(i)
            try:
                text = W.norm(el.inner_text(timeout=2000))
            except Exception:
                text = ""
            if not text:
                continue
            out.append({"who": "own" if self._is_own(el, v) else "company", "text": text})
        self._seen = n
        return out

    def _buttons_here(self, scope, v: Vendor) -> list:
        out = []
        for sel in vendor_roles(v, "menu"):
            try:
                loc = scope.locator(sel)
                n = min(loc.count(), MOST_MENU * 2)
            except Exception:
                continue
            for i in range(n):
                el = loc.nth(i)
                try:
                    if not el.is_visible():
                        continue
                    label = W.norm(el.inner_text(timeout=2000))
                except Exception:
                    continue
                if label and not re.fullmatch(r"send", label, re.I) \
                        and label not in [x[0] for x in out]:
                    out.append((label, el))
            if out:
                break
        return out[:MOST_MENU]

    def _menu_here(self) -> list:
        if self._status_here().state != "ok":
            return []
        scope, v, _ = self._scope_here()
        return [label for label, _ in self._buttons_here(scope, v)]

    def _choose_here(self, label: str) -> None:
        st = self._status_here()
        if st.state != "ok":
            raise RuntimeError(f"not pressing: the page needs you ({st.reason or st.state})")
        scope, v, _ = self._scope_here()
        for got, el in self._buttons_here(scope, v):
            if got == label:
                el.click()
                return
        raise RuntimeError("that button is not in the chat any more, so nothing was pressed")

    def _send_here(self, text: str) -> None:
        st = self._status_here()
        if st.state != "ok":
            raise RuntimeError(f"not sending: the page needs you ({st.reason or st.state})")
        scope, v, _ = self._scope_here()
        box = self._first(scope, vendor_roles(v, "input"))
        if box is None:
            raise RuntimeError("the chat's message box was not found")
        sel, loc = self._items(scope, v)
        before = loc.count() if loc is not None else 0
        self._type_message(box, text)
        if W.norm(self._input_text(box)) != W.norm(text):
            self._page.keyboard.press("Control+A")
            self._page.keyboard.press("Backspace")
            raise RuntimeError("the message box did not hold exactly the message, so nothing "
                               "was sent")
        btn = self._first(scope, vendor_roles(v, "send"))
        if btn is None:
            raise RuntimeError("the chat's Send button was not found (its selector may need "
                               "updating: run the check)")
        end = time.monotonic() + 5
        while not btn.is_enabled() and time.monotonic() < end:
            self._page.wait_for_timeout(100)
        btn.click()
        end = time.monotonic() + TAKEN_WAIT
        while time.monotonic() < end:
            if self._status_here().state != "ok":
                return
            _, loc2 = self._items(scope, v)
            if loc2 is not None and loc2.count() > before:
                return
            box2 = self._first(scope, vendor_roles(v, "input"))
            if box2 is not None and not W.norm(self._input_text(box2)):
                return
            self._page.wait_for_timeout(200)
        raise RuntimeError("the chat did not take the message")


def for_chat(chat) -> SupportWidget:
    """The window for one jarvis_support chat: its company's help page and
    hosts, nothing else."""
    return SupportWidget(chat.company_name, chat.help_url, tuple(chat.hosts))


# ============================================================================
#   The owner's commands: sign in, check (reads only), forget the sign-ins
# ============================================================================

def _company(argv: list) -> tuple:
    """(name, help address, hosts) from "groupon" or an https address."""
    import jarvis_support as S
    import urllib.parse
    what = argv[0] if argv else ""
    override = argv[1] if len(argv) > 1 else ""
    if what in S.COMPANIES:
        co = S.COMPANIES[what]
        url = override or co.help_url
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        hosts = tuple(dict.fromkeys(co.hosts + ((host,) if host else ())))
        return co.name, url, hosts
    why = S.address_problem(what)
    if why:
        raise ValueError(why)
    host = (urllib.parse.urlsplit(what).hostname or "").lower()
    return host, what, (host,)


def sign_in(argv: list, *, out=print, widget: Optional[SupportWidget] = None,
            wait: float = SIGN_IN_WAIT) -> int:
    """Open the support window on the company's help page and wait while the
    owner signs in to THEIR OWN account, by hand. Types nothing, reads no
    password; closes when the owner closes the window."""
    try:
        name, url, hosts = _company(argv)
    except ValueError as exc:
        out(f"Say which company: groupon, or its help page's address. ({exc})")
        return 2
    try:
        W.import_playwright()
    except W.WebUnavailable as exc:
        out(exc.owner_words)
        return 1
    a = widget or SupportWidget(name, url, hosts, open_wait=3)
    out(f"Opening Jarvis's support window on {url} (its own browser profile, in "
        f"{profile_dir()}).")
    out(f"Sign in to your own {name} account in that window, by hand. Jarvis does not see "
        "or keep the password. Close the window when you are done (it waits up to 30 "
        "minutes).")
    try:
        a.open()
    except Exception as exc:
        out(getattr(exc, "owner_words", "") or f"The window did not open ({type(exc).__name__}).")
        a.close()
        return 1
    end = time.monotonic() + wait
    try:
        while time.monotonic() < end:
            try:
                if not a._call(a._page_alive, 30):
                    break
            except Exception:
                break
            time.sleep(1.0)
    finally:
        a.close()
    out(f"Done. Jarvis's support window keeps your {name} sign-in in its own profile. To "
        f"check the chat can be worked, run: py -3 {MODULE_FILE} check "
        + (argv[0] if argv else "groupon"))
    return 0


def check(argv: list, *, out=print, widget: Optional[SupportWidget] = None,
          wait: float = CHECK_WAIT, report: Optional[Path] = None) -> int:
    """READS ONLY, SENDS NOTHING. Opens the help page, waits for the owner to
    open the chat by hand, and prints PASS or FAIL for each thing Jarvis
    needs: the page is the company's, no captcha or sign-in page, which chat
    maker it recognised, the chat's own host allowed, the message box and
    the Send button found (by which selector), the chat's lines readable,
    and its menu buttons (labels only). Never types, sends or presses
    anything."""
    import jarvis_support as S
    lines: list = []

    def step(ok: bool, what: str, detail: str = "") -> bool:
        line = f"{'PASS' if ok else 'FAIL'}  {what}" + (f" - {detail}" if detail else "")
        lines.append(line)
        out(line)
        return ok

    def note(what: str) -> None:
        lines.append(f"NOTE  {what}")
        out(f"NOTE  {what}")
    report = report or (W.config_dir() / "chatbot" / "support-check.txt")
    try:
        name, url, hosts = _company(argv)
    except ValueError as exc:
        out(f"Say which company: groupon, or its help page's address. ({exc})")
        return 2
    try:
        W.import_playwright()
        step(True, "Playwright is installed")
    except W.WebUnavailable as exc:
        step(False, "Playwright is installed", exc.owner_words)
        return W._finish(lines, report, out)
    a = widget or SupportWidget(name, url, hosts, open_wait=5)
    note(f"This check only reads the page. It never types, sends or presses anything in "
         f"{name}'s chat.")
    try:
        try:
            a.open()
            step(True, "The browser window opened (you can see it)")
        except Exception as exc:
            step(False, "The browser window opened",
                 getattr(exc, "owner_words", "") or type(exc).__name__)
            return W._finish(lines, report, out)
        st = a.status()
        if st.state == "needs_owner" and st.reason != S.NO_CHAT:
            step(False, f"{name}'s help page is showing (no captcha, sign-in or warning page)",
                 f"{st.reason} - deal with it in the window, then run this again")
            return W._finish(lines, report, out)
        step(st.state != "gone", f"{name}'s help page is showing", url)
        out(f"Now open the chat on the page yourself (its Chat or Help button). Waiting up to "
            f"{int(wait // 60)} minutes...")
        end = time.monotonic() + wait
        while time.monotonic() < end:
            st = a.status()
            if st.state != "needs_owner" or st.reason != S.NO_CHAT:
                break
            time.sleep(1.0)
        if not step(st.state == "ok", "A chat Jarvis can work in is open",
                    "" if st.state == "ok" else f"{st.state}: {st.reason}"):
            if a.vendor is not None:
                note(f"The chat looks like {a.vendor.name}'s.")
            return W._finish(lines, report, out)
        v = a.vendor or UNBRANDED
        step(True, "Recognised the chat's maker", v.name)
        step(True, "The chat's own address is allowed",
             a.frame_host or "it is part of the help page itself")

        def found(role: str) -> str:
            def look():
                scope, vv, _ = a._scope_here()
                for i, sel in enumerate(vendor_roles(vv, role), 1):
                    if a._first(scope, (sel,)) is not None:
                        return f"selector {i}: {sel}"
                return ""
            return a._call(look, 30)
        box = found("input")
        step(bool(box), "Found the message box", box or "no selector matched")
        btn = found("send")
        step(bool(btn), "Found the Send button", btn or "no selector matched")
        got = a.read_new()
        step(True, "Read the chat's lines", f"{len(got)} line(s); "
             f"{sum(1 for g in got if g['who'] == 'own')} marked as yours")
        buttons = a.menu()
        note("Menu buttons the chat shows: " + (", ".join(f'"{b}"' for b in buttons)
                                                 if buttons else "none"))
    finally:
        a.close()
        step(True, "Closed the window")
    return W._finish(lines, report, out)


def forget_sign_ins(*, out=print) -> int:
    """Delete the support window's browser profile: every sign-in and cookie
    kept for support chats. Nothing else."""
    folder = profile_dir()
    if not folder.exists():
        out("There are no support sign-ins to forget.")
        return 0
    try:
        shutil.rmtree(folder)
    except OSError as exc:
        out(f"Could not delete {folder} ({type(exc).__name__}): close the support window "
            "first, then run this again.")
        return 1
    out(f"Forgotten: the support window's sign-ins ({folder}) are deleted.")
    return 0


def main(argv: list) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    rest = argv[2:]
    if cmd == "sign-in":
        return sign_in(rest)
    if cmd == "check":
        return check(rest)
    if cmd == "forget-sign-ins":
        return forget_sign_ins()
    print("Jarvis's customer-support window. Three commands, run in Jarvis's folder:\n"
          f"  py -3 {MODULE_FILE} sign-in groupon     sign in to your own account, by hand\n"
          f"  py -3 {MODULE_FILE} check groupon       open the chat yourself; PASS/FAIL per "
          f"step (reads only, sends nothing)\n"
          f"  py -3 {MODULE_FILE} forget-sign-ins     delete the support window's sign-ins\n"
          "Instead of groupon, a company's help page address (https://...) works too.")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
