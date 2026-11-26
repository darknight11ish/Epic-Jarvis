"""jarvis_privacy_removal.py - the core of the personal-data discovery and
removal tool: the mode dial, the tracker, the profile reader, the official
portals and the self-explainer.

    py -3 jarvis_privacy_removal.py           what this PC holds, masked
    py -3 jarvis_privacy_removal.py overview   what the tool does, in words

WHAT THIS IS FOR

The owner asked (2026-11-26) for a personal-data removal tool in Atlas: find
where his name, home address, phone number and email address are listed by
data brokers, ask those brokers to delete the listings, and check afterwards
whether they really went - without handing his details to a stranger's cloud
service unless he says so.

THREE MODES, ONE DIAL (the owner's design, 2026-11-26)

  * `local` (the DEFAULT, and what this file ships as) - everything happens on
    this PC. The directory of brokers is a local cache, the deletion requests
    are emails sent through the owner's own Gmail App Password, and the
    confirmation links and CAPTCHA forms are queued for HIM to click. His
    details never leave the PC.
  * `optery_api` (opt-in) - a paid commercial service (Optery) does the parts
    that need a browser: the CAPTCHA/Turnstile forms, the before/after
    screenshots, the brokers spread across the US and Canada. It can only do
    that if his details are sent to Optery over HTTPS, so switching to it
    raises ONE consent card that says exactly that, and a denied card changes
    nothing.
  * `hybrid` (opt-in) - Optery for the brokers it covers, this PC for the rest,
    and the same consent card, because the same details go to the same cloud.

WHY LOCAL IS THE DEFAULT, IN ONE SENTENCE: the tool's whole point is that the
owner's home address stops being on strangers' computers, so the version that
puts it on ONE more computer first (a commercial broker's API) must be his
decision and not a default. The decision record is
`decisions.d/2026-11-26-personal-data-removal-local-by-default.md`.

WHAT IS HERE, AND IN WHAT ORDER

1. WHERE THE FILES LIVE - `config_dir()` and the three paths below it. The
   settings file `privacy-removal.json` sits beside `manner.json` and
   `answer-style.json`; the owner's own details and the tracker live in
   `privacy/` under it. NOTHING of the owner's is ever in this repository:
   `profile.json` is his, on his PC, and this file only reads it.
2. `JARVIS_CONFIG_DIR` FIRST, then `OPENJARVIS_CONFIG_DIR`, then
   `~/.openjarvis` - and that order is deliberate: the suites point
   `JARVIS_CONFIG_DIR` at a temporary folder, and a suite must never read or
   write the owner's real `privacy/` folder. Every test in
   `backend/test_privacy_removal.py` runs in one.
3. THE MODE DIAL - `mode()`, `read_mode()`, `write_mode()` and `set_mode()`.
   Only `local` is written without a card; `optery_api` and `hybrid` raise the
   cloud-PII consent card (`CLOUD_CONSENT_TEXT`) through the house gate, and a
   denial, a timeout or a withdrawal leaves the mode exactly as it was.
4. THE PROFILE - `load_profile()` reads `privacy/profile.json` and never
   logs, prints or returns it in a sentence; `masked_profile()` and
   `profile_words()` are the ONLY forms that reach a chat answer and they carry
   a label and the last four characters, never a whole address, phone number or
   email address.
5. THE TRACKER - `connect()` creates `privacy/tracker.db` with the three
   tables the owner specified (`brokers`, `requests`, `official_portals`), and
   `counts()`/`tracker_summary()` read it. An empty tracker answers with zeros
   in plain words: it never invents a number and never refuses to answer.
6. THE TWO FREE OFFICIAL PORTALS - `official_portals()` and
   `official_portals_words()`. Google's Results About You and (for California)
   California DROP are one-time/periodic wins that need no service and no
   email; they are a GUIDED CHECKLIST with a real link each, never scraped and
   never clicked for the owner.
7. THE SELF-EXPLAINER - `privacy_explain(topic)` for the four topics the
   owner named (`overview`, `pros_cons`, `limits`, `official_portals`) and
   `get_prompt_context()` for the model's own grounding. Every one of them is
   built from the LIVE state (the mode, whether the Gmail App Password is set,
   whether an Optery key is set, what the tracker holds), so an answer can
   never describe a tool this PC does not have or claim a removal that was
   never confirmed.
8. `prompt()` - the sentences the chat grammar in `jarvis_quick.py` claims, so
   "what is the data removal tool" and "what can't the data removal tool do"
   are answered here by intent and never handed to the model. The mode-change
   sentences go through `jarvis_settings_registry.set_data_removal_mode`, the
   ONE changeable row, which calls `set_mode()` below - so a typed change and a
   later Settings switch are the same function, the same card and the same
   rule.
9. THE BROKER DIRECTORY (PR 2) - `sync_directory()` downloads Optery's
   Open-Source Data Broker Directory, `parse_directory()` turns it into the
   `brokers` table's own columns, and the parsed copy is cached at
   `privacy/brokers.json` ON THIS PC. The directory is never vendored into this
   repository: it is third-party data under CC BY-NC-SA 4.0, it is 766 KB of
   churn, and the lot of it would be stale the week it landed.
10. THE CARDED BATCH SENDER (PR 2) - `send_optout_batch(template)` picks the
    next brokers that are asked by EMAIL, raises ONE approval card naming the
    exact brokers, the exact template (`ccpa`, `gdpr` or `generic`) and the
    count, and only on a person's yes sends through the owner's own Gmail App
    Password (`#1506`, Credential Manager) and records `sent_at` plus
    `verify_after` on every row. HARD CAP 20 PER CARD AND 250 A DAY. A denied,
    timed-out or refused card sends NOTHING and writes nothing.
11. THE REPLY SCANNER (PR 2) - `check_replies()` reads the owner's own mailbox
    over IMAP, finds the brokers' answers, and moves a request to
    `needs_verify_click` when a confirmation link or an ID request arrives. It
    NEVER clicks that link - the owner does - and it never marks anything
    `removed` from an email, a CAPTCHA page, a Cloudflare 403 or a timeout.
12. THE MANUAL CHECKLIST AND THE STATUS ANSWER (PR 2) -
    `manual_checklist_words()` lists the web-form brokers with their direct
    opt-out URLs and the two free official portals for the owner to click
    himself, and `status_words()` reports the live counts by status, the rows
    whose wait window has passed with no answer, and the official-portal
    checklist.

WHAT THIS SLICE STILL DOES NOT DO, PLAINLY

  * NO OPTERY CALL AND NO OPTERY KEY. The `optery_api` and `hybrid` modes exist
    as a dial and as a consent card, and this file only ASKS whether a key is
    present (through the same credential helper every other named secret uses).
    The adapter, the Credential Manager setup and the status/screenshot sync
    are PR 3; until then the two cloud modes are a choice with no engine behind
    them, and the answer says so.
  * No route, no Settings page, no desktop or phone screen. The mode dial is
    changeable from chat and from the settings registry, and the engine is
    driven from chat; the screens are a separate piece of work.
  * Nothing is in `_where.SHIPPED` yet, on the owner's own ruling: only the
    pull request that wires a live caller may ship a module whole. Every call
    site is still a GUARDED import, so the published base - which does not carry
    this module - imports and behaves exactly as before. PR 3 moves it into
    `SHIPPED` with the adapter that completes the feature.

STDLIB ONLY, ON PURPOSE (the owner's requirement, 2026-11-26). This file
imports `datetime`, `email`, `imaplib`, `json`, `os`, `re`, `smtplib`,
`sqlite3`, `threading`, `time`, `urllib` and `pathlib` - every one of them
Python's own standard library, and nothing third-party, so CI's exact package
list can never be broken by it.

NO NETWORK UNLESS THE OWNER ASKS, AND NEVER IN A TEST. The only three things
here that reach a network are `sync_directory()` (which downloads the public
directory), `_deliver()` (which sends one email through the owner's own Gmail
account) and `check_replies()` (which reads that same mailbox). Each one takes
its transport as an injected callable - `opener`, `transport`, `imap` - so the
suite drives the REAL code with fake doubles and opens no socket at all.

NO PII, ANYWHERE. Nothing in this file writes a detail of the owner's to a log,
an audit line, an error message, an answer or a card's own summary. The masked
labels exist for that reason and `mask_value()` is the only function that turns
a stored value into something a person may read.
"""
from __future__ import annotations

import email.message
import email.utils
import imaplib
import json
import os
import re
import smtplib
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------
#   The three modes and the files they live in
# --------------------------------------------------------------------------

#: The three modes, in the order a person wants to read them.
MODES = ("local", "optery_api", "hybrid")

#: The shipped default, and the reason: see the module's own paragraph above.
DEFAULT_MODE = "local"

#: The two modes that send the owner's details to a cloud service, and
#: therefore the two that can only be chosen behind the consent card.
CLOUD_MODES = ("optery_api", "hybrid")

#: The settings file, beside `manner.json` and `answer-style.json`.
MODE_FILE = "privacy-removal.json"

#: The folder under the settings folder that holds the owner's own things.
PRIVACY_DIR = "privacy"

#: The owner's details. NEVER in this repository, never committed, never logged.
PROFILE_FILE = "profile.json"

#: The tracker database.
TRACKER_FILE = "tracker.db"

#: What each mode is called when a person reads it. The ids never change; these
#: are the words in a chat answer.
MODE_NAMES = {
    "local": "local (this PC only)",
    "optery_api": "Optery's cloud API",
    "hybrid": "hybrid (Optery for covered brokers, this PC for the rest)",
}

#: The mode-change words a person may type, mapped to the mode id. The
#: settings registry row and `prompt()` below both read THIS table, so the two
#: can never accept different words for the same mode.
MODE_WORDS = {
    "local": "local",
    "local only": "local",
    "local mode": "local",
    "on this pc": "local",
    "this pc": "local",
    "private": "local",
    "optery": "optery_api",
    "optery api": "optery_api",
    "optery's api": "optery_api",
    "optery_api": "optery_api",
    "optery mode": "optery_api",
    "the optery api": "optery_api",
    "hybrid": "hybrid",
    "hybrid mode": "hybrid",
    "both": "hybrid",
    "mixed": "hybrid",
}

#: The two free official portals the owner named (2026-11-26), with the real
#: links and what each one really does. Reference data, never the owner's.
OFFICIAL_PORTALS = (
    {
        "portal_id": "google_results_about_you",
        "name": "Google Results About You",
        "url": "https://myactivity.google.com/results-about-you",
        "note": ("Asks Google to take your phone number, home address or email "
                 "address out of Google Search results. It removes the RESULT, "
                 "not the page: the listing on the broker's own site stays until "
                 "that broker deletes it, which is what the rest of this tool is "
                 "for."),
    },
    {
        "portal_id": "california_drop",
        "name": "California DROP",
        "url": "https://privacy.ca.gov/drop/",
        "note": ("One request to every data broker registered in California (600+ "
                 "of them) through Delete Request and Opt-out Platform. Every one "
                 "of them must process a DROP request at least every 45 days. This "
                 "is the one to file FIRST if you are a California resident."),
    },
)

#: The credential the optional Optery adapter will read in PR 3. Named here, in#: one place, so the presence check and the adapter can never disagree about
#: which secret they mean. The value is never read into an answer.
OPTERY_ENV = "JARVIS_OPTERY_API_KEY"
OPTERY_TARGET = "Jarvis Backend/Optery API key"

#: Where this PC's own mailbox password lives, through jarvis_email's own
#: helpers: the Gmail App Password (`#1506`, the owner's decision of
#: 2026-11-25). Named here only so the state line can say whether it is set;
#: the value itself is never read into a sentence.
GMAIL_ENV = "JARVIS_IMAP_PASSWORD"
GMAIL_TARGET = "Jarvis Backend/IMAP password"

#: The tool names this feature owns, in `jarvis_asks_first.TOOL_GROUPS`' own
#: shape: (group title, (tool names...)). `jarvis_asks_first.py` appends this
#: row under a guarded import, the same way `jarvis_storage_health.TOOL_ROWS`
#: is appended, so the owner's spec's "one canonical `Privacy` category, zero
#: uncategorised tools" exists from this slice onward and the category work can
#: find it.
#:
#: ONLY WHAT REALLY EXISTS IS NAMED. PR 1 answered `privacy_explain`; PR 2 adds
#: the four reads and the one carded send the local engine really has:
#: `privacy_status`, `privacy_manual_checklist`, `privacy_sync_directory`,
#: `privacy_check_replies` and `privacy_send_optout_batch`. Every one of them is
#: a `privacy_*` intent in `jarvis_quick.py` and a real function below - none is
#: a placeholder. PR 3 adds `privacy_optery_action` (and the `privacy_set_mode`
#: name the spec's table gives the consent-carded switch PR 1 already built as
#: `privacy_mode_change`), each to this same row as it becomes real. Claiming
#: them now would be the one thing this file's own docstring forbids.
#:
#: NONE OF THEM IS A SWITCH. `_app_can_switch` in `jarvis_asks_first.py` only
#: lets a row the tools list can really turn on be switched, so this category is
#: present in TOOL_GROUPS (where the categories live) and absent from
#: SWITCHABLE_GROUPS (where the switches live): there is nothing here an app may
#: turn off, and the ask-first page draws no empty group.
TOOL_ROWS = (
    ("Privacy", (
        "privacy_explain",
        "privacy_status",
        "privacy_manual_checklist",
        "privacy_sync_directory",
        "privacy_check_replies",
        "privacy_send_optout_batch",
    )),
)

#: The gate action the cloud consent card is raised under. It is an EXISTING
#: action - the same `change_own_config` every other "change one of Jarvis's own
#: settings" card uses, tier `ask` - so this file adds no gate row, no tier row
#: and no settings-file key of its own. That is the route
#: `jarvis_phone_apps.py` took on 2026-11-02 and it is the route here.
CONSENT_ACTION = "change_own_config"

#: The card's own words. They name the four kinds of detail and the fact that
#: they would leave this PC, in that order, because that is what the owner is
#: being asked to agree to - and the masked labels from HIS profile, never a
#: value. The spec's own wording (2026-11-26, section 0).
CLOUD_CONSENT_TEXT = (
    "Switch personal data removal to Optery's cloud API?\n"
    "From then on, your name, home address, phone number and email address - the "
    "details in the removal profile on this PC - are sent over HTTPS to Optery's "
    "API at optery.com, so their service can scan brokers and file removals for "
    "you. Nothing is sent before you approve this card, and denying it leaves "
    "data removal exactly as it is now.\n"
    "What stays true either way: every send and every API call still needs its "
    "own approval card, and a removal is never reported as done until the verify "
    "pass confirms it."
)

#: The outcomes a consent card can end in, in the owner's own words. The same
#: four the web-search switch already uses: a card nobody answered is NOT a no
#: and is never reported as a change.
CARD_WORDS = {
    "changed": "You approved the card, so data removal is now using {mode}.",
    "denied": ("The card was turned down, so data removal stays on {was}. "
               "Nothing was sent anywhere."),
    "timed_out": ("Nobody answered the card in time, so data removal stays on "
                  "{was}. Nothing was sent anywhere."),
    "withdrawn": ("The mode changed back while the card waited, so approving it "
                  "would change nothing. Data removal is on {was}."),
    "refused": ("The card could not be approved ({why}), so data removal stays on "
                "{was}. Nothing was sent anywhere."),
    "failed": ("The card was approved, but the mode could not be saved "
               "({why}), so data removal stays on {was}."),
}

#: The statuses a tracked request can be in (the owner's list, 2026-11-26),
#: in the order a person reads them: what is waiting, what is out, what needs
#: his click, what is confirmed, and what went wrong.
STATUSES = ("queued", "sent", "needs_verify_click", "pending_window", "removed",
            "blocked_captcha", "failed")

#: The `brokers.method` values (the owner's list).
METHODS = ("email", "web_form", "optery_api", "official_portal")

#: The methods that end with the owner clicking something himself, so a broker
#: on one of them with no request row is a `manual_todo`.
MANUAL_METHODS = ("web_form", "official_portal")

# --------------------------------------------------------------------------
#   The local engine's own numbers (PR 2)
# --------------------------------------------------------------------------
#
# EVERY NUMBER HERE IS THE OWNER'S, from the spec of 2026-11-26, and each one is
# a boundary this file refuses to cross rather than a target it aims at:
#
#   * 20 brokers per approval card and 250 emails a day - the hard caps in
#     section 1.3. Gmail's own limit is about 500 a day and the caps sit well
#     under it on purpose: this tool files deletion requests, not a marketing
#     campaign, and a mistake must cost 20 emails rather than 500.
#   * 7 days for a people-search site and 45 for a statutory CCPA/GDPR request -
#     the two wait windows in section 2 (a deletion request is not a removal
#     until the window has passed and the verify pass agrees).
#   * 90 days for the re-list check once a removal is confirmed, because brokers
#     re-scrape public sources and a removal is not a one-off erasure.

#: Gmail's own servers: the App Password path (`#1506`) is an ordinary Gmail
#: account, so SMTP over 465 and IMAP over 993 with the same login.
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
MAIL_TIMEOUT = 30

#: The gate action the batch card is raised under. It is the EXISTING
#: `send_email` action - the one outbound-mail authorization this PC already
#: has, already tier "ask" in the shipped settings file and already in the
#: gate's own "acts only on tier ask" table - so this file adds no gate row, no
#: tier row and no settings key, exactly as PR 1 reused `change_own_config` for
#: the consent card. It is honest rather than a shortcut: what the card
#: authorizes IS email leaving this PC from the owner's own account, one card
#: for one batch instead of one card for one email.
BATCH_ACTION = "send_email"

#: The three templates the owner's spec names, and the words a card uses for
#: each. `generic` is the default: a deletion request that cites no statute is
#: always true, while a CCPA or GDPR citation is only true for the person and
#: the jurisdiction it names.
TEMPLATES = ("ccpa", "gdpr", "generic")
TEMPLATE_NAMES = {
    "ccpa": "CCPA (the California Consumer Privacy Act)",
    "gdpr": "GDPR (the EU General Data Protection Regulation, Article 17)",
    "generic": "a general deletion request (no statute cited)",
}

#: The wait window each template earns, in days (the owner's spec, section 2).
#: A statutory request gets the 45-day window the law allows; a plain deletion
#: request to a people-search site gets 7, because those sites answer quickly or
#: not at all. The window is stored PER ROW as `verify_after`, so changing this
#: table later can never move a request that is already in flight.
WAIT_DAYS = {"ccpa": 45, "gdpr": 45, "generic": 7}

#: The two hard caps (section 1.3).
BATCH_CAP = 20
DAILY_CAP = 250

#: Once a removal is confirmed, when to look again.
RELIST_DAYS = 90

#: The public directory this PC caches. Optery's open-source list, JSON endpoint,
#: `master` branch - the file is 766 KB of third-party data under CC BY-NC-SA
#: 4.0 and is NEVER in this repository.
DIRECTORY_URL = ("https://raw.githubusercontent.com/optery/optery-data-brokers-"
                 "directory/master/data/data-brokers.json")
DIRECTORY_NAME = "Optery's Open-Source Data Broker Directory"
DIRECTORY_LICENSE = ("CC BY-NC-SA 4.0, Optery, Inc. - cached on this PC only, "
                     "never in this repository")
DIRECTORY_TIMEOUT = 30

#: A downloaded directory bigger than this is refused rather than parsed: the
#: real one is under a megabyte, so 16 MB is already a symptom of something
#: wrong (a captive portal's error page, a redirect to a video, a bad mirror).
DIRECTORY_MAX_BYTES = 16 * 1024 * 1024

#: The local cache's own file, inside `privacy/`.
BROKERS_FILE = "brokers.json"

#: How many replies one scan fetches, newest first, and how many listing pages
#: one verify pass reads. Bounded so a mailbox with years of mail cannot turn one
#: chat sentence into a hundred round trips.
MAX_SCAN_MESSAGES = 60
PAGE_TIMEOUT = 20
PAGE_MAX_BYTES = 2 * 1024 * 1024

#: How many web-form brokers one checklist answer lists before it says "and N
#: more". The count is always the real one; only the printed list is bounded.
CHECKLIST_LIMIT = 25

# --------------------------------------------------------------------------
#   Where the files live: JARVIS_CONFIG_DIR first
# --------------------------------------------------------------------------


def config_dir() -> Path:
    """Jarvis's settings folder, for this file.

    THE ORDER IS THE POINT (the owner's spec, 2026-11-26: "`JARVIS_CONFIG_DIR`
    must be respected first so all tests run in isolated temp folders").
    `JARVIS_CONFIG_DIR`, then `OPENJARVIS_CONFIG_DIR`, then the framework's own
    `CONFIG_DIR`, then `~/.openjarvis` - which on Windows is
    `%USERPROFILE%\\.openjarvis`, exactly where the owner asked for the profile
    and the tracker to live.

    Most modules in this folder read `OPENJARVIS_CONFIG_DIR` first. That is
    fine for them and is NOT copied here: a suite that sets only
    `JARVIS_CONFIG_DIR` must be able to keep this file away from the owner's
    real profile, and a test that accidentally wrote into
    `~/.openjarvis/privacy/` would be the one bug this tool cannot afford.
    """
    for name in ("JARVIS_CONFIG_DIR", "OPENJARVIS_CONFIG_DIR"):
        raw = os.environ.get(name)
        if raw:
            return Path(os.path.expanduser(raw))
    try:
        import jarvis_framework as fw
        folder = getattr(fw, "CONFIG_DIR", None)
        if folder:
            return Path(folder)
    except Exception:                       # noqa: BLE001 - an older PC
        pass
    return Path.home() / ".openjarvis"


def privacy_dir() -> Path:
    """`<settings folder>/privacy` - the owner's own folder, never in git."""
    return config_dir() / PRIVACY_DIR


def mode_path() -> Path:
    """`privacy-removal.json`, the mode dial."""
    return config_dir() / MODE_FILE


def profile_path() -> Path:
    """`privacy/profile.json` - the owner's details. Never read aloud, never
    logged, never in this repository."""
    return privacy_dir() / PROFILE_FILE


def tracker_path() -> Path:
    """`privacy/tracker.db` - the SQLite tracker."""
    return privacy_dir() / TRACKER_FILE


def _read_json(path: Path) -> tuple:
    """(the document, "") or (None, why it could not be read, in plain words).

    A missing file is NOT an error: every caller below says "not set up yet" in
    its own words rather than treating an absent file as a fault. The `why`
    never contains a value from the file - only the file's name and the kind of
    problem - so a damaged profile cannot leak itself through an error.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, "there is no such file yet"
    except OSError as exc:
        return None, f"it could not be read ({type(exc).__name__})"
    try:
        doc = json.loads(raw)
    except ValueError:
        return None, "it is not readable JSON"
    if not isinstance(doc, dict):
        return None, "it is not the shape Jarvis writes"
    return doc, ""


def _write_json(path: Path, doc: dict) -> None:
    """Write one small JSON file atomically, LF endings, UTF-8.

    The temporary file is a sibling so the replace is on the same volume, which
    is what makes it atomic on Windows: a half-written settings file would read
    as "not set up", and the owner's mode would quietly go back to the default.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(doc, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp, path)


# --------------------------------------------------------------------------
#   The mode dial
# --------------------------------------------------------------------------


def read_mode() -> tuple:
    """(the mode this PC is on, where it came from) - never raises.

    `local` when there is no file, when the file cannot be read, or when it
    holds something this file does not know: the shipped default is the safe
    one, and a damaged dial must not become a cloud mode by accident.
    """
    doc, why = _read_json(mode_path())
    if doc is None:
        return DEFAULT_MODE, ("the shipped default"
                              if why == "there is no such file yet"
                              else f"the shipped default ({why})")
    raw = doc.get("mode")
    mode = str(raw if isinstance(raw, str) else "").strip().lower()
    if mode in MODES:
        return mode, "the saved setting on this PC"
    return DEFAULT_MODE, ("the shipped default (the saved value is not one of "
                          + ", ".join(MODES) + ")")


def mode() -> str:
    """The active mode: always one of `MODES`, never a guess."""
    return read_mode()[0]


def write_mode(value: str) -> str:
    """Save one of `MODES`. The ONLY writer of `privacy-removal.json`.

    Raises `ValueError` for anything else - an unknown value is a bug in the
    caller, not a mode. Nothing else in this file writes the dial, so every
    route to a cloud mode goes through the consent card in `set_mode()`.
    """
    want = str(value or "").strip().lower()
    if want not in MODES:
        raise ValueError("a data removal mode is one of: " + ", ".join(MODES))
    _write_json(mode_path(), {"mode": want, "saved_at": _now_text()})
    return want


def mode_from_words(words: str) -> Optional[str]:
    """The mode a person's words name, or None (never a guess)."""
    said = " ".join(re.sub(r"[^a-z0-9]+", " ", str(words or "").lower()).split())
    if not said:
        return None
    return MODE_WORDS.get(said)


def _now_text() -> str:
    """A UTC timestamp, the shape the tracker's own date columns use."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --------------------------------------------------------------------------
#   The consent card - for `optery_api` and `hybrid` only
# --------------------------------------------------------------------------
#
# The house pattern, copied from `jarvis_search.request_enabled` rather than
# invented: the card is raised on the gate, the answer comes back on a daemon
# thread, and the caller is told "waiting" immediately. Only a person's yes
# writes the file, and `tier_of` must really say "ask" before a card is raised
# at all - a settings file that loosened it must not turn a consent into
# nothing.

_LOCK = threading.Lock()
_PENDING: dict = {}
_WITHDRAWN: set = set()
_LAST: dict = {}


def _gate(action: str, detail: dict, prompt: str):
    """The house gate, imported lazily so a PC without it still answers."""
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tier(action: str) -> str:
    """The tier this PC's settings file gives the action, or "unreadable ..."."""
    try:
        import jarvis_framework as fw
        return str(fw.action_tier(action))
    except Exception as exc:                # noqa: BLE001 - said, never guessed
        return f"unreadable ({type(exc).__name__})"


def _spawn(fn) -> None:
    threading.Thread(target=fn, name="jarvis-privacy-card", daemon=True).start()


def _audit(event: str, detail: dict) -> None:
    """The one audit line a card writes - the mode's ID only, never a detail."""
    try:
        import jarvis_framework as fw
        fw.audit_log(event, detail)
    except Exception:                       # noqa: BLE001 - an older PC
        pass


def mode_card_state() -> dict:
    """{"waiting": bool, "last": {...} or None} - what the card is doing."""
    with _LOCK:
        return {"waiting": bool(_PENDING), "last": dict(_LAST) or None}


def _finish(pid: str, outcome: str, *, mode_wanted: str = "", why: str = "",
            was: str = "") -> None:
    with _LOCK:
        if _PENDING.get("id") == pid:
            _PENDING.clear()
        _WITHDRAWN.discard(pid)
        said = CARD_WORDS.get(outcome, "").format(
            mode=MODE_NAMES.get(mode_wanted, mode_wanted), why=why,
            was=MODE_NAMES.get(was, was))
        _LAST.clear()
        _LAST.update(outcome=outcome, why=why, at=time.time(), said=said,
                     mode=mode_wanted)
    _audit("privacy.mode_card", {"outcome": outcome, "mode": mode_wanted})


def _decide(pid: str, wanted: str, was: str, gate, tier_of) -> None:
    """Wait for the card's answer, and write the mode only on a person's yes."""
    try:
        verdict = gate(CONSENT_ACTION, _consent_detail(wanted), CLOUD_CONSENT_TEXT)
    except Exception as exc:                # noqa: BLE001 - said, never a change
        return _finish(pid, "refused", mode_wanted=wanted, was=was,
                       why=f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(verdict, "tier", "unknown")
    allowed = getattr(verdict, "allowed", False) is True
    outcome = getattr(verdict, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    if vtier != "ask" or tier_of(CONSENT_ACTION) != "ask":
        return _finish(pid, "refused", mode_wanted=wanted, was=was,
                       why=f"the gate answered at tier {vtier!r}, which is not a "
                           "person saying yes")
    if not (allowed and outcome == "approved"):
        if outcome in ("denied", "timed_out"):
            return _finish(pid, outcome, mode_wanted=wanted, was=was)
        return _finish(pid, "refused", mode_wanted=wanted, was=was,
                       why=str(getattr(verdict, "reason", "refused") or "refused"))
    with _LOCK:
        withdrawn = pid in _WITHDRAWN
    if withdrawn:
        return _finish(pid, "withdrawn", mode_wanted=wanted, was=was)
    try:
        write_mode(wanted)
    except Exception as exc:                # noqa: BLE001 - said, never swallowed
        return _finish(pid, "failed", mode_wanted=wanted, was=was,
                       why=type(exc).__name__)
    _finish(pid, "changed", mode_wanted=wanted, was=was)


def _consent_detail(wanted: str) -> dict:
    """What the card's machine side carries. Masked labels only - no value."""
    return {
        "text": CLOUD_CONSENT_TEXT,
        "what": f"switch data removal to {MODE_NAMES.get(wanted, wanted)}",
        # The whole point: from this mode on, details DO leave this PC.
        "leaves_this_pc": True,
        "mode": wanted,
        # The masked labels the owner would be sending - a label and the last
        # four characters, never a value (this module's own mask_value()).
        "fields": ["name", "address", "phone", "email"],
        "profile": profile_words(),
    }


def set_mode(value, *, gate=None, tier_of=None, spawn=None,
             peer=None, local=None) -> tuple:
    """Change the mode. `local` at once; a cloud mode behind ONE consent card.

    `peer` and `local` are accepted because every setter in
    `jarvis_settings_registry.py` has that signature and passes them down; the
    consent card itself is raised on this PC through the gate, which is the one
    place the PC-only rule lives, so nothing here re-decides it.

    `local` is written immediately and raises no card: it only ever narrows
    what happens (nothing leaves this PC), and it withdraws any consent card
    that is still waiting - a card for a mode the owner has just left must
    never land afterwards.

    `optery_api` and `hybrid` return `(202, {"waiting": True, ...})` with the
    consent card raised, and the file is written only inside `_decide`, only on
    a person's yes. A denial, a timeout and a withdrawal all leave the mode
    exactly as it was.

    Returns `(http code, body)` - the same shape every other `request_*` in
    this folder returns, so the settings registry's `_say` can read it.
    """
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    wanted = str(value or "").strip().lower()
    if wanted not in MODES:
        return 400, {"ok": False, "changed": False, "card": False,
                     "error": ("A data removal mode is one of: " + ", ".join(MODES)
                               + ". Nothing was changed.")}
    was = mode()
    if was == wanted:
        return 200, {"ok": True, "changed": False, "card": False, "mode": was,
                     "said": f"Data removal is already on {MODE_NAMES[was]}."}
    if wanted not in CLOUD_MODES:
        with _LOCK:
            if _PENDING:
                _WITHDRAWN.add(_PENDING["id"])
                _PENDING.clear()
        try:
            write_mode(wanted)
        except Exception as exc:            # noqa: BLE001 - said, never swallowed
            return 500, {"ok": False, "changed": False, "card": False,
                         "error": f"the mode could not be saved "
                                  f"({type(exc).__name__}), so nothing was changed."}
        _audit("privacy.mode", {"mode": wanted})
        return 200, {"ok": True, "changed": True, "card": False, "mode": wanted,
                     "said": (f"Data removal is on {MODE_NAMES[wanted]} now. "
                              "Nothing is sent anywhere, and every email or "
                              "request still needs its own approval card.")}
    tier = tier_of(CONSENT_ACTION)
    if tier != "ask":
        return 409, {"ok": False, "changed": False, "card": False, "mode": was,
                     "error": (f"{CONSENT_ACTION} is tier {tier!r} in this PC's "
                               "settings file; switching to a cloud mode needs a "
                               "person to say yes, so it must be 'ask'. Nothing "
                               "was changed.")}
    with _LOCK:
        if _PENDING:
            return 202, {"ok": True, "waiting": True, "changed": False,
                         "card": True, "mode": was,
                         "said": ("A consent card for a cloud data removal mode is "
                                  "already waiting for your approval.")}
        pid = f"privacy-{int(time.time() * 1000):x}"
        _PENDING.update(id=pid, since=time.time(), mode=wanted)
    try:
        spawn(lambda: _decide(pid, wanted, was, gate, tier_of))
    except Exception:                       # noqa: BLE001 - said, never a change
        with _LOCK:
            _PENDING.clear()
        return 503, {"ok": False, "changed": False, "card": False,
                     "error": "the consent card could not be raised, so nothing "
                              "was changed."}
    return 202, {"ok": True, "waiting": True, "changed": False, "card": True,
                 "mode": was, "wanted": wanted,
                 "said": (f"Waiting for your yes on the consent card. Data removal "
                          f"stays on {MODE_NAMES[was]}, and sending your details to "
                          f"{MODE_NAMES.get(wanted, wanted)} happens only if you "
                          "approve it.")}


def _reset_for_tests() -> None:
    """Drop every pending card and its record. Tests only; never production."""
    with _LOCK:
        _PENDING.clear()
        _WITHDRAWN.clear()
        _LAST.clear()
        _BATCH_PENDING.clear()
        _BATCH_LAST.clear()


# --------------------------------------------------------------------------
#   The owner's details: read them, and mask them
# --------------------------------------------------------------------------
#
# THE ONE RULE. A stored value may reach a person ONLY through `mask_value()`,
# which returns a label and the last four characters. Nothing else in this file
# formats a value into a sentence, an error, a card or an audit line, so there
# is exactly one place to audit and exactly one behaviour to test.

#: The fields the profile may carry, in the order a card lists them.
PROFILE_FIELDS = (
    ("name", "Primary name"),
    ("address", "Primary address"),
    ("phone", "Primary phone"),
    ("email", "Primary email"),
)


def mask_value(value) -> str:
    """The last four characters of a stored value, as `...1234`.

    Punctuation and spaces are dropped first, so a phone number written
    "(555) 010-1234" masks to `...1234` - four DIGITS, not four characters of
    decoration, and a street address masks to the last four of its postcode.

    AN EMAIL ADDRESS IS MASKED ON ITS LOCAL PART ONLY. The part before the "@"
    is the part that names a person and the part after it is a provider, so
    keeping the tail of the whole string would show `...com` for every address
    there is - and, worse, would show the LOCAL PART of a short address whole.
    "dan@example.com" masks to `...dan`, never to a piece of the domain.

    Anything shorter than four characters masks to `...` plus what it has, so a
    value is never shown whole by being short.
    """
    text = str(value or "")
    if "@" in text:
        text = text.split("@", 1)[0]
    cleaned = re.sub(r"[^0-9A-Za-z]+", "", text)
    if not cleaned:
        return "..."
    return "..." + cleaned[-4:]


def load_profile() -> dict:
    """The owner's details, as stored, or {} when there is no profile yet.

    THIS IS NOT FOR A SENTENCE. It exists so `masked_profile()` and
    `profile_words()` can be built from the real file; the value it returns
    must never be logged, printed, put in a card, or handed to a model. A
    damaged file reads as {} rather than raising: a broken profile must not
    take the whole answer down.
    """
    doc, _why = _read_json(profile_path())
    if doc is None:
        return {}
    return {key: doc[key] for key, _label in PROFILE_FIELDS
            if isinstance(doc.get(key), str) and str(doc.get(key)).strip()}


def masked_profile() -> dict:
    """{field: "Primary address (...1234)"} - the ONLY form a person reads.

    A field the profile does not have is absent, and `profile_words()` says so
    in words. Nothing here is a value: `mask_value()` keeps four characters and
    the label says which thing they belong to.
    """
    raw = load_profile()
    return {key: f"{label} ({mask_value(raw[key])})"
            for key, label in PROFILE_FIELDS if raw.get(key)}


def profile_words() -> str:
    """The masked profile in one sentence, or "not set up yet" in plain words."""
    masked = masked_profile()
    if not masked:
        return ("No removal profile is set up on this PC yet - the file "
                f"{PRIVACY_DIR}/{PROFILE_FILE} is not there, so there are no "
                "details to send anywhere and no details to remove.")
    said = ", ".join(masked[key] for key, _label in PROFILE_FIELDS if key in masked)
    return f"The removal profile on this PC holds {said}."


# --------------------------------------------------------------------------
#   The tracker: privacy/tracker.db
# --------------------------------------------------------------------------

#: The three tables the owner specified (2026-11-26, section 2), word for word
#: in their columns. Written with IF NOT EXISTS so a second open is a no-op and
#: an existing tracker is never rebuilt - the owner's history IS the table.
SCHEMA = """
CREATE TABLE IF NOT EXISTS brokers (
    broker_id     TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    category      TEXT NOT NULL DEFAULT '',
    method        TEXT NOT NULL DEFAULT 'email',
    optout_url    TEXT NOT NULL DEFAULT '',
    privacy_email TEXT NOT NULL DEFAULT '',
    dead_url      INTEGER NOT NULL DEFAULT 0,
    last_updated  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS requests (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    broker_id      TEXT NOT NULL,
    engine         TEXT NOT NULL DEFAULT 'manual',
    status         TEXT NOT NULL DEFAULT 'queued',
    request_ref    TEXT NOT NULL DEFAULT '',
    listing_url    TEXT NOT NULL DEFAULT '',
    sent_at        TEXT,
    verify_after   TEXT,
    relist_check_at TEXT,
    notes          TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS official_portals (
    portal_id    TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    url          TEXT NOT NULL,
    note         TEXT NOT NULL DEFAULT '',
    done         INTEGER NOT NULL DEFAULT 0,
    last_checked TEXT
);

CREATE INDEX IF NOT EXISTS idx_requests_broker ON requests(broker_id);
CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
"""


def connect() -> sqlite3.Connection:
    """Open `privacy/tracker.db`, creating the folder and the schema if needed.

    Re-openable by design: a second call finds the tables already there and
    changes nothing (`IF NOT EXISTS`), which is what lets PR 2 add a broker
    without a migration and lets a suite open the same file twice.
    """
    path = tracker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _seed_portals(conn)
    conn.commit()
    return conn


def _seed_portals(conn: sqlite3.Connection) -> None:
    """Put the two free official portals in, without touching a row that is
    already there - a `done` mark and a `last_checked` date are the owner's."""
    for row in OFFICIAL_PORTALS:
        conn.execute(
            "INSERT OR IGNORE INTO official_portals (portal_id, name, url, note) "
            "VALUES (?, ?, ?, ?)",
            (row["portal_id"], row["name"], row["url"], row["note"]))


def counts(conn: Optional[sqlite3.Connection] = None) -> dict:
    """How many requests are in each status, plus the tracker's own totals.

    Every status the owner listed is always present, as 0 when nothing is
    tracked - an empty tracker answers honestly with zeros rather than with a
    missing key that a sentence would have to invent words for.

    `manual_todo` is the number of brokers whose own method ends with the owner
    clicking something (`web_form`, `official_portal`) and which have no request
    row at all: they are waiting on him, not on Jarvis.
    """
    own = conn is None
    conn = conn or connect()
    try:
        out = {status: 0 for status in STATUSES}
        for row in conn.execute("SELECT status, COUNT(*) AS n FROM requests "
                                "GROUP BY status"):
            status = str(row["status"] or "")
            if status in out:
                out[status] = int(row["n"])
        out["total"] = int(conn.execute("SELECT COUNT(*) AS n FROM requests")
                           .fetchone()["n"])
        out["brokers"] = int(conn.execute("SELECT COUNT(*) AS n FROM brokers")
                             .fetchone()["n"])
        marks = ",".join("?" for _ in MANUAL_METHODS)
        out["manual_todo"] = int(conn.execute(
            "SELECT COUNT(*) AS n FROM brokers b WHERE b.method IN (" + marks + ") "
            "AND NOT EXISTS (SELECT 1 FROM requests r WHERE r.broker_id = b.broker_id)",
            MANUAL_METHODS).fetchone()["n"])
        return out
    finally:
        if own:
            conn.close()


def official_portals(conn: Optional[sqlite3.Connection] = None) -> list:
    """The two free official portals, with their real links and the owner's own
    `done` / `last_checked` marks. A guided checklist - never scraped."""
    own = conn is None
    conn = conn or connect()
    try:
        return [{"portal_id": row["portal_id"], "name": row["name"],
                 "url": row["url"], "note": row["note"],
                 "done": bool(row["done"]), "last_checked": row["last_checked"] or ""}
                for row in conn.execute(
                    "SELECT portal_id, name, url, note, done, last_checked "
                    "FROM official_portals ORDER BY portal_id")]
    finally:
        if own:
            conn.close()


def mark_portal(portal_id: str, *, done: bool = True,
                conn: Optional[sqlite3.Connection] = None) -> bool:
    """Tick or untick one official portal, and date it. False when the id is
    not one of the two - this is a checklist of two, not an open table."""
    if portal_id not in {row["portal_id"] for row in OFFICIAL_PORTALS}:
        return False
    own = conn is None
    conn = conn or connect()
    try:
        conn.execute("UPDATE official_portals SET done = ?, last_checked = ? "
                     "WHERE portal_id = ?", (1 if done else 0, _now_text(), portal_id))
        conn.commit()
        return True
    finally:
        if own:
            conn.close()


# --------------------------------------------------------------------------
#   Dates, and the two wait windows
# --------------------------------------------------------------------------
#
# Every date this file writes is a UTC ISO stamp (`2026-11-26T07:00:00Z`) in the
# tracker's own shape, and every comparison is done on a REAL datetime rather
# than on the string - a lexicographic comparison of ISO stamps happens to work
# until somebody writes a local offset into one, and this tool's whole promise
# is that a wait window is a fact rather than a guess.

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _parse_stamp(text) -> Optional[datetime]:
    """A stored stamp as a UTC datetime, or None when it is not one."""
    raw = str(text or "").strip()
    if not raw:
        return None
    for shape in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, shape).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _stamp(moment: datetime) -> str:
    """A datetime as the tracker's own UTC stamp."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_moment(now=None) -> datetime:
    """The moment a call is being made, injectable so a wait window is testable.

    `now` may be a datetime, a stamp this file wrote, or None for this instant.
    A test that wants to prove "the 45-day window has passed" must not have to
    wait 45 days, and a test that changes the clock must change nothing else.
    """
    if now is None:
        return datetime.now(timezone.utc)
    if isinstance(now, datetime):
        return (now if now.tzinfo else now.replace(tzinfo=timezone.utc)
                ).astimezone(timezone.utc)
    return _parse_stamp(now) or datetime.now(timezone.utc)


def _day_start(moment: datetime) -> str:
    """Midnight UTC of that day, as a stamp - the daily cap's boundary."""
    return _stamp(moment.replace(hour=0, minute=0, second=0, microsecond=0))


def _imap_date(moment: datetime) -> str:
    """`26-Nov-2026`, the one date shape IMAP's SINCE search accepts.

    The month names are the table above rather than `strftime("%b")`, because
    that one follows the PC's locale: on a German Windows it would answer
    "Nov" for November but "Mär" for March, which no IMAP server accepts.
    """
    return f"{moment.day:02d}-{_MONTHS[moment.month - 1]}-{moment.year}"


def wait_days(template: str) -> int:
    """The wait window a template earns: 7 days, or 45 for a statutory request."""
    return int(WAIT_DAYS.get(str(template or "").strip().lower(), 7))


def verify_after_for(sent_at: str, template: str) -> str:
    """`sent_at` plus the template's own window, as a tracker stamp.

    THE TWO WINDOWS ARE RECORDED PER METHOD (the owner's spec, section 2):
    a people-search site's plain deletion request gets 7 days and a statutory
    CCPA/GDPR request gets 45. The row keeps the date it was given, so a later
    change to `WAIT_DAYS` cannot shorten a window that is already running.
    """
    moment = _parse_stamp(sent_at) or _now_moment()
    return _stamp(moment + timedelta(days=wait_days(template)))


# --------------------------------------------------------------------------
#   The broker directory: downloaded, parsed, cached ON THIS PC
# --------------------------------------------------------------------------
#
# WHAT THIS IS. Optery publishes an open-source directory of the data brokers it
# knows about (`https://github.com/optery/optery-data-brokers-directory`): one
# entry per broker, with its website, its opt-out page and, for many of them, a
# privacy email address. That directory is the list this tool works from, and
# the owner's spec is explicit about how it may be used - download it and cache
# it at `privacy/brokers.json` on this PC, and NEVER vendor the dump into git.
#
# WHY A CACHE AND NOT A COMMIT. It is about 766 KB of third-party data under
# CC BY-NC-SA 4.0 (Optery, Inc.; this product is non-commercial, and the licence
# is written into the cache itself so the credit travels with the data). A
# snapshot in the repository would be stale the week it landed, would make every
# refresh a code change, and would put a third party's data into a public tree.
# A cache on the owner's own disk is refreshed by one tool call and never
# appears in a diff - which is also why `privacy/brokers.json` must never be
# added to git by hand.
#
# WHAT IS PARSED, AND WHY SOME ENTRIES ARE LEFT OUT. Each entry has `id`,
# `title`, `website`, `opt_out_url`, `opt_out_guide_url`, `email` and `type`. A
# broker is imported only when it has a route this PC can really use: a privacy
# EMAIL (`method` = `email`, which the batch sender can file) or an opt-out URL
# (`method` = `web_form`, which the manual checklist can hand to the owner). An
# entry with neither is COUNTED AND SAID in the answer rather than imported as
# a row nobody can act on - a checklist of dead ends is worse than a shorter
# checklist that is true.


def brokers_cache_path() -> Path:
    """`privacy/brokers.json` - the parsed directory, on this PC only."""
    return privacy_dir() / BROKERS_FILE


def _directory_items(payload) -> list:
    """The list of broker objects inside a directory document (or a cache)."""
    if isinstance(payload, dict):
        items = payload.get("brokers")
    else:
        items = payload
    if not isinstance(items, list):
        raise ValueError("the directory is not a list of brokers")
    return items


def _clean_email(raw) -> str:
    """A usable privacy email, or "" - never a "see our form" instruction."""
    text = str(raw or "").strip()
    if text.lower().startswith("mailto:"):
        text = text[7:].strip()
    if not text or "@" not in text:
        return ""
    local, _, domain = text.partition("@")
    # An address has no spaces and needs something on both sides of the "@".
    # A few directory entries name a contact route in this field instead of an
    # address ("use the form at ...") and sending mail to those would bounce.
    if not local or not domain or any(ch.isspace() for ch in text):
        return ""
    if "." not in domain:
        return ""
    return text


def _clean_url(raw) -> str:
    """A real http(s) URL, or "" - never a placeholder or a javascript: link."""
    text = str(raw or "").strip()
    if text.lower().startswith(("http://", "https://")) and " " not in text:
        return text
    return ""


def _slug(text: str) -> str:
    """A stable id fragment from a name: lower case, single hyphens."""
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")


def parse_directory(payload, *, updated_at: str = "") -> dict:
    """The directory document -> the `brokers` table's own rows.

    Returns `{"rows", "count", "skipped", "email", "web_form", "no_route"}`.
    `skipped` and `no_route` are the same number said twice for different
    readers: one is "left out of the import" and the other is the reason.

    A broker with BOTH a privacy email and an opt-out page is filed as an
    `email` broker: email is the route this PC can file by itself, and the form
    stays available to the owner in his browser either way. A duplicate id in
    the directory is kept once (the first one wins), because `broker_id` is the
    table's primary key and a second row would silently replace the first.
    """
    stamp = str(updated_at or _now_text())
    rows, seen = [], set()
    email_count = web_count = no_route = 0
    for item in _directory_items(payload):
        if not isinstance(item, dict):
            no_route += 1
            continue
        name = str(item.get("title") or item.get("name") or "").strip()
        if not name:
            no_route += 1
            continue
        ident = str(item.get("id") or "").strip()
        broker_id = f"optery-{ident}" if ident else f"optery-{_slug(name)}"
        if broker_id in seen:
            continue
        address = _clean_email(item.get("email"))
        optout = (_clean_url(item.get("opt_out_url"))
                  or _clean_url(item.get("opt_out_guide_url")))
        if address:
            method = "email"
            email_count += 1
        elif optout:
            method = "web_form"
            web_count += 1
        else:
            # No email and no opt-out page: the directory knows the broker but
            # this PC has no route to it. Counted, never imported as a dead end.
            no_route += 1
            continue
        seen.add(broker_id)
        rows.append({
            "broker_id": broker_id,
            "name": name,
            "category": str(item.get("type") or "").strip(),
            "method": method,
            "optout_url": optout,
            "privacy_email": address,
            "dead_url": 0,
            "last_updated": stamp,
        })
    return {"rows": rows, "count": len(rows), "skipped": no_route,
            "no_route": no_route, "email": email_count, "web_form": web_count}


def import_brokers(rows, conn: Optional[sqlite3.Connection] = None) -> int:
    """Write parsed broker rows into the `brokers` table; returns how many.

    AN UPSERT, not an insert: refreshing the directory again must update the
    name, category, route and date of a broker it already knows and must never
    duplicate it or throw away the owner's own `dead_url` mark. `broker_id` is
    the primary key, so that is what "the same broker" means here.
    """
    own = conn is None
    conn = conn or connect()
    written = 0
    try:
        for row in rows or ():
            conn.execute(
                "INSERT INTO brokers (broker_id, name, category, method, "
                "optout_url, privacy_email, dead_url, last_updated) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(broker_id) DO UPDATE SET "
                "name = excluded.name, category = excluded.category, "
                "method = excluded.method, optout_url = excluded.optout_url, "
                "privacy_email = excluded.privacy_email, "
                "last_updated = excluded.last_updated",
                (row["broker_id"], row["name"], row.get("category", ""),
                 row.get("method", "email"), row.get("optout_url", ""),
                 row.get("privacy_email", ""), int(row.get("dead_url", 0) or 0),
                 row.get("last_updated", "") or _now_text()))
            written += 1
        conn.commit()
        return written
    finally:
        if own:
            conn.close()


def read_directory_cache() -> tuple:
    """(the cached broker rows, why there are none) - never raises."""
    doc, why = _read_json(brokers_cache_path())
    if doc is None:
        return [], why
    try:
        rows = _directory_items(doc)
    except ValueError:
        return [], "the cache is not the shape this file writes"
    return [row for row in rows if isinstance(row, dict)], why


def _fetch_bytes(opener, url: str) -> bytes:
    """Read one URL with a ceiling; the ONLY place the directory is downloaded.

    `opener` is `urllib.request.urlopen`-shaped and is injected, so the suite
    drives this with a fake response and opens no socket. The size ceiling is
    checked after the read as well as before the parse: a redirect to something
    enormous must be refused rather than loaded into memory.
    """
    with opener(url, timeout=DIRECTORY_TIMEOUT) as response:
        raw = response.read(DIRECTORY_MAX_BYTES + 1)
    if not isinstance(raw, (bytes, bytearray)):
        raise ValueError("the directory answered with something that is not text")
    if len(raw) > DIRECTORY_MAX_BYTES:
        raise ValueError("the directory is larger than this tool will read")
    return bytes(raw)


def sync_directory(*, opener=None, url: str = "", now=None) -> dict:
    """Download the directory, parse it, cache it here, import it. Never raises.

    Returns a summary dict: `{"ok", "count", "skipped", "email", "web_form",
    "error", "source", "cache"}`. A network problem, a captive portal's HTML and
    a malformed document all come back as `ok: False` with a plain-words
    `error`, because a refresh that could not happen must be SAID rather than
    crash the chat turn - and the copy already on this PC stays exactly as it
    was, so a failed refresh loses nothing.
    """
    resolved = str(url or DIRECTORY_URL)
    moment = _now_moment(now)
    try:
        raw = _fetch_bytes(opener or urllib.request.urlopen, resolved)
    except Exception as exc:                    # noqa: BLE001 - said, never raised
        return {"ok": False, "count": 0, "skipped": 0, "email": 0, "web_form": 0,
                "source": resolved, "cache": str(brokers_cache_path()),
                "error": f"the directory could not be downloaded "
                         f"({type(exc).__name__})"}
    try:
        payload = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return {"ok": False, "count": 0, "skipped": 0, "email": 0, "web_form": 0,
                "source": resolved, "cache": str(brokers_cache_path()),
                "error": "the directory answered with something that is not JSON"}
    try:
        parsed = parse_directory(payload, updated_at=_stamp(moment))
    except ValueError as exc:
        return {"ok": False, "count": 0, "skipped": 0, "email": 0, "web_form": 0,
                "source": resolved, "cache": str(brokers_cache_path()),
                "error": str(exc)}
    if not parsed["rows"]:
        return {"ok": False, "count": 0, "skipped": parsed["skipped"],
                "email": 0, "web_form": 0, "source": resolved,
                "cache": str(brokers_cache_path()),
                "error": "the directory held no broker this PC can act on"}
    try:
        _write_json(brokers_cache_path(), {
            "source": resolved,
            "name": DIRECTORY_NAME,
            "license": DIRECTORY_LICENSE,
            "fetched_at": _stamp(moment),
            "count": parsed["count"],
            "skipped": parsed["skipped"],
            "brokers": parsed["rows"],
        })
        imported = import_brokers(parsed["rows"])
    except Exception as exc:                    # noqa: BLE001 - said, never raised
        return {"ok": False, "count": 0, "skipped": parsed["skipped"],
                "email": parsed["email"], "web_form": parsed["web_form"],
                "source": resolved, "cache": str(brokers_cache_path()),
                "error": f"the broker list could not be saved "
                         f"({type(exc).__name__})"}
    _audit("privacy.directory", {"count": imported, "skipped": parsed["skipped"]})
    return {"ok": True, "count": imported, "skipped": parsed["skipped"],
            "email": parsed["email"], "web_form": parsed["web_form"],
            "error": "", "source": resolved,
            "cache": str(brokers_cache_path()), "fetched_at": _stamp(moment)}


def sync_words(result: dict) -> str:
    """The refresh in plain words: what came in, what was left out, and where.

    THE NUMBERS ARE THE REAL ONES from `sync_directory()`, including the entries
    that were left out and why - so an answer can never imply the directory
    holds 956 actionable brokers when 89 of them have no route at all.
    """
    if not result.get("ok"):
        cached = len(read_directory_cache()[0])
        tail = (f"The copy already on this PC still holds {cached} broker(s), so "
                "nothing was lost." if cached else
                "No broker list is cached on this PC yet, so the only thing to do "
                "is try again when the connection is back.")
        return f"The broker list could not be refreshed: {result.get('error')}. {tail}"
    said = (f"Refreshed the broker list from {DIRECTORY_NAME}: {result['count']} "
            f"broker(s) now have a route this PC can use - {result['email']} by "
            f"email and {result['web_form']} by web form.")
    if result.get("skipped"):
        said += (f" {result['skipped']} entr(y/ies) in the directory publish "
                 "neither an email address nor an opt-out page, so they are "
                 "counted and left out rather than listed as dead ends.")
    return said + (f" The parsed list is cached at {result.get('cache')} on this "
                   "PC only, never in the repository.")


# --------------------------------------------------------------------------
#   The carded batch sender: ONE card, at most 20 brokers, 250 a day
# --------------------------------------------------------------------------
#
# THE SHAPE, AND EVERY PART OF IT IS A RULE FROM THE OWNER'S SPEC (section 1.3
# and section 5 item 2):
#
#   1. THE CARD NAMES THE EXACT BROKERS, THE EXACT TEMPLATE AND THE COUNT. One
#      card per batch, never one card per email and never a cardless send. The
#      gate action is the EXISTING `send_email` ask-tier action, so this file
#      adds no gate row, no tier row and no settings key (the route PR 1 took
#      with `change_own_config`).
#   2. THE CAPS ARE HARD. `BATCH_CAP` (20) is applied when the batch is picked,
#      so a card can never name 21; `DAILY_CAP` (250) is counted from the
#      tracker's own `sent_at` column for TODAY, so a second batch the same day
#      is smaller rather than refused only after the fact.
#   3. DENY SENDS NOTHING AND WRITES NOTHING. The rows are written only inside
#      the card's decision, only after `approved`, so a denied, timed-out,
#      refused or crashed card leaves the tracker exactly as it was.
#   4. THE WAIT WINDOW IS RECORDED PER METHOD. Each row gets `sent_at` and
#      `verify_after` (`verify_after_for()`: 45 days for a CCPA or GDPR
#      request, 7 for a plain one).
#   5. THE PASSWORD IS THE ONE THAT ALREADY EXISTS. The email goes out through
#      `jarvis_email.imap_user()` / `imap_password()` - the owner's Gmail App
#      Password (`#1506`, Windows Credential Manager) - never a second store,
#      never a file, and never a logged value. The transport is injected in
#      tests, so the suite sends no real mail and reads no real credential.
#
# WHY THE BATCH CARD IS SPAWNED ON A THREAD. The gate blocks until a person
# answers, and the chat turn must not hang on a card nobody has answered yet:
# the same reason `jarvis_send_file.py` answers 202 with `waiting: true`. The
# sends happen on that thread, only after the yes, and the outcome is kept in
# `batch_card_state()` so a later "show my removal status" can say what happened.

#: The outcomes a batch card can end in, in the owner's own words.
BATCH_WORDS = {
    "approved": ("You approved the card, so {sent} removal email(s) went out with "
                 "{template}, and {failed} failed. Each one is tracked with the "
                 "date it was sent and the date its wait window ends."),
    "denied": ("The card was turned down, so nothing was sent and nothing was "
               "written down."),
    "timed_out": ("Nobody answered the card in time, so nothing was sent and "
                  "nothing was written down."),
    "refused": ("The card could not be approved ({why}), so nothing was sent and "
                "nothing was written down."),
}

_BATCH_PENDING: dict = {}
_BATCH_LAST: dict = {}


def sent_today(conn: Optional[sqlite3.Connection] = None, *, now=None) -> int:
    """How many removal emails went out TODAY (UTC), from the tracker itself.

    The number is counted from `requests.sent_at` rather than from a counter in
    a file, so restarting this PC cannot reset the daily cap and a hand-edited
    tracker is the only way to get round it.
    """
    moment = _now_moment(now)
    start = _day_start(moment)
    end = _stamp(moment.replace(hour=0, minute=0, second=0, microsecond=0)
                 + timedelta(days=1))
    own = conn is None
    conn = conn or connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM requests WHERE sent_at IS NOT NULL "
            "AND sent_at != '' AND sent_at >= ? AND sent_at < ?",
            (start, end)).fetchone()
        return int(row["n"])
    finally:
        if own:
            conn.close()


def batch_candidates(conn: Optional[sqlite3.Connection] = None, *, now=None,
                     limit: Optional[int] = None) -> dict:
    """The next brokers to email, and why there are none when there are none.

    Returns `{"rows", "why", "sent_today", "room"}`. A broker is a candidate
    when its own `method` is `email`, it has a privacy address, its URL is not
    marked dead, and no live request exists for it - `sent`,
    `needs_verify_click`, `pending_window` and `removed` all mean "already
    filed or already done", while a `failed` row may be tried again.

    `limit` can only make the batch SMALLER: `min(limit, BATCH_CAP, room)`, so a
    caller cannot talk this function past either hard cap.
    """
    moment = _now_moment(now)
    own = conn is None
    conn = conn or connect()
    try:
        used = sent_today(conn, now=moment)
        room = DAILY_CAP - used
        if room <= 0:
            return {"rows": [], "sent_today": used, "room": 0,
                    "why": (f"The {DAILY_CAP}-a-day cap is reached: {used} removal "
                            "emails have already gone out today, and nothing more "
                            "goes out until tomorrow.")}
        wanted = min(int(limit or BATCH_CAP), BATCH_CAP, room)
        rows = conn.execute(
            "SELECT b.broker_id, b.name, b.category, b.method, b.optout_url, "
            "b.privacy_email FROM brokers b WHERE b.method = 'email' "
            "AND b.privacy_email != '' AND b.dead_url = 0 "
            "AND NOT EXISTS (SELECT 1 FROM requests r "
            "                WHERE r.broker_id = b.broker_id AND r.status IN "
            "                ('sent', 'needs_verify_click', 'pending_window', "
            "                 'removed')) "
            "ORDER BY b.name COLLATE NOCASE LIMIT ?", (wanted,)).fetchall()
        picked = [dict(row) for row in rows]
        if not picked:
            cached = len(read_directory_cache()[0])
            why = ("No broker is waiting for an email: either the broker list has "
                   "not been loaded yet (say \"sync the broker list\"), or every "
                   "email broker already has a request.")
            if not cached:
                why = ("No broker is waiting for an email, and no broker list is "
                       "cached on this PC yet. Say \"sync the broker list\" first.")
            return {"rows": [], "sent_today": used, "room": room, "why": why}
        return {"rows": picked, "sent_today": used, "room": room, "why": ""}
    finally:
        if own:
            conn.close()


def batch_card(rows: list, template: str) -> str:
    """The ONE card's own words: the exact brokers, the template, the count.

    A person reading this card can see every recipient before anything leaves
    the PC - which is the whole point of the cap and the card - and the closing
    lines say what a denial does, because "nothing happens" is the answer to the
    question a card like this raises.
    """
    names = ", ".join(str(row.get("name") or row.get("broker_id")) for row in rows)
    return (
        f"Send {len(rows)} data-broker deletion email(s)?\n"
        f"They go to exactly these {len(rows)} broker(s): {names}.\n"
        f"The template is {TEMPLATE_NAMES.get(template, template)}.\n"
        "Each email comes from your own Gmail account through the App Password "
        "saved on this PC, and asks that broker to delete your personal "
        "information. Nothing is sent before you approve this card; denying it "
        "sends nothing at all and writes nothing down.\n"
        f"The caps still hold: at most {BATCH_CAP} brokers per card and "
        f"{DAILY_CAP} emails a day."
    )


def _profile_lines(profile: dict) -> list:
    """The identifying lines a deletion request must carry, in order.

    This is the ONE place a raw profile value becomes part of a sentence, and
    that sentence is an email to the broker who is being asked to delete it -
    never a log, a card, an answer or an audit line. A field the profile does
    not have is left out rather than printed as "None".
    """
    lines = []
    for key, label in (("name", "Full name"), ("address", "Home address"),
                       ("email", "Email address"), ("phone", "Phone number")):
        value = str(profile.get(key) or "").strip()
        if value:
            lines.append(f"{label}: {value}")
    return lines


def _subject_for(broker: dict, template: str) -> str:
    """The email's subject: the request's kind and the broker's own name."""
    name = str(broker.get("name") or broker.get("broker_id") or "")
    if template == "ccpa":
        return f"California consumer deletion request (CCPA) - {name}"
    if template == "gdpr":
        return f"GDPR Article 17 erasure request - {name}"
    return f"Personal information removal request - {name}"


def _body_for(profile: dict, broker: dict, template: str) -> str:
    """The one email's words, per template. No owner detail is ever logged."""
    name = str(broker.get("name") or broker.get("broker_id") or "")
    details = "\n".join(_profile_lines(profile))
    if template == "ccpa":
        opening = (
            f"To the privacy team at {name},\n\n"
            "I am a California resident and I am exercising my right to delete "
            "personal information under the California Consumer Privacy Act "
            "(Cal. Civ. Code section 1798.105). Please delete the personal "
            "information you hold about me, and tell me in writing when it is "
            "done."
        )
    elif template == "gdpr":
        opening = (
            f"To the privacy team at {name},\n\n"
            "I am exercising my right to erasure under Article 17 of the EU "
            "General Data Protection Regulation. Please erase the personal data "
            "you hold about me, and confirm in writing when it is done."
        )
    else:
        opening = (
            f"To the privacy team at {name},\n\n"
            "Please remove the personal information you hold about me from your "
            "site, your search results and any listing you publish, and confirm "
            "in writing when it is done."
        )
    closing = (
        "The details you need to find me are below. Please do not use them for "
        "anything else.\n\n"
        f"{details}\n\n"
        "If you need more information to identify me, please reply and say "
        "exactly what you need.\n\n"
        "Thank you."
    )
    return f"{opening}\n\n{closing}"


def _mail_message(profile: dict, broker: dict, template: str):
    """One broker's email as an `EmailMessage` - built, never sent here."""
    msg = email.message.EmailMessage()
    msg["To"] = str(broker.get("privacy_email") or "")
    owner = str(profile.get("email") or "").strip()
    if owner:
        msg["From"] = owner
    msg["Subject"] = _subject_for(broker, template)
    # A Message-ID must be globally unique and must not carry anything about
    # this PC: `make_msgid` with a fixed, non-routable domain keeps the id
    # stable in shape and free of the machine's own hostname.
    msg["Message-ID"] = email.utils.make_msgid(domain="privacy.invalid")
    msg.set_content(_body_for(profile, broker, template))
    return msg


def _mail_credentials() -> tuple:
    """(user, password) from `jarvis_email`'s own helpers - the ONE read.

    THE VALUES NEVER LEAVE THIS FUNCTION EXCEPT TO THE SMTP/IMAP LOGIN THAT
    NEEDS THEM: no sentence, card, note or audit line ever carries one, and the
    suite replaces this function so it never touches the owner's Windows
    Credential Manager at all (the same seam `gmail_state()` already gives it).
    """
    try:
        import jarvis_email as mail
        return (str(mail.imap_user() or "").strip(),
                str(mail.imap_password() or "").strip())
    except Exception:                           # noqa: BLE001 - absent: not set
        return "", ""


def _deliver(msg, *, transport=None) -> str:
    """Send ONE built message. Returns its Message-ID.

    `transport` is injected by the suite, so the tests exercise this exact
    function with a fake that records the message and opens no socket; the real
    path resolves the SAME Gmail App Password every other mail tool uses
    (`#1506`, Windows Credential Manager) and never logs it, never writes it to
    a file and never returns it.
    """
    if transport is not None:
        transport(msg)
        return str(msg.get("Message-ID") or "")
    user, password = _mail_credentials()
    if not user or not password:
        raise RuntimeError("the Gmail App Password is not set")
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=MAIL_TIMEOUT) as box:
        box.login(user, password)
        box.send_message(msg)
    return str(msg.get("Message-ID") or "")


def _person_said_yes(verdict) -> bool:
    """A card answer is a yes only at tier "ask" and outcome "approved"."""
    allowed = getattr(verdict, "allowed", False) is True
    outcome = getattr(verdict, "outcome", None)
    tier = str(getattr(verdict, "tier", "") or "")
    if not allowed:
        return False
    if outcome is not None:
        return outcome == "approved" and tier == "ask"
    return tier == "ask"


def batch_card_state() -> dict:
    """{"waiting": bool, "last": {...} or None} - what the batch card is doing."""
    with _LOCK:
        return {"waiting": bool(_BATCH_PENDING), "last": dict(_BATCH_LAST) or None}


def _finish_batch(pid: str, outcome: str, *, sent: int = 0, failed: int = 0,
                  count: int = 0, template: str = "", why: str = "") -> None:
    """Record one batch card's outcome, and never a detail of the owner's."""
    with _LOCK:
        if _BATCH_PENDING.get("id") == pid:
            _BATCH_PENDING.clear()
        said = BATCH_WORDS.get(outcome, BATCH_WORDS["refused"]).format(
            sent=sent, failed=failed, why=why,
            template=TEMPLATE_NAMES.get(template, template))
        _BATCH_LAST.clear()
        _BATCH_LAST.update(outcome=outcome, said=said, sent=sent, failed=failed,
                           count=count, template=template, at=time.time())
    _audit("privacy.batch_card", {"outcome": outcome, "sent": sent,
                                  "failed": failed, "template": template})


def _record_sent(conn: sqlite3.Connection, broker: dict, template: str,
                 ref: str, moment: datetime) -> None:
    """One `sent` row: the date it went, and the date its wait window ends."""
    sent_at = _stamp(moment)
    conn.execute(
        "INSERT INTO requests (broker_id, engine, status, request_ref, "
        "listing_url, sent_at, verify_after, notes) "
        "VALUES (?, 'local_email', 'sent', ?, ?, ?, ?, ?)",
        (broker["broker_id"], ref, "", sent_at,
         verify_after_for(sent_at, template),
         f"Filed with the {template} template; waiting for the broker's answer."))
    conn.commit()


def _record_failed(conn: sqlite3.Connection, broker: dict, why: str,
                   moment: datetime) -> None:
    """One `failed` row - the exception's TYPE only, never its text.

    An SMTP error's own message can quote the recipient's address, so the note
    carries the class name and nothing else. A `failed` row may be retried by a
    later batch; `_record_sent`'s four "already filed" statuses may not.
    """
    conn.execute(
        "INSERT INTO requests (broker_id, engine, status, request_ref, "
        "listing_url, sent_at, verify_after, notes) "
        "VALUES (?, 'local_email', 'failed', '', '', ?, '', ?)",
        (broker["broker_id"], _stamp(moment),
         f"Could not be sent ({why}); it can be tried again."))
    conn.commit()


def _batch_detail(rows: list, template: str) -> dict:
    """What the card carries on its machine side. No value of the owner's."""
    return {"template": template, "count": len(rows),
            "brokers": [str(row.get("name") or row.get("broker_id")) for row in rows],
            "fields": ["name", "address", "phone", "email"],
            "profile": profile_words(),
            "leaves_this_pc": True}


def _send_decide(pid: str, template: str, rows: list, gate, tier_of, transport,
                 moment: datetime) -> None:
    """Wait for the card's answer, and SEND only on a person's yes."""
    detail = _batch_detail(rows, template)
    card = batch_card(rows, template)
    try:
        verdict = gate(BATCH_ACTION, detail, card)
    except Exception as exc:                    # noqa: BLE001 - said, never sent
        return _finish_batch(pid, "refused", template=template, count=len(rows),
                             why=f"the approval gate failed ({type(exc).__name__})")
    try:
        action_tier = str(tier_of(BATCH_ACTION))
    except Exception:                           # noqa: BLE001 - said, never sent
        action_tier = "unreadable"
    if str(getattr(verdict, "tier", "")) != "ask" or action_tier != "ask":
        return _finish_batch(pid, "refused", template=template, count=len(rows),
                             why="the gate did not answer at tier 'ask'")
    if not _person_said_yes(verdict):
        outcome = str(getattr(verdict, "outcome", "") or "")
        return _finish_batch(pid, outcome if outcome in ("denied", "timed_out")
                             else "refused", template=template, count=len(rows),
                             why="the card was not approved")
    profile = load_profile()
    sent = failed = 0
    try:
        conn = connect()
    except Exception as exc:                    # noqa: BLE001 - said, never sent
        return _finish_batch(pid, "refused", template=template, count=len(rows),
                             why=f"the tracker could not be opened "
                                 f"({type(exc).__name__})")
    try:
        for row in rows:
            try:
                ref = _deliver(_mail_message(profile, row, template),
                               transport=transport)
                _record_sent(conn, row, template, ref, moment)
            except Exception as exc:            # noqa: BLE001 - one row, not all
                failed += 1
                try:
                    _record_failed(conn, row, type(exc).__name__, moment)
                except Exception:               # noqa: BLE001 - the count is enough
                    pass
                continue
            sent += 1
    finally:
        try:
            conn.close()
        except Exception:                       # noqa: BLE001 - already closing
            pass
    _finish_batch(pid, "approved", sent=sent, failed=failed,
                  count=len(rows), template=template)


def _guarded_send(pid: str, template: str, rows: list, gate, tier_of, transport,
                  moment: datetime) -> None:
    """Run one card's send, and ALWAYS settle the card even if something breaks.

    A card left pending would block every later batch, so an unexpected error
    anywhere in the send settles it as refused with the error's CLASS name -
    never its message, which can quote an address - and sends nothing further.
    """
    try:
        _send_decide(pid, template, rows, gate, tier_of, transport, moment)
    except Exception as exc:                    # noqa: BLE001 - the card still settles
        _finish_batch(pid, "refused", template=template, count=len(rows),
                      why=f"the batch stopped on an error ({type(exc).__name__})")


def send_optout_batch(template: str = "generic", *, gate=None, tier_of=None,
                      spawn=None, transport=None, now=None) -> tuple:
    """The one carded send: `(http code, body)` with the words in `body["said"]`.

    `template` is `ccpa`, `gdpr` or `generic` and decides both the email's words
    and its wait window. Everything that could make a send pointless is answered
    BEFORE any card is raised - the wrong mode, no Gmail App Password, no
    profile, a tier that is not "ask" - because a card the owner cannot act on
    is noise. When there IS something to send, this returns `202` with
    `waiting: True` and the card is answered on its own thread.

    A DENIED CARD WRITES NOTHING: no request row, no `sent_at`, no note. The
    test suite proves that by counting rows before and after a denial.
    """
    wanted = str(template or "generic").strip().lower()
    if wanted not in TEMPLATES:
        return 400, {"ok": False, "sent": 0, "waiting": False,
                     "said": ("A removal email template is one of: "
                              + ", ".join(TEMPLATES) + ". Nothing was sent.")}
    if mode() == "optery_api":
        return 200, {"ok": False, "sent": 0, "waiting": False,
                     "said": ("Data removal is on Optery's cloud API, so this PC "
                              "is not sending any email. Switch to local or hybrid "
                              "first; nothing is sent by that switch either.")}
    if not gmail_state().get("ready"):
        return 200, {"ok": False, "sent": 0, "waiting": False,
                     "said": ("The Gmail App Password is not set on this PC, so no "
                              "removal email can be sent. Set it in Settings, then "
                              "ask again. Nothing was sent.")}
    profile = load_profile()
    if not profile.get("name") and not profile.get("email"):
        return 200, {"ok": False, "sent": 0, "waiting": False,
                     "said": ("There is no removal profile on this PC yet, so there "
                              "are no details to put in a deletion request. The file "
                              "is privacy/profile.json, and nothing was sent.")}
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    tier = tier_of(BATCH_ACTION)
    if tier != "ask":
        return 409, {"ok": False, "sent": 0, "waiting": False,
                     "said": (f"Sending removal email needs a person to say yes, so "
                              f"{BATCH_ACTION} must be tier 'ask' in this PC's "
                              f"settings file (it is {tier!r}). Nothing was sent.")}
    picked = batch_candidates(now=now)
    rows = picked["rows"]
    if not rows:
        return 200, {"ok": False, "sent": 0, "waiting": False,
                     "said": picked["why"] + " Nothing was sent."}
    with _LOCK:
        if _BATCH_PENDING:
            return 202, {"ok": True, "sent": 0, "waiting": True,
                         "count": int(_BATCH_PENDING.get("count") or 0),
                         "said": ("A removal-email card is already waiting for your "
                                  "approval. Nothing was sent twice.")}
        pid = f"privacy-batch-{int(time.time() * 1000):x}"
        _BATCH_PENDING.update(id=pid, since=time.time(), template=wanted,
                              count=len(rows))
    moment = _now_moment(now)
    try:
        spawn(lambda: _guarded_send(pid, wanted, rows, gate, tier_of, transport,
                                    moment))
    except Exception:                           # noqa: BLE001 - said, never sent
        with _LOCK:
            _BATCH_PENDING.clear()
        return 503, {"ok": False, "sent": 0, "waiting": False,
                     "said": ("The approval card could not be raised, so nothing "
                              "was sent.")}
    # The card is answered on its own thread. When it has ALREADY settled by the
    # time this returns - a denial the owner had waiting, or a test driving the
    # thread inline - the answer carries the real outcome rather than "waiting",
    # the same way `jarvis_send_file.prepare_route` reads `seen` before it
    # answers. A card still open answers 202 with `waiting: true`.
    settled = batch_card_state()
    last = settled.get("last") or {}
    if not settled.get("waiting") and last.get("said"):
        return 200, {"ok": True, "waiting": False,
                     "sent": int(last.get("sent") or 0),
                     "failed": int(last.get("failed") or 0),
                     "count": len(rows), "template": wanted,
                     "outcome": last.get("outcome"),
                     "said": str(last.get("said"))}
    return 202, {"ok": True, "sent": 0, "waiting": True, "template": wanted,
                 "count": len(rows),
                 "brokers": [str(row.get("name") or row.get("broker_id"))
                             for row in rows],
                 "said": (f"Waiting for your yes on ONE card for {len(rows)} "
                          f"broker(s), template {TEMPLATE_NAMES[wanted]}. Nothing "
                          "is sent unless you approve it, and a denial sends "
                          "nothing at all.")}


# --------------------------------------------------------------------------
#   The reply scanner, and the verify pass that alone may say "removed"
# --------------------------------------------------------------------------
#
# THE TWO-PASS RULE, AND WHY IT IS NOT A FORMALITY (the owner's spec, section
# 2). Filing a request is pass one; CONFIRMING the removal is pass two, and the
# two are never collapsed:
#
#   * A broker's answer with a CONFIRMATION LINK moves the request to
#     `needs_verify_click`. THIS FILE NEVER CLICKS IT. The link is opened by the
#     owner, in his own browser, signed in as himself - an automated click on a
#     deletion confirmation is exactly the kind of action this tool must not
#     take for him, and a request the owner has not really confirmed is not a
#     removal.
#   * A broker's answer asking for ID or more detail moves it to
#     `needs_verify_click` too, with a note saying which: that is his step in
#     his own inbox, and the note never copies the broker's words, which could
#     quote his address back.
#   * A broker's answer SAYING it removed the data moves it to
#     `pending_window` - NOT `removed`. The wait window is still running, and a
#     company's own sentence is not a listing that is gone.
#   * `removed` is written by ONE place only, `_verify_pass()`, and only when a
#     recorded `listing_url` answers 200 with no trace of the owner on it after
#     the wait window has passed. A 403, a CAPTCHA, a Cloudflare interstitial, a
#     timeout, an empty page and a "thank you" form are all `unverified` - never
#     a removal.
#
# NOTHING FROM AN EMAIL IS EVER WRITTEN INTO A NOTE OR A LOG. A broker's reply
# can quote the very address this tool is asking it to delete, so the notes
# below are fixed sentences written by this file, and the sender's address is
# used to MATCH a request and for nothing else.

#: Mail providers where two different brokers can share a domain, so matching a
#: reply by DOMAIN alone would attribute one broker's answer to another.
_PUBLIC_MAIL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com",
    "live.com", "aol.com", "proton.me", "protonmail.com", "icloud.com",
    "me.com", "gmx.com", "mail.com", "zoho.com",
})

#: The kinds of answer this scan can recognise.
REPLY_KINDS = ("confirmation_link", "id_request", "confirmation")

_CLICK_URL = re.compile(
    r"https?://[^\s<>\"')\]]*(?:confirm|verify|opt-?out|remove|unsubscribe|delete)",
    re.I)
_ID_ASK = re.compile(
    r"(?:government[- ]issued|photo id|proof of (?:your )?identity|verify your "
    r"identity|copy of your (?:id|driver'?s? licen[cs]e)|additional information "
    r"to (?:verify|process)|state your full name|confirm your (?:name and )?"
    r"address)", re.I)
_DONE = re.compile(
    r"(?:(?:has|have|was|were) (?:been )?(?:successfully )?(?:removed|deleted|"
    r"erased|suppressed)|(?:deletion|erasure|removal|opt-?out) (?:request )?"
    r"(?:has been |is )?(?:completed|processed|fulfilled)|successfully "
    r"(?:removed|deleted|erased|opted you out)|you have been (?:removed|opted "
    r"out|unsubscribed))", re.I)

_ADDRESS_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _open_imap(user: str, password: str):
    """The real mailbox: Gmail over SSL, the same account as the App Password."""
    box = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    box.login(user, password)
    return box


def _address_of(raw: str) -> str:
    """The bare address inside a From header, lower case, or ""."""
    found = _ADDRESS_RE.search(str(raw or ""))
    return found.group(0).lower() if found else ""


def _plain_text(msg) -> str:
    """Every text/plain part of a message, joined; never HTML as words."""
    chunks = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() != "text/plain":
                continue
            payload = part.get_payload(decode=True)
            if isinstance(payload, (bytes, bytearray)):
                chunks.append(bytes(payload).decode(
                    part.get_content_charset() or "utf-8", "replace"))
    else:
        payload = msg.get_payload(decode=True)
        if isinstance(payload, (bytes, bytearray)):
            chunks.append(bytes(payload).decode(
                msg.get_content_charset() or "utf-8", "replace"))
        elif isinstance(msg.get_payload(), str):
            chunks.append(msg.get_payload())
    return "\n".join(chunks)


def _reply_analysis(raw: bytes) -> dict:
    """{"from", "subject", "text"} for one fetched message."""
    msg = email.message_from_bytes(raw)
    return {"from": _address_of(str(msg.get("From") or "")),
            "subject": str(msg.get("Subject") or ""),
            "text": _plain_text(msg)}


def classify_reply(text: str) -> str:
    """Which of `REPLY_KINDS` this answer is, or "" when it is none of them.

    The ORDER is the meaning: a confirmation LINK wins over everything (the
    owner has an action to take), then an ID request (also his action), then a
    completion sentence. A reply that only says "we received your request" is
    none of the three and changes nothing.
    """
    said = str(text or "")
    if not said.strip():
        return ""
    if _CLICK_URL.search(said):
        return "confirmation_link"
    if _ID_ASK.search(said):
        return "id_request"
    if _DONE.search(said):
        return "confirmation"
    return ""


def _open_requests(conn: sqlite3.Connection) -> list:
    """Every request a broker could still reply about, with its broker's row."""
    return [dict(row) for row in conn.execute(
        "SELECT r.id, r.broker_id, r.status, r.sent_at, r.verify_after, "
        "r.listing_url, b.name, b.privacy_email FROM requests r "
        "JOIN brokers b ON b.broker_id = r.broker_id "
        "WHERE r.status IN ('sent', 'needs_verify_click', 'pending_window') "
        "ORDER BY r.id")]


def _match_request(rows: list, address: str) -> Optional[dict]:
    """The request a reply belongs to, by an EXACT address, then by domain.

    A domain match is only used when the domain is not a public mail provider:
    two brokers who both write from a gmail.com address are not the same broker,
    and attributing one's answer to the other would move the wrong row.
    """
    if not address:
        return None
    for row in rows:
        if str(row.get("privacy_email") or "").strip().lower() == address:
            return row
    domain = address.split("@", 1)[1] if "@" in address else ""
    if not domain or domain in _PUBLIC_MAIL_DOMAINS:
        return None
    for row in rows:
        theirs = str(row.get("privacy_email") or "").strip().lower()
        if "@" in theirs and theirs.split("@", 1)[1] == domain:
            return row
    return None


def _scan_mailbox(box, oldest: datetime) -> list:
    """The raw bytes of up to `MAX_SCAN_MESSAGES` messages since `oldest`."""
    try:
        box.select("INBOX")
        status, data = box.search(None, "SINCE", _imap_date(oldest))
    except Exception:                           # noqa: BLE001 - said as zero
        return []
    if str(status) != "OK" or not data:
        return []
    blob = b" ".join(part for part in data
                     if isinstance(part, (bytes, bytearray)))
    out = []
    for num in blob.split()[-MAX_SCAN_MESSAGES:]:
        try:
            status, fetched = box.fetch(num, "(RFC822)")
        except Exception:                       # noqa: BLE001 - one message
            continue
        if str(status) != "OK":
            continue
        for item in fetched or ():
            if (isinstance(item, tuple) and len(item) > 1
                    and isinstance(item[1], (bytes, bytearray))):
                out.append(bytes(item[1]))
                break
    return out


def _apply_reply(conn: sqlite3.Connection, row: dict, kind: str) -> str:
    """Move one request because of one reply. Returns "click", "confirmed" or ""."""
    current = conn.execute("SELECT status FROM requests WHERE id = ?",
                           (row["id"],)).fetchone()
    status = str(current["status"] or "") if current is not None else ""
    if kind == "confirmation":
        if status not in ("sent", "needs_verify_click"):
            return ""
        conn.execute(
            "UPDATE requests SET status = 'pending_window', notes = ? WHERE id = ?",
            ("The broker wrote that it removed the data. The wait window is still "
             "running, so this is not called removed yet.", row["id"]))
        conn.commit()
        return "confirmed"
    if kind in ("confirmation_link", "id_request"):
        if status != "sent":
            return ""
        note = ("A confirmation link arrived. Open it yourself in your own inbox - "
                "this tool never clicks it for you." if kind == "confirmation_link"
                else "The broker asked for ID or more details. That is your own "
                     "step, in your own inbox - this tool never sends it for you.")
        conn.execute(
            "UPDATE requests SET status = 'needs_verify_click', notes = ? "
            "WHERE id = ?", (note, row["id"]))
        conn.commit()
        return "click"
    return ""


def _listing_markers(profile: dict) -> tuple:
    """The strings whose presence on a page means the listing is still there.

    A name, the local part of the address and the last seven digits of the phone
    number - never the whole address or the whole phone number, because the
    fetch is a page's own text and only a "still there" signal is wanted. A
    false match keeps a row pending (the safe direction); a false miss is what
    this list exists to make as unlikely as it can.
    """
    out = []
    name = str(profile.get("name") or "").strip()
    if len(name) >= 3:
        out.append(name)
    address = str(profile.get("email") or "").strip()
    if "@" in address:
        local = address.split("@", 1)[0]
        if len(local) >= 4:
            out.append(local)
    digits = re.sub(r"\D", "", str(profile.get("phone") or ""))
    if len(digits) >= 7:
        out.append(digits[-7:])
    return tuple(out)


def _fetch_page(opener, url: str) -> tuple:
    """(status code, page text) - never raises, and a 403 is not a removal.

    `urllib.error.HTTPError` is caught BEFORE the general handler because it is
    the interesting one: a broker answering 403 is a page that refused to tell
    this tool anything, and the caller must be able to see the code to say so.
    A 0 means "no answer at all" (a timeout, a DNS failure, a broken redirect).
    """
    try:
        with opener(url, timeout=PAGE_TIMEOUT) as response:
            code = int(getattr(response, "status", 200) or 200)
            raw = response.read(PAGE_MAX_BYTES)
    except urllib.error.HTTPError as exc:
        return int(getattr(exc, "code", 0) or 0), ""
    except Exception:                           # noqa: BLE001 - said as no answer
        return 0, ""
    if not isinstance(raw, (bytes, bytearray)):
        return code, str(raw or "")
    return code, bytes(raw).decode("utf-8", "replace")


def _verify_verdict(status: int, text: str, markers: tuple) -> str:
    """`removed`, `still_listed` or `unverified` - the ONE place "removed" is earned.

    THE RULE, in one place so it can be read and tested: a removal needs a real
    200, a page with enough text on it to be a page, no CAPTCHA or Cloudflare
    interstitial in its words, and NONE of the owner's own markers in it.
    Everything else - a 403, a 404, a timeout, an empty body, a challenge page,
    and a PC with no profile to look for (no markers means there is nothing to
    check, not that the page is clean) - is `unverified`, which NEVER changes a
    row's status.
    """
    if not markers:
        return "unverified"
    if int(status or 0) != 200:
        return "unverified"
    body = str(text or "")
    if len(body.strip()) < 200:
        return "unverified"
    low = body.lower()
    if any(word in low for word in ("captcha", "turnstile", "just a moment",
                                    "checking your browser", "access denied",
                                    "enable javascript to continue")):
        return "unverified"
    if any(str(marker).lower() in low for marker in markers if marker):
        return "still_listed"
    return "removed"


def _verify_pass(conn: sqlite3.Connection, *, opener=None, now=None) -> dict:
    """Re-check every listing whose wait window has passed. Never raises."""
    moment = _now_moment(now)
    rows = [dict(row) for row in conn.execute(
        "SELECT r.id, r.listing_url, r.verify_after, b.name FROM requests r "
        "JOIN brokers b ON b.broker_id = r.broker_id "
        "WHERE r.status IN ('sent', 'pending_window') "
        "AND r.verify_after IS NOT NULL AND r.verify_after != '' "
        "AND r.verify_after <= ? AND r.listing_url != '' ORDER BY r.id",
        (_stamp(moment),))]
    markers = _listing_markers(load_profile())
    fetch = opener or urllib.request.urlopen
    checked = removed = listed = unverified = 0
    for row in rows:
        status, text = _fetch_page(fetch, str(row["listing_url"]))
        verdict = _verify_verdict(status, text, markers)
        checked += 1
        if verdict == "removed":
            conn.execute(
                "UPDATE requests SET status = 'removed', relist_check_at = ?, "
                "notes = ? WHERE id = ?",
                (_stamp(moment + timedelta(days=RELIST_DAYS)),
                 "The listing was gone when it was re-checked after the wait "
                 "window. It will be checked again 90 days later.", row["id"]))
            removed += 1
        elif verdict == "still_listed":
            conn.execute(
                "UPDATE requests SET notes = ? WHERE id = ?",
                ("Still listed after the wait window. Check it yourself, or file "
                 "again once the broker answers.", row["id"]))
            listed += 1
        else:
            conn.execute(
                "UPDATE requests SET notes = ? WHERE id = ?",
                ("The re-check could not see the listing. A 403, a CAPTCHA page or "
                 "a timeout is not proof of removal, so this row is unchanged.",
                 row["id"]))
            unverified += 1
    conn.commit()
    return {"checked": checked, "removed": removed, "still_listed": listed,
            "unverified": unverified}


def _replies_words(scanned: int, click: int, confirmed: int, verify: dict,
                   pending: int) -> str:
    """The scan's answer, in plain words, with no address and no link in it."""
    if not scanned:
        said = ("I scanned the mailbox and found no broker answer this time. "
                "Nothing was clicked and nothing was marked removed.")
    else:
        said = (f"I scanned {scanned} recent message(s) and found the brokers' "
                f"answers: {click} moved to \"waiting for you to click a "
                f"confirmation link\" and {confirmed} to \"the broker says it is "
                "done, window still running\".")
    if click:
        said += (" I did NOT click any confirmation link - that is yours to open in "
                 "your own inbox, because a removal nobody confirmed is not a "
                 "removal.")
    if confirmed:
        said += (" A broker's own sentence is still not proof: the row stays in the "
                 "wait window until that window ends.")
    if verify.get("checked"):
        said += (f" The verify pass re-checked {verify['checked']} listing(s) whose "
                 f"window had passed: {verify['removed']} confirmed removed, "
                 f"{verify['still_listed']} still listed, "
                 f"{verify['unverified']} could not be seen (a 403, a CAPTCHA or a "
                 "timeout is never counted as a removal).")
    if pending:
        said += (f" {pending} request(s) are still open - waiting for their window, "
                 "or waiting for your own click in your inbox.")
    return said


def check_replies(*, imap=None, opener=None, now=None) -> tuple:
    """Read the owner's own mailbox and move rows. NEVER clicks, never sends.

    Returns `(http code, body)` with the words in `body["said"]`. The mailbox and
    the listing pages are both reached through injected callables (`imap`,
    `opener`), so the suite drives this exact function with fake doubles, opens
    no socket and never touches the owner's real Gmail account.
    """
    moment = _now_moment(now)
    if not gmail_state().get("ready"):
        return 200, {"ok": False, "replies": 0, "click": 0, "confirmed": 0,
                     "checked": 0, "removed": 0, "still_listed": 0,
                     "unverified": 0,
                     "said": ("The Gmail App Password is not set on this PC, so "
                              "there is no mailbox to check. Nothing was scanned "
                              "and nothing was changed.")}
    try:
        user, password = _mail_credentials()
    except Exception:                           # noqa: BLE001 - said, nothing done
        user = password = ""
    if not user or not password:
        return 200, {"ok": False, "replies": 0, "click": 0, "confirmed": 0,
                     "checked": 0, "removed": 0, "still_listed": 0,
                     "unverified": 0,
                     "said": ("The Gmail App Password could not be read on this PC, "
                              "so there is no mailbox to check. Nothing was scanned "
                              "and nothing was changed.")}
    conn = connect()
    try:
        open_rows = _open_requests(conn)
        if not open_rows:
            return 200, {"ok": False, "replies": 0, "click": 0, "confirmed": 0,
                         "checked": 0, "removed": 0, "still_listed": 0,
                         "unverified": 0,
                         "said": ("Nothing is waiting for a broker's answer yet: no "
                                  "removal email has been filed. Nothing was "
                                  "scanned and nothing was changed.")}
        seen = [_parse_stamp(row["sent_at"]) for row in open_rows]
        oldest = min([moment_ for moment_ in seen if moment_] or
                     [moment - timedelta(days=45)])
        try:
            box = (imap or _open_imap)(user, password)
        except Exception as exc:                # noqa: BLE001 - said, nothing done
            return 200, {"ok": False, "replies": 0, "click": 0, "confirmed": 0,
                         "checked": 0, "removed": 0, "still_listed": 0,
                         "unverified": 0,
                         "said": (f"The mailbox could not be opened "
                                  f"({type(exc).__name__}), so nothing was scanned "
                                  "and nothing was changed.")}
        try:
            raws = _scan_mailbox(box, oldest)
        finally:
            try:
                box.logout()
            except Exception:                   # noqa: BLE001 - already closing
                pass
        click = confirmed = 0
        for raw in raws:
            got = _reply_analysis(raw)
            kind = classify_reply(got["text"] + "\n" + got["subject"])
            if not kind:
                continue
            row = _match_request(open_rows, got["from"])
            if row is None:
                continue
            moved = _apply_reply(conn, row, kind)
            if moved == "click":
                click += 1
            elif moved == "confirmed":
                confirmed += 1
        verify = _verify_pass(conn, opener=opener, now=moment)
        pending = int(conn.execute(
            "SELECT COUNT(*) AS n FROM requests WHERE status IN "
            "('sent', 'pending_window', 'needs_verify_click')").fetchone()["n"])
        _audit("privacy.replies", {"scanned": len(raws), "click": click,
                                   "confirmed": confirmed,
                                   "removed": verify["removed"]})
        return 200, {"ok": True, "replies": len(raws), "click": click,
                     "confirmed": confirmed, "pending": pending, **verify,
                     "said": _replies_words(len(raws), click, confirmed, verify,
                                             pending)}
    finally:
        conn.close()


def overdue_count(conn: Optional[sqlite3.Connection] = None, *, now=None) -> int:
    """Requests past their wait window that still have no answer."""
    own = conn is None
    conn = conn or connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM requests WHERE status IN "
            "('sent', 'needs_verify_click', 'pending_window') "
            "AND verify_after IS NOT NULL AND verify_after != '' "
            "AND verify_after <= ?", (_stamp(_now_moment(now)),)).fetchone()
        return int(row["n"])
    finally:
        if own:
            conn.close()


# --------------------------------------------------------------------------
#   The status answer and the manual checklist
# --------------------------------------------------------------------------


def status_words() -> str:
    """What is happening, live: the mode, the counts, the overdue rows, the portals.

    Every number comes from `counts()` and `overdue_count()` - the tracker's own
    rows - so the answer can never be a hope. It carries no value of the
    owner's: a broker's name and a public URL are not his details.
    """
    live = state()
    counted = live["counts"]
    overdue = overdue_count()
    lines = [state_words(live)]
    if counted["total"]:
        lines.append(
            f"By status: {counted['queued']} queued, {counted['sent']} sent and "
            f"waiting, {counted['needs_verify_click']} waiting for YOU to click a "
            f"confirmation link or answer an ID request, "
            f"{counted['pending_window']} with the broker saying it is done and "
            f"the window still running, {counted['removed']} confirmed removed, "
            f"{counted['blocked_captcha']} blocked by a CAPTCHA and "
            f"{counted['failed']} failed.")
    if overdue:
        lines.append(
            f"{overdue} request(s) are past their wait window with no confirming "
            "answer. Say \"check for replies\" to scan the mailbox again, and "
            "check the listing yourself - a window ending is not a removal.")
    if counted["manual_todo"]:
        lines.append(
            f"{counted['manual_todo']} broker(s) need your own click on their web "
            "form. Say \"what do I need to do by hand\" for the direct links.")
    cached = len(read_directory_cache()[0])
    if cached:
        lines.append(f"The broker list cached on this PC holds {cached} broker(s).")
    else:
        lines.append("No broker list is cached on this PC yet - say \"sync the "
                     "broker list\" to load it.")
    marks = []
    for row in official_portals():
        mark = ""
        if row["done"]:
            mark = " (done" + (f" on {row['last_checked']}" if row["last_checked"]
                               else "") + ")"
        marks.append(f"{row['name']} - {row['url']}{mark}")
    lines.append("The two free official portals: " + "; ".join(marks) + ".")
    last = batch_card_state().get("last")
    if last and last.get("said"):
        lines.append("The last removal-email batch: " + str(last["said"]))
    return "\n".join(lines)


def manual_checklist(conn: Optional[sqlite3.Connection] = None, *,
                     limit: int = CHECKLIST_LIMIT) -> dict:
    """The brokers that need the owner's own click, plus the two official portals.

    Returns `{"portals", "web_form", "shown", "more", "no_route"}`. `web_form`
    is every tracked web-form broker that publishes an opt-out link, `shown` is
    the first `limit` of them (the printed list is bounded, the count is not),
    and `no_route` is how many publish no link at all - said rather than hidden.
    """
    own = conn is None
    conn = conn or connect()
    try:
        rows = [dict(row) for row in conn.execute(
            "SELECT name, optout_url, category FROM brokers "
            "WHERE method = 'web_form' ORDER BY name COLLATE NOCASE")]
        with_url = [row for row in rows if str(row.get("optout_url") or "").strip()]
        return {"portals": official_portals(conn),
                "web_form": with_url,
                "shown": with_url[:max(1, int(limit or CHECKLIST_LIMIT))],
                "more": max(0, len(with_url) - max(1, int(limit or
                                                        CHECKLIST_LIMIT))),
                "no_route": len(rows) - len(with_url)}
    finally:
        if own:
            conn.close()


def checklist_words(*, limit: int = CHECKLIST_LIMIT) -> str:
    """The two portals and the web-form brokers, each with a link the owner clicks.

    A CHECKLIST, NOT AN AUTOMATION. Nothing here is filled in, submitted or
    clicked by this tool: each line is a public URL and the owner's own browser
    does the rest. The two official portals come first because they are the
    highest-leverage free wins in the whole feature.
    """
    got = manual_checklist(limit=limit)
    lines = ["Two free official portals first - one-time wins no broker request "
             "can replace:"]
    for row in got["portals"]:
        mark = " (done)" if row["done"] else ""
        lines.append(f"- {row['name']} - {row['url']}{mark}")
    lines.append("")
    if got["shown"]:
        lines.append(
            f"Then these {len(got['web_form'])} broker(s) need your own click on "
            "their opt-out page. I cannot fill in a CAPTCHA or a Turnstile form, "
            "and I will not try:")
        for row in got["shown"]:
            lines.append(f"- {row['name']} - {row['optout_url']}")
        if got["more"]:
            lines.append(f"... and {got['more']} more in the broker list, all "
                         "tracked here.")
    else:
        lines.append(
            "No web-form broker is tracked yet. Say \"sync the broker list\" to "
            "load the directory, and the CAPTCHA-heavy ones will appear here with "
            "a direct link.")
    if got["no_route"]:
        lines.append(
            f"{got['no_route']} tracked web-form broker(s) publish no opt-out link "
            "at all, so there is nothing to hand you for them.")
    lines.append("Nothing here is filled in or clicked for you: each link opens "
                 "the broker's own page, and you decide what to send.")
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   The live state every answer is built from
# --------------------------------------------------------------------------


def gmail_state() -> dict:
    """Whether this PC has the Gmail mail details the local engine would use.

    Read through `jarvis_email`'s OWN helpers (`imap_user`, `imap_password`),
    which resolve the same Credential Manager entries the mail tools read - so
    this is the app password the batch sender will really use (`#1506`, the
    owner's decision of 2026-11-25), not a second copy of it.

    THE VALUES ARE NEVER RETURNED: this answers two booleans and nothing else.
    A PC without `jarvis_email` answers False for both, honestly - "not set",
    which is what it is.
    """
    out = {"address": False, "password": False, "ready": False}
    try:
        import jarvis_email as mail
        out["address"] = bool(str(mail.imap_user() or "").strip())
        out["password"] = bool(str(mail.imap_password() or "").strip())
    except Exception:                       # noqa: BLE001 - module absent: not set
        return out
    out["ready"] = out["address"] and out["password"]
    return out


def optery_state() -> dict:
    """Whether an Optery API key is stored on this PC - and never its value.

    The presence check only, through the same resolver every other named secret
    uses (`jarvis_token_store.resolve_secret`). PR 1 stores no key and calls
    nothing; PR 3's adapter reads the same two names (`OPTERY_ENV`,
    `OPTERY_TARGET`), so this answer stays true when the adapter lands.
    """
    try:
        import jarvis_token_store as store
        raw = store.resolve_secret(OPTERY_ENV, OPTERY_TARGET)
    except Exception:                       # noqa: BLE001 - absent: not set
        return {"set": False, "env": OPTERY_ENV}
    return {"set": bool(str(raw or "").strip()), "env": OPTERY_ENV}


def state() -> dict:
    """Everything an answer needs, read live, with no value in it.

    {"mode", "mode_source", "gmail", "optery", "counts", "portals_set"}
    """
    current, source = read_mode()
    return {"mode": current, "mode_source": source, "gmail": gmail_state(),
            "optery": optery_state(), "counts": counts()}


def state_words(live: Optional[dict] = None) -> str:
    """The live state in plain sentences - the line every answer carries."""
    live = live if live is not None else state()
    counts_now = live["counts"]
    gmail_now = live["gmail"]
    optery_now = live["optery"]
    gmail_said = ("The Gmail App Password is set" if gmail_now.get("ready")
                  else "The Gmail App Password is not set")
    optery_said = ("an Optery API key is set" if optery_now.get("set")
                   else "no Optery API key is set")
    if not counts_now["total"] and not counts_now["brokers"]:
        tracked = ("Nothing is tracked yet: the tracker has no brokers and no "
                   "requests in it.")
    else:
        tracked = (f"The tracker holds {counts_now['brokers']} broker(s) and "
                   f"{counts_now['total']} request(s): {counts_now['queued']} queued, "
                   f"{counts_now['sent']} sent, {counts_now['needs_verify_click']} "
                   f"waiting for you to click a confirmation link, "
                   f"{counts_now['removed']} confirmed removed, "
                   f"{counts_now['manual_todo']} needing your own click on a web form.")
    return (f"Right now the data removal mode is {MODE_NAMES[live['mode']]}, and "
            f"that setting comes from {live['mode_source']}. {gmail_said} and "
            f"{optery_said}. {tracked}")


# --------------------------------------------------------------------------
#   The self-explainer: the four topics
# --------------------------------------------------------------------------

#: The four topics, in the order a person asks them. A topic outside this tuple
#: is answered by naming these four - never by a refusal.
TOPICS = ("overview", "pros_cons", "limits", "official_portals")

#: The topic each word a person might use belongs to.
TOPIC_WORDS = {
    "overview": "overview",
    "what": "overview",
    "how it works": "overview",
    "how does it work": "overview",
    "pros cons": "pros_cons",
    "pros and cons": "pros_cons",
    "compare": "pros_cons",
    "compare the modes": "pros_cons",
    "which mode": "pros_cons",
    "limits": "limits",
    "what it cannot do": "limits",
    "official portals": "official_portals",
    "portals": "official_portals",
}

PROS_CONS_LOCAL = (
    "Local (the default):\n"
    "- Free. Your details never leave this PC - no service, no account, no cloud.\n"
    "- Deletion requests go out through your own Gmail App Password, behind one "
    "approval card per batch, and every reply is tracked here.\n"
    "- It uses the free open-source broker directory (Optery publishes one with "
    "640+ brokers), cached on this PC.\n"
    "- The cost: roughly a fifth to a third of brokers still need YOU - clicking "
    "a confirmation link, or filling in a CAPTCHA or Turnstile form. Atlas lists "
    "those with a direct link instead of pretending it did them, and there are no "
    "before/after screenshots."
)

PROS_CONS_OPTERY = (
    "Optery's cloud API (opt-in):\n"
    "- It does the parts that need a browser: the CAPTCHA and Turnstile forms "
    "that stop an automated request, and the before/after proof screenshots.\n"
    "- It covers brokers in both the US and Canada, and it scored the highest "
    "removal rate in the Consumer Reports testing that CNET writes up.\n"
    "- The cost: it is a paid commercial service, and your name, address, phone "
    "number and email address are sent to Optery's cloud over HTTPS. That is why "
    "switching to it raises a consent card that says exactly that, and why a "
    "denied card changes nothing."
)

PROS_CONS_HYBRID = (
    "Hybrid (opt-in):\n"
    "- The widest coverage: Optery handles the brokers it covers and the "
    "CAPTCHA-heavy ones, and this PC handles the brokers it does not cover, your "
    "own custom ones, and the two free official portals.\n"
    "- The cost: the same paid Optery key and the same cloud sharing of your "
    "details as Optery's own mode, behind the same consent card."
)

LIMITS = (
    "What it does NOT do - said plainly, because a tool that oversells itself is "
    "worse than one that does less:\n"
    "- Nothing is sent, and no API is called, without an approval card. There is "
    "no bulk yes and nothing auto-approves.\n"
    "- It never tries to get round a CAPTCHA or Turnstile silently. Those brokers "
    "go on a checklist for you, with a direct link.\n"
    "- It never marks a listing \"removed\" because a form said thank you or a "
    "site answered 403. Only the verify pass, after the wait window, confirms a "
    "removal - 7 days for people-search sites, 45 for a statutory CCPA or GDPR "
    "request.\n"
    "- It does not delete accounts you made yourself (Amazon, a social network, "
    "your bank). That is the account's own delete button, and this tool does not "
    "pretend to have one.\n"
    "- It does not touch statutory public records - a deed, a court filing, a "
    "business registration. Those are public on purpose and a removal request "
    "cannot change that.\n"
    "- Removals take 7 to 45 days, and brokers re-scrape public sources "
    "afterwards, so a confirmed removal is re-checked 90 days later. A removal is "
    "not a one-off erasure."
)


def _portal_words() -> str:
    rows = official_portals()
    lines = []
    for row in rows:
        mark = " (you marked this done" + (f" on {row['last_checked']}" if
                                           row["last_checked"] else "") + ")" \
            if row["done"] else ""
        lines.append(f"- {row['name']} - {row['url']}{mark}\n  {row['note']}")
    return "\n".join(lines)


def privacy_explain(topic: str = "overview") -> str:
    """What the tool is, its modes, its limits and the two free portals.

    SIX TOPICS, all built from the LIVE state of this PC: the mode it is on,
    whether the Gmail App Password is set, whether an Optery key is set, and
    what the tracker holds. `topic` outside `TOPICS` is answered with the four
    topics named, never with a refusal - the same rule the rest of this folder
    keeps: an unknown word is a question, not a failure.
    """
    wanted = str(topic or "overview").strip().lower()
    if wanted not in TOPICS:
        return (f"I can explain the data removal tool by: {', '.join(TOPICS)}. "
                "Ask me for any of those, or ask \"" + _first_trigger() + "\".")
    live = state()
    live_line = state_words(live)
    if wanted == "overview":
        body = (
            "The data removal tool finds and tracks where data brokers list your "
            "personal details - your name, home address, phone number and email "
            "address - asks those brokers to delete the listings, checks afterwards "
            "whether the listing really went, and schedules a re-check 90 days "
            "later because brokers re-scrape public sources.\n"
            "It has three modes. Local, the default, does all of it on this PC with "
            "your own Gmail App Password and never sends your details anywhere. "
            "Optery's cloud API and hybrid do the CAPTCHA-heavy brokers for you, "
            "and send your details to Optery, so switching to either one raises a "
            "consent card first.\n"
            "Two free official portals are worth doing before any of it: Google's "
            "Results About You, and California DROP if you live in California.\n"
            f"{profile_words()}\n"
            f"{live_line}"
        )
        return body
    if wanted == "pros_cons":
        return (f"{live_line}\n\n{PROS_CONS_LOCAL}\n\n{PROS_CONS_OPTERY}\n\n"
                f"{PROS_CONS_HYBRID}")
    if wanted == "limits":
        return f"{live_line}\n\n{LIMITS}"
    return (f"{live_line}\n\nTwo free official portals are worth doing before, or "
            f"beside, any broker request:\n{_portal_words()}\n"
            "Both are a checklist here with the real link - the tool never fills "
            "one in for you.")


def _first_trigger() -> str:
    """The first sentence `prompt()` claims, so an unknown topic can point at
    a real one rather than inventing words."""
    return TRIGGERS[0][2]


# --------------------------------------------------------------------------
#   The capability card, for the model's own grounding
# --------------------------------------------------------------------------


def get_prompt_context() -> str:
    """The live capability card the model is given when a turn is about this.

    THE FIVE FACTS, read from live state with ZERO raw PII in them: the active
    mode, whether Gmail is connected, whether an Optery key is configured, the
    tracked counts (queued, sent, needs_verify_click, removed), and the four
    rules that must never be got wrong in a discussion. The masked labels are
    the only thing allowed to stand for a detail - never a value.

    This is Layer B of the owner's design (2026-11-26, section 4): an
    open-ended follow-up ("is Optery worth it if I mostly care about
    Whitepages?") is answered by the model, grounded in THIS text, so it cannot
    invent an ability the PC does not have or a limit that does not exist.
    """
    live = state()
    counts_now = live["counts"]
    gmail_now = live["gmail"]
    return (
        "DATA REMOVAL - the live state of THIS PC, read now. Answer only from "
        "these facts.\n"
        f"- Mode: {live['mode']} ({MODE_NAMES[live['mode']]}), setting from "
        f"{live['mode_source']}.\n"
        f"- Gmail connected: {'yes' if gmail_now.get('ready') else 'no'}"
        + ("" if gmail_now.get("ready") else
           " (the App Password is not set, so the local engine cannot send yet)")
        + ".\n"
        f"- Optery key configured: {'yes' if live['optery'].get('set') else 'no'}"
        + ("" if live["optery"].get("set") else
           " (so no Optery call can happen even in a cloud mode)")
        + ".\n"
        f"- Tracked now: {counts_now['queued']} queued, {counts_now['sent']} sent, "
        f"{counts_now['needs_verify_click']} waiting for a confirmation click, "
        f"{counts_now['removed']} confirmed removed.\n"
        f"- Profile: {profile_words()}\n"
        "THE FOUR RULES, and they are not negotiable:\n"
        "1. Local mode is free, keeps every detail on this PC, and leaves the "
        "CAPTCHA/Turnstile brokers on a manual checklist.\n"
        "2. Optery's API is a paid service and sends the details to Optery's "
        "cloud, which is why it is opt-in behind a consent card; it handles the "
        "forms and the before/after screenshots.\n"
        "3. Every send and every API call needs its own approval card - at most "
        "20 brokers per card and 250 emails a day.\n"
        "4. Never say a removal is done until the verify pass confirms it: a "
        "confirmation screen or a 403 is not a removal.\n"
        "Never quote a home address, phone number or full email address; the "
        "masked labels above are all that may be repeated."
    )


# --------------------------------------------------------------------------
#   The sentences the chat grammar claims
# --------------------------------------------------------------------------
#
# WHY HERE AND NOT IN jarvis_quick.py. `jarvis_quick.py` is 37,000 lines and is
# the ONE file every feature adds to; the words this feature claims are this
# feature's, so they live with it and `jarvis_quick.py` only asks this file
# whether a sentence is its own (the route `jarvis_cloud_settings.py` took on
# 2026-11-18). The grammar below is WHOLE-SENTENCE: a sentence that does not
# match exactly is not claimed, so "remove my personal info from the internet"
# in the middle of a longer request still reaches whatever handled it before.
#
# Every trigger in the owner's spec (2026-11-26, section 4, Layer A) is here,
# and `backend/test_privacy_removal.py` puts all of them through the REAL
# `jarvis_quick.match()` and requires this file's own intent back.

#: (pattern, topic, the sentence that names it) - matched against the
#: normalised sentence with `fullmatch`, so nothing here can swallow a longer
#: request. `_ART` allows the leading "the"/"my"/"a" the owner really says.
_ART = r"(?:the\s+|my\s+|your\s+|a\s+|an\s+)?"
_TOOL = (r"(?:data removal tool|data removal|personal data removal tool|"
         r"personal data removal|personal info removal tool|personal information "
         r"removal tool|personal info removal|personal information removal|"
         r"privacy removal tool|privacy removal)")

TRIGGERS = (
    # --- overview ---------------------------------------------------------
    (rf"{_ART}{_TOOL}", "overview", "what is the data removal tool"),
    (rf"what(?:s| is| does)(?:\s+{_ART}{_TOOL})?(?:\s+do|\s+work)?", "overview",
     "what is the data removal tool"),
    (rf"what (?:is|are) {_ART}{_TOOL}(?: do| work| for)?", "overview",
     "what is the data removal tool"),
    (rf"what does {_ART}{_TOOL} do", "overview", "what is the data removal tool"),
    (rf"how does {_ART}{_TOOL} work", "overview",
     "how does your personal info removal work"),
    (rf"how does your (?:personal info|personal information) removal work", "overview",
     "how does your personal info removal work"),
    (rf"(?:can|could|will|would) you (?:remove|delete|take down) my "
     r"(?:personal info|personal information|personal data|details) from the "
     r"internet", "overview",
     "can you remove my personal info from the internet"),
    (rf"(?:tell me about|explain) {_ART}{_TOOL}", "overview",
     "what is the data removal tool"),
    # --- pros and cons ---------------------------------------------------
    (rf"pros and cons of {_ART}(?:data|privacy|personal info) removal", "pros_cons",
     "pros and cons of local vs optery"),
    (rf"pros and cons of local vs\.? optery(?: api)?", "pros_cons",
     "pros and cons of local vs optery"),
    (rf"pros and cons of local (?:vs\.?|versus|or) optery(?: api)?", "pros_cons",
     "pros and cons of local vs optery"),
    (rf"(?:should|shall) i use local or optery(?: api)?", "pros_cons",
     "should I use local or optery"),
    (rf"local (?:vs\.?|versus|or) optery(?: api)?(?: for data removal)?", "pros_cons",
     "pros and cons of local vs optery"),
    (rf"which is better,? local or optery(?: api)?", "pros_cons",
     "pros and cons of local vs optery"),
    # --- limits ----------------------------------------------------------
    (rf"what can(?:t|not) {_ART}{_TOOL} do", "limits",
     "what can't the data removal tool do"),
    (rf"what can(?:t|not) you do (?:about|with) (?:data removal|my personal info|"
     r"my personal information)", "limits", "what can't the data removal tool do"),
    (rf"how private is (?:data removal|the data removal tool|{_TOOL})", "limits",
     "how private is data removal"),
    (rf"what are the limits of {_ART}{_TOOL}", "limits",
     "what can't the data removal tool do"),
    # --- the two free official portals ------------------------------------
    (rf"what (?:are|is) the official (?:portals|tools)(?: for data removal)?",
     "official_portals", "the official portals for data removal"),
    (rf"google results about you", "official_portals",
     "the official portals for data removal"),
    (rf"california drop", "official_portals", "the official portals for data removal"),
)

#: (pattern, mode) - the change sentences. They go through the settings
#: registry's ONE row, which calls `set_mode()` above.
_CHANGES = (
    rf"(?:switch|set|change|put|move) {_ART}(?:data removal|personal info removal|"
    rf"privacy removal)(?: tool)? (?:to|over to|onto) (?P<mode>[a-z0-9 ]+)",
    rf"use (?P<mode>[a-z0-9 ]+) for (?:data removal|personal info removal|"
    rf"privacy removal)",
    rf"use (?P<mode>local|optery api|optery|hybrid)(?: data removal)?(?: instead)?",
    rf"(?:switch|set|change) (?P<mode>data removal) (?:to|into) (?P<mode2>[a-z0-9 ]+)",
)


def _norm(text: str) -> str:
    """A sentence as this file compares it: lower case, tidy spaces, no
    apostrophes (so "can't" and "cannot" both read the same way), no final
    full stop or question mark."""
    said = str(text or "").lower().replace("\u2019", "'").replace("'", "")
    said = re.sub(r"[^a-z0-9]+", " ", said)
    return " ".join(said.split())


def _topic_for(said: str) -> Optional[str]:
    """The topic a whole normalised sentence names, or None."""
    for pattern, topic, _example in TRIGGERS:
        if re.fullmatch(pattern, said):
            return topic
    return None


def _mode_change_for(raw: str) -> Optional[str]:
    """The mode a whole sentence asks for, or None - never a guess.

    "use local data removal" and "switch data removal to the optery api" both
    land here; "use my local bank" does not, because every pattern needs the
    words "data removal" or "personal info removal" beside the mode.
    """
    said = _norm(raw)
    if "data removal" not in said and "personal info removal" not in said \
            and "privacy removal" not in said:
        return None
    for pattern in _CHANGES:
        match = re.fullmatch(pattern, said)
        if not match:
            continue
        groups = match.groupdict()
        for key in ("mode", "mode2"):
            got = groups.get(key)
            if got:
                mode_id = mode_from_words(got)
                if mode_id:
                    return mode_id
    return None


#: (pattern, intent) - the five ENGINE sentences (PR 2). Whole-sentence like the
#: topics above, so nothing longer is swallowed: "send my removal emails" is the
#: batch, but "send an email to Bob about my removal emails" is not this
#: feature's sentence at all. `_mode_change_for` runs before this table, so a
#: sentence that names a mode still goes to the consent-carded switch.
ACTIONS = (
    # -- what is tracked, and how it is going ------------------------------
    (r"(?:what|which) (?:data )?brokers have my (?:info|information|details|data)",
     "privacy_status"),
    (r"(?:show|give me|tell me|whats|what is) (?:me )?(?:my )?(?:removal|data "
     r"removal|privacy removal|opt out|optout) status", "privacy_status"),
    (r"(?:how is|hows) my (?:data |privacy )?removal going", "privacy_status"),
    # -- refresh the directory ---------------------------------------------
    (r"(?:sync|refresh|update|download) (?:the |my )?(?:data )?brokers? "
     r"(?:list|directory)", "privacy_sync_directory"),
    # -- send the batch ----------------------------------------------------
    (r"send (?:my |the )?(?:removal|opt out|optout|deletion|data removal) "
     r"emails", "privacy_send_optout_batch"),
    (r"send (?:my |the )?(?:removal|opt out|optout|deletion) requests",
     "privacy_send_optout_batch"),
    # -- scan the mailbox --------------------------------------------------
    (r"check (?:for )?(?:my )?(?:broker |removal )?replies",
     "privacy_check_replies"),
    (r"check (?:the |my )?(?:broker |removal )?(?:replies|inbox for replies)",
     "privacy_check_replies"),
    # -- the manual checklist ----------------------------------------------
    (r"what do i (?:need|have) to do (?:by hand|myself|manually)",
     "privacy_manual_checklist"),
    (r"what (?:needs|has) to be done (?:by hand|myself|manually)",
     "privacy_manual_checklist"),
    (r"what needs doing (?:by hand|myself|manually)",
     "privacy_manual_checklist"),
)


def _action_for(said: str) -> Optional[str]:
    """The engine intent a whole normalised sentence is, or None."""
    for pattern, intent in ACTIONS:
        if re.fullmatch(pattern, said):
            return intent
    return None


def prompt(normalized: str, raw: str = "") -> Optional[dict]:
    """The intent this sentence is, or None when it is not this feature's.

    Returns `{"intent": "privacy_explain", "topic": ...}`,
    `{"intent": "privacy_mode_change", "mode": ...}` or one of the five engine
    intents with no fields - the same shape `jarvis_cloud_settings.prompt`
    returns, so `jarvis_quick.py` needs one helper and no knowledge of this
    file's rules.

    THE ORDER IS THE MEANING. A mode change is checked first (it names a mode,
    and no other sentence here does), then the five engine sentences, then the
    four explainer topics. A sentence none of them fits is not this feature's
    and goes wherever it went before.
    """
    text = raw or normalized or ""
    wanted = _mode_change_for(text)
    if wanted:
        return {"intent": "privacy_mode_change", "mode": wanted}
    said = _norm(text)
    action = _action_for(said)
    if action:
        return {"intent": action}
    topic = _topic_for(said)
    if topic:
        return {"intent": "privacy_explain", "topic": topic}
    return None


# --------------------------------------------------------------------------
#   The command line: what this PC holds, and never a value
# --------------------------------------------------------------------------


def main(argv=None) -> int:
    """`py -3 jarvis_privacy_removal.py [overview|pros_cons|limits|
    official_portals|sync|status|checklist]` - what this PC holds, masked.

    `sync` is the ONE command here that reaches a network, and only because a
    person typed it: it refreshes the broker list from the public directory.
    """
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in TOPICS:
        print(privacy_explain(args[0]))
        return 0
    if args and args[0] == "sync":
        print(sync_words(sync_directory()))
        return 0
    if args and args[0] == "status":
        print(status_words())
        return 0
    if args and args[0] == "checklist":
        print(checklist_words())
        return 0
    current, source = read_mode()
    print(f"Mode: {current} ({source})")
    print(profile_words())
    print(state_words())
    print("")
    print("The tracker is at: " + str(tracker_path()))
    print("The profile is at: " + str(profile_path()) + " (never in this repository)")
    print("The broker cache is at: " + str(brokers_cache_path()))
    print("")
    print("Topics: " + ", ".join(TOPICS))
    print("Commands: sync, status, checklist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
