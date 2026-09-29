"""jarvis_chatbot_chatgpt.py - the ChatGPT adapter for the chatbot driver:
Jarvis types into chatgpt.com in a browser window the owner can see.

NEW MODULE, shipped whole. A THIN SITE FILE: everything every chatbot
website shares - the browser thread, the visible window, the typing, the
host lock, "is the reply finished?", every "needs the owner" page, the
sign-in helper and the self-check - is jarvis_chatbot_web.py. This file
holds only what is ChatGPT's own: the SELECTORS table, the hosts and the
words. Registered as chatbot `chatgpt_web`.
Reachable from both apps through /api/chatbot/* (jarvis_chatbot_routes.py,
docs/JARVIS-API.md section 87) once its window has been signed in.
NOT yet tried against the real site.

THE OWNER'S DECISION (CLAUDE.md, 2026-09-28, "The chatbot driver becomes
versatile"): more chatbot websites, driven in a visible window like Gemini, each with its
own SPARE account used only by Jarvis.
  * OpenAI's Terms of Use forbid "automatically or programmatically
    extract[ing] data or Output" - as quoted from Open Terms Archive's
    copy in docs/CHATBOT-DRIVER-DESIGN.md (not re-read for this file).
    The account may be blocked or closed; the owner accepted that risk (2026-09-29).
  * REVERSED 2026-09-29 (owner): the old "driven openly, nothing that hides
    the automation" rule is gone - the ban risk was explained and accepted.
    THIS window is still a real, visible browser (a real browser), and this
    file adds no spoofing of its own to it. Still true: no proxy, no captcha
    solving (a captcha is handed to the owner), nothing private typed into
    the chat (the shared base does all the driving; test_chatbot_sites.py
    reads this file and the base for any such code).

WHAT IT OPENS: only a new chat at chatgpt.com/ (it becomes
chatgpt.com/c/<id>). Any other host is refused. A sign-in page is reached
only by the OWNER clicking "Sign in" in the window.

ONE-TIME SET-UP ON THE PC (PowerShell, in Jarvis's folder)
    py -3 jarvis_chatbot_chatgpt.py sign-in
        sign in once, by hand, to the spare OpenAI account; its own
        profile folder is <config>/chatbot/chatgpt-profile
    py -3 jarvis_chatbot_chatgpt.py check
        two harmless fixed questions in one new chat; PASS/FAIL per
        step and which selector matched

THE SELECTORS ARE BEST GUESSES, NOT VERIFIED. They were written without
access to chatgpt.com (the container this was built in cannot reach it, and
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

ID = "chatgpt_web"
NAME = "ChatGPT"
HOST = "chatgpt.com"
#: The one address this adapter opens by itself: a new, empty chat.
START_URL = "https://chatgpt.com/"
#: Sign-in pages (reason "login"). Reached only when the OWNER clicks.
SIGN_IN_HOSTS = (
    "auth.openai.com",
    "auth0.openai.com",
    "accounts.google.com",
    "login.microsoftonline.com",
    "login.live.com",
    "appleid.apple.com",
)


# ============================================================================
#   THE SELECTORS - everything that depends on how chatgpt.com looks
# ============================================================================
#
# Tried in order; the first that finds something VISIBLE wins. Plain CSS,
# role and aria-label based first where the site is known to have them.
# NOT VERIFIED: `py -3 jarvis_chatbot_chatgpt.py check`
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
        'div#prompt-textarea[contenteditable="true"]',
        '#prompt-textarea',
        'div.ProseMirror[contenteditable="true"]',
        '[contenteditable="true"][role="textbox"]',
        'textarea[placeholder*="Message" i]',
    ),
    "send": (
        'button[data-testid="send-button"]',
        'button[aria-label="Send prompt"]',
        'button[aria-label*="Send" i]',
    ),
    "stop": (
        'button[data-testid="stop-button"]',
        'button[aria-label="Stop streaming"]',
        'button[aria-label*="Stop" i]',
    ),
    "reply": (
        'div[data-message-author-role="assistant"]',
        '[data-message-author-role="assistant"]',
        'article[data-turn="assistant"]',
    ),
    "reply_text": (
        '.markdown',
        '.prose',
    ),
    "own": (
        '[data-message-author-role="user"]',
        'article[data-turn="user"]',
    ),
    "signed_out": (
        'button[data-testid="login-button"]',
        'a[href*="auth/login"]',
        'button[aria-label="Log in" i]',
    ),
    "sign_in_form": W.SIGN_IN_FORM,
    "captcha": W.CAPTCHA,
    "warning": W.WARNING,
    "notice": W.NOTICE,
}

SITE = W.Site(
    id=ID, name=NAME, host=HOST, start_url=START_URL,
    module="jarvis_chatbot_chatgpt.py", profile_name="chatgpt",
    account="OpenAI account", company="OpenAI", selectors=SELECTORS,
    sign_in_hosts=SIGN_IN_HOSTS,
    sign_in_paths='^/(?:auth/|log-?in(?:/|$))',
    chat_address='^/c/[\\w-]+/?$',
    terms="OpenAI's terms forbid automatically extracting ChatGPT's answers.",
    browser_env="JARVIS_CHATGPT_BROWSER")

SIGN_IN_LINE = SITE.sign_in_line
CHECK_LINE = SITE.check_line
NOT_SIGNED_IN = SITE.not_signed_in


def profile_dir() -> Path:
    """The browser profile used ONLY for Jarvis's ChatGPT window."""
    return W.profile_dir(SITE)


def ready() -> str:
    """"" when a conversation can start, else why not (jarvis_chatbot_web.ready)."""
    return W.ready(SITE)


class ChatGPTWeb(W.WebAdapter):
    """ChatGPT through its website, in a window the owner can see."""
    SITE = SITE
    id = ID
    name = NAME
    host = HOST


def _factory() -> CB.Adapter:
    """The registry's factory: the real site, the real profile. Opens
    nothing until the driver calls open()."""
    return ChatGPTWeb()


W.register(SITE, _factory, ready)


def sign_in(*, out=print, adapter: Optional[ChatGPTWeb] = None,
            wait: float = W.SIGN_IN_WAIT) -> int:
    """Sign in once, by hand, to the spare OpenAI account."""
    return W.sign_in(SITE, ChatGPTWeb, out=out, adapter=adapter, wait=wait)


def self_check(*, out=print, adapter: Optional[ChatGPTWeb] = None,
               report: Optional[Path] = None, reply_wait: float = 120.0) -> int:
    """Send the two fixed questions and print PASS or FAIL per step."""
    return W.self_check(SITE, ChatGPTWeb, out=out, adapter=adapter, report=report,
                        reply_wait=reply_wait)


def main(argv: list) -> int:
    return W.main(SITE, ChatGPTWeb, argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
