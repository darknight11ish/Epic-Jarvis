"""jarvis_chatbot_metaai.py - the Meta AI adapter for the chatbot driver:
Jarvis types into www.meta.ai in a browser window the owner can see.

NEW MODULE, shipped whole. A THIN SITE FILE: everything every chatbot
website shares - the browser thread, the visible window, the typing, the
host lock, "is the reply finished?", every "needs the owner" page, the
sign-in helper and the self-check - is jarvis_chatbot_web.py. This file
holds only what is Meta AI's own: the SELECTORS table, the hosts and the
words. Registered as chatbot `metaai_web`. Not reachable from either app yet
(docs/JARVIS-API.md section 60).

THE OWNER'S DECISION (CLAUDE.md, 2026-09-28, "The chatbot driver becomes
versatile"): more chatbot websites, driven OPENLY like Gemini, each with its
own SPARE account used only by Jarvis.
  * Meta's terms restrict automated access (not read word for word for
    this file). Not checked either: whether Meta allows a second
    account kept only for this.
    The account may be blocked or closed; Jarvis will not work around a block.
  * No stealth plug-in, no change to how the browser presents itself, nothing
    that hides that a program is driving, no proxy, no captcha solving (the
    shared base does all the driving; test_chatbot_sites.py reads this file
    and the base for any such code).

WHAT IT OPENS: only a new chat at www.meta.ai/ (it becomes .../c/<id> or
.../prompt/<id>). Any other host is refused. A sign-in page is reached only
by the OWNER clicking "Sign in" in the window.

ONE-TIME SET-UP ON THE PC (PowerShell, in Jarvis's folder)
    py -3 jarvis_chatbot_metaai.py sign-in
        sign in once, by hand, to the spare Meta account; its own
        profile folder is <config>/chatbot/metaai-profile
    py -3 jarvis_chatbot_metaai.py check
        one harmless fixed question; PASS/FAIL per step and which
        selector matched

THE SELECTORS ARE BEST GUESSES, NOT VERIFIED. They were written without
access to www.meta.ai (the container this was built in cannot reach it, and
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

ID = "metaai_web"
NAME = "Meta AI"
HOST = "www.meta.ai"
#: The one address this adapter opens by itself: a new, empty chat.
START_URL = "https://www.meta.ai/"
#: Sign-in pages (reason "login"). Reached only when the OWNER clicks.
SIGN_IN_HOSTS = (
    "www.facebook.com",
    "facebook.com",
    "m.facebook.com",
    "www.instagram.com",
    "auth.meta.com",
    "accountscenter.meta.com",
)


# ============================================================================
#   THE SELECTORS - everything that depends on how www.meta.ai looks
# ============================================================================
#
# Tried in order; the first that finds something VISIBLE wins. Plain CSS,
# role and aria-label based first where the site is known to have them.
# NOT VERIFIED: `py -3 jarvis_chatbot_metaai.py check`
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
        'textarea[aria-label*="Ask Meta AI" i]',
        'div[contenteditable="true"][aria-label*="Ask" i]',
        'textarea[placeholder*="Ask" i]',
        '[contenteditable="true"][role="textbox"]',
    ),
    "send": (
        'div[role="button"][aria-label="Send message"]',
        'button[aria-label="Send message"]',
        '[role="button"][aria-label*="Send" i]',
    ),
    "stop": (
        'div[role="button"][aria-label*="Stop" i]',
        'button[aria-label*="Stop" i]',
    ),
    "reply": (
        'div[data-testid="assistant-message"]',
        '[data-message-author-role="assistant"]',
        'div[class*="assistant-message"]',
    ),
    "reply_text": (
        '[class*="markdown"]',
        '.prose',
    ),
    "own": (
        'div[data-testid="user-message"]',
        '[data-message-author-role="user"]',
    ),
    "signed_out": (
        'a[href*="facebook.com/login"]',
        'div[role="button"][aria-label*="Log in" i]',
        'button[aria-label*="Log in" i]',
    ),
    "sign_in_form": W.SIGN_IN_FORM,
    "captcha": W.CAPTCHA,
    "warning": W.WARNING,
    "notice": W.NOTICE,
}

SITE = W.Site(
    id=ID, name=NAME, host=HOST, start_url=START_URL,
    module="jarvis_chatbot_metaai.py", profile_name="metaai",
    account="Meta account", company="Meta", selectors=SELECTORS,
    sign_in_hosts=SIGN_IN_HOSTS,
    sign_in_paths='',
    chat_address='^/(?:c|prompt)/[\\w-]+/?$',
    terms="Meta's terms restrict automated access.",
    browser_env="JARVIS_METAAI_BROWSER")

SIGN_IN_LINE = SITE.sign_in_line
CHECK_LINE = SITE.check_line
NOT_SIGNED_IN = SITE.not_signed_in


def profile_dir() -> Path:
    """The browser profile used ONLY for Jarvis's Meta AI window."""
    return W.profile_dir(SITE)


def ready() -> str:
    """"" when a conversation can start, else why not (jarvis_chatbot_web.ready)."""
    return W.ready(SITE)


class MetaAIWeb(W.WebAdapter):
    """Meta AI through its website, in a window the owner can see."""
    SITE = SITE
    id = ID
    name = NAME
    host = HOST


def _factory() -> CB.Adapter:
    """The registry's factory: the real site, the real profile. Opens
    nothing until the driver calls open()."""
    return MetaAIWeb()


W.register(SITE, _factory, ready)


def sign_in(*, out=print, adapter: Optional[MetaAIWeb] = None,
            wait: float = W.SIGN_IN_WAIT) -> int:
    """Sign in once, by hand, to the spare Meta account."""
    return W.sign_in(SITE, MetaAIWeb, out=out, adapter=adapter, wait=wait)


def self_check(*, out=print, adapter: Optional[MetaAIWeb] = None,
               report: Optional[Path] = None, reply_wait: float = 120.0) -> int:
    """Send the one fixed question and print PASS or FAIL per step."""
    return W.self_check(SITE, MetaAIWeb, out=out, adapter=adapter, report=report,
                        reply_wait=reply_wait)


def main(argv: list) -> int:
    return W.main(SITE, MetaAIWeb, argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
