"""jarvis_chatbot_perplexity.py - the Perplexity adapter for the chatbot
driver: Jarvis types into www.perplexity.ai in a browser window the owner
can see.

NEW MODULE, shipped whole. A THIN SITE FILE: everything every chatbot
website shares - the browser thread, the visible window, the typing, the
host lock, "is the reply finished?", every "needs the owner" page, the
sign-in helper and the self-check - is jarvis_chatbot_web.py. This file
holds only what is Perplexity's own: the SELECTORS table, the hosts and the
words. Registered as chatbot `perplexity_web`. Not reachable from either app
yet (docs/JARVIS-API.md section 60).

THE OWNER'S DECISION (CLAUDE.md, 2026-09-28, "The chatbot driver becomes
versatile"): more chatbot websites, driven OPENLY like Gemini, each with its
own SPARE account used only by Jarvis.
  * Perplexity's terms restrict automated access (not read word for word
    for this file).
    The account may be blocked or closed; Jarvis will not work around a block.
  * No stealth plug-in, no change to how the browser presents itself, nothing
    that hides that a program is driving, no proxy, no captcha solving (the
    shared base does all the driving; test_chatbot_sites.py reads this file
    and the base for any such code).

WHAT IT OPENS: only a new question at www.perplexity.ai/ (it becomes
.../search/<slug>). Any other host is refused. A sign-in page is reached
only by the OWNER clicking "Sign in" in the window.

ONE-TIME SET-UP ON THE PC (PowerShell, in Jarvis's folder)
    py -3 jarvis_chatbot_perplexity.py sign-in
        sign in once, by hand, to the spare Perplexity account; its own
        profile folder is <config>/chatbot/perplexity-profile
    py -3 jarvis_chatbot_perplexity.py check
        one harmless fixed question; PASS/FAIL per step and which
        selector matched

SOURCES
Perplexity lists the web pages its answer came from. The reply Jarvis
hands back is the answer's words, then "Sources listed by Perplexity (links
not opened):" and each listed link as plain text (its label and address),
read from the reply with get_attribute - never clicked, opened or followed -
so a comparison can say which answers came with sources. At most 20, only
http(s) addresses, each once. The "sources" row of SELECTORS finds them.

THE SELECTORS ARE BEST GUESSES, NOT VERIFIED. They were written without
access to www.perplexity.ai (the container this was built in cannot reach
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

ID = "perplexity_web"
NAME = "Perplexity"
HOST = "www.perplexity.ai"
#: The one address this adapter opens by itself: a new, empty chat.
START_URL = "https://www.perplexity.ai/"
#: Sign-in pages (reason "login"). Reached only when the OWNER clicks.
SIGN_IN_HOSTS = ("accounts.google.com", "appleid.apple.com")


# ============================================================================
#   THE SELECTORS - everything that depends on how www.perplexity.ai looks
# ============================================================================
#
# Tried in order; the first that finds something VISIBLE wins. Plain CSS,
# role and aria-label based first where the site is known to have them.
# NOT VERIFIED: `py -3 jarvis_chatbot_perplexity.py check`
# prints which one matched per role.
#
#   input        the box the message is typed into
#   send         the button that sends it (the only other thing clicked)
#   stop         the stop control, shown while it writes
#   reply        ONE reply (the newest is last)
#   reply_text   the words inside one reply (none found: the whole reply)
#   sources      the source links listed in one reply, read as text
#   own          one of Jarvis's own messages (skipped by the warning check)
#   signed_out   a "Sign in" / "Log in" button: nobody is signed in
#   sign_in_form, captcha, warning, notice: the shared lists in
#                jarvis_chatbot_web.py, the same for every site
SELECTORS: dict = {
    "input": (
        'textarea[aria-label*="Ask" i]',
        '#ask-input',
        'textarea[placeholder*="Ask" i]',
        '[contenteditable="true"][role="textbox"]',
    ),
    "send": (
        'button[aria-label="Submit"]',
        'button[aria-label*="Submit" i]',
        'button[aria-label*="Send" i]',
    ),
    "stop": (
        'button[aria-label="Stop"]',
        'button[aria-label*="Stop" i]',
    ),
    "reply": (
        'div[data-testid="answer"]',
        'div[id^="markdown-content-"]',
        'div.prose',
    ),
    "reply_text": (
        'div[id^="markdown-content-"]',
        '.prose',
    ),
    "sources": (
        'div[data-testid="sources"] a[href]',
        'div[class*="source"] a[href]',
        'a.citation[href]',
        'a[href^="http"]',
    ),
    "own": (
        'div[data-testid="query"]',
        'h1[class*="query"]',
    ),
    "signed_out": (
        'button[aria-label="Sign in" i]',
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
    module="jarvis_chatbot_perplexity.py", profile_name="perplexity",
    account="Perplexity account", company="Perplexity", selectors=SELECTORS,
    sign_in_hosts=SIGN_IN_HOSTS,
    sign_in_paths='^/(?:auth|login|signin)(?:/|$)',
    chat_address='^/search/[^/]+/?$',
    terms=("It copies the sources Perplexity lists as text and never opens them. "
           "Perplexity's terms restrict automated access."),
    browser_env="JARVIS_PERPLEXITY_BROWSER")

SIGN_IN_LINE = SITE.sign_in_line
CHECK_LINE = SITE.check_line
NOT_SIGNED_IN = SITE.not_signed_in


def profile_dir() -> Path:
    """The browser profile used ONLY for Jarvis's Perplexity window."""
    return W.profile_dir(SITE)


def ready() -> str:
    """"" when a conversation can start, else why not (jarvis_chatbot_web.ready)."""
    return W.ready(SITE)


class PerplexityWeb(W.WebAdapter):
    """Perplexity through its website, in a window the owner can see."""
    SITE = SITE
    id = ID
    name = NAME
    host = HOST


def _factory() -> CB.Adapter:
    """The registry's factory: the real site, the real profile. Opens
    nothing until the driver calls open()."""
    return PerplexityWeb()


W.register(SITE, _factory, ready)


def sign_in(*, out=print, adapter: Optional[PerplexityWeb] = None,
            wait: float = W.SIGN_IN_WAIT) -> int:
    """Sign in once, by hand, to the spare Perplexity account."""
    return W.sign_in(SITE, PerplexityWeb, out=out, adapter=adapter, wait=wait)


def self_check(*, out=print, adapter: Optional[PerplexityWeb] = None,
               report: Optional[Path] = None, reply_wait: float = 120.0) -> int:
    """Send the one fixed question and print PASS or FAIL per step."""
    return W.self_check(SITE, PerplexityWeb, out=out, adapter=adapter, report=report,
                        reply_wait=reply_wait)


def main(argv: list) -> int:
    return W.main(SITE, PerplexityWeb, argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
