"""jarvis_chatbot_copilot.py - the Copilot adapter for the chatbot driver:
Jarvis types into copilot.microsoft.com in a browser window the owner can
see.

NEW MODULE, shipped whole. A THIN SITE FILE: everything every chatbot
website shares - the browser thread, the visible window, the typing, the
host lock, "is the reply finished?", every "needs the owner" page, the
sign-in helper and the self-check - is jarvis_chatbot_web.py. This file
holds only what is Copilot's own: the SELECTORS table, the hosts and the
words. Registered as chatbot `copilot_web`.
Reachable from both apps through /api/chatbot/* (jarvis_chatbot_routes.py,
docs/JARVIS-API.md section 60) once its window has been signed in.
NOT yet tried against the real site.

THE OWNER'S DECISION (CLAUDE.md, 2026-09-28, "The chatbot driver becomes
versatile"): more chatbot websites, driven OPENLY like Gemini, each with its
own SPARE account used only by Jarvis.
  * Microsoft's terms restrict automated access (not read word for word
    for this file).
    The account may be blocked or closed; Jarvis will not work around a block.
  * No stealth plug-in, no change to how the browser presents itself, nothing
    that hides that a program is driving, no proxy, no captcha solving (the
    shared base does all the driving; test_chatbot_sites.py reads this file
    and the base for any such code).

WHAT IT OPENS: only a new chat at copilot.microsoft.com/ (it becomes
.../chats/<id>). Any other host is refused. A sign-in page is reached only
by the OWNER clicking "Sign in" in the window.

ONE-TIME SET-UP ON THE PC (PowerShell, in Jarvis's folder)
    py -3 jarvis_chatbot_copilot.py sign-in
        sign in once, by hand, to the spare Microsoft account; its own
        profile folder is <config>/chatbot/copilot-profile
    py -3 jarvis_chatbot_copilot.py check
        two harmless fixed questions in one new chat; PASS/FAIL per
        step and which selector matched

THE SELECTORS ARE BEST GUESSES, NOT VERIFIED. They were written without
access to copilot.microsoft.com (the container this was built in cannot
reach it, and must not automate it). The self-check above, on the owner's
PC, is the proof; when a step FAILs, the fix is the SELECTORS table below.

    python3 test_chatbot_sites.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import jarvis_chatbot as CB
import jarvis_chatbot_web as W

ID = "copilot_web"
NAME = "Copilot"
HOST = "copilot.microsoft.com"
#: The one address this adapter opens by itself: a new, empty chat.
START_URL = "https://copilot.microsoft.com/"
#: Sign-in pages (reason "login"). Reached only when the OWNER clicks.
SIGN_IN_HOSTS = (
    "login.live.com",
    "login.microsoftonline.com",
    "account.live.com",
    "accounts.google.com",
    "appleid.apple.com",
)


# ============================================================================
#   THE SELECTORS - everything that depends on how copilot.microsoft.com looks
# ============================================================================
#
# Tried in order; the first that finds something VISIBLE wins. Plain CSS,
# role and aria-label based first where the site is known to have them.
# NOT VERIFIED: `py -3 jarvis_chatbot_copilot.py check`
# prints which one matched per role.
#
#   input        the box the message is typed into
#   send         the button that sends it (the only other thing clicked)
#   stop         the stop control, shown while it writes
#   reply        ONE reply (the newest is last)
#   reply_text   the words inside one reply (none found: the whole reply)
#   own          one of Jarvis's own messages (skipped by the warning check)
#   signed_out   a "Sign in" / "Log in" button: nobody is signed in
#   sign_in_form, captcha, warning, notice: the shared lists in
#                jarvis_chatbot_web.py, the same for every site
SELECTORS: dict = {
    "input": (
        'textarea[aria-label*="Message Copilot" i]',
        'textarea#userInput',
        'textarea[placeholder*="Message Copilot" i]',
        '[contenteditable="true"][role="textbox"]',
    ),
    "send": (
        'button[aria-label="Submit message"]',
        'button[aria-label*="Submit" i]',
        'button[aria-label*="Send" i]',
    ),
    "stop": (
        'button[aria-label="Stop generating"]',
        'button[aria-label*="Stop" i]',
        'button[aria-label*="Interrupt" i]',
    ),
    "reply": (
        '[data-content="ai-message"]',
        'div[class*="ai-message"]',
    ),
    "reply_text": (
        '.prose',
        '[class*="markdown"]',
    ),
    "own": (
        '[data-content="user-message"]',
        'div[class*="user-message"]',
    ),
    "signed_out": (
        'button[aria-label="Sign in" i]',
        'button[title="Sign in"]',
        'a[href*="login.live.com"]',
    ),
    "sign_in_form": W.SIGN_IN_FORM,
    "captcha": W.CAPTCHA,
    "warning": W.WARNING,
    "notice": W.NOTICE,
}

SITE = W.Site(
    id=ID, name=NAME, host=HOST, start_url=START_URL,
    module="jarvis_chatbot_copilot.py", profile_name="copilot",
    account="Microsoft account", company="Microsoft", selectors=SELECTORS,
    sign_in_hosts=SIGN_IN_HOSTS,
    sign_in_paths='',
    chat_address='^/chats/[\\w-]+/?$',
    terms="Microsoft's terms restrict automated access.",
    browser_env="JARVIS_COPILOT_BROWSER")

SIGN_IN_LINE = SITE.sign_in_line
CHECK_LINE = SITE.check_line
NOT_SIGNED_IN = SITE.not_signed_in


def profile_dir() -> Path:
    """The browser profile used ONLY for Jarvis's Copilot window."""
    return W.profile_dir(SITE)


def ready() -> str:
    """"" when a conversation can start, else why not (jarvis_chatbot_web.ready)."""
    return W.ready(SITE)


class CopilotWeb(W.WebAdapter):
    """Copilot through its website, in a window the owner can see."""
    SITE = SITE
    id = ID
    name = NAME
    host = HOST


def _factory() -> CB.Adapter:
    """The registry's factory: the real site, the real profile. Opens
    nothing until the driver calls open()."""
    return CopilotWeb()


W.register(SITE, _factory, ready)


def sign_in(*, out=print, adapter: Optional[CopilotWeb] = None,
            wait: float = W.SIGN_IN_WAIT) -> int:
    """Sign in once, by hand, to the spare Microsoft account."""
    return W.sign_in(SITE, CopilotWeb, out=out, adapter=adapter, wait=wait)


def self_check(*, out=print, adapter: Optional[CopilotWeb] = None,
               report: Optional[Path] = None, reply_wait: float = 120.0) -> int:
    """Send the two fixed questions and print PASS or FAIL per step."""
    return W.self_check(SITE, CopilotWeb, out=out, adapter=adapter, report=report,
                        reply_wait=reply_wait)


def main(argv: list) -> int:
    return W.main(SITE, CopilotWeb, argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
