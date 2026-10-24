"""jarvis_tellme.py - "Tell me when ...": Jarvis looks every few minutes for
an email from a named sender, or a Home Assistant device reaching a state,
and ONLY tells the owner when it happens - urgently, if they asked.

NEW MODULE, shipped whole. No patch: it is a KIND of job on the one
scheduler (jarvis_schedule.register_kind), set up through the scheduler's
existing POST /api/schedule/add and its ONE schedule_repeat card, listed in
Coming up in both apps like any repeating job, and set up by voice or text
through jarvis_quick.py ("tell me when an email from Alex arrives").

THE OWNER'S DECISION (CLAUDE.md, 2026-09-25, after the prompt pack):
"Urgent alerts without phone calls: 'tell me when ...' (a named sender's
email, a device change) set up with one card; a match only notifies -
urgent ones as a phone notification that keeps ringing until seen. No
telephony service: a call would send private text to an outside voice
company (rule 1)."

WHAT IT MAY DO, AND WHAT IT NEVER DOES
  * Setting one up is ONE approval card (schedule_repeat, tier "ask" - the
    scheduler refuses any other tier). The card says exactly what is
    watched, which server is asked, how often, until when, whether it tells
    once or every time, and whether it is urgent.
  * A match ONLY notifies. Never an action, never a reply, never a card,
    never a message to anyone. Nothing read here goes to the AI model.
  * The notification's words are built from the OWNER'S words, never from
    the email or the device: "An email from Alex arrived." - where "Alex" is
    what the owner asked to watch for, not the From line. No subject, no
    sender address, no text of the email is ever shown, kept or logged.
    The device's own state value is not shown either: "The washing machine
    finished." A locked phone, and both apps while App lock or "Hide memory
    lists and chat history" is on, show only LOCK_SCREEN.
  * The model has no tool for this: a watch is set up only by the owner's
    own typed or said words (the fast path) or from an app. A web page or
    an email cannot set one up.

HOW OFTEN IT LOOKS, AND WHY THOSE NUMBERS
  * Email: every 5 minutes at most often (EMAIL_MINUTES). Each look is one
    sign-in to the owner's mail server; most mail apps check every 5 to 15
    minutes, and some providers slow down or block accounts that sign in
    much more often. Five minutes late is fine for "tell me when Alex
    writes".
  * Home Assistant: every minute at most often (HOME_MINUTES). One small
    request to a server on the owner's own network; "the washing machine
    finished" is worth knowing within a minute, and a door opening sooner
    than that is a job for Home Assistant's own automations, not this.
  * These floors are for this kind only. Every other repeat keeps the
    scheduler's hourly floor (jarvis_schedule.MIN_EVERY_HOURS): the generic
    rule check still refuses "every N minutes"; only this kind's own check
    (register_kind(check=...)) accepts it.
  * It ends: DEFAULT_DAYS (30) unless the owner says otherwise ("for the
    next 2 hours", "today"), at most MAX_DAYS (90) - a forgotten watch must
    not sign in to the inbox for ever. By default it tells ONCE and then
    ends; "tell me every time ..." keeps going until the end date.

EMAIL - READ-ONLY, THE FROM LINE ONLY, NOTHING MARKED AS READ
One connection per look to the server jarvis_email.plan() names (the same
JARVIS_IMAP_* settings, read fresh each time), and only these commands:
    LOGIN, EXAMINE (read-only select), UID SEARCH UID <n>:*,
    UID FETCH <uids> (BODY.PEEK[HEADER.FIELDS (FROM)]), CLOSE, LOGOUT
PEEK, so the server sets no \\Seen flag. No STORE, COPY, MOVE or EXPUNGE,
no subject, no body. The first look only notes where the mailbox is
(UIDNEXT); every later look reads the From line of mail that arrived since
the look before, at most MAX_NEW messages. The sender's name is matched on
this PC and never sent to the server. A mailbox whose UIDVALIDITY changes
(rebuilt by the provider) starts again from there, telling nothing.

HOME ASSISTANT - ONE DEVICE, READ ONLY
jarvis_home.plan_states([entity]) - one GET of one named entity, the same
read the model's home_read tool makes, through the same gate action. It
tells when the state CHANGES to one the owner asked for (off, open, ...):
a washing machine already off when the watch starts is not "finished".
"unavailable" and "unknown" (Home Assistant restarting) are skipped.

"TELL ME WHEN THIS PAGE CHANGES" (I67, 2026-09-27, CLAUDE.md's decision of
2026-09-27: "one card per address the owner adds, read-only, never follows
links elsewhere, never acts on what it reads") - a third source, "page":
one plain GET of one address the owner typed (no account to sign in to, so
no readiness "is it set up?" - only the tier), never a redirect anywhere
the check below would refuse. The changedetection.io pattern: the look keeps
a SHA-256 fingerprint of the page's words (reusing the same `last_state`
column Home Assistant's state uses - it is a hash there too, just of a
device's state word), never the page's actual text - and a match is never a
diff or a quote of the page. Every address is refused if it resolves - by a
REAL DNS lookup, not spelling - to this PC or a private network address
(`jarvis_local_http.private_fetch_problem`), checked again immediately
before every look, not only when the address is added: a name's DNS answer
can change (DNS rebinding), and a page's own redirect could otherwise point
back at the home network after the check already passed once.
  * "PRICE, VERSION OR STOCK - WHAT ACTUALLY CHANGED" (Pillar 26,
    2026-10-17; Blueprint C of Volume III): a look now understands the
    page's structure too. `strip_page_noise` removes what changes on a page
    nobody changed (the script/style/noscript/svg/nav/footer/aside
    elements' text, timestamps, view counts, CSRF/session nonces, utm_*
    parameters and the SecAlign chat/tool markers), `extract_watch_signals`
    reads - by plain code, never the model - every price in whole cents,
    every version/release tag, a three-state stock state and the hash of the
    clean words, and `diff_watch_snapshot` says what changed ("The price is
    now 199.99 (it was 249.99)."). Since 2026-10-21 it reads the price and
    availability a shop marks for MACHINES first - schema.org JSON-LD and
    OpenGraph/meta tags, the markup `price_of()` already used for price
    watches - because a discount or an "OutOfStock" is often only there, and
    the visible price is not counted a second time when it says the same. When the two looks differ only in the
    stripped noise the answer is the `[SILENT]` watermark (`PAGE_SILENT`)
    and nothing is notified; a failed fetch is stale, keeps the old
    snapshot and its `last_good_at`, and never alerts. A real change is
    outside text, so it latches the gate's conversation taint
    (`jarvis_gate.latch_taint(why="page_watch")`). The page's words
    themselves are still never kept, shown or quoted - only the
    noise-stripped hash and those short structured facts - so this is still
    a reader that only tells the owner, on both apps, through the same
    generic alert.

THE GATE, EVERY LOOK
Each look asks jarvis_gate first, like the morning briefing's reads:
email_read or home_read, and it runs only when that says yes without a
person at tier "auto" (the shipped tier). A read set to "ask" cannot be
asked every few minutes, and one set to "notify" would send a "Jarvis read
your email" message every few minutes - so with either, setting one up is
refused with the reason, and a look that meets it later is skipped and says
so under Coming up. (The morning briefing, which reads once a day, accepts
"notify" too.) So the audit log gets one line per look - the price of every
read leaving this PC going through the same gate.

THE EVENT
The scheduler rings no doorbell for a look (the kind is `silent`). On a
match this publishes `schedule` {"id", "kind": "tellme", "state":
"matched", "urgent": bool} - ids, the kind and a flag, never words. The
apps then read the job by id (GET /api/schedule?id=), whose `alert` is the
sentence above. Urgent: the phone rings and vibrates until the owner looks
(an alarm-style notification); the PC shows an alarm toast whose sound
loops until it is dismissed.

INSTANT EMAIL - ONE CONNECTION THE MAIL SERVER NUDGES (IMAP IDLE; 2026-09-26)
The owner chose instant "tell me when" for email (CLAUDE.md, cutting-edge
decision, "Documents & email"). While at least one email watch is on, this
module keeps ONE connection open to the owner's mail server and asks it
(IMAP IDLE) to say the moment new mail arrives. It sends only LOGIN,
CAPABILITY, EXAMINE (read-only), IDLE, DONE and LOGOUT - never FETCH,
SEARCH or anything that changes the mailbox. A nudge ("new mail") only makes
the ordinary look above happen straight away, through the gate as
email_read, like every look; so a match is told within seconds instead of
within 5 minutes, and still only NOTIFIES.
  * Owned by this kind, not a service of its own: it opens when an email
    watch's look runs and no connection is up, and closes when the last
    email watch ends, is paused or deleted, when Jarvis goes on STANDBY, and
    when the owner presses STOP EVERYTHING (a stopper registered with
    jarvis_stop_all). After Standby or Stop everything it opens again only
    at a watch's next regular look - the watch the owner approved carries
    on; the open connection is how it looks, not a second permission.
  * Renewed every IDLE_RENEW_SECONDS (9 minutes): the IMAP standard (RFC
    2177) lets a server drop an idle client after 29 minutes, and a home
    router may drop a quiet connection sooner. Gmail's own limit was not
    checked.
  * On any drop it says so under Coming up and tries again after
    IDLE_BACKOFF (30 seconds, then longer, up to 30 minutes). Meanwhile - and
    whenever it is not connected - the looks every 5 minutes carry on
    exactly as before. While it IS connected, the regular looks skip the
    sign-in, except one full look every SAFETY_MINUTES (30) in case a nudge
    was missed.
  * The password is read fresh from the environment for each connection,
    sent only to the owner's mail server, and never logged, kept or put in
    an error: a failure is said in fixed words. The server's certificate is
    checked (jarvis_email.tls_context).
  * Written by hand on a socket: the owner's Python 3.12 imaplib has no IDLE
    (it arrived in 3.14), and a hand loop needs no new package.

"TELL ME IF ALEX HASN'T REPLIED BY FRIDAY" (I69, 2026-09-26)
The same From-line match, the other way round: {"missing": true, "by": a
time}. An email from Alex before then ends the watch quietly ("Alex wrote at
14:02 - nothing to tell you."); none by then, and the owner is told "No
email from Alex arrived by Friday 26 September at 17:00." It looks every 5
minutes (or instantly) until the time and once after it, and waits up to a
day after it for a PC that was off: then it tells, marked as missed, and it
does not ring (the owner's rule for anything more than 10 minutes late).
Same ONE card, same list, same notification - it only notifies.

WATCHES, 2026-09-28 (the owner chose the "Watches" group of
docs/RESEARCH-AUDIT-2026-09-28.md section 3, ideas 1, 2 and 5). Three more
sources, each ONE card like the others, each only notifying:
  * "search" - "tell me when a search for <words> shows something new". The
    owner's own words are searched once a day (every 6 hours at the most
    often, once a week at the least) through the web search the owner chose
    in Settings (jarvis_search.plan/run: SearXNG by default; never another
    provider by itself - if the chosen one is down, the look says so and
    offers to switch, as a chat search does). Only a short fingerprint of
    each result's ADDRESS is kept; a match is "an address not seen before".
    Titles, snippets and the addresses themselves are never kept, shown or
    sent to the AI model - the results are outside text, never learned
    from and never acted on. If the owner switches provider, the next look
    only re-records (another provider's results are not comparable).
    "Ask before every web search" on, or web search set to "never", and a
    search watch cannot run - it cannot ask every day.
  * "price" - "tell me when the price on <url> drops below 25". The same
    one GET as a page watch (page_read, the private-address checks, the
    redirect rule), and the price is read by PLAIN CODE, never the AI model:
    the price a shop marks for machines (schema.org's JSON-LD "price", or
    a price <meta> tag), else the first price shown on the page. Only that
    number is kept. It never buys, never presses anything on the page.
  * "github" - "tell me when CI finishes/fails on owner/repo [branch]" and
    "tell me when PR #N on owner/repo merges". One read-only GET to
    api.github.com per look (gate action github_read, tier "auto" only),
    with the GitHub key Jarvis already has for github_search
    (JARVIS_GITHUB_TOKEN) when one is set - sent to api.github.com only,
    never with a redirect, never logged, never put in a card or an error.
    Kept: the newest commit's first 12 characters and "running/done,
    failed/ok", or "open/merged/closed".
And a watch that BREAKS tells the owner once: a look that could not happen
("Could not look: ...") used to be written only under the watch, so an
urgent watch could be dead for days unseen. Now failures are grouped by
(watch, kind of problem - the sentence without its bracketed detail); the
owner is told once (an ordinary notification, never ringing), repeats of
the same problem are held back for BROKEN_AGAIN_HOURS, and the next good
look clears it silently. The Hermes agent's cron/incidents.py (MIT) was the
idea; no code is copied. The event is `schedule` {"id", "kind": "tellme",
"state": "broken"} - no words; the apps read `broken` by id.

WHAT IS KEPT
The watch (the owner's words: a sender's name or a device) is in the job's
rule in schedule.db, like a reminder's words. This module's own table,
`tellme` in the same file, keeps per job only: the mailbox position (a
number), the device's last state (a short word), when it last looked and
how that went (a fixed sentence), and when it last matched. No sender, no
subject, no email text, ever. A page watch keeps in the same `last_state`
column a small JSON snapshot (Pillar 26): the SHA-256 of the page's
noise-stripped words, every price in whole cents (integers; machine-marked
ones first, then the visible ones not already counted), every version
tag, one of three stock states, the plain words for the last real change and
when the last good look was - never the page's words, never a quote, and
nothing from it is sent to the AI model.
"""
from __future__ import annotations

import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

import jarvis_schedule as S

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

# --------------------------------------------------------------------------
#   Words - both apps say the same (jarvis-desktop/src/coming-up.js,
#   jarvis-client net/Schedule.kt; tests/coming-up.mjs checks)
# --------------------------------------------------------------------------

KIND = "tellme"
TITLE = "Tell me when"
NOUN = "\"tell me when\""

#: All a lock screen shows - and all either app shows while App lock or
#: "Hide memory lists and chat history" is on.
LOCK_SCREEN = "Jarvis: something you asked to be told about happened."

EMAIL_MINUTES = 5
HOME_MINUTES = 1
MAX_MINUTES = 60
#: "Tell me when this page changes" (I67, 2026-09-27): a page on someone
#: else's server, not the owner's own account - looked at less often than
#: email or Home Assistant on purpose (it is a third party's server, not
#: the owner's own), and its ceiling is its own: once a day is a fine
#: floor for "let me know when the price drops", so PAGE_MAX_MINUTES is not
#: MAX_MINUTES above, which is the email/home ceiling only.
PAGE_MINUTES = 30
PAGE_MAX_MINUTES = 24 * 60
DEFAULT_DAYS = 30
MAX_DAYS = 90
#: At most this many at once, and this many that read email (each is one
#: sign-in to the mail server every EMAIL_MINUTES).
MAX_WATCHES = 10
MAX_EMAIL_WATCHES = 5
#: Each is one GET to someone else's server every PAGE_MINUTES at least.
MAX_PAGE_WATCHES = 5
#: New messages whose From line one look reads, at most.
MAX_NEW = 50
MAX_NAME = 60
#: "Hasn't replied by ...": how long after its time it still tells, for a PC
#: that was off then (as missed, and without ringing).
NO_REPLY_GRACE = 86400.0
#: The owner's rule (2026-09-26): more than 10 minutes late, nothing rings.
LATE_RING = 600.0

#: Instant email (IMAP IDLE) - see the module docstring.
IDLE_RENEW_SECONDS = 9 * 60
IDLE_TICK = 5.0
IDLE_LIST_SECONDS = 30.0
IDLE_TIMEOUT = 30.0
IDLE_DEBOUNCE = 2.0
SAFETY_MINUTES = 30
IDLE_BACKOFF = (30, 60, 120, 300, 600, 1200, 1800)
#: A server with no IDLE is asked again this much later.
NO_IDLE_RETRY = 6 * 3600.0

EMAIL_ACTION = "email_read"
EMAIL_TOOL = "email_check"
HOME_ACTION = "home_read"
HOME_TOOL = "home_read"
#: "Tell me when this page changes" (I67) - a plain GET of one address the
#: owner typed, gated like any other read; unlike email/home there is no
#: account to set up first, so no PAGE_TOOL: readiness() only checks the tier.
PAGE_ACTION = "page_read"

#: The one FETCH item a look asks for (jarvis_email.SENDER_FETCH's shape).
SENDER_FETCH = "(BODY.PEEK[HEADER.FIELDS (FROM)])"
#: A page watch's own limits: how much of the page is read, and how long
#: Jarvis waits for it to answer.
PAGE_MAX_BYTES = 2 * 1024 * 1024
PAGE_TIMEOUT = 15.0
PAGE_MAX_URL = 500

#: "Tell me when a search shows something new" (2026-09-28). Once a day by
#: default: a search leaves this PC for a search service (Brave's can cost
#: money past its free credit, and DeepSeek bills $0.75 per 1,000 searches),
#: and "something new" on the web is rarely
#: worth knowing within the hour. Every 6 hours at the most often, once a
#: week at the least.
SEARCH_MINUTES = 6 * 60
SEARCH_DEFAULT_MINUTES = 24 * 60
SEARCH_MAX_MINUTES = 7 * 24 * 60
MAX_SEARCH_WATCHES = 5
SEARCH_MAX_WORDS = 200
#: Fingerprints of result addresses remembered, at most (newest first).
SEARCH_KEEP = 200
#: jarvis_search.PROVIDERS, written out so check_watch needs no import.
SEARCH_PROVIDERS = ("searxng", "duckduckgo", "exa", "tavily", "brave", "deepseek")

#: "Tell me when the price on <url> drops below X" (2026-09-28): a page watch
#: that reads one number. Hourly by default; the page's own floor and ceiling.
PRICE_MINUTES = 60
PRICE_MAX = 1_000_000_000
#: The currency signs the owner may say; only for the words - the number
#: alone is compared.
CURRENCIES = ("", "£", "$", "€")

#: GitHub watches (2026-09-28): CI finishing or failing, a pull request
#: merging. Every 10 minutes at the most often - GitHub allows 60 requests an
#: hour without a key, shared with GitHub research; 5 watches at once.
GITHUB_ACTION = "github_read"
GITHUB_API = "https://api.github.com"
GITHUB_MINUTES = 10
GITHUB_MAX_MINUTES = 24 * 60
MAX_GITHUB_WATCHES = 5
GITHUB_EVENTS = ("ci_done", "ci_failed", "pr_merged")
GITHUB_TOKEN_ENV = "JARVIS_GITHUB_TOKEN"
GITHUB_TIMEOUT = 15.0
GITHUB_MAX_BYTES = 1_000_000
#: A workflow run's conclusions that count as "failed".
CI_FAILED = ("failure", "timed_out", "startup_failure")

#: A watch that cannot look: told once, then not again about the same
#: problem for this many hours; cleared by itself at the next good look.
BROKEN_AGAIN_HOURS = 12
#: A watch that looks more often than hourly is told on its second failed
#: look in a row - one dropped connection is not "broken".
BROKEN_AFTER_LOOKS = 2
#: What a lock screen (and either app, while App lock or "Hide memory lists
#: and chat history" is on) shows for it.
BROKEN_LOCK_SCREEN = "Jarvis: a \"tell me when\" cannot look right now."

#: What the owner may say a device does, and the Home Assistant states that
#: count as it. The card lists the states in full.
STATE_WORDS = {
    "finishes": ("off", "idle", "finished", "complete", "completed", "done", "stopped",
                 "standby"),
    "opens": ("on", "open", "opening", "unlocked"),
    "closes": ("off", "closed", "closing", "locked"),
    "turns on": ("on",),
    "turns off": ("off",),
}
#: The same, said after it happened.
PAST = {"finishes": "finished", "opens": "opened", "closes": "closed",
        "turns on": "turned on", "turns off": "turned off"}
#: States that say "Home Assistant cannot see it right now", not a change.
_NOT_A_STATE = ("unavailable", "unknown", "")

_TOKEN = re.compile(r"[a-z0-9_]{1,30}")
_ENTITY = re.compile(r"[a-z0-9_]+\.[a-z0-9_]+")
_NAME_OK = re.compile(r"[\w .@'&+-]{1,60}", re.UNICODE)
#: GitHub's own rules, near enough: an owner (letters, digits, hyphens) and
#: a repository name (letters, digits, ".", "_", "-"), never starting with ".".
_REPO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_-][A-Za-z0-9._-]{0,99}")
_BRANCH = re.compile(r"[A-Za-z0-9._/-]{1,100}")

# --------------------------------------------------------------------------
#   Settings, the gate and the bus - replaceable, so the tests open no socket
# --------------------------------------------------------------------------


def _tier_of(action: str) -> str:
    try:
        return str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception:
        return "ask"


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tools_enabled() -> set:
    try:
        cfg = fw.load_framework() if fw is not None else {}
        return set((cfg.get("tools") or {}).get("enabled") or [])
    except Exception:
        return set()


def _publish(kind: str, data: dict) -> None:
    try:
        import jarvis_events
        jarvis_events.BUS.publish(kind, data)
    except Exception:
        pass


def _audit(event: str, detail: dict) -> None:
    # Ids, the source and outcomes. Never a name, a device or a state.
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


@dataclass
class Deps:
    tier_of: Callable[[str], str] = _tier_of
    gate: Callable = _gate
    tools_enabled: Callable[[], set] = _tools_enabled
    publish: Callable[[str, dict], None] = _publish
    #: (plan, base_uid, uidvalidity) -> {"uidvalidity", "base", "new": [raw From]}
    email_look: Optional[Callable] = None
    #: jarvis_home.run's `fetch`
    home_fetch: Optional[Callable] = None
    sched: Optional[Callable[[], object]] = None
    #: (plan) -> an open IDLE connection (_Imap). None: the real one - but
    #: only when email_look is the real one too: a test that fakes the
    #: looks never opens a real socket for the instant watch.
    idle_connect: Optional[Callable] = None
    #: Is Jarvis on standby? (jarvis_power)
    standby: Optional[Callable[[], bool]] = None
    #: (url) -> the page's current state right now (a "t2:" PAGE_STATE
    #: string), or raises. An old-format fingerprint string is accepted too,
    #: so a test written before Pillar 26 keeps its meaning. None: the real
    #: one (_default_page_fetch) - one GET, no proxy, capped; a test never
    #: opens a real socket.
    page_fetch: Optional[Callable[[str], str]] = None
    #: (url) -> the price read from the page (a float), or None when there is
    #: none, or raises. None: the real one (_default_price_fetch).
    price_fetch: Optional[Callable[[str], Optional[float]]] = None
    #: (jarvis_search.Plan) -> jarvis_search.run's answer. None: the real
    #: run(plan, approved=True) - one provider, never another.
    search_run: Optional[Callable] = None
    #: (url) -> (HTTP status, the parsed JSON or None). None: the real one
    #: (_default_github_get) - api.github.com only, no redirect.
    github_get: Optional[Callable[[str], tuple]] = None


DEPS = Deps()


def _sched():
    if DEPS.sched is not None:
        return DEPS.sched()
    return S._SCHED if S._SCHED is not None else S.get()


def _env(name: str) -> str:
    return str(os.environ.get(name, "") or "").strip()


# --------------------------------------------------------------------------
#   Is a source set up? (settings only - no socket)
# --------------------------------------------------------------------------

def readiness(source: str, deps: Optional[Deps] = None) -> str:
    """"" when a watch on `source` could look, else the sentence why not."""
    deps = deps or DEPS
    if _lockdown_on():
        # Lockdown (jarvis_asks_first.py, 2026-09-28): every way out of this
        # PC asks first, or stops - and a watch cannot stop to ask. Said
        # first, and for every source, so the reason is the real one (the
        # tier words below would blame a settings line nobody changed).
        return LOCKDOWN_WORDS
    enabled = deps.tools_enabled()
    if source == "email":
        if not _env("JARVIS_IMAP_HOST") or EMAIL_TOOL not in enabled:
            return ("Email is not set up for Jarvis on this PC, so there is no inbox to "
                    "watch.")
        return _tier_words(deps.tier_of(EMAIL_ACTION), "email", "every 5 minutes", "email")
    if source == "home":
        url = _env("JARVIS_HOME_URL")
        if not url or HOME_TOOL not in enabled:
            return ("Home Assistant is not set up for Jarvis on this PC, so there is no "
                    "device to watch.")
        try:
            import jarvis_local_http
            bad = jarvis_local_http.plain_http_problem(url, "JARVIS_HOME_URL",
                                                       "the Home Assistant token")
        except Exception:
            bad = ""
        if bad:
            return bad
        return _tier_words(deps.tier_of(HOME_ACTION), "Home Assistant", "every minute",
                           "a device")
    if source == "page":
        # No account to set up first - any address the owner names is
        # "ready" - but the tier must still be "auto", exactly like email
        # and home, or a look every 30 minutes would mean a card every 30
        # minutes.
        return _tier_words(deps.tier_of(PAGE_ACTION), "a web page", "every 30 minutes",
                           "a web page")
    if source == "price":
        # The same one GET as a page watch, under the same action.
        return _tier_words(deps.tier_of(PAGE_ACTION), "a web page", "every hour",
                           "a price on a web page")
    if source == "search":
        return _search_readiness(deps)
    if source == "github":
        why = _tier_words(deps.tier_of(GITHUB_ACTION), "GitHub", "every 10 minutes", "GitHub")
        if why:
            why += (" To allow it, add the line github_read = \"auto\" under [autonomy.tiers] "
                    "in jarvis-framework.toml on the PC.")
        return why
    return ("Jarvis can watch for an email from someone, a Home Assistant device, a web page, "
            "a price, a web search, or GitHub.")


#: Why a watch does not look while Lockdown is on.
LOCKDOWN_WORDS = ("Lockdown is on, so it does not look until you turn Lockdown off (on the PC, "
                  "Settings, What asks first).")


def _lockdown_on() -> bool:
    """Lockdown (jarvis_asks_first.py): False without that module; True if
    it cannot be read - a watch that cannot tell does not look."""
    try:
        import jarvis_asks_first
    except Exception:
        return False
    try:
        return bool(jarvis_asks_first.lockdown_on())
    except Exception:
        return True


def _search_readiness(deps: "Deps") -> str:
    """"" when a search watch could search now, else the sentence why not.
    Settings only - no socket. The provider is the one the owner chose; the
    words are never sent anywhere else."""
    try:
        import jarvis_search as WS
    except Exception:
        return ("Web search is not on this PC's Jarvis yet - run apply-patches.ps1 on the "
                "PC.")
    if deps.tier_of(WS.ACTION_SEARCH) == "never":
        return ("Web search is switched off on this PC (your settings say never), so there "
                "is nothing to search with.")
    try:
        s = WS.settings()
    except Exception:
        return "Jarvis could not read the web search settings on this PC."
    if s.get("ask_every_time"):
        return ("You chose \"Ask before every web search\", and a \"tell me when\" cannot ask "
                "you every day - so it cannot watch a search.")
    state, said = WS.readiness(s.get("provider"), s)
    return said if state else ""


def _tier_words(tier: str, what: str, often: str, watched: str) -> str:
    """Only tier "auto" lets a watch look: "ask" would mean a card every few
    minutes, and "notify" a "Jarvis read your email" message every few
    minutes - so both are refused, with the reason, rather than obeyed badly."""
    if tier == "auto":
        return ""
    if tier == "notify":
        return (f"Your settings tell you each time Jarvis reads {what}, and a \"tell me "
                f"when\" would then tell you {often} - so it cannot watch {watched}.")
    return (f"Your settings ask for a yes each time Jarvis reads {what}, and a \"tell me "
            f"when\" cannot ask you {often} - so it cannot watch {watched}.")


# --------------------------------------------------------------------------
#   The watch, and its rule
# --------------------------------------------------------------------------

def _clean_name(v) -> str:
    t = " ".join(str(v or "").split()).strip(" \"'.,;:!?")
    if not t or len(t) > MAX_NAME or not _NAME_OK.fullmatch(t):
        raise ValueError("say the sender's name or address in a few plain words, like Alex "
                         "or alex@example.com")
    return t


def check_watch(w) -> dict:
    """The watch, tidied, or ValueError with a sentence."""
    if not isinstance(w, dict):
        raise ValueError("a \"tell me when\" needs what to watch")
    source = str(w.get("source") or "").strip().lower()
    urgent = w.get("urgent") is True
    once = w.get("once") is not False
    if source == "email":
        sender = _clean_name(w.get("sender"))
        if sender.casefold() in ("anyone", "anybody", "someone", "somebody", "everyone"):
            raise ValueError("say who the email is from, like \"tell me when an email from "
                             "Alex arrives\"")
        if w.get("missing") is True:
            # "Tell me if Alex hasn't replied by Friday" (I69): told when NO
            # email from them has arrived by `by`. Always once.
            by = w.get("by")
            if not isinstance(by, (int, float)) or isinstance(by, bool):
                raise ValueError("say by when, like \"tell me if Alex hasn't replied by "
                                 "Friday\"")
            return {"source": "email", "sender": sender, "urgent": urgent, "once": True,
                    "missing": True, "by": float(by)}
        return {"source": "email", "sender": sender, "urgent": urgent, "once": once}
    if source == "home":
        entity = str(w.get("entity") or "").strip().lower()
        if not _ENTITY.fullmatch(entity) or len(entity) > 120:
            raise ValueError("a device is its Home Assistant name, like "
                             "switch.washing_machine")
        say = str(w.get("say") or "").strip().lower()
        states = w.get("states")
        if say in STATE_WORDS:
            want = list(STATE_WORDS[say])
        else:
            if isinstance(states, str):
                states = [states]
            if not isinstance(states, list) or not states or len(states) > 10:
                raise ValueError("say what the device should do: finish, open, close, turn "
                                 "on or off - or which state, like off")
            want = []
            for x in states:
                x = str(x or "").strip().lower()
                if not _TOKEN.fullmatch(x) or x in _NOT_A_STATE:
                    raise ValueError("a state is one short word, like off or open")
                if x not in want:
                    want.append(x)
            say = "is " + want[0] if len(want) == 1 else "is " + " or ".join(want)
        name = " ".join(str(w.get("name") or "").split()).lower()
        if name and (len(name) > 40 or not re.fullmatch(r"[a-z0-9' -]+", name)):
            name = ""
        return {"source": "home", "entity": entity, "name": name, "say": say,
                "states": want, "urgent": urgent, "once": once}
    if source == "page":
        url = str(w.get("url") or "").strip()
        if not url or len(url) > PAGE_MAX_URL:
            raise ValueError("a page to watch is a web address starting with http:// or "
                             "https://")
        if not re.match(r"^https?://", url, re.IGNORECASE):
            raise ValueError("a page to watch is a web address starting with http:// or "
                             "https://")
        if any(ord(ch) < 0x20 for ch in url):
            raise ValueError("that is not a web address")
        return {"source": "page", "url": url, "urgent": urgent, "once": once}
    if source == "price":
        url = _check_url(w.get("url"))
        below = w.get("below")
        if isinstance(below, str):
            below = parse_number(below)
        if (not isinstance(below, (int, float)) or isinstance(below, bool)
                or not below == below or below <= 0 or below > PRICE_MAX):
            raise ValueError("say the price to watch for as a number, like \"drops below 25\"")
        currency = str(w.get("currency") or "").strip()
        if currency not in CURRENCIES:
            currency = ""
        return {"source": "price", "url": url, "below": round(float(below), 2),
                "currency": currency, "urgent": urgent, "once": once}
    if source == "search":
        words = clean_search_words(w.get("words"))
        provider = str(w.get("provider") or "").strip().lower()
        if provider and provider not in SEARCH_PROVIDERS:
            raise ValueError("that is not a web search Jarvis knows")
        return {"source": "search", "words": words, "provider": provider, "urgent": urgent,
                "once": once}
    if source == "github":
        repo = str(w.get("repo") or "").strip().strip("/")
        if repo.lower().startswith(("https://github.com/", "http://github.com/")):
            repo = repo.split("github.com/", 1)[1].strip("/")
        if repo.lower().endswith(".git"):
            repo = repo[:-4]
        if not _REPO.fullmatch(repo) or ".." in repo:
            raise ValueError("say the repository as owner/name, like darknight11ish/Epic-Jarvis")
        event = str(w.get("event") or "").strip().lower()
        if event not in GITHUB_EVENTS:
            raise ValueError("say what to watch on GitHub: CI finishing, CI failing, or a pull "
                             "request merging")
        out = {"source": "github", "repo": repo, "event": event, "urgent": urgent}
        if event == "pr_merged":
            pr = w.get("pr")
            if isinstance(pr, str) and pr.strip().lstrip("#").isdigit():
                pr = int(pr.strip().lstrip("#"))
            if not isinstance(pr, int) or isinstance(pr, bool) or not 0 < pr < 10 ** 8:
                raise ValueError("say which pull request, by its number, like PR #12")
            # A pull request merges once: there is no "every time".
            out.update(pr=pr, once=True)
            return out
        branch = str(w.get("branch") or "").strip()
        if branch and (not _BRANCH.fullmatch(branch) or ".." in branch
                       or branch.startswith(("-", "/")) or branch.endswith("/")):
            raise ValueError("that is not a branch name GitHub would have, like main")
        out.update(branch=branch, once=once)
        return out
    raise ValueError("Jarvis can watch for an email from someone, a Home Assistant device, a web "
                     "page, a price, a web search, or GitHub")


def _check_url(v) -> str:
    """A web address the owner typed, for a page or a price watch."""
    url = str(v or "").strip()
    if not url or len(url) > PAGE_MAX_URL or not re.match(r"^https?://", url, re.IGNORECASE):
        raise ValueError("a page to watch is a web address starting with http:// or "
                         "https://")
    if any(ord(ch) < 0x20 or ch.isspace() for ch in url):
        raise ValueError("that is not a web address")
    return url


def clean_search_words(v) -> str:
    """The owner's search words, tidied: one line, no quotes around them."""
    t = "".join(ch if ch.isprintable() else " " for ch in str(v or ""))
    t = " ".join(t.split()).strip(" \"'“”‘’")
    if not t:
        raise ValueError("say what to search for, like \"tell me when a search for "
                         "Kokoro voices shows something new\"")
    if len(t) > SEARCH_MAX_WORDS:
        raise ValueError(f"the search words can be up to {SEARCH_MAX_WORDS} characters")
    return t


def parse_number(v) -> Optional[float]:
    """A price as people and pages write it: "25", "1,299.99", "1.299,99",
    "24,99", "£ 1 299" - or None. Plain code: no model reads a price."""
    t = str(v or "").strip()
    t = re.sub(r"^(?:[£$€]|us\$|usd|gbp|eur)\s*|\s*(?:[£$€]|usd|gbp|eur)$", "", t,
               flags=re.IGNORECASE)
    t = t.replace(" ", " ").replace(" ", " ").strip()
    if not re.fullmatch(r"\d[\d ,.']*", t) or len(t) > 20:
        return None
    t = t.replace(" ", "").replace("'", "")
    last_dot, last_comma = t.rfind("."), t.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        dec = "." if last_dot > last_comma else ","
        thou = "," if dec == "." else "."
        t = t.replace(thou, "").replace(dec, ".")
    elif last_comma >= 0:
        # "24,99" is a decimal comma; "1,299" and "1,299,000" are thousands.
        if len(t) - last_comma - 1 == 2 and t.count(",") == 1:
            t = t.replace(",", ".")
        else:
            t = t.replace(",", "")
    elif t.count(".") > 1:
        t = t.replace(".", "")
    elif last_dot >= 0 and len(t) - last_dot - 1 == 3 and not t.startswith("0"):
        # "1.299" on a European page is a thousand, not one and a bit.
        t = t.replace(".", "")
    try:
        n = float(t)
    except ValueError:
        return None
    return n if 0 <= n <= PRICE_MAX else None


#: Each source's (most often, least often, default), in minutes.
_MINUTES = {
    "email": (EMAIL_MINUTES, MAX_MINUTES, EMAIL_MINUTES),
    "home": (HOME_MINUTES, MAX_MINUTES, HOME_MINUTES),
    "page": (PAGE_MINUTES, PAGE_MAX_MINUTES, PAGE_MINUTES),
    "price": (PAGE_MINUTES, PAGE_MAX_MINUTES, PRICE_MINUTES),
    "search": (SEARCH_MINUTES, SEARCH_MAX_MINUTES, SEARCH_DEFAULT_MINUTES),
    "github": (GITHUB_MINUTES, GITHUB_MAX_MINUTES, GITHUB_MINUTES),
}


def check_rule(rule, now: float) -> dict:
    """This kind's own rule check (register_kind(check=...)): every N minutes
    from a start, with an end and the watch. The generic check_rule refuses
    minutes, so no other kind can look this often."""
    if not isinstance(rule, dict):
        raise ValueError("a \"tell me when\" needs what to watch")
    watch = check_watch(rule.get("watch"))
    floor, ceiling, default = _MINUTES[watch["source"]]
    n = rule.get("minutes", default)
    if not isinstance(n, int) or isinstance(n, bool):
        raise ValueError("how often is a whole number of minutes")
    if n < floor:
        raise ValueError("the most often it can look is "
                         + S.rule_words({"every": "minutes", "minutes": floor}))
    if n > ceiling:
        raise ValueError("the least often it can look is "
                         + S.rule_words({"every": "minutes", "minutes": ceiling}))
    start = rule.get("start")
    if not isinstance(start, (int, float)) or isinstance(start, bool):
        start = now
    ends = rule.get("ends")
    if watch.get("missing"):
        # The watch runs to its time and one look after it - and waits up to
        # NO_REPLY_GRACE for a PC that was off then, so the owner is still
        # told (as missed) rather than never.
        by = float(watch["by"])
        if by <= now + n * 60:
            raise ValueError("that time is too soon - Jarvis could not look even once before "
                             "it")
        if by > days_later(now, MAX_DAYS) + 60:
            raise ValueError(f"a \"tell me when\" can run for up to {MAX_DAYS} days")
        ends = by + NO_REPLY_GRACE
    elif ends is None:
        ends = days_later(now, DEFAULT_DAYS)
    if not isinstance(ends, (int, float)) or isinstance(ends, bool):
        raise ValueError("the end is a time")
    ends = float(ends)
    if ends <= now + n * 60:
        raise ValueError("that ends before it could look even once")
    if ends > days_later(now, MAX_DAYS) + 60 + (NO_REPLY_GRACE if watch.get("missing") else 0):
        raise ValueError(f"a \"tell me when\" can run for up to {MAX_DAYS} days")
    return {"every": "minutes", "minutes": n, "start": float(start), "ends": ends,
            "watch": watch}


def days_later(now: float, days: int) -> float:
    """The same time on this PC's clock `days` days on - across a clock
    change, 12:00 stays 12:00."""
    lt = time.localtime(now)
    y, mo, d = S._add_days(lt.tm_year, lt.tm_mon, lt.tm_mday, int(days))
    return S.wall_to_epoch(y, mo, d, lt.tm_hour, lt.tm_min)


def what_words(watch: dict) -> str:
    """The job's words, in Coming up: "an email from Alex arrives", "the
    washing machine finishes", "sensor.washer is idle"."""
    if watch.get("source") == "email":
        if watch.get("missing"):
            return f"no email from {watch['sender']} by {S.long_date(float(watch['by']))}"
        return f"an email from {watch['sender']} arrives"
    if watch.get("source") == "page":
        return f"{watch['url']} changes"
    if watch.get("source") == "price":
        return f"the price on {watch['url']} drops below {money(watch['below'], watch)}"
    if watch.get("source") == "search":
        return f"a search for “{watch['words']}” shows something new"
    if watch.get("source") == "github":
        return _github_what(watch)
    subject = f"the {watch['name']}" if watch.get("name") else watch.get("entity", "")
    return f"{subject} {watch.get('say') or 'changes'}"


def money(n, watch: Optional[dict] = None) -> str:
    """25 -> "25", 24.5 -> "24.50", with the owner's currency sign if they
    said one ("£25")."""
    n = float(n)
    words = f"{n:,.0f}" if n == int(n) else f"{n:,.2f}"
    return f"{(watch or {}).get('currency') or ''}{words}"


def _branch_words(watch: dict) -> str:
    return f" (branch {watch['branch']})" if watch.get("branch") else ""


def _github_what(watch: dict) -> str:
    repo = watch["repo"]
    if watch["event"] == "pr_merged":
        return f"pull request #{watch['pr']} on {repo} is merged"
    verb = "fails" if watch["event"] == "ci_failed" else "finishes"
    return f"CI {verb} on {repo}{_branch_words(watch)}"


def alert_words(watch: dict, count: int = 1, st: Optional[dict] = None) -> str:
    """What the notification says - from the owner's words only. `st`: what
    this module kept for the watch (a price read, a CI or pull request
    outcome - numbers and fixed words chosen by code, never a page's or
    GitHub's own text)."""
    st = st or {}
    if watch.get("source") == "email":
        if watch.get("missing"):
            return (f"No email from {watch['sender']} arrived by "
                    f"{S.long_date(float(watch['by']))}.")
        if count > 1:
            return f"{count} emails from {watch['sender']} arrived."
        return f"An email from {watch['sender']} arrived."
    if watch.get("source") == "page":
        base = f"The page you're watching changed: {watch['url']}"
        last = str(_page_state_fields(st.get("last_state")).get("words") or "")
        return base + (" " + last if last else "")
    if watch.get("source") == "price":
        now = _price_of_state(st.get("last_state"))
        tail = f" It is now {money(now, watch)}." if now is not None else ""
        return (f"The price on {watch['url']} is below {money(watch['below'], watch)}."
                + tail)
    if watch.get("source") == "search":
        new = f"{count} new results" if count > 1 else "a new result"
        return f"Your search for “{watch['words']}” shows {new}."
    if watch.get("source") == "github":
        return _github_alert(watch, st.get("last_state"))
    subject = f"The {watch['name']}" if watch.get("name") else watch.get("entity", "")
    say = watch.get("say") or ""
    if say in PAST:
        return f"{subject} {PAST[say]}."
    if say.startswith("is "):
        return f"{subject} is now {say[3:]}."
    return f"{subject} changed."


def _end_words(ends: float, now: float) -> str:
    return f"{S.long_date(ends)} ({_left_words(ends - now)})"


def _left_words(seconds: float) -> str:
    days = seconds / 86400.0
    if days >= 1.5:
        return f"{int(round(days))} days"
    hours = seconds / 3600.0
    if hours >= 1.5:
        return f"{int(round(hours))} hours"
    return S.length_words(max(60.0, round(seconds / 60.0) * 60.0))


# --------------------------------------------------------------------------
#   The card - ONE, listing exactly what is watched
# --------------------------------------------------------------------------

def card(rule: dict, text: str, now: float) -> str:
    w = rule["watch"]
    n = rule["minutes"]
    every = S.rule_words(rule)
    lines = [f"Set up \"{TITLE}\".", ""]
    if w["source"] == "email":
        try:
            import jarvis_email as MAIL
            p = MAIL.plan(1, unread_only=False)
            where = f"{p.host}:{p.port}, mailbox \"{p.mailbox}\"" if p.configured \
                else "(no mail server is set up)"
        except Exception:
            where = "your mail server"
        if w.get("missing"):
            lines += [
                f"Watching for: an email from {w['sender']}, until "
                f"{S.long_date(float(w['by']))}. If none has arrived by then, Jarvis tells "
                "you. If one arrives first, the watch ends quietly.",
            ]
        else:
            lines += [f"Watching for: an email from {w['sender']}."]
        lines += [
            f"How: {every}, Jarvis signs in to your mail server ({where}) and reads only "
            "the From line of mail that arrived since it last looked - with PEEK, so nothing "
            "is marked as read. No subject, no text and no attachment is read, and nothing "
            "goes to the AI model.",
            "Instantly, too: while Jarvis is running and not on standby, it keeps one "
            "connection open to that server, which tells it the moment new mail arrives "
            "(IMAP IDLE); it then reads the From line straight away, the same way. That "
            "connection closes when Jarvis goes on standby or you press Stop everything, "
            f"and if it drops, the looks {every} carry on.",
            f"It matches when the sender's name or address has \"{w['sender']}\" in it, as "
            "whole words. Your words stay on this PC: they are not sent to the mail server.",
        ]
    elif w["source"] == "page":
        lines += [
            f"Watching for: {w['url']} - when its text changes.",
            f"How: {every}, Jarvis fetches that address (a plain GET, never a link on the "
            "page - it never follows anything else there) and compares a short fingerprint "
            "of its words, with timestamps, view counts, session nonces, tracking parameters "
            "and the site's own chrome stripped out first, plus every price (in whole cents), "
            "every version tag and the stock state read by plain code. It tells you what "
            "changed - a price, a version, a stock state - or that the text changed. The "
            "page's actual words are never shown, kept, or sent to the AI model; only the "
            "fingerprint and those short facts are kept.",
            "Refused if that address turns out to lead to this PC or a private network "
            "address, checked again on every look (never only when you add it), so a web "
            "address can never become a way to reach your own network.",
        ]
    elif w["source"] == "price":
        lines += [
            f"Watching for: the price on {w['url']} - when it drops below "
            f"{money(w['below'], w)}.",
            f"How: {every}, Jarvis fetches that address (a plain GET, never a link on the "
            "page) and reads the price with plain code, never the AI model: the price the "
            "page marks for shops' machines (schema.org), or else the first price shown on the "
            "page. Only that number is kept. It never buys anything and never presses "
            "anything on the page.",
            "It tells you when the price it reads is below that - straight away, if it "
            "already is at the first look. The number is shown under the watch after each "
            "look, so you can check Jarvis read the right one.",
            "Refused if that address turns out to lead to this PC or a private network "
            "address, checked again on every look.",
        ]
    elif w["source"] == "search":
        lines += _search_card_lines(w, every)
    elif w["source"] == "github":
        lines += _github_card_lines(w, every)
    else:
        try:
            import jarvis_home as HOME
            p = HOME.plan_states([w["entity"]])
            url = p.queries[0].url if p.queries else "(Home Assistant is not set up)"
        except Exception:
            url = "your Home Assistant"
        named = f"the {w['name']} ({w['entity']})" if w.get("name") else w["entity"]
        lines += [
            f"Watching for: {named} - when it {w['say']}.",
            f"How: {every}, Jarvis reads that one device's state from your Home Assistant: "
            f"GET {url}. Nothing in your home is changed.",
            "It matches when the state CHANGES to: " + ", ".join(w["states"]) + ".",
        ]
    if w.get("missing"):
        until = ("Until: " + _end_words(float(w["by"]), now) + ". If the PC is off then, it "
                 "tells you when it is next on, up to a day later, marked as missed.")
    else:
        until = ("Until: " + _end_words(float(rule["ends"]), now)
                 + (", or the first time it happens - whichever comes first." if w["once"]
                    else ". It tells you every time it happens until then."))
    lines += [
        until,
        ("Urgent: yes. Your phone rings and vibrates until you look, and the PC plays an "
         "alarm sound until you dismiss it." if w["urgent"] else
         "Urgent: no. An ordinary notification on both apps."),
        "",
        f"When it happens, Jarvis only tells you: \"{alert_words(w)}\" It never replies, never "
        "acts, and never opens or reads out the email or anything else.",
        f"A locked phone shows only: \"{LOCK_SCREEN}\"",
        "",
        "It runs on this PC, by this PC's clock. Each look is a request to "
        + {"email": "your own mail server", "home": "your own Home Assistant",
           "page": "that one address on the internet",
           "price": "that one address on the internet",
           "search": "the web search service you chose",
           "github": "GitHub (api.github.com)"}[w["source"]]
        + (", under the same settings as asking Jarvis to read it"
           if w["source"] in ("email", "home") else "")
        + "; the notification goes only to your own apps. Nothing else is sent anywhere.",
        "If a look cannot happen (a server down, a setting changed), Jarvis tells you once, "
        f"not at every look, and at most every {BROKEN_AGAIN_HOURS} hours after that while it "
        "stays that way.",
        "Stopping or deleting it is immediate, from either app.",
        "",
        "If you say no: nothing is set up, and nothing is watched.",
    ]
    return "\n".join(lines)


def _search_card_lines(w: dict, every: str) -> list:
    try:
        import jarvis_search as WS
        s = WS.settings()
        provider = s.get("provider")
        label = WS.name(provider or "")
        p = WS.plan(w["words"], s=s)
        if provider == "searxng":
            where = (f"your SearXNG at {p.searxng_url or WS.DEFAULT_SEARXNG_URL}, which asks "
                     "several search engines for you - they see the words and your internet "
                     "address")
        elif provider == "duckduckgo":
            where = f"DuckDuckGo ({p.host}), which sees them and your internet address"
        elif provider in WS.NEEDS_KEY:
            where = (f"{label} ({p.host}), with your {label} key - so {label} knows the "
                     f"search is yours. The key goes to {p.host} only")
            if provider == "brave":
                where += (". Brave charges your payment card past its free monthly credit, "
                          "so this watch can cost money")
            elif provider == "deepseek":
                where += (". DeepSeek charges $0.75 for 1,000 searches, so a watch that "
                          "runs often costs money - a search that finds nothing is not "
                          "charged")
        else:
            where = label
    except Exception:
        label, where = "the web search you chose", "the web search you chose in Settings"
    return [
        f"Watching for: new results when Jarvis searches the web for “{w['words']}”.",
        f"How: {every}, Jarvis searches for exactly those words with {label} - the web search "
        f"you chose in Settings - the same way as when you ask it. What leaves this PC: those "
        f"words, and nothing else, to {where}.",
        "It compares the addresses of the results (up to 5) with the ones it has seen before, "
        "and keeps only a short fingerprint of each address - never the titles, text or the "
        "addresses themselves. The results are outside text: never learned from, never acted "
        "on, and never sent to the AI model.",
        "The first look only notes what is there now. If you choose another web search later, "
        "the watch uses that one from then on (and starts afresh); it never switches by "
        "itself - if the search service is down, it says so under the watch and tells you.",
    ]


def _github_card_lines(w: dict, every: str) -> list:
    keyed = bool(_env(GITHUB_TOKEN_ENV))
    if w["event"] == "pr_merged":
        what = (f"Watching for: pull request #{w['pr']} on {w['repo']} - when it is merged "
                "(or closed without being merged, which Jarvis tells you too, and then stops).")
    elif w["event"] == "ci_failed":
        what = (f"Watching for: CI (GitHub Actions) on {w['repo']}"
                + (f", branch {w['branch']}" if w.get("branch") else ", any branch")
                + " - when a run for the newest commit fails.")
    else:
        what = (f"Watching for: CI (GitHub Actions) on {w['repo']}"
                + (f", branch {w['branch']}" if w.get("branch") else ", any branch")
                + " - when every run for the newest commit has finished (it says whether they "
                  "passed or something failed).")
    return [
        what,
        f"How: {every}, Jarvis asks GitHub one read-only question: GET {github_url(w)}. "
        "Nothing on GitHub is changed, and nothing goes to the AI model.",
        ("Your GitHub key (saved on this PC for GitHub research) goes with each request, to "
         "api.github.com only - never anywhere else, never written down, never shown."
         if keyed else
         "No GitHub key is set on this PC, so only public repositories can be seen, and GitHub "
         "allows 60 looks an hour between all of them."),
    ]


# --------------------------------------------------------------------------
#   What this module keeps: where each watch has got to
# --------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tellme (
    id          TEXT PRIMARY KEY,
    base_uid    INTEGER,
    uidvalidity INTEGER,
    last_state  TEXT,
    looked_at   REAL,
    look_said   TEXT NOT NULL DEFAULT '',
    matched_at  REAL,
    matched_n   INTEGER NOT NULL DEFAULT 0,
    alert_count INTEGER NOT NULL DEFAULT 0
);
"""
#: Added 2026-09-28, for a watch that breaks - added to an older table in
#: place (ALTER TABLE), so a PC that had watches keeps them. The kind of
#: problem (the "Could not look" sentence without its bracketed detail),
#: when it started, how many looks in a row, and when the owner was told.
_BROKEN_COLUMNS = (("broken_kind", "TEXT"), ("broken_since", "REAL"),
                   ("broken_n", "INTEGER NOT NULL DEFAULT 0"), ("broken_told", "REAL"))
_KEYS = ("base_uid", "uidvalidity", "last_state", "looked_at", "look_said", "matched_at",
         "matched_n", "alert_count") + tuple(n for n, _t in _BROKEN_COLUMNS)
_LOCK = threading.RLock()


def _db(sched=None):
    import sqlite3
    path = (sched or _sched()).path
    c = sqlite3.connect(path, timeout=30)
    c.row_factory = sqlite3.Row
    c.executescript(_SCHEMA)
    have = {r["name"] for r in c.execute("PRAGMA table_info(tellme)").fetchall()}
    for name, typ in _BROKEN_COLUMNS:
        if name not in have:
            try:
                c.execute(f"ALTER TABLE tellme ADD COLUMN {name} {typ}")
            except sqlite3.OperationalError:
                pass    # another process added it a moment ago
    return c


def _state(job_id: str, sched=None) -> dict:
    with _LOCK:
        c = _db(sched)
        try:
            r = c.execute("SELECT * FROM tellme WHERE id = ?", (job_id,)).fetchone()
            return dict(r) if r is not None else {}
        finally:
            c.close()


def _save(job_id: str, sched=None, **fields) -> None:
    with _LOCK:
        c = _db(sched)
        try:
            c.execute("INSERT OR IGNORE INTO tellme (id) VALUES (?)", (job_id,))
            for key, value in fields.items():
                if key not in _KEYS:
                    raise KeyError(key)
                c.execute(f"UPDATE tellme SET {key} = ? WHERE id = ?", (value, job_id))
            c.commit()
        finally:
            c.close()


def _tidy(sched) -> None:
    """Forget where watches that are gone had got to (deleted, or over for
    more than a day - the scheduler removes those)."""
    with _LOCK:
        c = _db(sched)
        try:
            c.execute("DELETE FROM tellme WHERE id NOT IN (SELECT id FROM jobs)")
            c.commit()
        except Exception:
            pass
        finally:
            c.close()


def _watch_of(job_id: str, sched) -> tuple:
    """(row, rule, watch) of a tellme job, straight from schedule.db."""
    with sched._lock, sched._db() as c:
        row = sched._row(c, job_id)
    if row is None or row["kind"] != KIND or not row["rule"]:
        return None, None, None
    rule = json.loads(row["rule"])
    return row, rule, rule.get("watch") or {}


# --------------------------------------------------------------------------
#   Looking
# --------------------------------------------------------------------------

def _ok_to_read(action: str, what: str, text: str, deps: Deps) -> bool:
    """The same gate every read of the owner's accounts goes through - and
    only a yes without a person counts here (nobody is asked every minute)."""
    if deps.tier_of(action) != "auto":
        return False
    try:
        v = deps.gate(action, {"text": text, "for": "tell me when", "what": what}, text)
    except Exception:
        return False
    return getattr(v, "allowed", False) is True and getattr(v, "tier", "auto") == "auto"


def _words(s: str) -> list:
    return [w for w in re.split(r"[^\w]+", s.casefold()) if w]


def sender_matches(watched: str, raw_from) -> bool:
    """Does one From header name the sender the owner asked about? An
    address is compared whole; a name matches when every one of its words
    is a whole word of the sender's display name or address - "Alex" finds
    "Alex Smith <a.smith@x.com>" and "alex@x.com", never "alexandra@x.com".
    Read on this PC only; never shown."""
    from email.utils import getaddresses
    import email as _email
    try:
        import jarvis_email as MAIL
        decode = MAIL._decode
    except Exception:
        def decode(v):
            return str(v or "")
    if isinstance(raw_from, bytes):
        try:
            value = _email.message_from_bytes(raw_from).get("From") or ""
        except Exception:
            return False
    else:
        value = str(raw_from or "")
    try:
        pairs = getaddresses([str(value)[:2000]])
    except Exception:
        return False
    want = watched.strip().casefold()
    want_words = [w for w in _words(want) if w not in ("the", "my")]
    for name, addr in pairs:
        addr = decode(addr).strip().casefold()
        if "@" in want:
            if addr == want:
                return True
            continue
        have = set(_words(decode(name))) | set(_words(addr))
        if want_words and all(w in have for w in want_words):
            return True
    return False


def _resp(conn, code: str) -> Optional[int]:
    try:
        _typ, data = conn.response(code)
        v = data[-1] if data else None
        if isinstance(v, bytes):
            v = v.decode("ascii", "replace")
        return int(str(v).strip()) if v not in (None, "") else None
    except Exception:
        return None


def _default_email_look(p, base_uid: Optional[int], uidvalidity: Optional[int]) -> dict:
    """ONE connection, read-only. The first look (no base) only notes where
    the mailbox is; later looks read the From line of mail that arrived
    since. Credentials read fresh - the environment, or (ease-of-use audit
    row 15) Windows Credential Manager - never kept."""
    import imaplib
    import jarvis_email as MAIL
    user = MAIL.imap_user()
    password = MAIL.imap_password()
    # The certificate is checked (jarvis_email.tls_context): imaplib alone
    # would hand the password to whoever answered.
    conn = imaplib.IMAP4_SSL(p.host, p.port, timeout=20.0, ssl_context=MAIL.tls_context(p.host))
    try:
        conn.login(user, password)
        typ, _ = conn.select(p.mailbox, readonly=True)
        if typ != "OK":
            raise RuntimeError("EXAMINE failed")
        uv = _resp(conn, "UIDVALIDITY")
        nxt = _resp(conn, "UIDNEXT")
        if base_uid is None or uv != uidvalidity:
            if nxt is None:
                typ, data = conn.uid("SEARCH", "ALL")
                ids = [int(x) for x in (data[0] or b"").split() if x.isdigit()] \
                    if typ == "OK" and data else []
                nxt = (max(ids) + 1) if ids else 1
            return {"uidvalidity": uv, "base": int(nxt) - 1, "new": [], "fresh": True}
        typ, data = conn.uid("SEARCH", "UID", f"{int(base_uid) + 1}:*")
        if typ != "OK":
            raise RuntimeError("SEARCH failed")
        # "n:*" always answers the newest message, even an older one:
        # only UIDs above the base are new.
        uids = sorted(int(x) for x in (data[0] or b"").split()
                      if x.isdigit() and int(x) > int(base_uid))
        heads = []
        take = uids[-MAX_NEW:]
        if take:
            typ, got = conn.uid("FETCH", ",".join(str(u) for u in take), SENDER_FETCH)
            if typ == "OK":
                for part in got or []:
                    if isinstance(part, tuple) and len(part) > 1 and isinstance(part[1], bytes):
                        heads.append(part[1])
        return {"uidvalidity": uv, "base": uids[-1] if uids else int(base_uid), "new": heads}
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            conn.logout()
        except Exception:
            pass


def _look_email(job_id: str, watch: dict, st: dict, deps: Deps, sched) -> tuple:
    """(how many matched, the sentence for Coming up)."""
    import jarvis_email as MAIL
    p = MAIL.plan(1, unread_only=False)
    if not p.configured:
        return 0, "Could not look: email's settings on this PC need a look."
    text = (f"Jarvis would like to look for new mail in the \"{p.mailbox}\" mailbox on "
            f"{p.host}:{p.port} for a \"tell me when\": one connection, the From line only of "
            "mail that arrived since the last look, with PEEK - no subject or text is read.")
    if not _ok_to_read(EMAIL_ACTION, "look for an email from a named sender", text, deps):
        return 0, ("Could not look: your settings ask for a yes each time Jarvis reads "
                   "email.")
    look = deps.email_look or _default_email_look
    try:
        out = look(p, st.get("base_uid"), st.get("uidvalidity"))
    except Exception as exc:
        return 0, f"Could not look: the mail server did not answer ({type(exc).__name__})."
    base = out.get("base")
    _save(job_id, sched, base_uid=int(base) if base is not None else None,
          uidvalidity=out.get("uidvalidity"))
    n = sum(1 for h in (out.get("new") or []) if sender_matches(watch["sender"], h))
    return n, ""


def _look_home(job_id: str, watch: dict, st: dict, deps: Deps, sched) -> tuple:
    import jarvis_home as HOME
    p = HOME.plan_states([watch["entity"]])
    if p.reason_empty:
        return 0, "Could not look: Home Assistant's settings on this PC need a look."
    text = HOME.describe(p)
    if not _ok_to_read(HOME_ACTION, "look at one device for a \"tell me when\"", text, deps):
        return 0, ("Could not look: your settings ask for a yes each time Jarvis reads "
                   "Home Assistant.")
    out = HOME.run(p, fetch=deps.home_fetch, approved=True)
    if not out.get("ok"):
        if _not_found(out):
            return 0, "Could not look: Home Assistant says there is no such device."
        return 0, "Could not look: Home Assistant did not answer."
    raw = str((out.get("states") or [{}])[0].get("state") or "").strip().lower()
    if not _TOKEN.fullmatch(raw) or raw in _NOT_A_STATE:
        # Home Assistant cannot see it right now (restarting): not a change,
        # and not the new "before".
        return 0, ""
    before = st.get("last_state")
    _save(job_id, sched, last_state=raw)
    if before is None:
        return 0, ""
    wanted = set(watch.get("states") or [])
    return (1 if (raw in wanted and before not in wanted) else 0), ""


class _PageRedirect(urllib.request.HTTPRedirectHandler):
    """Refuses to follow a redirect anywhere the private-address check would
    refuse in the first place (a page could otherwise send Jarvis on to an
    address on the home network after the check already passed)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        import jarvis_local_http as LH
        problem = LH.private_fetch_problem(newurl)
        if problem:
            raise urllib.error.HTTPError(
                req.full_url, code,
                f"refused to follow a redirect to {newurl}: {problem}", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


#: What a page's fingerprint is taken over. "t1": the page's VISIBLE words
#: (see _visible_text). Before 2026-09-27 it was the raw bytes of the page,
#: with no prefix - and most pages change a few hidden bytes on every load
#: (security tokens, ad ids, script timestamps), so a page nobody changed
#: could match on every look. A fingerprint in the old form is re-recorded
#: once, silently, rather than compared (see _look_page).
#:
#: "t3:" is what a look keeps now (Pillar 26, 2026-10-17; Blueprint C of
#: Volume III; t3 on 2026-10-21 when the snapshot learned to read the price
#: and stock a page marks for MACHINES): a JSON snapshot of the signals
#: `extract_watch_signals` reads - the hash of the noise-stripped words,
#: every price in whole cents (machine-marked first), every version tag, a
#: three-state stock state - plus the last real change's plain words and the
#: last good look's time (see the Pillar 26 section below). Both older kinds
#: are still recognised so an upgraded PC re-records once, silently - and
#: that is exactly why the kind changed: a JSON-LD price the old reader could
#: not see must not ring the owner as a "price change" on the first look
#: after the upgrade; the look records a new baseline instead.
PAGE_PRINT = "t1:"
PAGE_STATE = "t3:"
#: The watermark rule: `diff_watch_snapshot` returns this instead of words
#: when the page differs only in dynamic noise, so a look cannot ring for it.
PAGE_SILENT = "[SILENT]"

#: Elements whose contents a reader never sees. Their text is left out of
#: the fingerprint (the same list changedetection.io strips before it
#: compares a page - the approach, not its code).
_UNSEEN_TAGS = frozenset({"head", "script", "style", "noscript", "template",
                          "svg", "iframe", "object", "canvas"})


def _visible_text(body: bytes, content_type: str = "") -> str:
    """The words a person would see on the page, as one line with single
    spaces. HTML is read with the standard library's own parser - one fresh
    parser per call, so the watch threads never share one. Anything that is
    not HTML is taken as plain text. Used only to take the fingerprint: the
    words are never kept, returned to a caller outside this module, or shown."""
    import html.parser
    charset = "utf-8"
    m = re.search(r"charset=([\w.-]+)", content_type or "", re.I)
    if m:
        charset = m.group(1)
    try:
        text = body.decode(charset, errors="replace")
    except LookupError:
        text = body.decode("utf-8", errors="replace")
    looks_html = ("html" in (content_type or "").lower()
                  or re.search(r"<\s*(html|body|div|p|span|head)\b", text[:4096], re.I))
    if not looks_html:
        return " ".join(text.split())

    class _Words(html.parser.HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.hidden = 0
            self.words = []

        def handle_starttag(self, tag, attrs):
            if tag in _UNSEEN_TAGS:
                self.hidden += 1

        def handle_startendtag(self, tag, attrs):
            pass  # <br/>, <img/>: nothing is opened, so nothing to close

        def handle_endtag(self, tag):
            if tag in _UNSEEN_TAGS and self.hidden:
                self.hidden -= 1

        def handle_data(self, data):
            if not self.hidden:
                self.words.append(data)

    p = _Words()
    try:
        p.feed(text)
        p.close()
    except Exception:
        # A page too broken to read as HTML: its plain text still gives a
        # steadier fingerprint than its bytes.
        return " ".join(re.sub(r"<[^>]*>", " ", text).split())
    return " ".join(" ".join(p.words).split())


def _page_print(body: bytes, content_type: str = "") -> str:
    """The fingerprint _look_page compares: PAGE_PRINT plus a hash of the
    page's visible words."""
    import hashlib
    words = _visible_text(body[:PAGE_MAX_BYTES], content_type)
    return PAGE_PRINT + hashlib.sha256(words.encode("utf-8")).hexdigest()


def _default_page_fetch(url: str) -> str:
    """ONE GET, through jarvis_local_http.public_urlopen (never a proxy, and
    the private-address check made again on the connection itself), a
    redirect followed only where the check above would allow it,
    the body capped at PAGE_MAX_BYTES. Returns the page's current SNAPSHOT
    (_page_state): the signals extract_watch_signals() read from its
    noise-stripped words, prices in whole cents, versions and stock. The
    bytes and the words themselves are never kept or returned."""
    import jarvis_local_http as LH
    req = urllib.request.Request(url, headers={"User-Agent": "Jarvis (tell me when this page "
                                                              "changes)"})
    # public_urlopen: the private-address check is made again on the
    # connection itself (DNS rebinding between _look_page's check and this
    # connect - the security/privacy audit of 2026-09-27).
    with LH.public_urlopen(req, PAGE_TIMEOUT, _PageRedirect()) as resp:
        body = resp.read(PAGE_MAX_BYTES + 1)
        content_type = resp.headers.get("Content-Type", "") if resp.headers else ""
    return _page_state(body, content_type)


def _print_kind(digest: str) -> str:
    """"t2:" for a current page snapshot, "t1:" for the pre-Pillar-26
    fingerprint of the visible words, "" for the oldest kind (raw bytes)."""
    if not isinstance(digest, str):
        return ""
    if digest.startswith(PAGE_STATE):
        return PAGE_STATE
    return PAGE_PRINT if digest.startswith(PAGE_PRINT) else ""


def _look_page(job_id: str, watch: dict, st: dict, deps: Deps, sched) -> tuple:
    """(how many matched, the sentence for Coming up). Checked again here,
    immediately before the GET, not only when the watch was added: DNS can
    answer differently later (see jarvis_local_http.private_fetch_problem's
    own docstring)."""
    import jarvis_local_http as LH
    url = watch["url"]
    problem = LH.private_fetch_problem(url)
    if problem:
        return 0, f"Could not look: {problem}"
    text = (f"Jarvis would like to fetch {url} for a \"tell me when\": one plain GET, to see "
            "what changed since the look before - the page's price, version and stock state "
            "read by plain code, and a fingerprint of its words with timestamps, session "
            "nonces, view counts and site chrome stripped out first. Never a link on the page, "
            "and the page's own words are never read out, kept, or shown.")
    if not _ok_to_read(PAGE_ACTION, "fetch a web page for a \"tell me when\"", text, deps):
        return 0, ("Could not look: your settings ask for a yes each time Jarvis fetches a "
                   "web page.")
    fetch = deps.page_fetch or _default_page_fetch
    try:
        digest = fetch(url)
    except Exception as exc:
        # A failed look changes nothing: the last-known-good snapshot stays,
        # and the owner is told once through the broken-watch notice.
        return 0, f"Could not look: the page did not answer ({type(exc).__name__})."
    if digest is None:
        return 0, "Could not look: the page did not answer."
    now = sched.now()
    before = st.get("last_state")
    if before is None or _print_kind(before) != _print_kind(digest):
        # The first look, or a snapshot recorded by an older Jarvis (raw
        # bytes, or the pre-Pillar-26 visible-words fingerprint): the two
        # cannot be compared, so this look only records the new kind - a page
        # nobody changed must not match once just because Jarvis was updated.
        fields = _page_state_fields(digest)
        if _print_kind(digest) == PAGE_STATE:
            fields["last_good_at"] = now
            _save(job_id, sched, last_state=_page_state_text(fields))
        else:
            _save(job_id, sched, last_state=digest)
        return 0, ""
    if _print_kind(digest) == PAGE_STATE:
        old, new = _page_state_fields(before), _page_state_fields(digest)
        delta = diff_watch_snapshot(old, new)
        fields = dict(new)
        fields["last_good_at"] = now
        # Keep the last REAL change's words, so the app can still say what
        # changed when it reads the alert after a later quiet look.
        fields["words"] = (delta["status"] if delta["changed"]
                           else (old.get("words") or ""))
        _save(job_id, sched, last_state=_page_state_text(fields))
        if delta["changed"]:
            _latch_page_watch()
            return 1, ""
        return 0, ""
    _save(job_id, sched, last_state=digest)
    return (1 if digest != before else 0), ""


# --------------------------------------------------------------------------
#   "Tell me when the price on <url> drops below X" (2026-09-28)
# --------------------------------------------------------------------------

#: A JSON-LD block (schema.org, what shops mark up for search engines).
_LD_JSON = re.compile(r"<script\b[^>]*type\s*=\s*[\"']?application/ld\+json[^>]*>(.*?)</script>",
                      re.IGNORECASE | re.DOTALL)
_META = re.compile(r"<meta\b[^>]{0,500}>", re.IGNORECASE)
_ATTR = r"\b{name}\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'>]+))"
_META_PRICE = ("price", "product:price:amount", "og:price:amount")
#: A price shown on the page: a currency sign before or after a number.
_SHOWN_PRICE = re.compile(
    r"(?:[£$€]|US\$)\s?(?P<a>\d[\d.,']{0,15}\d|\d)"
    r"|(?P<b>\d[\d.,']{0,15}\d|\d)\s?(?:€|EUR\b|GBP\b|USD\b)", re.IGNORECASE)
_OFFER_TYPES = ("Offer", "AggregateOffer", "PriceSpecification", "UnitPriceSpecification",
                "CompoundPriceSpecification")


def _decode_body(body: bytes, content_type: str = "") -> str:
    charset = "utf-8"
    m = re.search(r"charset=([\w.-]+)", content_type or "", re.I)
    if m:
        charset = m.group(1)
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _attr(tag: str, name: str) -> str:
    m = re.search(_ATTR.format(name=re.escape(name)), tag, re.IGNORECASE)
    if not m:
        return ""
    import html as _html
    return _html.unescape(next(g for g in m.groups() if g is not None)).strip()


def _as_price(v) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        n = float(v)
    elif isinstance(v, str):
        n = parse_number(v)
    else:
        return None
    return n if n is not None and 0 < n <= PRICE_MAX else None


def _ld_price(node, depth: int = 0) -> Optional[float]:
    """The first offer's price in a JSON-LD document - or None."""
    if depth > 8:
        return None
    if isinstance(node, list):
        for x in node[:50]:
            p = _ld_price(x, depth + 1)
            if p is not None:
                return p
        return None
    if not isinstance(node, dict):
        return None
    t = node.get("@type")
    types = [str(x) for x in (t if isinstance(t, list) else [t])]
    if any(x in _OFFER_TYPES for x in types):
        for key in ("price", "lowPrice"):
            p = _as_price(node.get(key))
            if p is not None:
                return p
    for key in ("offers", "@graph", "mainEntity", "priceSpecification", "itemOffered"):
        if key in node:
            p = _ld_price(node[key], depth + 1)
            if p is not None:
                return p
    return None


def price_of(body: bytes, content_type: str = "") -> Optional[float]:
    """The price on a page, read by plain code - never the AI model. First
    the price the page marks for machines (schema.org JSON-LD, then a price
    <meta> tag), else the first price SHOWN on the page (a currency sign
    beside a number, in its visible words). None when there is none."""
    body = body[:PAGE_MAX_BYTES]
    text = _decode_body(body, content_type)
    for m in _LD_JSON.finditer(text):
        try:
            doc = json.loads(m.group(1).strip())
        except ValueError:
            continue
        p = _ld_price(doc)
        if p is not None:
            return p
    for m in _META.finditer(text):
        tag = m.group(0)
        name = (_attr(tag, "itemprop") or _attr(tag, "property") or _attr(tag, "name")).lower()
        if name in _META_PRICE:
            p = _as_price(_attr(tag, "content"))
            if p is not None:
                return p
    m = _SHOWN_PRICE.search(_visible_text(body, content_type))
    if m:
        return _as_price(m.group("a") or m.group("b"))
    return None


def _page_get(url: str, agent: str) -> tuple:
    """(body bytes, Content-Type): ONE GET, the same way as _default_page_fetch
    (jarvis_local_http.public_urlopen, _PageRedirect, capped)."""
    import jarvis_local_http as LH
    req = urllib.request.Request(url, headers={"User-Agent": agent})
    with LH.public_urlopen(req, PAGE_TIMEOUT, _PageRedirect()) as resp:
        body = resp.read(PAGE_MAX_BYTES + 1)
        content_type = resp.headers.get("Content-Type", "") if resp.headers else ""
    return body[:PAGE_MAX_BYTES], content_type


def _default_price_fetch(url: str) -> Optional[float]:
    body, content_type = _page_get(url, "Jarvis (tell me when a price drops)")
    return price_of(body, content_type)


# --------------------------------------------------------------------------
#   Fetch hygiene for the price radar (Slice 1, 2026-10-21): an address
#   canonicaliser, a coherent browser-header builder and a jittered
#   scheduling helper. Zero dependencies, no state, deterministic. They are
#   exported for the radar's own fetch/schedule path (Slice 2) and are not
#   wired into the existing watch path - see each docstring for why.
# --------------------------------------------------------------------------

#: Query parameters that only say WHERE a click came from. Removed by
#: `canonicalize_watch_url`; product-identifying ones (id, sku, model, pid,
#: variant, ...) are never touched.
_TRACKING_QUERY_EXACT = frozenset({
    "gclid", "fbclid", "msclkid", "mc_eid", "_ga", "ref", "tag",
    "ascsubtag", "psc",
})
_TRACKING_QUERY_PREFIXES = ("utm_", "ref_", "pf_rd_", "pd_rd_")


def canonicalize_watch_url(url: str) -> str:
    """The same product page with click-tracking taken out.

    Removes utm_*, gclid, fbclid, msclkid, mc_eid, _ga, ref, ref_*, tag,
    ascsubtag, psc, pf_rd_* and pd_rd_* from the QUERY only: the scheme, host
    and path stay exactly as given, the fragment is kept, and every other
    parameter - including the ones that identify the product (id, sku, model,
    pid, variant) - stays in its original order. Idempotent. An empty value,
    or one with no scheme and host, is returned unchanged: there is no
    address to canonicalise.

    NOT wired into the stored watch addresses yet, on purpose: a watch made
    before this existed must not silently change its address. Slice 2
    canonicalises at the moment a watch is created."""
    text = str(url or "").strip()
    if not text:
        return ""
    import urllib.parse as up
    try:
        parts = up.urlsplit(text)
    except ValueError:
        return text
    if not parts.scheme or not parts.netloc:
        return text
    kept = []
    dropped = False
    for key, value in up.parse_qsl(parts.query, keep_blank_values=True):
        lower = key.lower()
        if lower in _TRACKING_QUERY_EXACT or any(
                lower.startswith(prefix) for prefix in _TRACKING_QUERY_PREFIXES):
            dropped = True
            continue
        kept.append((key, value))
    if not dropped:
        return text
    query = up.urlencode(kept, doseq=True, safe="*,:;@/?")
    return up.urlunsplit((parts.scheme, parts.netloc, parts.path, query,
                          parts.fragment))


#: Browser header profiles for the radar's future fetcher (Slice 2). Each
#: profile is ONE real browser and every header in it agrees with that
#: browser's own User-Agent: a client-hint platform matches the UA (Windows
#: Chrome/Edge say "Windows", the macOS ones "macOS", the Android one
#: "Android"), the mobile hint matches the UA, Sec-Fetch-* describe the same
#: kind of request, and Accept-Language is one a real browser sends. Firefox,
#: Safari and iOS browsers send NO Sec-CH-UA at all, and those profiles have
#: none - that is the coherent shape, not a gap.
_HEADER_PROFILES = (
    {  # 0: Windows Chrome
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"),
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "image/avif,image/webp,*/*;q=0.8"),
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-CH-UA": ('"Chromium";v="141", "Google Chrome";v="141", '
                      '"Not?A_Brand";v="24"'),
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    },
    {  # 1: Windows Edge
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0"),
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "image/avif,image/webp,*/*;q=0.8"),
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-CH-UA": ('"Chromium";v="141", "Microsoft Edge";v="141", '
                      '"Not?A_Brand";v="24"'),
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    },
    {  # 2: macOS Safari (no client hints)
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"),
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Upgrade-Insecure-Requests": "1",
    },
    {  # 3: macOS Chrome
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 "
                       "Safari/537.36"),
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "image/avif,image/webp,*/*;q=0.8"),
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-CH-UA": ('"Chromium";v="141", "Google Chrome";v="141", '
                      '"Not?A_Brand";v="24"'),
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": '"macOS"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    },
    {  # 4: Windows Firefox (no client hints)
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) "
                       "Gecko/20100101 Firefox/131.0"),
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "image/avif,image/webp,*/*;q=0.8"),
        "Accept-Language": "en-US,en;q=0.5",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    },
    {  # 5: iOS Safari (no client hints)
        "User-Agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
                       "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
                       "Mobile/15E148 Safari/604.1"),
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Upgrade-Insecure-Requests": "1",
    },
    {  # 6: Android Chrome
        "User-Agent": ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36"),
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "image/avif,image/webp,*/*;q=0.8"),
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-CH-UA": ('"Chromium";v="141", "Google Chrome";v="141", '
                      '"Not?A_Brand";v="24"'),
        "Sec-CH-UA-Mobile": "?1",
        "Sec-CH-UA-Platform": '"Android"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Upgrade-Insecure-Requests": "1",
    },
)
#: Headers this builder must NEVER emit: they would carry the owner's
#: cookies, or revalidate a page they hold cached (a first look has neither).
_NEVER_SENT = ("Cookie", "If-None-Match", "If-Modified-Since")
#: The one referrer a price comparison may send: a search result, never the
#: owner's own page or a previous private page.
_REFERER_MODES = {"": "", "search_comparison": "https://www.google.com/"}


def build_decoupled_headers(persona_index=None, referer_mode: str = "") -> dict:
    """A browser-coherent header set for ONE outbound page GET (Slice 2 uses
    it; the existing fetchers keep this project's own Jarvis identity on
    purpose, so no second builder is in use anywhere yet).

    `persona_index` picks a profile deterministically (None = 0; any int is
    taken modulo the number of profiles, so callers can pass a stable job id).
    `referer_mode` is "" (no Referer) or "search_comparison" (a Google search
    result). NEVER sends Cookie, If-None-Match or If-Modified-Since - by
    construction, and filtered again in case a future profile ever carries
    one. Each profile's Sec-CH-UA platform and mobile hint match its own
    User-Agent."""
    if persona_index is None or isinstance(persona_index, bool):
        index = 0
    else:
        try:
            index = int(persona_index) % len(_HEADER_PROFILES)
        except (TypeError, ValueError):
            index = 0
    headers = dict(_HEADER_PROFILES[index])
    for name in _NEVER_SENT:
        headers.pop(name, None)
    mode = str(referer_mode or "")
    referer = _REFERER_MODES.get(mode, "")
    if referer:
        headers["Referer"] = referer
    return headers


#: The radar never looks more often than this, whatever the base interval.
POLL_MIN_SECONDS = 300
#: How much a look may drift from its base interval, either way.
POLL_JITTER = 0.30


def next_poll_timestamp(base_interval_s, rng=None, now=None) -> float:
    """When the next look is due: `now` plus a jittered interval.

    The interval is `base_interval_s` changed by up to +/-30%, never below
    `POLL_MIN_SECONDS` (300 s). `rng` may be a `random.Random` (or anything
    with `.uniform(a, b)`) for a DETERMINISTIC sequence - the same rng state
    and the same `now` give the same timestamp; None uses the module's
    random source. `now` defaults to the current time. Exported for the
    radar's own scheduler (Slice 2): the existing page watch's cadence is
    chosen once when the watch is made, so nothing here is wired into it."""
    try:
        base = float(base_interval_s)
    except (TypeError, ValueError):
        base = float(POLL_MIN_SECONDS)
    if not base > 0:
        base = float(POLL_MIN_SECONDS)
    import random as _random
    source = rng if rng is not None and hasattr(rng, "uniform") else _random
    factor = 1.0 + float(source.uniform(-POLL_JITTER, POLL_JITTER))
    interval = max(float(POLL_MIN_SECONDS), base * factor)
    moment = time.time() if now is None else float(now)
    return round(moment + interval, 3)


#: What a price watch keeps: "p1:" and the price it last read.
PRICE_PRINT = "p1:"


def _price_of_state(state) -> Optional[float]:
    if isinstance(state, str) and state.startswith(PRICE_PRINT):
        try:
            return float(state[len(PRICE_PRINT):])
        except ValueError:
            return None
    return None


def _look_price(job_id: str, watch: dict, st: dict, deps: Deps, sched) -> tuple:
    """(1 when the price is now below the owner's number and was not at the
    look before, the sentence for Coming up). The same checks as a page."""
    import jarvis_local_http as LH
    url = watch["url"]
    problem = LH.private_fetch_problem(url)
    if problem:
        return 0, f"Could not look: {problem}"
    text = (f"Jarvis would like to fetch {url} for a \"tell me when\": one plain GET, to read "
            "the price on it with plain code - never a link on the page, never a purchase; "
            "only the number is kept.")
    if not _ok_to_read(PAGE_ACTION, "read a price on a web page for a \"tell me when\"", text,
                       deps):
        return 0, ("Could not look: your settings ask for a yes each time Jarvis fetches a "
                   "web page.")
    fetch = deps.price_fetch or _default_price_fetch
    try:
        price = fetch(url)
    except Exception as exc:
        return 0, f"Could not look: the page did not answer ({type(exc).__name__})."
    if price is None:
        return 0, "Could not look: Jarvis could not find a price on that page."
    before = _price_of_state(st.get("last_state"))
    _save(job_id, sched, last_state=f"{PRICE_PRINT}{float(price):.2f}")
    below = float(watch["below"])
    was_below = before is not None and before < below
    return (1 if float(price) < below and not was_below else 0), ""


# --------------------------------------------------------------------------
#   Pillar 26 (2026-10-17): a noise-immune structured page-watch delta
# --------------------------------------------------------------------------
#
# Blueprint C of Volume III. The page watch above used to compare one
# fingerprint of the visible words, so a clock stamp, a rotating ad or a view
# counter changed the fingerprint of a page nobody changed. A look is now a
# small deterministic pipeline, all plain code - no model call and no network
# in it; every function takes the text the one GET already returned:
#
#   strip_page_noise(html_or_text)   the words, with the noise removed
#   extract_watch_signals(text)      prices in whole cents, versions, stock,
#                                    and the hash of the clean words
#   diff_watch_snapshot(prev, curr)  what changed - and "[SILENT]" when
#                                    nothing meaningful did
#
# The look keeps a small JSON snapshot (PAGE_STATE) of those signals, so a
# match can say WHAT changed ("The price is now 199.99 (it was 249.99).")
# without keeping or quoting the page's words. A fetch that fails is
# stale=True with last_good_at preserved: the old snapshot is never
# overwritten and nothing is alerted. A page that really changed latches the
# gate's conversation taint (why="page_watch"), because outside text was read.

PAGE_SILENT = "[SILENT]"
#: The page-state kinds a look keeps. "t3:" is the current JSON snapshot (it
#: gained the machine-marked price/stock signals on 2026-10-21, so a t2
#: snapshot is re-recorded once, silently); "t2:", "t1:" and the raw kind
#: are what older Jarvis versions kept - those can only be compared for
#: equality and are re-recorded once, silently.
PAGE_STATE = "t3:"
#: The chat/tool marker families a page could use to pretend to be a turn
#: ("SecAlign markers"): removed before anything is compared, so a page
#: cannot smuggle a role or tool marker into what the watch keeps or says.
_SEC_ALIGN_MARKERS = ("<|im_start|>", "<|im_end|>", "<|endoftext|>", "<tool_call>",
                      "</tool_call>", "<tool_response>", "</tool_response>",
                      "<think>", "</think>", "<|system|>", "<|user|>",
                      "<|assistant|>")

#: The elements whose TEXT is not page content, or is site chrome rather than
#: the page: script/style/noscript/svg/nav/footer/aside (Blueprint C), plus
#: their kin a reader never sees.
_NO_CONTENT_TAGS = frozenset({"script", "style", "noscript", "svg", "nav", "footer",
                              "aside", "template", "iframe", "object", "canvas"})

#: Relative timestamps: "Updated 3 minutes ago", "Just now".
_REL_TIME = re.compile(
    r"\b(?:just now|moments? ago|today|yesterday|"
    r"\d[\d,.]*\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|"
    r"months?|years?)\s+ago)\b", re.I)
#: Absolute clock stamps: an ISO date/time, or a bare clock time. Both change
#: on a page nobody changed.
_ABS_TIME = re.compile(
    r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?"
    r"(?:Z|[+-]\d{2}:?\d{2})?)?\b"
    r"|(?<![\w.$\u00a3\u20ac])\b\d{1,2}:\d{2}(?::\d{2})?\b(?![\w.])")
#: "1,234 views", "1.2k visitors", "12 people are viewing": a different number
#: on every visit.
_VIEW_COUNTS = re.compile(
    r"\b\d[\d,.]*\s*k?\s*(?:views?|viewers?|visitors?|people\s+(?:are\s+)?viewing|"
    r"watching(?:\s+now)?|sold|sales|shoppers?)\b", re.I)
#: CSRF/session nonces written as key=value.
_NONCE_PAIR = re.compile(
    r"\b(?:csrf[a-z_]*|xsrf[a-z_]*|session[a-z_]*|nonce|authenticity_token|_token|token)"
    r"\s*=\s*[\"']?[A-Za-z0-9+/_.:-]{8,}[\"']?", re.I)
#: A long hex token, a UUID, or a long mixed letter/digit token: a session id.
_HEX_TOKEN = re.compile(r"\b[0-9a-f]{16,}\b", re.I)
_UUID_TOKEN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_MIXED_TOKEN = re.compile(
    r"\b(?=[A-Za-z0-9_]{20,}\b)(?=[A-Za-z0-9_]*\d)(?=[A-Za-z0-9_]*[A-Za-z])"
    r"[A-Za-z0-9_]{20,}\b")
#: A utm_* tracking parameter in any address on the page.
_UTM_PARAM = re.compile(r"[?&]utm_[A-Za-z0-9_]+=[^&\s#]*", re.I)
#: Chat/tool markers, matched case-insensitively in one pass.
_SEC_ALIGN_RX = re.compile("|".join(re.escape(m) for m in _SEC_ALIGN_MARKERS), re.I)

#: A version a page names: "Version 2.4.0", "v1.2.3", "release 4.0". The
#: prefix is required, so a price ("$199.99") is never read as a version.
_VERSION = re.compile(r"\b(?:version|ver\.?|release|v)\s*"
                      r"([0-9]+(?:\.[0-9]+){1,3}(?:[-+][0-9A-Za-z.]+)?)", re.I)
#: Stock words. Fixed phrases in a fixed order; only one of the three states
#: is kept, never the page's own sentence.
_OUT_OF_STOCK = re.compile(
    r"\b(?:out of stock|sold out|out of print|not available|no longer available|"
    r"unavailable|discontinued)\b", re.I)
_IN_STOCK = re.compile(
    r"\b(?:in stock|back in stock|add to (?:cart|basket)|buy now|available(?: now)?)\b",
    re.I)


def strip_sec_align_markers(text: str) -> str:
    """Remove the chat/tool marker families ("SecAlign markers") from text, so
    a watched page cannot pretend to be a chat turn in anything this module
    keeps or says. Case-insensitive and local."""
    return _SEC_ALIGN_RX.sub("", str(text or ""))


def _html_words(text: str) -> str:
    """The words a reader would see, with the no-content and chrome elements
    (script/style/noscript/svg/nav/footer/aside and their kin) left out. Text
    with no HTML in it is returned as it is."""
    import html.parser
    if not re.search(r"<\s*(?:html|body|div|p|span|head|nav|footer|aside|script)\b",
                     text[:4096], re.I):
        return text

    class _Words(html.parser.HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.hidden = 0
            self.words = []

        def handle_starttag(self, tag, attrs):
            if tag in _NO_CONTENT_TAGS:
                self.hidden += 1

        def handle_startendtag(self, tag, attrs):
            pass  # <br/>, <img/>: nothing is opened, so nothing to close

        def handle_endtag(self, tag):
            if tag in _NO_CONTENT_TAGS and self.hidden:
                self.hidden -= 1

        def handle_data(self, data):
            if not self.hidden:
                self.words.append(data)

    p = _Words()
    try:
        p.feed(text)
        p.close()
    except Exception:
        return re.sub(r"<[^>]*>", " ", text)
    return " ".join(p.words)


def strip_page_noise(html_or_text: str) -> str:
    """The page's words with everything that changes on a page nobody changed
    removed - deterministically and locally, never with a model:
      * the script/style/noscript/svg/nav/footer/aside elements' text;
      * relative timestamps ("Updated 3 minutes ago", "Just now") and
        absolute clock stamps;
      * view counts ("1,234 views", "12 people are viewing");
      * CSRF/session nonces, UUIDs, long hex and long mixed tokens;
      * utm_* tracking parameters in any address;
      * the SecAlign chat/tool markers.
    The real words are kept in order; only whitespace is tidied."""
    text = _html_words(str(html_or_text or ""))
    text = strip_sec_align_markers(text)
    text = _UTM_PARAM.sub("", text)
    text = _NONCE_PAIR.sub(" ", text)
    text = _UUID_TOKEN.sub(" ", text)
    text = _HEX_TOKEN.sub(" ", text)
    text = _MIXED_TOKEN.sub(" ", text)
    text = _REL_TIME.sub(" ", text)
    text = _ABS_TIME.sub(" ", text)
    text = _VIEW_COUNTS.sub(" ", text)
    text = re.sub(r"[?&]{2,}", lambda m: m.group(0)[0], text)
    return " ".join(text.split())


# --------------------------------------------------------------------------
#   Machine-marked prices and stock (2026-10-21): the page-watch snapshot
#   reads the price and availability a shop marks for machines FIRST - the
#   schema.org JSON-LD blocks `price_of()` already used, and the
#   OpenGraph/meta tags beside them - then the prices SHOWN in the visible
#   words. A discount or an "OutOfStock" is often only in that markup, so the
#   page watch missed changes the price watch could see. Plain code, integer
#   cents, deterministic; a machine price already counted is never counted
#   again from the visible words.
# --------------------------------------------------------------------------

#: schema.org availability, normalised to its last path segment and lower
#: case, mapped to the three states a snapshot keeps. PreOrder/BackOrder map
#: to "unknown" on purpose: the page does not say it is in stock, and "out of
#: stock" would be a claim it did not make.
_LD_AVAILABILITY = {
    "instock": "in_stock",
    "in_stock": "in_stock",
    "onlineonly": "in_stock",
    "limitedavailability": "in_stock",
    "outofstock": "out_of_stock",
    "out_of_stock": "out_of_stock",
    "soldout": "out_of_stock",
    "sold_out": "out_of_stock",
    "discontinued": "out_of_stock",
    "preorder": "unknown",
    "pre_order": "unknown",
    "backorder": "unknown",
    "back_order": "unknown",
}
#: The @type names whose node carries a price and/or an availability. A page
#: may write the bare name or the full schema.org address - both match.
_LD_SIGNAL_TYPES = frozenset({"product", "offer", "aggregateoffer", "flight",
                              "productgroup"})
#: Keys a JSON-LD document nests those nodes under (schema.org's own shape).
_LD_SIGNAL_KEYS = ("offers", "@graph", "mainEntity", "itemOffered",
                   "priceSpecification", "hasVariant")
_LD_MAX_DEPTH = 8
_LD_MAX_NODES = 4000
#: The currency signs/words allowed around a price, the same set
#: `parse_number` accepts.
_CURRENCY_EDGES = re.compile(
    r"^(?:[£$€]|us\$|usd|gbp|eur)\s*|\s*(?:[£$€]|usd|gbp|eur)$", re.IGNORECASE)


def _short_type(value) -> str:
    """"https://schema.org/Product" and "Product" both become "product"."""
    return str(value or "").strip().rstrip("/").rsplit("/", 1)[-1].lower()


def _ld_availability(value) -> str:
    """One schema.org availability -> the snapshot's vocabulary, or ""."""
    return _LD_AVAILABILITY.get(_short_type(value), "")


def _decimal_words(value) -> Optional[object]:
    """A price as people and pages write it, as an exact Decimal: "25",
    "1,299.99", "1.299,99", "24,99", "£ 1 299". The same shapes
    `parse_number` accepts, but WITHOUT turning the number into a float."""
    from decimal import Decimal, InvalidOperation
    text = _CURRENCY_EDGES.sub("", str(value or "").strip())
    text = text.replace("\u00a0", " ").replace("\u202f", " ").strip()
    if not re.fullmatch(r"\d[\d ,.']*", text) or len(text) > 20:
        return None
    text = text.replace(" ", "").replace("'", "")
    last_dot, last_comma = text.rfind("."), text.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        dec = "." if last_dot > last_comma else ","
        thou = "," if dec == "." else "."
        text = text.replace(thou, "").replace(dec, ".")
    elif last_comma >= 0:
        # "24,99" is a decimal comma; "1,299" and "1,299,000" are thousands.
        if len(text) - last_comma - 1 == 2 and text.count(",") == 1:
            text = text.replace(",", ".")
        else:
            text = text.replace(",", "")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    elif last_dot >= 0 and len(text) - last_dot - 1 == 3 and not text.startswith("0"):
        # "1.299" on a European page is a thousand, not one and a bit.
        text = text.replace(".", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _cents_from_price(value) -> Optional[int]:
    """A machine-marked price as INTEGER whole cents, read with `Decimal`
    from the thing the page actually wrote: "$1,249.99" and the JSON number
    1249.99 both become 124999, never a float artefact. More than two
    decimals rounds half-up to cents (deterministic); a price that is not a
    positive number under PRICE_MAX is None."""
    from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
    if isinstance(value, bool) or value is None:
        return None
    try:
        if isinstance(value, Decimal):
            amount = value
        elif isinstance(value, int):
            amount = Decimal(value)
        elif isinstance(value, float):
            # The JSON block is parsed with parse_float=Decimal; this arm is
            # for a caller that already turned it into a float.
            amount = Decimal(repr(value))
        else:
            amount = _decimal_words(value)
            if amount is None:
                return None
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount <= 0:
        return None
    try:
        cents = (amount * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None
    if cents <= 0 or cents > PRICE_MAX * 100:
        return None
    return int(cents)


def _ld_watch_signal_nodes(node, depth, prices, stock, seen) -> None:
    """Walk one parsed JSON-LD document in ITS order, collecting integer cents
    and availability states from the nodes that carry them. Bounded in depth
    and node count; malformed shapes are simply skipped."""
    if depth > _LD_MAX_DEPTH or len(seen) >= _LD_MAX_NODES:
        return
    if isinstance(node, list):
        for item in node[:100]:
            _ld_watch_signal_nodes(item, depth + 1, prices, stock, seen)
        return
    if not isinstance(node, dict):
        return
    seen.append(1)
    types = node.get("@type")
    types = types if isinstance(types, list) else [types]
    if any(_short_type(t) in _LD_SIGNAL_TYPES for t in types):
        for key in ("price", "lowPrice"):
            if key in node:
                cents = _cents_from_price(node.get(key))
                if cents is not None and cents not in prices:
                    prices.append(cents)
        # Only a DEFINITE state overrides the visible words. PreOrder and
        # BackOrder map to "unknown" and are left to the visible words: the
        # page did not say in/out of stock, and an unknown must not hide a
        # definite visible answer.
        state = _ld_availability(node.get("availability"))
        if state in ("in_stock", "out_of_stock") and state not in stock:
            stock.append(state)
    for key in _LD_SIGNAL_KEYS:
        if key in node:
            _ld_watch_signal_nodes(node[key], depth + 1, prices, stock, seen)


def _machine_watch_signals(text: str) -> tuple:
    """(prices_cents, stock_states) a page marks for MACHINES, in document
    order: every JSON-LD block first (schema.org Product/Offer/AggregateOffer/
    Flight), then the OpenGraph/meta price tags. JSON numbers are parsed with
    `Decimal` from their own decimal text so cents are exact, and one
    malformed block never hides the others."""
    from decimal import Decimal
    prices, stock = [], []
    raw = str(text or "")
    for m in _LD_JSON.finditer(raw):
        block = m.group(1).strip()
        if block.startswith("<!--"):
            block = block[4:].lstrip()
        if block.endswith("-->"):
            block = block[:-3].rstrip()
        if not block:
            continue
        try:
            doc = json.loads(block, parse_float=Decimal)
        except ValueError:
            continue
        _ld_watch_signal_nodes(doc, 0, prices, stock, [])
    for m in _META.finditer(raw):
        tag = m.group(0)
        name = (_attr(tag, "itemprop") or _attr(tag, "property")
                or _attr(tag, "name")).lower()
        if name not in _META_PRICE:
            continue
        cents = _cents_from_price(_attr(tag, "content"))
        if cents is not None and cents not in prices:
            prices.append(cents)
    return prices, stock


def extract_watch_signals(text: str) -> dict:
    """The structured signals a page shows, read by plain code - never a
    model, and never a float price:
      * "prices_cents": the page's prices as INTEGER whole-cent values in a
        deterministic order - the machine-marked ones first (schema.org
        JSON-LD Product/Offer/AggregateOffer/Flight and OpenGraph/meta tags,
        read with `Decimal` so "$1,249.99" is exactly 124999), then each
        price SHOWN in the visible words that the markup did not already give,
        in the order a reader meets them. The same amount is never counted
        twice;
      * "versions": every version/release tag, its prefix dropped ("v1.2.3"
        is "1.2.3"), first-seen order, no repeats;
      * "stock_state": "in_stock", "out_of_stock" or "unknown" - a state the
        page marks for machines (schema.org availability) wins, else the
        visible words say it;
      * "clean_sha256": the SHA-256 hex digest of the noise-stripped words,
        case folded - what "the page's text changed" means. The machine
        markup is not page words, so adding or changing it does not move it."""
    import hashlib
    machine_prices, machine_stock = _machine_watch_signals(str(text or ""))
    clean = strip_page_noise(str(text or ""))
    prices = list(machine_prices)
    for m in _SHOWN_PRICE.finditer(clean):
        value = parse_number(m.group("a") or m.group("b") or "")
        if value is not None and 0 < value <= PRICE_MAX:
            cents = int(round(float(value) * 100))
            if cents > 0 and cents not in machine_prices:
                prices.append(cents)
    versions = []
    for m in _VERSION.finditer(clean):
        version = m.group(1)
        if version not in versions:
            versions.append(version)
    if machine_stock:
        stock = machine_stock[0]
    elif _OUT_OF_STOCK.search(clean):
        stock = "out_of_stock"
    elif _IN_STOCK.search(clean):
        stock = "in_stock"
    else:
        stock = "unknown"
    return {"prices_cents": prices, "versions": versions, "stock_state": stock,
            "clean_sha256": hashlib.sha256(clean.casefold().encode("utf-8")).hexdigest()}


def _cents_words(cents) -> str:
    """19999 -> "199.99": a whole-cent price said the way a page shows it."""
    try:
        return f"{int(cents) / 100:.2f}"
    except (TypeError, ValueError):
        return ""


def _stock_words(state) -> str:
    return {"in_stock": "in stock", "out_of_stock": "out of stock",
            "unknown": "unknown"}.get(state, "unknown")


def _diff_words(prev: dict, curr: dict) -> list:
    """The plain sentences for one changed page, in a fixed order - price,
    version, stock. Fixed words and numbers only: never the page's text."""
    words = []
    before, after = list(prev.get("prices_cents") or []), list(curr.get("prices_cents") or [])
    if before and after and before[0] != after[0]:
        words.append(f"The price is now {_cents_words(after[0])} "
                     f"(it was {_cents_words(before[0])}).")
    elif before != after:
        if after and not before:
            words.append(f"It now shows a price of {_cents_words(after[0])}.")
        elif before and not after:
            words.append("It no longer shows a price.")
        else:
            words.append("The prices it shows changed.")
    was_versions, now_versions = list(prev.get("versions") or []), list(curr.get("versions") or [])
    if was_versions != now_versions:
        added = [v for v in now_versions if v not in was_versions]
        removed = [v for v in was_versions if v not in now_versions]
        if len(added) == 1 and len(removed) == 1:
            words.append(f"The version is now {added[0]} (it was {removed[0]}).")
        elif added:
            words.append("It now names version " + ", ".join(added) + ".")
        elif removed:
            words.append("It no longer names version " + ", ".join(removed) + ".")
    was_stock, now_stock = prev.get("stock_state"), curr.get("stock_state")
    if was_stock != now_stock:
        if was_stock in ("in_stock", "out_of_stock") and now_stock in ("in_stock",
                                                                      "out_of_stock"):
            words.append(f"It is now {_stock_words(now_stock)} "
                         f"(it was {_stock_words(was_stock)}).")
        elif now_stock in ("in_stock", "out_of_stock"):
            words.append(f"It now says {_stock_words(now_stock)}.")
        elif was_stock in ("in_stock", "out_of_stock"):
            words.append(f"It no longer says {_stock_words(was_stock)}.")
    if not words:
        words.append("The page's text changed.")
    return words


def diff_watch_snapshot(prev, curr, *, watch_mode: str = "any") -> dict:
    """Compare two page snapshots and say what changed - pure and
    deterministic: no clock, no network, no model.

    `prev` and `curr` are extract_watch_signals()'s dicts (a stored snapshot
    may also carry "words" and "last_good_at"). `watch_mode` is "any" (the
    default), "price", "release" or "stock": it chooses which signal a watch
    cares about. In "price" mode a page whose words changed but whose prices
    did not is [SILENT]; "release"/"stock" watch their own signal only; "any"
    is the noise-stripped words plus every signal.

    Returns {"changed", "status", "stale", "last_good_at",
    "price_delta_cents", "versions", "stock", "words"}:
      * unchanged answers {"changed": False, "status": "[SILENT]"} - the
        watermark rule, never a notification;
      * a real change answers plain words in "status"/"words" and, when the
        first price changed, "price_delta_cents" (new minus old: a
        $249.99 -> $199.99 drop is -5000);
      * curr is None means the fetch FAILED: stale is True, changed is False,
        "[SILENT]", and last_good_at is carried from prev - the caller keeps
        the old snapshot and never alerts on a fetch error."""
    if watch_mode not in ("any", "price", "release", "stock"):
        raise ValueError('watch_mode is "any", "price", "release" or "stock"')
    prev = prev or {}
    if curr is None:
        return {"changed": False, "status": PAGE_SILENT, "stale": True,
                "last_good_at": prev.get("last_good_at"), "price_delta_cents": None,
                "versions": {"from": list(prev.get("versions") or []), "to": []},
                "stock": {"from": prev.get("stock_state"),
                          "to": prev.get("stock_state")},
                "words": ""}
    before_prices = list(prev.get("prices_cents") or [])
    after_prices = list(curr.get("prices_cents") or [])
    price_delta = None
    if before_prices and after_prices and before_prices[0] != after_prices[0]:
        price_delta = int(after_prices[0]) - int(before_prices[0])
    if not prev:
        changed = False
    elif watch_mode == "price":
        changed = before_prices != after_prices
    elif watch_mode == "release":
        changed = list(prev.get("versions") or []) != list(curr.get("versions") or [])
    elif watch_mode == "stock":
        changed = prev.get("stock_state") != curr.get("stock_state")
    else:
        changed = (prev.get("clean_sha256") != curr.get("clean_sha256")
                   or before_prices != after_prices
                   or list(prev.get("versions") or []) != list(curr.get("versions") or [])
                   or prev.get("stock_state") != curr.get("stock_state"))
    words = _diff_words(prev, curr) if changed else []
    return {"changed": changed,
            "status": (" ".join(words) if changed else PAGE_SILENT),
            "stale": False,
            "last_good_at": curr.get("last_good_at", prev.get("last_good_at")),
            "price_delta_cents": price_delta if changed else None,
            "versions": {"from": list(prev.get("versions") or []),
                         "to": list(curr.get("versions") or [])},
            "stock": {"from": prev.get("stock_state"),
                      "to": curr.get("stock_state")},
            "words": " ".join(words)}


def _page_state_text(fields: dict) -> str:
    """One page snapshot as the string the look keeps - compact and
    sort-keyed, so the same page always gives the same bytes."""
    return PAGE_STATE + json.dumps(fields, sort_keys=True, separators=(",", ":"))


def _page_state_fields(state) -> dict:
    """The JSON fields of a "t2:" snapshot, or {} for an older kind and a
    damaged value."""
    if isinstance(state, dict):
        return dict(state)
    if isinstance(state, str) and state.startswith(PAGE_STATE):
        try:
            got = json.loads(state[len(PAGE_STATE):])
        except ValueError:
            return {}
        return got if isinstance(got, dict) else {}
    return {}


def _page_state(body: bytes, content_type: str = "") -> str:
    """A page's current snapshot: the signals extract_watch_signals() read
    from its one GET (a noise-stripped hash, prices in whole cents, versions,
    stock), plus the empty change words and last-good time the look fills in.
    Never the page's words, and nothing here is sent anywhere."""
    text = _decode_body(body[:PAGE_MAX_BYTES], content_type)
    fields = extract_watch_signals(text)
    fields["words"] = ""
    fields["last_good_at"] = None
    return _page_state_text(fields)


def _latch_page_watch() -> bool:
    """A changed page was outside text, so latch the gate's conversation
    taint (why="page_watch") - the one place this module says "what I just
    read is not the owner's words". Optional: a backend folder without
    jarvis_gate.py (this repository's base has it; repo-mode tests do not)
    simply does not latch, and nothing fails."""
    try:
        import jarvis_gate
        return bool(jarvis_gate.latch_taint(why="page_watch"))
    except Exception:
        return False


# --------------------------------------------------------------------------
#   "Tell me when a search shows something new" (2026-09-28)
# --------------------------------------------------------------------------

#: What a search watch keeps: "s1:", the provider, and a short fingerprint
#: of each result address seen (never the address itself).
SEARCH_PRINT = "s1:"
_TRACKING = ("fbclid", "gclid", "msclkid", "ref", "ref_src", "mc_cid", "mc_eid")


def address_print(url) -> str:
    """A short fingerprint of a result's address - the same page gives the
    same one whatever "www.", "https", a closing "/" or tracking tags say.
    "" for something that is not an http(s) address."""
    import hashlib
    import urllib.parse
    try:
        parts = urllib.parse.urlsplit(str(url or "").strip())
    except ValueError:
        return ""
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return ""
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/") or "/"
    query = sorted((k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
                   if not k.lower().startswith("utm_") and k.lower() not in _TRACKING)
    norm = host + path + ("?" + urllib.parse.urlencode(query) if query else "")
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def _search_said(problem: str, offer: str = "") -> str:
    said = " ".join(str(problem or "The search did not work.").split())
    if offer:
        said += " " + " ".join(str(offer).split())
    return "Could not look: " + said


def _look_search(job_id: str, watch: dict, st: dict, deps: Deps, sched) -> tuple:
    """(how many result addresses are new, the sentence for Coming up). The
    owner's words, through the ONE web search they chose - jarvis_search's
    own plan and run, so the secret check, the one-provider rule and "no
    silent fallback" are the same as in a chat. Nothing read goes to the AI
    model; only fingerprints of the addresses are kept."""
    import jarvis_search as WS
    try:
        s = WS.settings()
    except Exception:
        return 0, "Could not look: Jarvis could not read the web search settings on this PC."
    provider = s.get("provider") or ""
    p = WS.plan(watch["words"], s=s)
    if p.problem:
        return 0, _search_said(p.problem, p.offer)
    run = deps.search_run or (lambda plan: WS.run(plan, approved=True))
    try:
        out = run(p) or {}
    except Exception as exc:
        return 0, f"Could not look: the search failed ({type(exc).__name__})."
    _audit("tellme.search", {"id": job_id, "provider": provider, "ok": bool(out.get("ok"))})
    if not out.get("ok") and out.get("state") != "no_results":
        return 0, _search_said(out.get("error"), out.get("offer") or "")
    prints = []
    for r in out.get("results") or []:
        a = address_print((r or {}).get("url")) if isinstance(r, dict) else ""
        if a and a not in prints:
            prints.append(a)
    before = str(st.get("last_state") or "")
    head = f"{SEARCH_PRINT}{provider}:"
    if not before.startswith(head):
        # The first look - or the owner chose another web search since: its
        # results are not comparable with the last one's, so only record.
        _save(job_id, sched, last_state=head + ",".join(prints[:SEARCH_KEEP]))
        return 0, ""
    seen = [x for x in before[len(head):].split(",") if x]
    new = [a for a in prints if a not in seen]
    _save(job_id, sched, last_state=head + ",".join((new + seen)[:SEARCH_KEEP]))
    return len(new), ""


# --------------------------------------------------------------------------
#   GitHub watches (2026-09-28): CI finishing or failing, a pull request merging
# --------------------------------------------------------------------------

#: What a GitHub watch keeps: "g1:" and either "pr:<open|merged|closed>" or
#: "<first 12 of the newest commit>:<running|done>:<failed|ok>" (or "none").
GITHUB_PRINT = "g1:"


def github_url(w: dict) -> str:
    """The ONE address a GitHub watch asks - on the card in full."""
    import urllib.parse
    repo = urllib.parse.quote(w["repo"], safe="/._-")
    if w["event"] == "pr_merged":
        return f"{GITHUB_API}/repos/{repo}/pulls/{int(w['pr'])}"
    q = {"per_page": "20"}
    if w.get("branch"):
        q["branch"] = w["branch"]
    return f"{GITHUB_API}/repos/{repo}/actions/runs?" + urllib.parse.urlencode(q)


class _GitHubNoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is refused, never followed: urllib copies every header -
    the GitHub key included - onto the redirect target, another host too
    (jarvis_research._RefuseRedirect's reason)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "refused to follow a redirect",
                                     headers, fp)


def _default_github_get(url: str) -> tuple:
    """(HTTP status, the parsed answer or None). api.github.com only; the
    key, when one is set, is read fresh, handed to the log scrubber by value,
    and sent in this one request's header only."""
    if not url.startswith(GITHUB_API + "/"):
        raise ValueError("not a GitHub API address")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "jarvis-tellme",
               "X-GitHub-Api-Version": "2022-11-28"}
    token = _env(GITHUB_TOKEN_ENV)
    if token:
        try:
            import jarvis_scrub
            jarvis_scrub.register_secret(token)
        except Exception:
            pass
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    import jarvis_local_http as LH
    opener = LH.opener_for(url, _GitHubNoRedirect)
    try:
        with opener.open(req, timeout=GITHUB_TIMEOUT) as r:
            status = r.status
            body = r.read(GITHUB_MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return exc.code, None
    if len(body) > GITHUB_MAX_BYTES:
        raise ValueError("GitHub's answer was too large")
    try:
        return status, json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return status, None


def _github_state(w: dict, doc: dict) -> str:
    """What is kept from GitHub's answer - fixed words chosen here."""
    if w["event"] == "pr_merged":
        if doc.get("merged") is True or doc.get("merged_at"):
            return GITHUB_PRINT + "pr:merged"
        return GITHUB_PRINT + ("pr:closed" if doc.get("state") == "closed" else "pr:open")
    runs = [r for r in (doc.get("workflow_runs") or []) if isinstance(r, dict)]
    if not runs:
        return GITHUB_PRINT + "none"
    sha = str(runs[0].get("head_sha") or "")
    group = [r for r in runs if str(r.get("head_sha") or "") == sha]
    done = all(r.get("status") == "completed" for r in group)
    failed = any(r.get("status") == "completed" and r.get("conclusion") in CI_FAILED
                 for r in group)
    short = re.sub(r"[^0-9a-f]", "", sha.lower())[:12] or "unknown"
    return (f"{GITHUB_PRINT}{short}:{'done' if done else 'running'}:"
            f"{'failed' if failed else 'ok'}")


def _github_parts(state) -> list:
    if isinstance(state, str) and state.startswith(GITHUB_PRINT):
        return state[len(GITHUB_PRINT):].split(":")
    return []


def _github_matches(w: dict, before, now: str) -> bool:
    b, n = _github_parts(before), _github_parts(now)
    if w["event"] == "pr_merged":
        # Told when it is merged - or closed without merging, since then it
        # never will be. Already merged at the first look: told too.
        return n[-1:] in (["merged"], ["closed"]) and b != n
    if not b or len(n) != 3:
        return False    # the first look only records; no runs yet is nothing
    same = len(b) == 3 and b[0] == n[0]
    if w["event"] == "ci_failed":
        return n[2] == "failed" and not (same and b[2] == "failed")
    return n[1] == "done" and not (same and b[1] == "done")


def _github_alert(w: dict, state) -> str:
    n = _github_parts(state)
    repo = w["repo"]
    if w["event"] == "pr_merged":
        if n[-1:] == ["closed"]:
            return f"Pull request #{w['pr']} on {repo} was closed without being merged."
        return f"Pull request #{w['pr']} on {repo} was merged."
    where = f"{repo}{_branch_words(w)}"
    if w["event"] == "ci_failed":
        return f"CI failed on {where}."
    if len(n) == 3 and n[1] == "done":
        return (f"CI finished on {where}: something failed." if n[2] == "failed"
                else f"CI finished on {where}: everything passed.")
    return f"CI finished on {where}."


def _look_github(job_id: str, watch: dict, st: dict, deps: Deps, sched) -> tuple:
    """(1 on the change the owner asked about, the sentence for Coming up).
    One read-only GET to api.github.com, through the gate as github_read.
    Errors are said in fixed words - never GitHub's own text, never the key."""
    url = github_url(watch)
    text = (f"Jarvis would like to ask GitHub one read-only question for a \"tell me when\": "
            f"GET {url}. Nothing on GitHub is changed.")
    if not _ok_to_read(GITHUB_ACTION, "read one GitHub status for a \"tell me when\"", text,
                       deps):
        return 0, "Could not look: your settings ask for a yes each time Jarvis reads GitHub."
    get = deps.github_get or _default_github_get
    try:
        status, doc = get(url)
    except Exception as exc:
        return 0, f"Could not look: GitHub did not answer ({type(exc).__name__})."
    if status == 404:
        return 0, ("Could not look: GitHub says there is no such repository or pull request "
                   "- or it is private and no GitHub key that can see it is saved on this PC.")
    if status == 401:
        return 0, ("Could not look: GitHub refused the GitHub key saved on this PC (it may have "
                   "expired).")
    if status in (403, 429):
        return 0, ("Could not look: GitHub said no for now - usually too many looks in an hour "
                   "(its limit). It tries again at the next look.")
    if status != 200 or not isinstance(doc, dict):
        return 0, f"Could not look: GitHub answered with an error (HTTP {status})."
    now = _github_state(watch, doc)
    before = st.get("last_state")
    _save(job_id, sched, last_state=now)
    return (1 if _github_matches(watch, before, now) else 0), ""


_JOB_LOCKS: dict = {}
_JOB_LOCKS_LOCK = threading.Lock()
#: When each email watch last really signed in to look (this process only:
#: a restart forgets, and the next look is a full one).
_FULL: dict = {}


def _job_lock(job_id: str):
    with _JOB_LOCKS_LOCK:
        lk = _JOB_LOCKS.get(job_id)
        if lk is None:
            lk = _JOB_LOCKS[job_id] = threading.Lock()
        return lk


def look(job_id: str, *, deps: Optional[Deps] = None, sched=None, nudged: bool = False) -> dict:
    """One look for one watch (the scheduler calls this on its own thread
    when the job goes off; the instant watch calls it when the mail server
    says new mail arrived - `nudged`). Only ever notifies: a match rings the
    doorbell with the kind and a flag, and - if it was to tell once - ends
    the job. Nothing else happens, whatever was read. One look per watch at
    a time: a nudge and the regular look never both tell."""
    deps = deps or DEPS
    sched = sched or _sched()
    with _job_lock(job_id):
        out = _look(job_id, deps, sched, nudged)
    try:
        if _is_email_watch(job_id, sched):
            IDLE.ensure(deps, sched)
    except Exception:
        pass
    return out


def _is_email_watch(job_id: str, sched) -> bool:
    row, _rule, watch = _watch_of(job_id, sched)
    return row is not None and (watch or {}).get("source") == "email"


def _look(job_id: str, deps: Deps, sched, nudged: bool) -> dict:
    row, rule, watch = _watch_of(job_id, sched)
    if row is None or row["state"] not in ("active", "fired"):
        return {"ok": False, "why": "not on the list"}
    st = _state(job_id, sched)
    now = sched.now()
    ends = (rule or {}).get("ends")
    if ends is not None and now > float(ends) + S.LATE_AFTER:
        # Past the date the card promised (the PC slept through it): the
        # watch is over, and this look does not happen - it could tell the
        # owner about an email that came after the end.
        if row["state"] == "active":
            sched.end(job_id)
        return {"ok": False, "why": "ended"}
    _tidy(sched)
    try:
        watch = check_watch(watch)
    except ValueError:
        return {"ok": False, "why": "not a watch"}
    missing = bool(watch.get("missing"))
    due = missing and now >= float(watch["by"])
    if (watch["source"] == "email" and not nudged and not due
            and st.get("base_uid") is not None and IDLE.healthy()
            and time.time() - _FULL.get(job_id, 0.0) < SAFETY_MINUTES * 60):
        # The instant watch is connected and would have said if mail had
        # arrived: no sign-in this time (a full look still happens every
        # SAFETY_MINUTES).
        return {"ok": True, "matched": 0, "instant": True}
    ready = readiness(watch["source"], deps)
    if ready:
        n, said = 0, "Could not look: " + ready[0].lower() + ready[1:]
    elif watch["source"] == "email":
        n, said = _look_email(job_id, watch, st, deps, sched)
        if not said:
            _FULL[job_id] = time.time()
    elif watch["source"] == "page":
        n, said = _look_page(job_id, watch, st, deps, sched)
    elif watch["source"] == "price":
        n, said = _look_price(job_id, watch, st, deps, sched)
    elif watch["source"] == "search":
        n, said = _look_search(job_id, watch, st, deps, sched)
    elif watch["source"] == "github":
        n, said = _look_github(job_id, watch, st, deps, sched)
    else:
        n, said = _look_home(job_id, watch, st, deps, sched)
    _incident(job_id, rule or {}, watch, st, said, now, deps, sched)
    if missing:
        return _missing_after(job_id, watch, st, n, said, now, deps, sched)
    _save(job_id, sched, looked_at=now, look_said=said)
    if n <= 0:
        return {"ok": True, "matched": 0}
    _save(job_id, sched, matched_at=now, matched_n=int(st.get("matched_n") or 0) + 1,
          alert_count=int(n))
    _audit("tellme.matched", {"id": job_id, "source": watch["source"]})
    if watch["once"]:
        sched.end(job_id)
    deps.publish("schedule", {"id": job_id, "kind": KIND, "state": "matched",
                              "urgent": bool(watch["urgent"])})
    return {"ok": True, "matched": n}


def _missing_after(job_id: str, watch: dict, st: dict, n: int, said: str, now: float,
                   deps: Deps, sched) -> dict:
    """"Hasn't replied by ...": an email from them ends it quietly; none by
    the time, and the owner is told - only told."""
    if n > 0:
        # They wrote: nothing to tell. The line under the row says so.
        _save(job_id, sched, looked_at=now,
              look_said=f"{watch['sender']} wrote at {S.when_words(now, now)} - nothing to "
                        f"tell you.")
        _audit("tellme.replied", {"id": job_id})
        sched.end(job_id)
        return {"ok": True, "matched": 0, "replied": True}
    _save(job_id, sched, looked_at=now, look_said=said)
    if said or now < float(watch["by"]):
        # Not yet its time - or it could not look, so it cannot say "no email":
        # it tries again at the next look (up to NO_REPLY_GRACE after).
        return {"ok": True, "matched": 0}
    late = now - float(watch["by"]) > LATE_RING
    _save(job_id, sched, matched_at=now, matched_n=int(st.get("matched_n") or 0) + 1,
          alert_count=1)
    _audit("tellme.matched", {"id": job_id, "source": "email", "missing": True, "late": late})
    sched.end(job_id)
    deps.publish("schedule", {"id": job_id, "kind": KIND, "state": "matched",
                              "urgent": bool(watch["urgent"]) and not late})
    return {"ok": True, "matched": 1, "late": late}


def broken_kind(said: str) -> str:
    """The kind of problem a "Could not look" sentence names: the sentence
    without its bracketed detail ("(TimeoutError)", "(HTTP 502)"), so a
    timeout and a refused connection to the same server are one problem."""
    return " ".join(re.sub(r"\s*\([^()]*\)", "", str(said or "")).split()).casefold()[:300]


def _incident(job_id: str, rule: dict, watch: dict, st: dict, said: str, now: float,
              deps: Deps, sched) -> None:
    """A watch that cannot look tells the owner ONCE (the Hermes agent's
    grouped-failure idea, cron/incidents.py, MIT - no code copied): grouped
    by the kind of problem, told when it has lasted (BROKEN_AFTER_LOOKS looks
    in a row for a watch that looks more often than hourly, else at once),
    told again about the same problem only after BROKEN_AGAIN_HOURS, and
    cleared silently by the next look that works."""
    if not said.startswith("Could not look"):
        if st.get("broken_kind"):
            _save(job_id, sched, broken_kind=None, broken_since=None, broken_n=0,
                  broken_told=None)
            _audit("tellme.broken.cleared", {"id": job_id, "source": watch.get("source")})
        return
    kind = broken_kind(said)
    same = st.get("broken_kind") == kind
    n = (int(st.get("broken_n") or 0) + 1) if same else 1
    since = float(st.get("broken_since") or now) if same else now
    told = st.get("broken_told") if same else None
    needed = 1 if int(rule.get("minutes") or 0) >= 60 else BROKEN_AFTER_LOOKS
    tell = n >= needed and (told is None or now - float(told) >= BROKEN_AGAIN_HOURS * 3600)
    fields = {"broken_kind": kind, "broken_since": since, "broken_n": n,
              "broken_told": now if tell else told,
              # Saved before the doorbell rings: the apps read `broken` by id.
              "looked_at": now, "look_said": said}
    _save(job_id, sched, **fields)
    if tell:
        _audit("tellme.broken", {"id": job_id, "source": watch.get("source"),
                                 "again": told is not None})
        deps.publish("schedule", {"id": job_id, "kind": KIND, "state": "broken"})


def broken_words(watch: dict, said: str) -> str:
    """The notification for a watch that cannot look: what is watched (the
    owner's words) and why, in the fixed words of the look."""
    why = str(said or "")
    if why.startswith("Could not look: "):
        why = why[len("Could not look: "):]
    why = why[:1].upper() + why[1:] if why else "Jarvis could not look."
    return f"Your \"tell me when\" ({what_words(watch)}) cannot look right now. {why}"


def _on_fire(job_id: str) -> None:
    look(job_id)


# --------------------------------------------------------------------------
#   The view: a line under the row, and the alert by id
# --------------------------------------------------------------------------

def note(job_id: str) -> str:
    sched = _sched()
    row, rule, watch = _watch_of(job_id, sched)
    if row is None:
        return ""
    st = _state(job_id, sched)
    now = sched.now()
    parts = []
    if row["state"] in ("active", "paused", "waiting"):
        if watch.get("missing"):
            parts.append(f"Until {S.long_date(float(watch.get('by') or now))}: tells you if "
                         f"no email from {watch.get('sender', '')} has arrived by then.")
        else:
            ends = float(rule.get("ends") or now)
            parts.append(f"Until {S.long_date(ends)}"
                         + (", or the first time it happens." if watch.get("once", True)
                            else "."))
    if watch.get("urgent"):
        parts.append("Urgent: rings until you look.")
    if st.get("matched_at"):
        parts.append(f"Happened at {S.when_words(float(st['matched_at']), now)}.")
    elif st.get("look_said"):
        parts.append(st["look_said"])
    elif st.get("looked_at"):
        parts.append(f"Last looked at {S.clock(float(st['looked_at']))} - nothing yet.")
    if watch.get("source") == "price" and not st.get("look_said"):
        # The number it read, so the owner can check it read the right one.
        seen = _price_of_state(st.get("last_state"))
        if seen is not None:
            parts.append(f"Price at the last look: {money(seen, watch)}.")
    if st.get("broken_kind") and st.get("broken_told"):
        parts.append(f"Jarvis told you at {S.clock(float(st['broken_told']))} that it cannot "
                     "look; that clears by itself at the next look that works.")
    if watch.get("source") == "email" and row["state"] == "active":
        line = IDLE.note_words()
        if line:
            parts.append(line)
    return " ".join(parts)


def fields(job_id: str) -> dict:
    """`alert` (the notification's sentence) once it has happened."""
    sched = _sched()
    row, rule, watch = _watch_of(job_id, sched)
    if row is None:
        return {}
    st = _state(job_id, sched)
    out = {"watches": watch.get("source", "")}
    if st.get("matched_at"):
        try:
            out["alert"] = alert_words(check_watch(watch), int(st.get("alert_count") or 1), st)
        except ValueError:
            pass
        out["alert_at"] = float(st["matched_at"])
    if st.get("broken_kind") and st.get("broken_told"):
        # A watch that cannot look (2026-09-28): the notice's words, and when
        # the owner was told - one notification per telling.
        try:
            out["broken"] = broken_words(check_watch(watch), st.get("look_said") or "")
        except ValueError:
            pass
        out["broken_at"] = float(st["broken_told"])
    return out


# --------------------------------------------------------------------------
#   "What did I miss?" - real matches only, never an idle look
# --------------------------------------------------------------------------

def matched_since(since: float, now: Optional[float] = None, *, sched=None) -> list:
    """Watches that told the owner something between `since` and `now`,
    newest first - `{"id", "matched_at", "alert", "urgent"}`. This is the
    ease-of-use audit's "'tell me when' matches" for "What did I miss?"
    (docs/EASE-OF-USE-AUDIT-2026-09-27.md row 12), and deliberately NOT
    `jarvis_schedule.fired_since()` with its `silent`-kind filter lifted:
    that would also hand back every idle look this kind's own `on_fire`
    stamps `fired_at` for (tick()'s comment above `k.silent` says why a
    look rings no doorbell), which is exactly what
    test_tellme.py's `t_looks_are_not_what_i_missed` and
    `t_past_its_end_it_does_not_look_again` prove is NOT "something I
    missed". A match is different: it is stamped in THIS module's own
    `matched_at` (never on the `jobs` row), only when a look actually told
    the owner something, so this reads that column instead. "Tell every
    time" keeps only its LATEST match, so an earlier one inside the window
    followed by a later one outside it is not found separately - the same
    limit `note()`'s "Happened at ..." line already has."""
    sched = sched or _sched()
    now = sched.now() if now is None else now
    with sched._lock, sched._db() as c:
        job_ids = [r["id"] for r in c.execute(
            "SELECT id FROM jobs WHERE kind = ?", (KIND,)).fetchall()]
    out = []
    for jid in job_ids:
        st = _state(jid, sched)
        matched_at = st.get("matched_at")
        if matched_at is None:
            continue
        matched_at = float(matched_at)
        if not (since <= matched_at <= now):
            continue
        row, rule, watch = _watch_of(jid, sched)
        if row is None:
            continue
        try:
            alert = alert_words(check_watch(watch), int(st.get("alert_count") or 1), st)
        except ValueError:
            continue
        out.append({"id": jid, "matched_at": matched_at, "alert": alert,
                    "urgent": bool((watch or {}).get("urgent"))})
    out.sort(key=lambda d: d["matched_at"], reverse=True)
    return out


# --------------------------------------------------------------------------
#   Setting one up - from an app (the route) or the fast path
# --------------------------------------------------------------------------

def _count(listed: list, sched, sources: tuple) -> int:
    n = 0
    for j in listed:
        _r, _rule, jw = _watch_of(j["id"], sched)
        if jw and jw.get("source") in sources:
            n += 1
    return n


def add(watch: dict, *, ends: Optional[float] = None, minutes: Optional[int] = None,
        source: str = "app", sched=None, deps: Optional[Deps] = None) -> dict:
    """ONE card; nothing looks before it is approved. ValueError or
    OverflowError with a sentence."""
    deps = deps or DEPS
    sched = sched or _sched()
    w = check_watch(watch)
    why = readiness(w["source"], deps)
    if why:
        raise OverflowError(why[0].lower() + why[1:].rstrip("."))
    listed = [j for j in sched.listed() if j.get("kind") == KIND]
    if len(listed) >= MAX_WATCHES:
        raise OverflowError(f"there are already {MAX_WATCHES} \"tell me when\"s - delete one "
                            "first")
    if w["source"] == "email":
        mail = 0
        for j in listed:
            _r, _rule, jw = _watch_of(j["id"], sched)
            if jw and jw.get("source") == "email":
                mail += 1
        if mail >= MAX_EMAIL_WATCHES:
            raise OverflowError(f"there are already {MAX_EMAIL_WATCHES} watching email - each "
                                "signs in to your mail server every few minutes; delete one "
                                "first")
    if w["source"] in ("page", "price"):
        # Checked BEFORE the card is ever raised, not only on each look
        # (jarvis_local_http.private_fetch_problem's own docstring says
        # why it is checked again on every look too).
        import jarvis_local_http as LH
        problem = LH.private_fetch_problem(w["url"])
        if problem:
            raise ValueError(problem)
        pages = _count(listed, sched, ("page", "price"))
        if pages >= MAX_PAGE_WATCHES:
            raise OverflowError(f"there are already {MAX_PAGE_WATCHES} watching a web page - "
                                "each fetches someone else's server; delete one first")
    if w["source"] == "search":
        import jarvis_search as WS
        s = WS.settings()
        # The words are checked the way a chat search's are (a password or
        # key in them is refused) BEFORE any card; the provider is the one
        # chosen in Settings now - never one an app sent.
        p = WS.plan(w["words"], s=s)
        if p.problem:
            raise ValueError(p.problem.rstrip("."))
        w["provider"] = s.get("provider") or ""
        if _count(listed, sched, ("search",)) >= MAX_SEARCH_WATCHES:
            raise OverflowError(f"there are already {MAX_SEARCH_WATCHES} watching a web search "
                                "- delete one first")
    if w["source"] == "github":
        if _count(listed, sched, ("github",)) >= MAX_GITHUB_WATCHES:
            raise OverflowError(f"there are already {MAX_GITHUB_WATCHES} watching GitHub - "
                                "delete one first")
    rule = {"every": "minutes", "watch": w}
    if minutes is not None:
        rule["minutes"] = minutes
    if ends is not None:
        rule["ends"] = ends
    return sched.add_repeat(KIND, rule, what_words(w), source=source)


def add_route(body: dict) -> tuple:
    """POST /api/schedule/add {"kind": "tellme", "source": "email", "sender"}
    or {"kind": "tellme", "source": "home", "entity", "say" | "states",
    "name"?} or {"kind": "tellme", "source": "page", "url"}, or (2026-09-28)
    {"source": "price", "url", "below", "currency"?}, {"source": "search",
    "words"}, {"source": "github", "repo", "event": "ci_done" | "ci_failed" |
    "pr_merged", "branch"? | "pr"}, with "urgent"?, "once"?, "days"? (up to
    90), "minutes"?. 202 and ONE card, like any repeat. A search watch's
    provider is the one chosen in Settings - never one sent here."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "Need a JSON object."}
    watch = {k: body.get(k) for k in ("source", "sender", "entity", "say", "states", "name",
                                      "urgent", "once", "missing", "by", "url", "below",
                                      "currency", "words", "repo", "event", "branch", "pr")}
    ends = None
    days = body.get("days")
    if days is not None:
        if not isinstance(days, (int, float)) or isinstance(days, bool) or days <= 0:
            return 400, {"ok": False, "error": "Days is a number, like 7."}
        now = _sched().now()
        ends = (days_later(now, int(days)) if float(days).is_integer()
                else now + float(days) * 86400.0)
    minutes = body.get("minutes")
    if minutes is not None and (not isinstance(minutes, int) or isinstance(minutes, bool)):
        return 400, {"ok": False, "error": "How often is a whole number of minutes."}
    try:
        job = add(watch, ends=ends, minutes=minutes, source="app")
    except OverflowError as exc:
        return 409, {"ok": False, "error": S._sentence(exc)}
    except (ValueError, TypeError) as exc:
        return 400, {"ok": False, "error": S._sentence(exc)}
    return 202, {"ok": True, "waiting": True, "job": job,
                 "said": "It looks again and again, so it waits for your yes on the card."}


# --------------------------------------------------------------------------
#   Finding a device by the name the owner said ("the washing machine")
# --------------------------------------------------------------------------

#: The Home Assistant kinds of device tried for a name, by what it should do.
_TRY = {
    "opens": ("binary_sensor", "cover", "lock"),
    "closes": ("binary_sensor", "cover", "lock"),
}
_TRY_ANY = ("switch", "binary_sensor", "sensor")


def slug(name: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", name.lower())).strip("_")


def candidates(name: str, say: str) -> list:
    s = slug(name)
    if not s:
        return []
    return [f"{d}.{s}" for d in _TRY.get(say, _TRY_ANY)]


def find_device(name: str, say: str, *, deps: Optional[Deps] = None) -> dict:
    """Which of a few likely Home Assistant names exists for `name` - each
    read is ONE GET of ONE named entity through the gate (home_read), like
    the model's own reads; the whole house is never listed. {"found": [ids],
    "tried": [ids], "why": sentence or ""}."""
    deps = deps or DEPS
    tried = candidates(name, say)
    if not tried:
        return {"found": [], "tried": [], "why": ""}
    why = readiness("home", deps)
    if why:
        return {"found": [], "tried": tried, "why": why}
    import jarvis_home as HOME
    found = []
    for eid in tried:
        p = HOME.plan_states([eid])
        if p.reason_empty:
            continue
        text = HOME.describe(p)
        if not _ok_to_read(HOME_ACTION, "find a device for a \"tell me when\"", text, deps):
            return {"found": [], "tried": tried,
                    "why": readiness("home", deps) or "The approval gate did not let Jarvis "
                                                      "read Home Assistant."}
        out = HOME.run(p, fetch=deps.home_fetch, approved=True)
        if out.get("ok"):
            found.append(eid)
        elif not _not_found(out):
            return {"found": [], "tried": tried,
                    "why": "Home Assistant did not answer, so Jarvis could not look for it."}
    return {"found": found, "tried": tried, "why": ""}


def _not_found(out: dict) -> bool:
    why = str(out.get("reason") or "")
    return "404" in why or "Not Found" in why


# --------------------------------------------------------------------------
#   Instant email: ONE open connection the mail server nudges (IMAP IDLE)
# --------------------------------------------------------------------------

class IdleRefused(Exception):
    """A reason in fixed words - never the server's own, which can quote the
    sign-in name."""


class NoIdle(Exception):
    """The mail server does not offer IDLE."""


def _quote(s: str) -> bytes:
    """An IMAP quoted string, the way imaplib writes one."""
    if any(c in s for c in "\r\n\x00"):
        raise IdleRefused("the sign-in name or password cannot be sent that way")
    try:
        b = s.encode("ascii")
    except UnicodeEncodeError:
        raise IdleRefused("the sign-in name or password has letters the instant watch "
                          "cannot send") from None
    return b'"' + b.replace(b"\\", b"\\\\").replace(b'"', b'\\"') + b'"'


_EXISTS = re.compile(rb"^\*\s+(\d{1,9})\s+EXISTS\b", re.I)
_RECENT = re.compile(rb"^\*\s+(\d{1,9})\s+RECENT\b", re.I)


class _Imap:
    """The instant watch's whole conversation, by hand, on one socket: LOGIN,
    CAPABILITY, EXAMINE (read-only), IDLE, DONE, LOGOUT. Never FETCH, SEARCH,
    STORE or anything that reads or changes a message - a nudge only makes
    the ordinary look run, through the gate."""

    def __init__(self, sock):
        self.sock = sock
        self.buf = b""
        self.n = 0
        self.idle_tag = None
        self.exists = 0

    def _fill(self, deadline: float) -> bool:
        left = deadline - time.monotonic()
        if left <= 0:
            return False
        self.sock.settimeout(left)
        try:
            chunk = self.sock.recv(65536)
        except socket.timeout:
            return False
        if not chunk:
            raise ConnectionError("the mail server closed the connection")
        self.buf += chunk
        if len(self.buf) > 1 << 20:
            raise ConnectionError("the mail server sent too much at once")
        return True

    def line(self, timeout: float) -> Optional[bytes]:
        """One response line, or None when nothing came within `timeout`."""
        deadline = time.monotonic() + timeout
        while b"\r\n" not in self.buf:
            if not self._fill(deadline):
                return None
        line, _, self.buf = self.buf.partition(b"\r\n")
        m = re.search(rb"\{(\d{1,7})\}$", line)
        if m:
            # A literal: its bytes follow, then the rest of the line.
            need = int(m.group(1))
            hard = time.monotonic() + IDLE_TIMEOUT
            while len(self.buf) < need:
                if not self._fill(hard):
                    raise ConnectionError("the mail server stopped half way")
            line += b" " + self.buf[:need]
            self.buf = self.buf[need:]
            rest = self.line(IDLE_TIMEOUT)
            if rest is None:
                raise ConnectionError("the mail server stopped half way")
            line += rest
        return line

    def command(self, words: bytes, what: str, timeout: float = IDLE_TIMEOUT) -> list:
        self.n += 1
        tag = b"J%d" % self.n
        self.sock.sendall(tag + b" " + words + b"\r\n")
        seen = []
        while True:
            got = self.line(timeout)
            if got is None:
                raise ConnectionError(f"the mail server did not answer ({what})")
            if got.startswith(tag + b" "):
                if got[len(tag) + 1:].split(b" ", 1)[0].upper() != b"OK":
                    raise IdleRefused(what)
                return seen
            seen.append(got)

    def greet(self) -> None:
        got = self.line(IDLE_TIMEOUT)
        if got is None or not got.upper().startswith((b"* OK", b"* PREAUTH")):
            raise ConnectionError("the mail server did not say hello")

    def login(self, user: str, password: str) -> None:
        try:
            self.command(b"LOGIN " + _quote(user) + b" " + _quote(password), "sign-in")
        except IdleRefused as exc:
            if str(exc) == "sign-in":
                raise IdleRefused("the mail server refused the sign-in") from None
            raise

    def capable(self) -> bool:
        seen = self.command(b"CAPABILITY", "CAPABILITY")
        words = b" ".join(seen).upper().replace(b"]", b" ").split()
        return b"IDLE" in words

    def examine(self, mailbox: str) -> None:
        seen = self.command(b"EXAMINE " + _quote(mailbox), "open the mailbox")
        for got in seen:
            m = _EXISTS.match(got)
            if m:
                self.exists = int(m.group(1))

    def idle(self) -> list:
        """Start listening. The lines the server sent first - a new-mail
        line held back while it was not listening (during the looks a nudge
        started) arrives here, and must not be lost."""
        self.n += 1
        tag = b"J%d" % self.n
        self.sock.sendall(tag + b" IDLE\r\n")
        seen = []
        while True:
            got = self.line(IDLE_TIMEOUT)
            if got is None:
                raise ConnectionError("the mail server did not start listening")
            if got.startswith(b"+"):
                self.idle_tag = tag
                return seen
            if got.startswith(tag + b" "):
                raise NoIdle()
            seen.append(got)

    def wait(self, timeout: float) -> list:
        """The lines the server sent while listening, waiting at most
        `timeout` for the first."""
        out = []
        got = self.line(timeout)
        while got is not None:
            out.append(got)
            got = self.line(0.05)
        return out

    def done(self) -> list:
        """Stop listening. The lines that came meanwhile."""
        tag, self.idle_tag = self.idle_tag, None
        self.sock.sendall(b"DONE\r\n")
        seen = []
        while True:
            got = self.line(IDLE_TIMEOUT)
            if got is None:
                raise ConnectionError("the mail server did not answer (DONE)")
            if tag is not None and got.startswith(tag + b" "):
                return seen
            seen.append(got)

    def new_mail(self, lines: list) -> bool:
        """Did these lines say new mail arrived? EXISTS going UP, or RECENT."""
        news = False
        for got in lines:
            m = _EXISTS.match(got)
            if m:
                n = int(m.group(1))
                if n > self.exists:
                    news = True
                self.exists = n
            elif _RECENT.match(got) and int(_RECENT.match(got).group(1)) > 0:
                news = True
        return news

    def close(self) -> None:
        try:
            if self.idle_tag is not None:
                self.sock.sendall(b"DONE\r\n")
            self.n += 1
            self.sock.sendall(b"J%d LOGOUT\r\n" % self.n)
        except Exception:
            pass
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


def _default_idle_connect(p) -> _Imap:
    """Open, sign in, check IDLE is offered, open the mailbox read-only. The
    password is read fresh and handed to the socket only."""
    import jarvis_email as MAIL
    raw = socket.create_connection((p.host, p.port), timeout=IDLE_TIMEOUT)
    try:
        sock = MAIL.tls_context(p.host).wrap_socket(raw, server_hostname=p.host)
    except Exception:
        raw.close()
        raise
    return _open(_Imap(sock), p)


def _open(conn: _Imap, p) -> _Imap:
    import jarvis_email as MAIL
    try:
        conn.greet()
        conn.login(MAIL.imap_user(), MAIL.imap_password())
        if not conn.capable():
            raise NoIdle()
        conn.examine(p.mailbox)
        return conn
    except BaseException:
        conn.close()
        raise


def _default_standby() -> bool:
    try:
        import jarvis_power
        return str(jarvis_power.current()) == "standby"
    except Exception:
        return False


#: What the line under an email watch says about the instant watch.
IDLE_WORDS = {
    "on": "Instant: your mail server tells Jarvis the moment mail arrives.",
    "standby": "Jarvis is on standby, so it looks every few minutes, not instantly.",
    "stopped": "Stop everything closed the instant connection; it opens again at the next "
               "look.",
    "unsupported": "Your mail server does not offer instant notice, so Jarvis looks every "
                   "few minutes.",
}
STOPPED_WORDS = ("The instant email watch closed its connection to your mail server; your "
                 "\"tell me when\"s still look every few minutes.")


def _email_jobs(sched) -> list:
    """The ids of the email watches that are on (not paused, not waiting)."""
    out = []
    try:
        for j in sched.listed():
            if j.get("kind") != KIND or j.get("state") != "active":
                continue
            _r, _rule, w = _watch_of(j["id"], sched)
            if (w or {}).get("source") == "email":
                out.append(j["id"])
    except Exception:
        return []
    return out


class _IdleWatch:
    """The one instant connection (module docstring, INSTANT EMAIL)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.thread = None
        self.ev = None
        self.conn = None
        self.state = "off"
        self.why = ""
        self.heard = 0.0
        self.retry_at = 0.0

    # -- what the rest of the module asks ------------------------------------
    def healthy(self) -> bool:
        with self.lock:
            return (self.state == "on" and self.thread is not None and self.thread.is_alive()
                    and time.time() - self.heard < IDLE_RENEW_SECONDS + 120)

    def status(self) -> dict:
        with self.lock:
            return {"state": self.state, "why": self.why, "heard": self.heard}

    def note_words(self) -> str:
        st = self.status()
        if st["state"] == "dropped":
            return (f"Instant watch not connected ({st['why']}) - looking every few minutes "
                    "instead.")
        return IDLE_WORDS.get(st["state"], "")

    def _set(self, ev, state: str, why: str = "") -> None:
        with self.lock:
            if ev is not self.ev and ev is not None:
                return      # an older connection's thread: it is not the one shown
            self.state, self.why = state, why

    # -- starting and stopping -----------------------------------------------
    def ensure(self, deps: Deps, sched) -> None:
        """Open the connection if an email watch is on and nothing stops it.
        Called after every email look, so it is also how it comes back after
        Standby, Stop everything or a server with no IDLE."""
        if deps.idle_connect is None and deps.email_look is not None:
            return      # the looks are faked (a test): never a real socket
        standby = deps.standby or _default_standby
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                return
            if time.time() < self.retry_at:
                return
        if standby():
            self._set(None, "standby")
            return
        if not _email_jobs(sched) or readiness("email", deps):
            self._set(None, "off")
            return
        ev = threading.Event()
        t = threading.Thread(target=self._run, args=(deps, sched, ev),
                             name="jarvis-tellme-idle", daemon=True)
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                return
            self.ev, self.thread = ev, t
            self.state, self.why = "connecting", ""
        t.start()

    def stop(self, state: str = "stopped", why: str = "") -> Optional[str]:
        """Close it now. The sentence Stop everything says, or None when
        nothing was open."""
        with self.lock:
            running = self.thread is not None and self.thread.is_alive()
            ev, conn = self.ev, self.conn
            if ev is not None:
                ev.set()
            self.conn = None
            if running:
                self.state, self.why = state, why
        if conn is not None:
            conn.close()
        return STOPPED_WORDS if running else None

    def join(self, timeout: float = 5.0) -> None:
        t = self.thread
        if t is not None:
            t.join(timeout)

    # -- the connection ----------------------------------------------------------
    def _run(self, deps: Deps, sched, ev) -> None:
        import jarvis_email as MAIL
        standby = deps.standby or _default_standby
        fails = 0
        while not ev.is_set():
            if standby():
                return self._set(ev, "standby")
            if not _email_jobs(sched) or readiness("email", deps):
                return self._set(ev, "off")
            p = MAIL.plan(1, unread_only=False)
            text = (f"Jarvis would like to keep one connection open to your mail server "
                    f"({p.host}:{p.port}, mailbox \"{p.mailbox}\") so it hears the moment new "
                    "mail arrives, for a \"tell me when\". It reads nothing over it: each new "
                    "email's From line is then read the usual way, with PEEK.")
            if not _ok_to_read(EMAIL_ACTION, "keep one connection open for new mail", text,
                               deps):
                return self._set(ev, "off")
            self._set(ev, "connecting")
            conn = None
            try:
                conn = (deps.idle_connect or _default_idle_connect)(p)
                with self.lock:
                    if ev.is_set():
                        conn.close()
                        return None
                    self.conn = conn
                conn.idle()
                # Mail that came since the last look, while nothing was
                # listening: one ordinary look now, before the regular looks
                # start skipping the sign-in.
                self._nudge(deps, sched)
                with self.lock:
                    self.heard = time.time()
                self._set(ev, "on")
                fails = 0
                self._listen(conn, deps, sched, ev, standby)
                if not ev.is_set():
                    return None     # it ended by itself: no watch left, or standby
            except NoIdle:
                with self.lock:
                    self.retry_at = time.time() + NO_IDLE_RETRY
                self._set(ev, "unsupported")
                return None
            except IdleRefused as exc:
                why = str(exc)
            except Exception as exc:
                why = f"the connection dropped ({type(exc).__name__})"
            else:
                why = ""
            finally:
                if conn is not None:
                    with self.lock:
                        if self.conn is conn:
                            self.conn = None
                    conn.close()
            if ev.is_set():
                return None
            fails += 1
            self._set(ev, "dropped", why or "the connection dropped")
            _audit("tellme.instant.dropped", {"fails": fails})
            if ev.wait(IDLE_BACKOFF[min(fails, len(IDLE_BACKOFF)) - 1]):
                return None
        return None

    def _listen(self, conn: _Imap, deps: Deps, sched, ev, standby) -> None:
        renewed = listed = time.monotonic()
        nudge_at = None
        while not ev.is_set():
            got = conn.wait(IDLE_TICK)
            if got:
                with self.lock:
                    self.heard = time.time()
            if conn.new_mail(got) and nudge_at is None:
                nudge_at = time.monotonic()
            if ev.is_set():
                return
            if standby():
                self._set(ev, "standby")
                return
            if time.monotonic() - listed >= IDLE_LIST_SECONDS:
                listed = time.monotonic()
                if not _email_jobs(sched):
                    self._set(ev, "off")
                    return
            if nudge_at is not None and time.monotonic() - nudge_at >= IDLE_DEBOUNCE:
                conn.new_mail(conn.done())
                nudge_at = None
                self._nudge(deps, sched)
                if conn.new_mail(conn.idle()):
                    nudge_at = time.monotonic()     # more came during the looks
                renewed = time.monotonic()
                with self.lock:
                    self.heard = time.time()
            elif time.monotonic() - renewed >= IDLE_RENEW_SECONDS:
                if conn.new_mail(conn.done()):
                    self._nudge(deps, sched)
                if conn.new_mail(conn.idle()):
                    nudge_at = time.monotonic()
                renewed = time.monotonic()
                with self.lock:
                    self.heard = time.time()

    @staticmethod
    def _nudge(deps: Deps, sched) -> None:
        """New mail: every email watch looks now, the ordinary way."""
        for jid in _email_jobs(sched):
            try:
                with _job_lock(jid):
                    _look(jid, deps, sched, True)
            except Exception:
                pass


IDLE = _IdleWatch()

try:
    import jarvis_stop_all as _STOP_ALL
    _STOP_ALL.register("instant_email", lambda: IDLE.stop("stopped"))
except Exception:  # pragma: no cover - shipped beside it on the PC
    pass


S.register_kind(KIND, NOUN, LOCK_SCREEN, has_text=True, owner_listed=True,
                repeatable=True, silent=True, first_now=True, leaves=True,
                what="set up a \"tell me when\" (it looks every few minutes and only "
                     "notifies)",
                check=check_rule, card=card, add=add_route, note=note, fields=fields,
                on_fire=lambda job_id: _on_fire(job_id))
