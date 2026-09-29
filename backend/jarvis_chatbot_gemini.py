"""jarvis_chatbot_gemini.py - the Gemini adapter for the chatbot driver:
Jarvis types into gemini.google.com in a browser window the owner can see.

NEW MODULE, shipped whole (like jarvis_chatbot.py, which it plugs into).
STEP 2 OF THE CHATBOT DRIVER. Reachable from both apps through
/api/chatbot/* (jarvis_chatbot_routes.py, docs/JARVIS-API.md section 87)
once Playwright is installed and the window has been signed in. NOT yet
tried against the real gemini.google.com.

A THIN SITE FILE. What every chatbot website shares - the browser thread,
the visible window, the typing, the host lock, "is the reply finished?",
every "needs the owner" page, the sign-in helper and the self-check - is in
jarvis_chatbot_web.py. This file holds only what is Gemini's own: the
SELECTORS table, the hosts, and the words.

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

WHAT "OPENLY" MEANS HERE (jarvis_chatbot_web.py does it; test_chatbot_gemini.py
checks each one, over both files)
  * A real, VISIBLE browser window, launched with `headless=False` and
    Playwright's own defaults. Nothing hides that a program is driving it.
  * No stealth plug-in, no change to how the browser presents itself, no
    script injected into the page, no proxy, no captcha solving, no retrying
    to get past a limit.
  * A person's pace: a plain, fixed pause after every typed character.
  * At a captcha, a sign-in page, an "unusual activity" / "verify it's you"
    page (including Google's own google.com/sorry page), a notice over the
    page, or anything else it does not recognise, status() says
    "needs_owner" and the adapter does NOTHING else.

WHAT IT TOUCHES AND READS
  * One browser profile folder used ONLY for this:
    <Jarvis settings folder>/chatbot/gemini-profile (normally
    %USERPROFILE%\\.openjarvis\\chatbot\\gemini-profile). The owner signs in
    to the spare Google account once, by hand, with
        py -3 jarvis_chatbot_gemini.py sign-in
    Jarvis never types, sees or stores the password.
  * A NEW chat every conversation (it opens gemini.google.com/app fresh);
    only the newest reply that appeared AFTER its own message is read.
  * It clicks exactly two things: the message box and the send button.
  * The only address it opens by itself is gemini.google.com/app. Google's
    sign-in page is reached only by the OWNER clicking "Sign in".

WHEN THE SITE CHANGES
Every selector is in ONE table, SELECTORS, below, with fallbacks. They were
written without access to gemini.google.com (the container this was built
in cannot reach it, and must not automate it). NOT VERIFIED against the
live site: the owner checks them on the PC with one line, which sends two
harmless fixed questions in one new chat and prints PASS or FAIL per step:
    py -3 jarvis_chatbot_gemini.py check

IF PLAYWRIGHT IS NOT INSTALLED
open() raises GeminiUnavailable with the one-line install command, and
ready() says the same before any approval card is raised:
    py -3 -m pip install playwright; py -3 -m playwright install chromium

    python3 test_chatbot_gemini.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import jarvis_chatbot as CB
import jarvis_chatbot_web as W

ID = "gemini_web"
NAME = "Gemini"
HOST = "gemini.google.com"
#: The one address this adapter opens by itself: a new, empty chat.
START_URL = "https://gemini.google.com/app"
#: Google's sign-in pages. Reached only when the OWNER clicks "Sign in".
SIGN_IN_HOSTS = ("accounts.google.com",)

# The shared pace and waits (jarvis_chatbot_web.py), named here too.
TYPE_DELAY_MS = W.TYPE_DELAY_MS
SETTLE_SECONDS = W.SETTLE_SECONDS
POLL_SECONDS = W.POLL_SECONDS
OPEN_WAIT = W.OPEN_WAIT
SENT_WAIT = W.SENT_WAIT
STEP_TIMEOUT_MS = W.STEP_TIMEOUT_MS
SIGN_IN_WAIT = W.SIGN_IN_WAIT
BROWSERS = W.BROWSERS
NO_BOX = W.NO_BOX
UNUSUAL_WORDS = W.UNUSUAL_WORDS
SIGN_IN_WORDS = W.SIGN_IN_WORDS
CHECK_QUESTION = W.CHECK_QUESTION
INSTALL_LINE = W.INSTALL_LINE
NOT_INSTALLED = W.NOT_INSTALLED
NO_BROWSER = W.NO_BROWSER


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
#   own            one of Jarvis's own messages (never read    status() (skipped)
#                  for warnings)
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
    "own": (
        'user-query',
        'message-content',
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

SITE = W.Site(
    id=ID, name=NAME, host=HOST, start_url=START_URL,
    module="jarvis_chatbot_gemini.py", profile_name="gemini",
    account="Google account", company="Google", selectors=SELECTORS,
    sign_in_hosts=SIGN_IN_HOSTS,
    # Google's "unusual traffic" page (google.<tld>/sorry/...).
    blocked_page=W.is_google_sorry,
    browser_env="JARVIS_GEMINI_BROWSER",
    card_note=("Jarvis types at a person's pace and never hides that it is a program, "
               "never changes how the browser looks to Google, and never solves or skips "
               "a captcha - at a captcha, a sign-in or an \"unusual activity\" page it stops "
               "and asks you. It opens a new chat and reads only the replies to its own "
               "messages. Google's terms forbid automated use of its services, so the "
               "spare account could be closed."))

SIGN_IN_LINE = SITE.sign_in_line
CHECK_LINE = SITE.check_line
NOT_SIGNED_IN = SITE.not_signed_in
PROFILE_BUSY = SITE.profile_busy

#: The window cannot be opened (the same class for every website).
GeminiUnavailable = W.WebUnavailable
playwright_installed = W.playwright_installed


def profile_dir() -> Path:
    """The browser profile used ONLY for Jarvis's Gemini window."""
    return W.profile_dir(SITE)


def check_report_path() -> Path:
    return W.check_report_path(SITE)


def ready() -> str:
    """"" when a conversation can start, else why not (jarvis_chatbot_web.ready)."""
    return W.ready(SITE)


class GeminiWeb(W.WebAdapter):
    """Gemini through its website, in a window the owner can see."""
    SITE = SITE
    id = ID
    name = NAME
    host = HOST


def _factory() -> CB.Adapter:
    """The registry's factory: the real site, the real profile. Opens
    nothing until the driver calls open()."""
    return GeminiWeb()


W.register(SITE, _factory, ready)


def sign_in(*, out=print, adapter: Optional[GeminiWeb] = None,
            wait: float = SIGN_IN_WAIT) -> int:
    """Sign in once, by hand, to the spare Google account."""
    return W.sign_in(SITE, GeminiWeb, out=out, adapter=adapter, wait=wait)


def self_check(*, out=print, adapter: Optional[GeminiWeb] = None,
               report: Optional[Path] = None, reply_wait: float = 120.0) -> int:
    """Send the two fixed questions and print PASS or FAIL per step."""
    return W.self_check(SITE, GeminiWeb, out=out, adapter=adapter, report=report,
                        reply_wait=reply_wait)


def main(argv: list) -> int:
    return W.main(SITE, GeminiWeb, argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
