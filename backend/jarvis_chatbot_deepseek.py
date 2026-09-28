"""jarvis_chatbot_deepseek.py - the DeepSeek adapter for the chatbot driver:
Jarvis types into chat.deepseek.com in a browser window the owner can see.

NEW MODULE, shipped whole. A THIN SITE FILE: everything every chatbot
website shares - the browser thread, the visible window, the typing, the
host lock, "is the reply finished?", every "needs the owner" page, the
sign-in helper and the self-check - is jarvis_chatbot_web.py. This file
holds only what is DeepSeek's own: the SELECTORS table, the hosts and the
words. Registered as chatbot `deepseek_web`.
Reachable from both apps through /api/chatbot/* (jarvis_chatbot_routes.py,
docs/JARVIS-API.md section 60) once its window has been signed in.
NOT yet tried against the real site.

THE OWNER'S DECISION (CLAUDE.md, 2026-09-28, "The chatbot driver becomes
versatile"): more chatbot websites, driven OPENLY like Gemini, each with its
own SPARE account used only by Jarvis.
  * DeepSeek's terms restrict automated access (not read word for word
    for this file).
    The account may be blocked or closed; Jarvis will not work around a block.
  * No stealth plug-in, no change to how the browser presents itself, nothing
    that hides that a program is driving, no proxy, no captcha solving (the
    shared base does all the driving; test_chatbot_sites.py reads this file
    and the base for any such code).

WHAT IT OPENS: only a new chat at chat.deepseek.com/ (it becomes
.../a/chat/s/<id>). Any other host is refused. A sign-in page is reached
only by the OWNER clicking "Sign in" in the window.

ONE-TIME SET-UP ON THE PC (PowerShell, in Jarvis's folder)
    py -3 jarvis_chatbot_deepseek.py sign-in
        sign in once, by hand, to the spare DeepSeek account; its own
        profile folder is <config>/chatbot/deepseek-profile
    py -3 jarvis_chatbot_deepseek.py check
        two harmless fixed questions in one new chat; PASS/FAIL per
        step and which selector matched

THE SELECTORS ARE BEST GUESSES, NOT VERIFIED. They were written without
access to chat.deepseek.com (the container this was built in cannot reach
it, and must not automate it). The self-check above, on the owner's PC, is
the proof; when a step FAILs, the fix is the SELECTORS table below.

    python3 test_chatbot_sites.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import jarvis_chatbot as CB
import jarvis_chatbot_web as W

ID = "deepseek_web"
NAME = "DeepSeek"
HOST = "chat.deepseek.com"
#: The one address this adapter opens by itself: a new, empty chat.
START_URL = "https://chat.deepseek.com/"
#: Sign-in pages (reason "login"). Reached only when the OWNER clicks.
SIGN_IN_HOSTS = ("accounts.google.com",)


# ============================================================================
#   THE SELECTORS - everything that depends on how chat.deepseek.com looks
# ============================================================================
#
# Tried in order; the first that finds something VISIBLE wins. Plain CSS,
# role and aria-label based first where the site is known to have them.
# NOT VERIFIED: `py -3 jarvis_chatbot_deepseek.py check`
# prints which one matched per role.
#
#   input        the box the message is typed into
#   send         the button that sends it (the only other thing clicked)
#   stop         the stop control, shown while it writes
#   reply        ONE reply (the newest is last)
#   own          one of Jarvis's own messages (skipped by the warning check)
#   signed_out   a "Sign in" / "Log in" button: nobody is signed in
#   sign_in_form, captcha, warning, notice: the shared lists in
#                jarvis_chatbot_web.py, the same for every site
SELECTORS: dict = {
    "input": (
        'textarea[aria-label*="message" i]',
        'textarea#chat-input',
        'textarea[placeholder*="Message DeepSeek" i]',
        '[contenteditable="true"][role="textbox"]',
    ),
    "send": (
        'div[role="button"][aria-label*="Send" i]',
        'button[aria-label*="Send" i]',
    ),
    "stop": (
        'div[role="button"][aria-label*="Stop" i]',
        'button[aria-label*="Stop" i]',
    ),
    "reply": (
        'div.ds-markdown',
        '[class*="ds-markdown"]',
    ),
    "own": (
        '[data-role="user"]',
        'div[class*="user-message"]',
    ),
    "signed_out": (
        'a[href*="/sign_in"]',
        'a[href*="/login"]',
        'button[aria-label*="Log in" i]',
    ),
    "sign_in_form": W.SIGN_IN_FORM,
    "captcha": W.CAPTCHA,
    "warning": W.WARNING,
    "notice": W.NOTICE,
}

SITE = W.Site(
    id=ID, name=NAME, host=HOST, start_url=START_URL,
    module="jarvis_chatbot_deepseek.py", profile_name="deepseek",
    account="DeepSeek account", company="DeepSeek", selectors=SELECTORS,
    sign_in_hosts=SIGN_IN_HOSTS,
    sign_in_paths='^/(?:sign_in|sign_up|login)(?:/|$)',
    chat_address='^/a/chat/s/[\\w-]+/?$',
    terms="DeepSeek's terms restrict automated access.",
    browser_env="JARVIS_DEEPSEEK_BROWSER")

SIGN_IN_LINE = SITE.sign_in_line
CHECK_LINE = SITE.check_line
NOT_SIGNED_IN = SITE.not_signed_in


def profile_dir() -> Path:
    """The browser profile used ONLY for Jarvis's DeepSeek window."""
    return W.profile_dir(SITE)


def ready() -> str:
    """"" when a conversation can start, else why not (jarvis_chatbot_web.ready)."""
    return W.ready(SITE)


class DeepSeekWeb(W.WebAdapter):
    """DeepSeek through its website, in a window the owner can see."""
    SITE = SITE
    id = ID
    name = NAME
    host = HOST


def _factory() -> CB.Adapter:
    """The registry's factory: the real site, the real profile. Opens
    nothing until the driver calls open()."""
    return DeepSeekWeb()


W.register(SITE, _factory, ready)


def sign_in(*, out=print, adapter: Optional[DeepSeekWeb] = None,
            wait: float = W.SIGN_IN_WAIT) -> int:
    """Sign in once, by hand, to the spare DeepSeek account."""
    return W.sign_in(SITE, DeepSeekWeb, out=out, adapter=adapter, wait=wait)


def self_check(*, out=print, adapter: Optional[DeepSeekWeb] = None,
               report: Optional[Path] = None, reply_wait: float = 120.0) -> int:
    """Send the two fixed questions and print PASS or FAIL per step."""
    return W.self_check(SITE, DeepSeekWeb, out=out, adapter=adapter, report=report,
                        reply_wait=reply_wait)


def main(argv: list) -> int:
    return W.main(SITE, DeepSeekWeb, argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
