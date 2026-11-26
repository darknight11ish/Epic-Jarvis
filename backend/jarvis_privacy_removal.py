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

WHAT PR 1 DOES NOT DO, PLAINLY

This is the first of three pull requests and it is deliberately inert:

  * No email is ever sent. The Gmail App Password path (`#1506`) and the
    carded batch sender are PR 2.
  * No broker directory is downloaded or parsed, and no `urllib` request is
    made by this file. PR 2 adds the directory, PR 3 the API client.
  * No Optery call is made and no Optery key is stored. This file only ASKS
    whether a key is present, through the same credential helper every other
    named secret uses, so PR 3 needs no change here.
  * No route, no Settings page, no desktop or phone screen. The mode dial is
    changeable from chat and from the settings registry; the screens come with
    PR 2.
  * Nothing is in `_where.SHIPPED` yet, on the owner's own ruling: only the
    pull request that wires a live caller may ship a module whole. It is on
    `NOT_SHIPPED` in `backend/test_shipped_modules.py` with that reason, and
    `jarvis_quick.py` imports it inside a try, exactly as that suite's
    `REPO_ONLY_IMPORTS` requires.

STDLIB ONLY, ON PURPOSE (the owner's requirement, 2026-11-26). This file
imports `json`, `os`, `re`, `sqlite3`, `threading`, `time` and `pathlib` and
nothing else - no third-party package, so CI's exact package list can never be
broken by it. It makes no network call in this slice at all.

NO PII, ANYWHERE. Nothing in this file writes a detail of the owner's to a log,
an audit line, an error message, an answer or a card's own summary. The masked
labels exist for that reason and `mask_value()` is the only function that turns
a stored value into something a person may read.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
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
#: ONLY WHAT REALLY EXISTS IS NAMED. PR 1 answers `privacy_explain`; it is
#: read-only, so there is no switch for it and the Settings page draws no empty
#: group. PR 2 adds `privacy_status`, `privacy_manual_checklist`,
#: `privacy_send_optout_batch` and `privacy_check_replies`; PR 3 adds
#: `privacy_optery_action` and `privacy_set_mode`, each to this same row as it
#: becomes real. Claiming them now would be the one thing this file's own
#: docstring forbids.
TOOL_ROWS = (
    ("Privacy", ("privacy_explain",)),
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
    """Drop every pending consent card. Tests only; never called in production."""
    with _LOCK:
        _PENDING.clear()
        _WITHDRAWN.clear()
        _LAST.clear()


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


def prompt(normalized: str, raw: str = "") -> Optional[dict]:
    """The intent this sentence is, or None when it is not this feature's.

    Returns `{"intent": "privacy_explain", "topic": ...}` or
    `{"intent": "privacy_mode_change", "mode": ...}` - the same shape
    `jarvis_cloud_settings.prompt` returns, so `jarvis_quick.py` needs one
    helper and no knowledge of this file's rules.
    """
    text = raw or normalized or ""
    wanted = _mode_change_for(text)
    if wanted:
        return {"intent": "privacy_mode_change", "mode": wanted}
    topic = _topic_for(_norm(text))
    if topic:
        return {"intent": "privacy_explain", "topic": topic}
    return None


# --------------------------------------------------------------------------
#   The command line: what this PC holds, and never a value
# --------------------------------------------------------------------------


def main(argv=None) -> int:
    """`py -3 jarvis_privacy_removal.py [overview|pros_cons|limits|
    official_portals]` - what this PC holds, with every detail masked."""
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in TOPICS:
        print(privacy_explain(args[0]))
        return 0
    current, source = read_mode()
    print(f"Mode: {current} ({source})")
    print(profile_words())
    print(state_words())
    print("")
    print("The tracker is at: " + str(tracker_path()))
    print("The profile is at: " + str(profile_path()) + " (never in this repository)")
    print("")
    print("Topics: " + ", ".join(TOPICS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
