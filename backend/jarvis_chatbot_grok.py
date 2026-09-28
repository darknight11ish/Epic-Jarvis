"""jarvis_chatbot_grok.py - the Grok adapter for the chatbot driver: Jarvis
types into grok.com in a browser window the owner can see.

NEW MODULE, shipped whole. A THIN SITE FILE: everything every chatbot
website shares - the browser thread, the visible window, the typing, the
host lock, "is the reply finished?", every "needs the owner" page, the
sign-in helper and the self-check - is jarvis_chatbot_web.py. This file
holds only what is Grok's own: the SELECTORS table, the hosts and the words.
Registered as chatbot `grok_web`.
Reachable from both apps through /api/chatbot/* (jarvis_chatbot_routes.py,
docs/JARVIS-API.md section 87) once its window has been signed in.
NOT yet tried against the real site.

THE OWNER'S DECISION (CLAUDE.md, 2026-09-28, "The chatbot driver becomes
versatile"): more chatbot websites, driven OPENLY like Gemini, each with its
own SPARE account used only by Jarvis.
  * xAI's terms restrict automated access (not read word for word for
    this file).
    The account may be blocked or closed; Jarvis will not work around a block.
  * No stealth plug-in, no change to how the browser presents itself, nothing
    that hides that a program is driving, no proxy, no captcha solving (the
    shared base does all the driving; test_chatbot_sites.py reads this file
    and the base for any such code).

WHAT IT OPENS: only a new chat at grok.com/ (it becomes grok.com/c/<id>).
Any other host is refused. A sign-in page is reached only by the OWNER
clicking "Sign in" in the window.

ONE-TIME SET-UP ON THE PC (PowerShell, in Jarvis's folder)
    py -3 jarvis_chatbot_grok.py sign-in
        sign in once, by hand, to the spare Grok account; its own
        profile folder is <config>/chatbot/grok-profile
    py -3 jarvis_chatbot_grok.py check
        two harmless fixed questions in one new chat; PASS/FAIL per
        step and which selector matched

THE SELECTORS ARE BEST GUESSES, NOT VERIFIED. They were written without
access to grok.com (the container this was built in cannot reach it, and
must not automate it). The self-check above, on the owner's PC, is the
proof; when a step FAILs, the fix is the SELECTORS table below.

    python3 test_chatbot_sites.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import jarvis_chatbot as CB
import jarvis_chatbot_web as W

ID = "grok_web"
NAME = "Grok"
HOST = "grok.com"
#: The one address this adapter opens by itself: a new, empty chat.
START_URL = "https://grok.com/"
#: Sign-in pages (reason "login"). Reached only when the OWNER clicks.
SIGN_IN_HOSTS = (
    "accounts.x.ai",
    "x.com",
    "twitter.com",
    "api.x.com",
    "accounts.google.com",
    "appleid.apple.com",
)


# ============================================================================
#   THE SELECTORS - everything that depends on how grok.com looks
# ============================================================================
#
# Tried in order; the first that finds something VISIBLE wins. Plain CSS,
# role and aria-label based first where the site is known to have them.
# NOT VERIFIED: `py -3 jarvis_chatbot_grok.py check`
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
        'textarea[aria-label*="Ask Grok" i]',
        'div[contenteditable="true"][aria-label*="Ask" i]',
        'textarea[placeholder*="Ask" i]',
        '[contenteditable="true"][role="textbox"]',
    ),
    "send": (
        'button[aria-label="Submit"]',
        'button[aria-label*="Submit" i]',
        'button[aria-label*="Send" i]',
    ),
    "stop": (
        'button[aria-label="Stop model response"]',
        'button[aria-label*="Stop" i]',
    ),
    "reply": (
        'div[data-testid="assistant-message"]',
        '[data-message-author-role="assistant"]',
        'div.response-content-markdown',
    ),
    "reply_text": (
        '.response-content-markdown',
        '.prose',
        '[class*="markdown"]',
    ),
    "own": (
        'div[data-testid="user-message"]',
        '[data-message-author-role="user"]',
    ),
    "signed_out": (
        'a[href*="/sign-in"]',
        'a[href*="accounts.x.ai"]',
        'button[aria-label*="Sign in" i]',
    ),
    "sign_in_form": W.SIGN_IN_FORM,
    "captcha": W.CAPTCHA,
    "warning": W.WARNING,
    "notice": W.NOTICE,
}

SITE = W.Site(
    id=ID, name=NAME, host=HOST, start_url=START_URL,
    module="jarvis_chatbot_grok.py", profile_name="grok",
    account="Grok account", company="xAI", selectors=SELECTORS,
    sign_in_hosts=SIGN_IN_HOSTS,
    sign_in_paths='^/(?:sign-in|sign-up|login)(?:/|$)',
    chat_address='^/c/[\\w-]+/?$',
    terms="xAI's terms restrict automated access.",
    browser_env="JARVIS_GROK_BROWSER")

SIGN_IN_LINE = SITE.sign_in_line
CHECK_LINE = SITE.check_line
NOT_SIGNED_IN = SITE.not_signed_in


def profile_dir() -> Path:
    """The browser profile used ONLY for Jarvis's Grok window."""
    return W.profile_dir(SITE)


def ready() -> str:
    """"" when a conversation can start, else why not (jarvis_chatbot_web.ready)."""
    return W.ready(SITE)


class GrokWeb(W.WebAdapter):
    """Grok through its website, in a window the owner can see."""
    SITE = SITE
    id = ID
    name = NAME
    host = HOST


def _factory() -> CB.Adapter:
    """The registry's factory: the real site, the real profile. Opens
    nothing until the driver calls open()."""
    return GrokWeb()


W.register(SITE, _factory, ready)


def sign_in(*, out=print, adapter: Optional[GrokWeb] = None,
            wait: float = W.SIGN_IN_WAIT) -> int:
    """Sign in once, by hand, to the spare Grok account."""
    return W.sign_in(SITE, GrokWeb, out=out, adapter=adapter, wait=wait)


def self_check(*, out=print, adapter: Optional[GrokWeb] = None,
               report: Optional[Path] = None, reply_wait: float = 120.0) -> int:
    """Send the two fixed questions and print PASS or FAIL per step."""
    return W.self_check(SITE, GrokWeb, out=out, adapter=adapter, report=report,
                        reply_wait=reply_wait)


def main(argv: list) -> int:
    return W.main(SITE, GrokWeb, argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
