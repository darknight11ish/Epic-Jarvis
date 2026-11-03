"""test_connected_accounts.py - the accounts Jarvis can use, what it may do with
each one, what is changeable, and how each is removed (jarvis_accounts.py's
appended section; API-CONTRACT.md sections 2, 3, 4, 5 and 8).

    python3 backend/test_connected_accounts.py        (Windows: py -3 ...)

WHAT THIS PROVES, and why each check is here:

  - the TWELVE families, in one table, with the exact ids and kinds the frozen
    contract names, and the entry NAMES the owning modules really export - so a
    target name is never a second, drifting copy (the check compares every one
    against jarvis_calendar / jarvis_email / jarvis_home / jarvis_research /
    jarvis_search / jarvis_chatbot_api / jarvis_google_calendar themselves);
  - the abilities are resolved LIVE: swap jarvis_framework and jarvis_gate for
    fakes, and the same row reports the fake tiers; swap them again and it
    changes. Nothing in this module is a hardcoded copy of a tier;
  - a MISSING permission table yields tier None and asks None, with the row
    saying so - never a guessed tier and never an invented "never";
  - an action the gate has no risk row for carries classified False;
  - probe=False opens NO socket and writes nothing: a fake store whose every
    use raises, a fake verifier that records every call, and socket.socket
    itself replaced by a raising function - and the answer still comes back;
  - "connected" ONLY when a verifier actually ran in that call: a verifier
    that reports connected even when it was not asked cannot make a
    probe=False answer say connected, and a verifier that raised says "saved"
    with tested False;
  - the not_an_account families (Notion, Spotify/Drive/Dropbox) are never
    connected and carry no abilities;
  - every row carries connected_at None and connected_at_known False - the
    honest answer, because Credential Manager keeps no timestamp;
  - NO SECRET VALUE can appear anywhere: a sentinel is put into the injected
    store and the secret environment variables, and the JSON of every row,
    sentence, state_words and view must not contain it;
  - handle_accounts_get("") is (200, accounts_view()), ignores any query
    string, and never probes; the shipped /api/accounts/addresses answer keeps
    its own view()/handle_get() with its eight fields, untouched and tested
    separately;
  - account_from_words matches its closed vocabulary and returns None for a
    sentence that names nothing on it;
  - importing jarvis_accounts on its own pulls in no other backend module, so
    it still imports on a PC missing them.

Nothing here opens a socket, writes the owner's store or needs the owner's PC.
The real Credential Manager is never touched: jarvis_token_store is replaced by
an in-memory stand-in before this module imports anything that reads it.
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import traceback
import types
from contextlib import contextmanager
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-connected-accounts-"))
# Before anything imports jarvis_framework / jarvis_accounts: both read the
# config folder once, and no check here may touch the owner's real one.
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
# The suite is runnable on its own: never compare against a live install.
os.environ.pop("JARVIS_BACKEND", None)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

PASSED, FAILED, SKIPPED = [], [], []

#: A fake secret, built by concatenation so nothing here is shaped like a real
#: one and no scanner trips over the file.
SENTINEL = "sen" + "tinel-" + "not-a-real-value-" + "4f1c"

_ABSENT = object()


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


# --------------------------------------------------------------------------
#   The credential store stand-in, installed BEFORE any backend module imports
# --------------------------------------------------------------------------

STORE = {}
_STORES = {}
STORE_WRITES = []
STORE_DELETES = []
BOOM_READS = False
BOOM_OPEN = False


class FakeStoreError(Exception):
    """The shape jarvis_token_store.StoreError has, so isinstance checks work."""


class _FakeStore:
    def __init__(self, target):
        self.target = target
        self.reads = 0

    def read(self):
        self.reads += 1
        if BOOM_READS:
            raise FakeStoreError("this store refuses every use")
        got = STORE.get(self.target)
        if isinstance(got, Exception):
            raise got
        return got

    def write(self, value):                 # a read path must never reach here
        STORE_WRITES.append(self.target)
        raise AssertionError("a read-only answer wrote to the credential store")

    def delete(self):
        STORE_DELETES.append(self.target)
        raise AssertionError("a read-only answer deleted a credential")


def _default_store(target):
    if BOOM_OPEN:
        raise FakeStoreError("this store cannot even be opened")
    target = str(target)
    if target not in _STORES:
        _STORES[target] = _FakeStore(target)
    return _STORES[target]


def _resolve_secret(env_name, target, **_kw):
    got = str(os.environ.get(str(env_name), "") or "").strip()
    if got:
        return got
    return str(_default_store(target).read() or "")


def _store_secret(target, value, **_kw):
    STORE[str(target)] = str(value)


TOKEN_STORE = types.ModuleType("jarvis_token_store")
TOKEN_STORE.StoreError = FakeStoreError
TOKEN_STORE.Unavailable = FakeStoreError
TOKEN_STORE.default_store = _default_store
TOKEN_STORE.resolve_secret = _resolve_secret
TOKEN_STORE.store_secret = _store_secret
sys.modules["jarvis_token_store"] = TOKEN_STORE

from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_accounts.py", "jarvis_connect_account.py",
                "jarvis_token_store.py", "jarvis_vault.py", "jarvis_notes.py",
                "jarvis_notes_edit.py", "jarvis_search.py", "jarvis_chatbot_api.py",
                "jarvis_google_calendar.py", "jarvis_calendar.py", "jarvis_email.py",
                "jarvis_home.py", "jarvis_research.py", "jarvis_asks_first.py",
                "jarvis_local_http.py")

import jarvis_accounts as A  # noqa: E402
import jarvis_asks_first as ASKS  # noqa: E402
import jarvis_calendar as CAL  # noqa: E402
import jarvis_chatbot_api as CHAT  # noqa: E402
import jarvis_connect_account as CAC  # noqa: E402
import jarvis_email as EMAIL  # noqa: E402
import jarvis_google_calendar as GC  # noqa: E402
import jarvis_home as HOME  # noqa: E402
import jarvis_notes as NOTES  # noqa: E402
import jarvis_notes_edit as NOTES_EDIT  # noqa: E402
import jarvis_research as RES  # noqa: E402
import jarvis_search as WS  # noqa: E402


#: The twelve ids, in the contract's own order.
IDS = ("calendar_ics", "calendar_caldav", "google_calendar", "github", "email",
       "home_assistant", "search_keys", "chatbot_keys", "vault", "notes", "notion",
       "spotify_drive_dropbox")

#: Every environment variable any family is read under (plus the two the module
#: itself reads), so an outside variable cannot quietly supply an answer.
SECRET_PREFIXES = ("JARVIS_IMAP_", "JARVIS_SMTP_", "JARVIS_CALENDAR_",
                   "JARVIS_CALDAV_", "JARVIS_HOME_", "JARVIS_GITHUB",
                   "JARVIS_OBSIDIAN_VAULT", "JARVIS_JOPLIN")


def clear_env():
    for name in list(os.environ):
        if name.startswith(SECRET_PREFIXES):
            os.environ.pop(name, None)


def reset(**addresses):
    """No store, no environment, no accounts.json, no vault.json."""
    clear_env()
    STORE.clear()
    _STORES.clear()
    STORE_WRITES.clear()
    STORE_DELETES.clear()
    A.addresses_path().unlink(missing_ok=True)
    (A.addresses_path().parent / "vault.json").unlink(missing_ok=True)
    if addresses:
        A._save(**addresses)


def save_every_entry():
    """Make every fixed store entry read as saved, with the sentinel value."""
    for fam in A.FAMILIES:
        for entry in fam.store_entries:
            STORE[entry] = SENTINEL


# --------------------------------------------------------------------------
#   Fake backend modules: the LIVE resolution and the probe limits
# --------------------------------------------------------------------------

class _Swaps:
    def __init__(self):
        self.saved = []

    def set(self, name, module):
        self.saved.append((name, sys.modules.get(name, _ABSENT)))
        if module is None:
            sys.modules[name] = None      # `import name` raises ImportError
        else:
            sys.modules[name] = module
        return module

    def restore(self):
        while self.saved:
            name, old = self.saved.pop()
            if old is _ABSENT:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


@contextmanager
def swapped(pairs):
    swaps = _Swaps()
    try:
        for name, module in pairs.items():
            swaps.set(name, module)
        yield
    finally:
        swaps.restore()


def framework_module(tiers):
    mod = types.ModuleType("jarvis_framework")
    mod.action_tier = lambda action: tiers.get(str(action), "ask")
    return mod


def gate_module(rows):
    mod = types.ModuleType("jarvis_gate")

    def risk_for(action):
        got = rows.get(str(action))
        if got is None:
            return {"reversible": "no", "reach": "outbound", "swipe_ok": False,
                    "why": ("Unclassified action - treated as permanent and able to "
                            "leave this PC"),
                    "classified": False}
        return {"reversible": got[0], "reach": got[1], "swipe_ok": got[0] == "yes",
                "why": got[2], "classified": True}
    mod.risk_for = risk_for
    return mod


def asks_first_module(says):
    mod = types.ModuleType("jarvis_asks_first")
    mod.SAYS = dict(says)
    return mod


def connect_module(rows, calls, raises=False, configured=True):
    mod = types.ModuleType("jarvis_connect_account")

    def status(*, probe=True, clock=None):
        calls.append(bool(probe))
        if raises:
            raise RuntimeError("no verifier on this PC")
        return [dict(row, configured=configured) for row in rows]
    mod.status = status
    return mod


def google_module(connected, calls, raises=False):
    mod = types.ModuleType("jarvis_google_calendar")

    def status():
        calls.append(True)
        if raises:
            raise RuntimeError("no verifier on this PC")
        return {"mode": "google", "connected": bool(connected)}
    mod.status = status
    return mod


def _fake_connect_rows(connected=()):
    return [{"service": sid, "configured": True, "connected": sid in connected,
             "detail": ""} for sid in ("calendar_ics", "calendar_caldav", "github")]


# --------------------------------------------------------------------------
#   1. The table
# --------------------------------------------------------------------------

def t_the_table():
    reset()
    check("twelve families, in the contract's order",
          tuple(fam.id for fam in A.FAMILIES) == IDS,
          tuple(fam.id for fam in A.FAMILIES))
    check("FAMILIES is a tuple and Family is a frozen dataclass",
          isinstance(A.FAMILIES, tuple) and dataclasses.is_dataclass(A.Family)
          and A.Family.__dataclass_params__.frozen)
    kinds = ("card", "settings", "cli", "folder", "not_an_account")
    check("every kind is one the contract allows",
          all(fam.kind in kinds for fam in A.FAMILIES),
          [fam.kind for fam in A.FAMILIES])
    check("every family has a name, change, remove and can sentence",
          all(fam.name and fam.change and fam.remove and fam.can for fam in A.FAMILIES))
    check("every family's limit is a string (empty where there is none)",
          all(isinstance(fam.limit, str) for fam in A.FAMILIES))
    check("every family has a non-empty closed vocabulary, all lower case",
          all(fam.words and all(w == w.lower() and w.strip() for w in fam.words)
              for fam in A.FAMILIES))
    check("every fixed store entry is a Credential Manager entry NAME",
          all(entry.startswith("Jarvis Backend/")
              for fam in A.FAMILIES for entry in fam.store_entries))
    check("the route path is the contract's one path",
          A.OVERVIEW_PATH == "/api/accounts", A.OVERVIEW_PATH)
    check("the five kinds the contract names are all present",
          {fam.kind for fam in A.FAMILIES} == set(kinds),
          {fam.kind for fam in A.FAMILIES})


# --------------------------------------------------------------------------
#   2. Every fact is the owning module's own constant
# --------------------------------------------------------------------------

def t_facts_match_the_owning_modules():
    reset()
    by_id = {fam.id: fam for fam in A.FAMILIES}

    check("calendar_ics: the iCal target and variable are jarvis_calendar's",
          by_id["calendar_ics"].store_entries == (CAL.ICS_URL_TARGET,)
          and by_id["calendar_ics"].env_names == (CAL.ICS_URL_ENV,),
          (by_id["calendar_ics"].store_entries, CAL.ICS_URL_TARGET,
           by_id["calendar_ics"].env_names, CAL.ICS_URL_ENV))

    caldav = by_id["calendar_caldav"]
    real_caldav = tuple(CAC.targets("calendar_caldav").values())
    check("calendar_caldav: the two entries are jarvis_calendar's two targets",
          caldav.store_entries == real_caldav,
          (caldav.store_entries, real_caldav))
    check("calendar_caldav: the env names are jarvis_calendar's, plus the address",
          set(caldav.env_names) == {CAL.USER_ENV, CAL.PASSWORD_ENV, CAL.URL_ENV},
          (caldav.env_names, CAL.USER_ENV, CAL.PASSWORD_ENV, CAL.URL_ENV))

    github = by_id["github"]
    check("github: the entry and variable are jarvis_research's",
          github.store_entries == (RES.TOKEN_TARGET,)
          and github.env_names == (RES.TOKEN_ENV,),
          (github.store_entries, RES.TOKEN_TARGET, github.env_names, RES.TOKEN_ENV))

    email = by_id["email"]
    check("email: the two entries are jarvis_email's targets",
          email.store_entries == (EMAIL.IMAP_USER_TARGET, EMAIL.IMAP_PASSWORD_TARGET),
          (email.store_entries, EMAIL.IMAP_USER_TARGET, EMAIL.IMAP_PASSWORD_TARGET))
    check("email: the two variables are jarvis_email's",
          email.env_names == (EMAIL.USER_ENV, EMAIL.PASSWORD_ENV),
          (email.env_names, EMAIL.USER_ENV, EMAIL.PASSWORD_ENV))
    check("email: the address keys are the ones jarvis_email reads",
          set(email.address_keys) == {"imap_host", "imap_port", "imap_mailbox",
                                      "smtp_host", "smtp_port", "smtp_tls"})

    home = by_id["home_assistant"]
    check("home_assistant: the entry and variable are jarvis_home's",
          home.store_entries == (HOME.TOKEN_TARGET,)
          and home.env_names == (HOME.TOKEN_ENV,),
          (home.store_entries, HOME.TOKEN_TARGET, home.env_names, HOME.TOKEN_ENV))
    check("home_assistant: the address key is home_url",
          home.address_keys == ("home_url",), home.address_keys)

    search = by_id["search_keys"]
    check("search_keys: the four entries are jarvis_search.KEY_TARGETS",
          sorted(search.store_entries) == sorted(WS.KEY_TARGETS.values()),
          (search.store_entries, tuple(WS.KEY_TARGETS.values())))

    chatbot = by_id["chatbot_keys"]
    check("chatbot_keys: the six entries are jarvis_chatbot_api.KEY_TARGETS",
          sorted(chatbot.store_entries) == sorted(CHAT.KEY_TARGETS.values()),
          (chatbot.store_entries, tuple(CHAT.KEY_TARGETS.values())))

    google = by_id["google_calendar"]
    check("google_calendar: the two entries are jarvis_google_calendar's targets",
          google.store_entries == (GC.TARGET_CLIENT_SECRET, GC.TARGET_REFRESH),
          (google.store_entries, GC.TARGET_CLIENT_SECRET, GC.TARGET_REFRESH))
    check("google_calendar: the write action is the one its gate call uses",
          google.abilities == (GC.ACTION_WRITE,),
          (google.abilities, GC.ACTION_WRITE))

    check("notes: the write action is jarvis_notes_edit.ACTION",
          NOTES_EDIT.ACTION in by_id["notes"].abilities, NOTES_EDIT.ACTION)

    # Every ability id must be a real line in the shipped tier table, so a
    # typo cannot silently fall through to "ask" forever.
    toml = (REPO / "backend" / "rebuilt" / "jarvis-framework.toml").read_text(
        encoding="utf-8")
    missing = [aid for fam in A.FAMILIES for aid in fam.abilities
               if not re.search(r"(?m)^" + re.escape(aid) + r"\s*=\s*\"", toml)]
    check("every ability id is a real [autonomy.tiers] line", not missing, missing)

    gate_src = (REPO / "jarvis-backend" / "jarvis_gate.py").read_text(encoding="utf-8")
    check("home_control is the action jarvis_gate maps the home write tool to",
          '"jarvis_home_control_run": "home_control"' in gate_src)
    check("google_calendar_write and edit_vault_note are real action names",
          GC.ACTION_WRITE == "google_calendar_write"
          and NOTES_EDIT.ACTION == "edit_vault_note")


# --------------------------------------------------------------------------
#   3. The closed vocabulary
# --------------------------------------------------------------------------

def t_account_from_words():
    reset()
    wrong = []
    for fam in A.FAMILIES:
        for word in fam.words:
            got = A.account_from_words("tell me about " + word)
            if got != fam.id:
                wrong.append((word, got, fam.id))
    check("every family's words resolve to that family", not wrong, wrong)
    check("longest phrase wins: google calendar, not the iCal link",
          A.account_from_words("what can you do with my google calendar")
          == "google_calendar")
    check("... google drive is the not-an-account family",
          A.account_from_words("is google drive connected") == "spotify_drive_dropbox")
    check("... and 'disconnect notion' is Notion",
          A.account_from_words("how do i disconnect notion") == "notion")
    check("case and spacing do not matter",
          A.account_from_words("  CONNECT   My   GitHub ") == "github")
    check("a sentence naming nothing on the list returns None",
          A.account_from_words("what accounts are connected to jarvis") is None)
    check("whole words only: 'githubby' is not GitHub",
          A.account_from_words("githubby") is None)
    for bad in ("", None, 42, {"x": 1}):
        check(f"account_from_words({bad!r}) is None",
              A.account_from_words(bad) is None)


# --------------------------------------------------------------------------
#   4. Abilities are resolved LIVE, never copied
# --------------------------------------------------------------------------

def t_abilities_are_resolved_live():
    reset()
    says_a = {"auto": "FAKE: does it without asking",
              "ask": "FAKE: asks you first, every time"}
    says_b = {"auto": "FAKE: second table",
              "ask": "FAKE: second table asks",
              "never": "FAKE: second table says never"}
    with swapped({
        "jarvis_framework": framework_module({"calendar_read": "auto"}),
        "jarvis_gate": gate_module({"calendar_read": ("yes", "local", "fake why one")}),
        "jarvis_asks_first": asks_first_module(says_a),
    }):
        first = A.abilities("calendar_ics")[0]
    check("a swapped jarvis_framework changes the tier at once",
          first["tier"] == "auto", first)
    check("... the ask words come from jarvis_asks_first.SAYS",
          first["says"] == "FAKE: does it without asking", first)
    check("... and asks is False for auto", first["asks"] is False, first)
    check("... while the gate's own why is carried through",
          first["why"] == "fake why one" and first["classified"] is True, first)

    with swapped({
        "jarvis_framework": framework_module({"calendar_read": "never"}),
        "jarvis_gate": gate_module({"calendar_read": ("no", "outbound", "fake why two")}),
        "jarvis_asks_first": asks_first_module(says_b),
    }):
        second = A.abilities("calendar_ics")[0]
        in_rows = next(row for row in A.rows() if row["id"] == "calendar_ics")
    check("swapping the table again changes it again - nothing is hardcoded",
          second["tier"] == "never"
          and second["says"] == "FAKE: second table says never"
          and second["asks"] is True, second)
    check("rows() uses the same live answer",
          in_rows["abilities"][0]["tier"] == "never", in_rows["abilities"])

    # A tier outside the four is NOT trusted as a tier.
    with swapped({
        "jarvis_framework": framework_module({"calendar_read": "perhaps"}),
        "jarvis_gate": gate_module({}),
        "jarvis_asks_first": asks_first_module(ASKS.SAYS),
    }):
        third = A.abilities("calendar_ics")[0]
    check("an answer outside auto/notify/ask/never is not taken as a tier",
          third["tier"] is None and third["asks"] is None, third)


def t_a_missing_permission_table_is_said_so():
    reset()
    with swapped({"jarvis_framework": None, "jarvis_gate": None,
                  "jarvis_asks_first": None}):
        rows = A.abilities("github")
        whole_list = A.rows()
    check("every ability row has tier None when the table cannot be read",
          rows and all(row["tier"] is None for row in rows), rows)
    check("... asks is None, never a guess", all(row["asks"] is None for row in rows))
    check("... says is empty", all(row["says"] == "" for row in rows))
    check("... the row says the permission table could not be read",
          all("permission table could not be read" in row["why"] for row in rows), rows)
    check("... no row anywhere invents 'never'",
          not [row for row in whole_list
               for ability in row["abilities"] if ability["tier"] == "never"])
    check("... and the empty table is not a crash",
          len(whole_list) == len(A.FAMILIES))


def t_gate_unclassified_is_marked():
    reset()
    with swapped({
        "jarvis_framework": framework_module({}),
        "jarvis_gate": gate_module({"home_read": ("yes", "local", "reads state")}),
        "jarvis_asks_first": asks_first_module(ASKS.SAYS),
    }):
        rows = A.abilities("home_assistant")
    by_action = {row["action"]: row for row in rows}
    check("a gate-classified action carries classified True",
          by_action["home_read"]["classified"] is True, by_action["home_read"])
    check("a gate-unclassified action carries classified False",
          by_action["home_control"]["classified"] is False, by_action["home_control"])
    check("... and the gate's own unclassified warning is the why",
          "Unclassified action" in by_action["home_control"]["why"],
          by_action["home_control"])


# --------------------------------------------------------------------------
#   5. probe=False opens no socket and writes nothing
# --------------------------------------------------------------------------

def _boom(*_args, **_kwargs):
    raise AssertionError("something tried to open a socket on the default path")


def t_probe_false_opens_nothing():
    global BOOM_READS, BOOM_OPEN
    reset()
    for fam in A.FAMILIES:
        for name in fam.env_names:
            os.environ[name] = SENTINEL
    BOOM_READS = True
    connect_calls, google_calls = [], []
    before = {str(path) for path in _TMP.rglob("*")}
    real_socket, real_connect = socket.socket, socket.create_connection
    socket.socket, socket.create_connection = _boom, _boom
    try:
        with swapped({
            "jarvis_connect_account": connect_module(
                _fake_connect_rows(connected=("github",)), connect_calls),
            "jarvis_google_calendar": google_module(True, google_calls),
        }):
            got_rows = A.rows()
            got_view = A.accounts_view()
            got_sentence = A.sentence()
            got_words = [A.state_words(fam.id) for fam in A.FAMILIES]
            got_one = A.state_of("github")
    finally:
        socket.socket, socket.create_connection = real_socket, real_connect
        BOOM_READS = False
    after = {str(path) for path in _TMP.rglob("*")}

    check("probe=False never asks the card verifier for a service",
          connect_calls == [], connect_calls)
    check("probe=False never asks Google for a status", google_calls == [], google_calls)
    check("probe=False never says connected",
          not [row for row in got_rows if row["state"] == "connected"])
    check("probe=False marks every verifier-bearing row as not tested",
          all(row["tested"] is False for row in got_rows))
    check("probe=False writes no file", before == after, (before, after))
    check("probe=False writes no credential", STORE_WRITES == [], STORE_WRITES)
    check("probe=False deletes no credential", STORE_DELETES == [], STORE_DELETES)
    check("probe=False still answers every question",
          len(got_rows) == 12 and got_sentence and all(got_words) and got_one)

    # A store that refuses every use is a fact, not a crash.
    clear_env()
    BOOM_OPEN = True
    try:
        with swapped({"jarvis_connect_account": None, "jarvis_google_calendar": None}):
            boom_rows = A.rows()
    finally:
        BOOM_OPEN = False
    check("a store that cannot be opened answers 'not set up', never connected",
          all(row["state"] in ("not_set_up", "not_an_account") for row in boom_rows),
          [row["state"] for row in boom_rows])


# --------------------------------------------------------------------------
#   6. "connected" only when a verifier actually ran in that call
# --------------------------------------------------------------------------

def t_connected_only_after_a_verifier_ran():
    reset()
    save_every_entry()
    calls = []
    with swapped({
        "jarvis_framework": framework_module({}),
        "jarvis_gate": gate_module({}),
        "jarvis_asks_first": asks_first_module(ASKS.SAYS),
        "jarvis_connect_account": connect_module(
            _fake_connect_rows(connected=("github",)), calls),
        "jarvis_google_calendar": google_module(False, []),
    }):
        probed = {row["id"]: row for row in A.rows(probe=True)}
        quiet = {row["id"]: row for row in A.rows(probe=False)}
    check("a verifier that passed makes that family connected",
          probed["github"]["state"] == "connected", probed["github"])
    check("... and tested True", probed["github"]["tested"] is True)
    check("a verifier that ran and failed leaves it saved, tested",
          probed["calendar_ics"]["state"] == "saved"
          and probed["calendar_ics"]["tested"] is True, probed["calendar_ics"])
    check("the same answer without probe=False is never connected",
          quiet["github"]["state"] == "saved"
          and quiet["github"]["tested"] is False, quiet["github"])
    check("the verifier was asked to probe exactly once, never unprobed",
          calls == [True], calls)

    # A verifier that would claim "connected" even when not probing cannot
    # make a probe=False answer say connected: it is never called.
    calls = []
    with swapped({
        "jarvis_connect_account": connect_module(
            _fake_connect_rows(connected=("github",)), calls),
    }):
        quiet_again = {row["id"]: row for row in A.rows(probe=False)}
    check("a dishonest verifier cannot make the default answer connected",
          quiet_again["github"]["state"] == "saved" and calls == [],
          (quiet_again["github"], calls))

    # A verifier that raises did not run: saved, not connected.
    calls = []
    with swapped({
        "jarvis_connect_account": connect_module([], calls, raises=True),
        "jarvis_google_calendar": google_module(False, [], raises=True),
    }):
        failed = {row["id"]: row for row in A.rows(probe=True)}
    check("a verifier that raised leaves its family saved, not tested",
          failed["github"]["state"] == "saved"
          and failed["github"]["tested"] is False, failed["github"])
    check("a Google status that raised is saved too",
          failed["google_calendar"]["state"] == "saved"
          and failed["google_calendar"]["tested"] is False,
          failed["google_calendar"])

    # An unconfigured service cannot have run a verifier.
    calls = []
    with swapped({
        "jarvis_connect_account": connect_module([], calls, configured=False),
    }):
        unset = {row["id"]: row for row in A.rows(probe=True)}
    check("a service that is not configured is not 'tested'",
          unset["github"]["tested"] is False, unset["github"])


def t_google_is_resolved_live():
    reset()
    save_every_entry()
    calls = []
    with swapped({
        "jarvis_framework": framework_module({}),
        "jarvis_gate": gate_module({}),
        "jarvis_asks_first": asks_first_module(ASKS.SAYS),
        "jarvis_connect_account": connect_module([], []),
        "jarvis_google_calendar": google_module(True, calls),
    }):
        probed = {row["id"]: row for row in A.rows(probe=True)}
        quiet = {row["id"]: row for row in A.rows(probe=False)}
    check("Google's own status() is the verifier for the OAuth family",
          probed["google_calendar"]["state"] == "connected"
          and probed["google_calendar"]["tested"] is True,
          probed["google_calendar"])
    check("... and it is never called by the default answer",
          quiet["google_calendar"]["state"] == "saved" and calls == [True], calls)


def t_not_an_account_families():
    reset()
    save_every_entry()
    with swapped({
        "jarvis_framework": framework_module({}),
        "jarvis_gate": gate_module({}),
        "jarvis_asks_first": asks_first_module(ASKS.SAYS),
        "jarvis_connect_account": connect_module(
            _fake_connect_rows(connected=("github",)), []),
        "jarvis_google_calendar": google_module(True, []),
    }):
        probed = {row["id"]: row for row in A.rows(probe=True)}
        quiet = {row["id"]: row for row in A.rows(probe=False)}
    for fam_id in ("notion", "spotify_drive_dropbox"):
        check(f"{fam_id} is never connected, even with a live probe",
              probed[fam_id]["state"] == "not_an_account"
              and quiet[fam_id]["state"] == "not_an_account", probed[fam_id])
        check(f"{fam_id} has no abilities and is not tested",
              probed[fam_id]["abilities"] == [] and probed[fam_id]["tested"] is False)


# --------------------------------------------------------------------------
#   7. Every row is honest
# --------------------------------------------------------------------------

ROW_KEYS = {"id", "name", "kind", "named", "state", "tested", "store_entries",
            "env_wins", "change", "remove", "connect", "limit", "can", "abilities",
            "connected_at", "connected_at_known"}
ABILITY_KEYS = {"action", "words", "tier", "says", "asks", "why", "classified"}
STATES = {"connected", "saved", "not_set_up", "not_an_account"}


def t_every_row_shape():
    reset()
    save_every_entry()
    with swapped({
        "jarvis_framework": framework_module({}),
        "jarvis_gate": gate_module({}),
        "jarvis_asks_first": asks_first_module(ASKS.SAYS),
        "jarvis_connect_account": connect_module([], []),
        "jarvis_google_calendar": google_module(False, []),
    }):
        for probe in (False, True):
            rows = A.rows(probe=probe)
            check(f"probe={probe}: one row per family, all with the same keys",
                  len(rows) == 12 and all(set(row) == ROW_KEYS for row in rows),
                  [sorted(set(row) ^ ROW_KEYS) for row in rows])
            check(f"probe={probe}: every state is one of the four",
                  all(row["state"] in STATES for row in rows),
                  [row["state"] for row in rows])
            check(f"probe={probe}: connected_at is None and connected_at_known False",
                  all(row["connected_at"] is None
                      and row["connected_at_known"] is False for row in rows))
            check(f"probe={probe}: store_entries and env_wins are lists of names",
                  all(isinstance(row["store_entries"], list)
                      and isinstance(row["env_wins"], list)
                      and all(isinstance(x, str)
                              for x in row["store_entries"] + row["env_wins"])
                      for row in rows))
            check(f"probe={probe}: every ability row has the contract's seven keys",
                  all(set(ability) == ABILITY_KEYS
                      for row in rows for ability in row["abilities"]))
    # The environment wins is reported as a NAME, and only when it is set.
    clear_env()
    os.environ["JARVIS_GITHUB_TOKEN"] = SENTINEL
    github = A.state_of("github")
    check("env_wins names the variable that is set, and no value",
          github["env_wins"] == ["JARVIS_GITHUB_TOKEN"], github["env_wins"])


def t_configured_states():
    """Contract section 5: what makes each kind of family "saved"."""
    reset()
    # A card family: one saved entry (or one variable) is enough to say saved.
    STORE[CAL.ICS_URL_TARGET] = SENTINEL
    ical = A.state_of("calendar_ics")
    check("a card family with its entry saved is 'saved', not connected",
          ical["state"] == "saved" and ical["tested"] is False, ical)

    # The CalDAV card needs BOTH of its two entries (contract: every one).
    STORE[CAL.USER_TARGET] = SENTINEL
    caldav = A.state_of("calendar_caldav")
    check("a card family missing one of its two entries is not set up yet",
          caldav["state"] == "not_set_up", caldav)
    STORE[CAL.PASSWORD_TARGET] = SENTINEL
    caldav = A.state_of("calendar_caldav")
    check("... and with both saved it is 'saved'", caldav["state"] == "saved", caldav)

    # An environment variable alone configures it, and is NAMED as the winner.
    reset()
    os.environ[CAL.ICS_URL_ENV] = SENTINEL
    ical = A.state_of("calendar_ics")
    check("a card family with only its variable set is 'saved'",
          ical["state"] == "saved", ical)
    check("... and the variable that wins is named, never its value",
          ical["env_wins"] == [CAL.ICS_URL_ENV], ical["env_wins"])

    # A settings family: one address saved on this PC.
    reset()
    A._save(imap_host="imap.example.com")
    check("a settings family with one address saved is 'saved'",
          A.state_of("email")["state"] == "saved")
    reset()
    A._save(home_url="http://homeassistant.local:8123")
    check("Home Assistant is 'saved' once its address is set",
          A.state_of("home_assistant")["state"] == "saved")

    # A key family: ONE saved key is enough (any provider can be used).
    reset()
    STORE[WS.KEY_TARGETS["exa"]] = SENTINEL
    check("one saved web-search key makes the family 'saved'",
          A.state_of("search_keys")["state"] == "saved")
    reset()
    STORE[CHAT.KEY_TARGETS["openai_api"]] = SENTINEL
    check("one saved cloud key makes that family 'saved'",
          A.state_of("chatbot_keys")["state"] == "saved")

    # The vault: a name in vault.json, and the NAME is what the row carries.
    reset()
    vault_path = A.addresses_path().parent / "vault.json"
    vault_path.parent.mkdir(parents=True, exist_ok=True)
    vault_path.write_text(json.dumps({"names": {"work-github": {"for_host": "",
                                                               "used": 0}}}),
                          encoding="utf-8")
    vault = A.state_of("vault")
    check("the vault is 'saved' once it holds a name", vault["state"] == "saved", vault)
    check("... and its row carries the NAMES only",
          vault["store_entries"] == ["work-github"], vault["store_entries"])

    # The notes folder: the setting resolves to a folder.
    reset()
    os.environ[NOTES.OBSIDIAN_VAULT_ENV] = str(_TMP / "vault-folder")
    check("the notes family is 'saved' once a folder is set",
          A.state_of("notes")["state"] == "saved")

    # A stray store entry cannot make a not-an-account family into an account.
    reset()
    STORE["Jarvis Backend/Spotify token"] = SENTINEL
    check("a not-an-account family stays 'not_an_account'",
          A.state_of("spotify_drive_dropbox")["state"] == "not_an_account")


def t_a_single_family_probe_only_tests_that_family():
    reset()
    save_every_entry()
    connect_calls, google_calls = [], []
    with swapped({
        "jarvis_framework": framework_module({}),
        "jarvis_gate": gate_module({}),
        "jarvis_asks_first": asks_first_module(ASKS.SAYS),
        "jarvis_connect_account": connect_module(
            _fake_connect_rows(connected=("github",)), connect_calls),
        "jarvis_google_calendar": google_module(True, google_calls),
    }):
        A.state_words("google_calendar", probe=True)
        after_google = (list(connect_calls), list(google_calls))
        A.state_of("calendar_ics", probe=True)
        after_card = (list(connect_calls), list(google_calls))
        A.state_words("notion", probe=True)   # nothing to test at all
        after_nothing = (list(connect_calls), list(google_calls))
    check("a Google question tests Google and not the card services",
          after_google == ([], [True]), after_google)
    check("a card question adds only the card verifier",
          after_card == ([True], [True]), after_card)
    check("a not-an-account question tests nothing", after_nothing == after_card,
          after_nothing)


def t_no_secret_value_anywhere():
    reset()
    save_every_entry()
    for name in ("JARVIS_GITHUB_TOKEN", "JARVIS_IMAP_PASSWORD", "JARVIS_HOME_TOKEN",
                 "JARVIS_CALENDAR_ICS_SECRET_URL", "JARVIS_CALDAV_PASSWORD"):
        os.environ[name] = SENTINEL
    STORE[CAL.ICS_URL_TARGET] = SENTINEL
    check("the sentinel really is in the injected store",
          STORE.get(CAL.ICS_URL_TARGET) == SENTINEL)
    with swapped({
        "jarvis_framework": framework_module({}),
        "jarvis_gate": gate_module({}),
        "jarvis_asks_first": asks_first_module(ASKS.SAYS),
        "jarvis_connect_account": connect_module(
            _fake_connect_rows(connected=("github",)), []),
        "jarvis_google_calendar": google_module(True, []),
    }):
        blobs = [
            json.dumps(A.rows()),
            json.dumps(A.rows(probe=True)),
            json.dumps(A.accounts_view()),
            json.dumps(A.accounts_view(probe=True)),
            repr(A.rows()),
            repr(A.accounts_view()),
            A.sentence(),
            A.sentence(probe=True),
        ]
        blobs += [A.state_words(fam.id) for fam in A.FAMILIES]
        blobs += [A.state_words(fam.id, probe=True) for fam in A.FAMILIES]
        blobs += [json.dumps(A.state_of(fam.id)) for fam in A.FAMILIES]
    leaked = [i for i, blob in enumerate(blobs) if SENTINEL in blob]
    check("no secret value appears in any row, sentence, words or view",
          not leaked, leaked)


# --------------------------------------------------------------------------
#   8. The route's answer, and the addresses answer it must not break
# --------------------------------------------------------------------------

def t_handle_get():
    reset()
    code, out = A.handle_accounts_get("")
    check("handle_accounts_get('') is 200", code == 200)
    check("... and exactly accounts_view(probe=False)", out == A.accounts_view())
    check("... the query string is ignored, and cannot ask for a probe",
          A.handle_accounts_get("?probe=1")[1]["probed"] is False
          and A.handle_accounts_get("?probe=1")[1]["families"] == out["families"])
    check("... nothing in it says connected",
          not [row for row in out["families"] if row["state"] == "connected"])
    check("... and it is the overview, never the addresses answer",
          "fields" not in out and "why" not in out, sorted(out))
    check("the addresses answer this module already had is a separate function",
          isinstance(A.view(), dict) and "fields" in A.view()
          and "families" not in A.view(), sorted(A.view()))
    check("the view names the title the plates use",
          out["title"] == "The accounts Jarvis can use")

    with swapped({
        "jarvis_framework": framework_module({}),
        "jarvis_gate": gate_module({}),
        "jarvis_asks_first": asks_first_module(ASKS.SAYS),
        "jarvis_connect_account": connect_module(
            _fake_connect_rows(connected=("github",)), []),
        "jarvis_google_calendar": google_module(True, []),
    }):
        live = A.accounts_view(probe=True)
    check("a probing view marks itself probed and stamps when it checked",
          live["probed"] is True and isinstance(live["checked_at"], float), live)
    check("... and its families can say connected",
          live["families"][3]["state"] == "connected", live["families"][3])


# --------------------------------------------------------------------------
#   9. One family at a time
# --------------------------------------------------------------------------

def t_state_of_and_abilities():
    reset()
    by_id = {row["id"]: row for row in A.rows()}
    check("state_of is the same row rows() returns",
          all(A.state_of(fam.id) == by_id[fam.id] for fam in A.FAMILIES))
    check("state_of of an unknown name is {} and does not echo it",
          A.state_of("no-such-family") == {})
    check("abilities of an unknown name is []",
          A.abilities("no-such-family") == [])
    check("state_words of an unknown name is a plain sentence",
          "no account by that name" in A.state_words("no-such-family").lower())


def t_sentence_names_every_family():
    reset()
    said = A.sentence()
    check("the sentence names every family",
          all(fam.name in said for fam in A.FAMILIES),
          [fam.name for fam in A.FAMILIES if fam.name not in said])
    check("the default sentence says nothing was tested",
          "not tested" in said.lower() or "nothing above was tested" in said.lower())
    check("the sentence explains where each one changes and disconnects",
          all(fam.change in said and fam.remove in said for fam in A.FAMILIES),
          [fam.id for fam in A.FAMILIES
           if fam.change not in said or fam.remove not in said])


# --------------------------------------------------------------------------
#   10. The two-file rule, and a clean import
# --------------------------------------------------------------------------

def t_the_twin_is_identical():
    mine = (HERE / "jarvis_accounts.py").read_bytes()
    twin = (REPO / "jarvis-backend" / "jarvis_accounts.py").read_bytes()
    check("jarvis-backend/jarvis_accounts.py is a byte-identical copy",
          mine == twin, "copy backend/jarvis_accounts.py over the twin")


def t_import_is_clean():
    env = dict(os.environ)
    env["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
    code = (
        "import sys; sys.path.insert(0, %r); import jarvis_accounts; "
        "extra = sorted(m for m in sys.modules "
        "if m.startswith('jarvis_') and m != 'jarvis_accounts'); "
        "print(','.join(extra)); sys.exit(1 if extra else 0)"
        % str(HERE))
    done = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, env=env)
    check("importing jarvis_accounts pulls in no other backend module",
          done.returncode == 0, (done.stdout + done.stderr).strip())


if __name__ == "__main__":
    for fn in (t_the_table, t_facts_match_the_owning_modules, t_account_from_words,
               t_abilities_are_resolved_live, t_a_missing_permission_table_is_said_so,
               t_gate_unclassified_is_marked, t_probe_false_opens_nothing,
               t_connected_only_after_a_verifier_ran, t_google_is_resolved_live,
               t_not_an_account_families, t_every_row_shape, t_configured_states,
               t_a_single_family_probe_only_tests_that_family,
               t_no_secret_value_anywhere,
               t_handle_get, t_state_of_and_abilities, t_sentence_names_every_family,
               t_the_twin_is_identical, t_import_is_clean):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
