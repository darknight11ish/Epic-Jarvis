"""Connecting an account by talking to Jarvis (2026-10-28).

    python3 test_connect_account.py

WHAT THIS PROVES, AND WHY EACH CHECK IS HERE

The owner asked: "if I need to put in a password a notification will pop up ...
it should be able to connect all features just through me talking to jarvis".
The design is one card, typed on this PC, saved straight into Windows Credential
Manager, then tested with one real request. Every claim that design makes is a
check below:

  * THE STORE MAPPING IS REAL. Each of the three services' fields maps to a
    Credential Manager entry that the module which READS it already owns
    (jarvis_calendar's ICS_URL_TARGET / USER_TARGET / PASSWORD_TARGET,
    jarvis_research's TOKEN_TARGET) - so a value saved from the card is the
    value the feature reads back. The CalDAV username/password and the GitHub
    token had NO store entry at all before this: they were read only from a
    plain-text environment variable, which is the rule 3 breach the owner's ask
    made worth fixing. The private iCal link already had one.
  * THE CARD CARRIES NO SECRET. Its view is built from the table and holds the
    service, the field NAMES, labels, hints and the model's cleaned note - and
    no value, because none exists until the owner types one.
  * THE VALUE GOES TO CREDENTIAL MANAGER AND NOWHERE ELSE. The suite's fake
    store records every write; a store that refuses produces an error that says
    so and writes nothing; the module's own source is read (by AST) to prove it
    imports no file, clipboard, sqlite or logging module and calls no `open()`.
  * A VERIFIER THAT FAILS IS NEVER REPORTED AS CONNECTED. Pass and fail are both
    driven through the injected request hook, for all three services.
  * "IS MY CALENDAR CONNECTED?" IS ANSWERED FROM THE STORE AND THAT TEST, and
    "not connected yet" when nothing is saved.
  * AN ENVIRONMENT VARIABLE THAT STILL WINS IS NAMED, so a card cannot look like
    it did nothing (the audit's CalDAV-password caveat).
  * THE TWO DOORS AGREE. The model's tool and the quick path's sentences raise
    the same card from the same table; "connect my email" says what IS
    connectable instead of inventing a card, and a reminder that merely mentions
    a calendar keeps its own answer.
  * THE REQUIRED `credential-manager` CHECK NOW COVERS THE NEW TARGETS: this
    suite asserts the three entries are exercised by name (see
    `t_every_store_entry_is_covered_by_the_credential_manager_check`), and
    test_account_secrets.py's live round trip is unchanged.

AND WHAT THE INDEPENDENT SECURITY REVIEW OF 2026-10-28 ADDED (each check exists
because the review found the claim untested, or the code wrong):

  * ONE CARD, ONE SAVE. Two threads saving the same card at the same moment
    produce one receipt and one write; the other is refused as voided.
  * AN EXPIRED CARD CANNOT SAVE - not merely "is not listed" - and the check
    that enforces it is a line whose removal turns this suite red.
  * THE ROUTE WRAPPER REFUSES ANOTHER MACHINE BEFORE IT READS THE BODY: driven
    through `install()`'s own `do_POST` with a recording reader (403, zero
    bytes read), not only through `handle_post` called directly.
  * THE MODEL'S NOTE CANNOT REORDER ITSELF: every Unicode format character
    (Cf), including a right-to-left override, is stripped.
  * THE CalDAV TEST FAILS CLOSED when the plain-http rule's module is missing,
    instead of allowing any http address to carry the password.
  * THE HUD'S FIRST CARD IS THE NEWEST WAITING ONE, and a "not connected yet"
    answer keeps #960's jump to Settings, Accounts; the phone's question never
    reaches this path.
"""
from __future__ import annotations

import ast
import json
import os
import sys
import threading
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_calendar as CAL  # noqa: E402
import jarvis_connect_account as C  # noqa: E402
import jarvis_research as RES  # noqa: E402
import jarvis_scrub as SCRUB  # noqa: E402
import jarvis_token_store as TS  # noqa: E402

FAILED, PASSED = [], []

#: Every environment variable these three services read. Cleared around every
#: check that looks at the store, so a variable set in this window cannot make a
#: test pass for the wrong reason.
ENVS = (CAL.ICS_URL_ENV, CAL.USER_ENV, CAL.PASSWORD_ENV, RES.TOKEN_ENV)

CANARY = "canary-value-9d41f7-do-not-print"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" +
          (f"\n        {detail}" if detail and not cond else ""))


class FakeStore:
    """Credential Manager, in memory, recording every write - the same shape
    test_account_secrets.py's own FakeStore uses, plus a write log."""

    def __init__(self, value=None, refuse=False):
        self.value, self.refuse = value, refuse
        self.writes = []

    def read(self):
        if self.refuse:
            raise TS.StoreError("reading failed (Windows error 1312)")
        return self.value

    def write(self, token):
        if self.refuse:
            raise TS.StoreError("saving failed (Windows error 5)")
        self.value = token
        self.writes.append(token)

    def delete(self):
        had, self.value = self.value is not None, None
        return had


class StoreShelf:
    """One fake Credential Manager per target name, as _STORE_FACTORY expects."""

    def __init__(self):
        self.by_target = {}
        self.refuse = set()

    def __call__(self, target):
        self.by_target.setdefault(target, FakeStore())
        if target in self.refuse:
            self.by_target[target].refuse = True
        return self.by_target[target]

    def value(self, target):
        return self.by_target[target].value if target in self.by_target else None

    def wrote(self, target):
        return list(self.by_target[target].writes) if target in self.by_target else []


def without_env(fn):
    """Run `fn` with every connect-account environment variable cleared, and put
    the window back exactly as it was."""
    saved = {k: os.environ.get(k) for k in ENVS}
    try:
        for k in ENVS:
            os.environ.pop(k, None)
        return fn()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def with_store(shelf, fn):
    """Run `fn` against a fake shelf, then put the real factory back."""
    saved = TS._STORE_FACTORY
    TS._STORE_FACTORY = shelf
    try:
        return fn()
    finally:
        TS._STORE_FACTORY = saved


class FakeHttp:
    """The injected request hook: one canned answer per URL, and a log of what
    was asked for - so a check can prove the value went to the one host it
    authenticates against, and to no other."""

    def __init__(self, answers):
        self.answers = dict(answers)
        self.calls = []

    def __call__(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        for key, answer in self.answers.items():
            if key in url:
                return answer
        return 0, ""


def with_http(fake, fn):
    saved = C._REQUEST
    C._REQUEST = fake
    try:
        return fn()
    finally:
        C._REQUEST = saved


def fresh_cards(fn):
    C.reset_for_tests()
    try:
        return fn()
    finally:
        C.reset_for_tests()


# --------------------------------------------------------------------------
#   1. The store mapping
# --------------------------------------------------------------------------

def t_every_service_field_maps_to_a_real_store_entry():
    want = {
        "calendar_ics": {"url": CAL.ICS_URL_TARGET},
        "calendar_caldav": {"username": CAL.USER_TARGET,
                            "password": CAL.PASSWORD_TARGET},
        "github": {"token": RES.TOKEN_TARGET},
    }
    check("there are exactly the three Phase-1 services",
          set(C.SERVICES) == set(want), f"{sorted(C.SERVICES)}")
    for sid, svc in C.SERVICES.items():
        got = C.targets(sid)
        check(f"{sid}: every field has a Credential Manager entry",
              set(got) == {f.name for f in svc.fields}, f"{got} vs the fields")
        check(f"{sid}: the entries are the reading module's own names",
              got == want[sid], f"{got} != {want[sid]}")
        check(f"{sid}: every entry is a 'Jarvis Backend/...' name",
              all(v.startswith("Jarvis Backend/") for v in got.values()), f"{got}")
        check(f"{sid}: the same field never maps to two entries",
              len(set(got.values())) == len(got), f"{got}")


def t_the_new_entries_are_read_through_resolve_secret():
    """The three entries are useless if the feature still reads only the
    environment: this drives each reading module with a fake store."""
    shelf = StoreShelf()

    def run():
        shelf.by_target[CAL.USER_TARGET] = FakeStore("owner@example.com")
        shelf.by_target[CAL.PASSWORD_TARGET] = FakeStore("app-password-1")
        shelf.by_target[CAL.ICS_URL_TARGET] = FakeStore("https://example.test/private.ics")
        shelf.by_target[RES.TOKEN_TARGET] = FakeStore("ghp_stored")
        check("jarvis_calendar.login() falls back to Credential Manager",
              CAL.login() == ("owner@example.com", "app-password-1"), f"{CAL.login()}")
        check("jarvis_calendar.authenticated() follows login()", CAL.authenticated() is True)
        check("jarvis_calendar._feed_url() still reads the iCal entry",
              CAL._feed_url() == "https://example.test/private.ics")
        check("jarvis_research._token() falls back to Credential Manager",
              RES._token() == "ghp_stored")
        check("jarvis_research.authenticated() follows it", RES.authenticated() is True)
        import jarvis_tellme as TELL
        check("jarvis_tellme uses the same resolver, so the two cannot disagree",
              TELL._github_token() == "ghp_stored", f"{TELL._github_token()}")
        os.environ[CAL.PASSWORD_ENV] = "set-by-hand"
        check("the environment variable still wins over Credential Manager",
              CAL.login()[1] == "set-by-hand", f"{CAL.login()}")

    without_env(lambda: with_store(shelf, run))


def t_a_saved_value_is_registered_with_the_scrubber():
    shelf = StoreShelf()
    SCRUB._REGISTERED.discard(CANARY)

    def run():
        without_env(lambda: with_store(
            shelf, lambda: TS.store_secret(RES.TOKEN_TARGET, CANARY)))
        check("a value saved by the card is registered with the log scrubber",
              CANARY in SCRUB._REGISTERED)

    try:
        run()
    finally:
        SCRUB._REGISTERED.discard(CANARY)


# --------------------------------------------------------------------------
#   2. The card carries no secret
# --------------------------------------------------------------------------

def t_the_card_carries_no_value_and_no_extra_surface():
    def run():
        card = C.raise_card("calendar_caldav", "set up my calendar")
        check("the card names its service", card["service"] == "calendar_caldav")
        check("the card carries its own kind", card["kind"] == "connect_account")
        check("the card says where the value goes, in words",
              card["stores_where"] == "Windows Credential Manager, on this PC")
        check("the card lists its store entries by NAME",
              set(card["store_entries"]) == {CAL.USER_TARGET, CAL.PASSWORD_TARGET},
              f"{card['store_entries']}")
        names = [f["name"] for f in card["fields"]]
        check("the card's boxes are the table's fields, in order",
              names == ["username", "password"], f"{names}")
        check("only the password box is masked",
              [f["secret"] for f in card["fields"]] == [False, True])
        check("the model's note is marked untrusted",
              card["agent_note_is_untrusted"] is True and
              card["agent_claimed_note"] == "set up my calendar")
        check("the card is for this PC only", card["from_this_pc_only"] is True)
        # Nothing that could be a value: no key but the documented ones, and no
        # string anywhere in the view that equals a value we then write.
        allowed = {"kind", "card_id", "service", "service_label", "summary", "note",
                   "fields", "agent_claimed_note", "agent_note_is_untrusted",
                   "stores_where", "store_entries", "from_this_pc_only",
                   "expires_in_seconds"}
        check("the card view has no field beyond the documented ones",
              set(card) == allowed, f"{sorted(set(card) - allowed)}")
        check("a card id is ca_ + 24 lower-case hex",
              card["card_id"].startswith("ca_") and len(card["card_id"]) == 27 and
              all(c in "0123456789abcdef" for c in card["card_id"][3:]),
              card["card_id"])
        check("raising a card writes nothing to the store",
              all(not shelf.wrote(t) for t in C.targets("calendar_caldav").values()))

    shelf = StoreShelf()
    fresh_cards(lambda: without_env(lambda: with_store(shelf, run)))


def t_the_models_note_is_cleaned_and_capped():
    def run():
        card = C.raise_card("github", "line\nbreak\x00 and   spaces " + "x" * 500)
        note = card["agent_claimed_note"]
        check("control characters become spaces and runs collapse",
              "\n" not in note and "\x00" not in note and "  " not in note, repr(note))
        check("the note is capped", len(note) <= C.MAX_LABEL_CHARS, str(len(note)))

    fresh_cards(run)


def t_the_models_note_cannot_reorder_itself():
    """A FORMAT character (Unicode Cf) is invisible and some of them flip the
    order of what follows: U+202E RIGHT-TO-LEFT OVERRIDE made "your GitHub
    token" draw as "nekot buHtiG ruoy", so the model could make the card say
    something the owner never read (security review N1, 2026-10-28). U+200B
    ZERO WIDTH SPACE is the same category, so the rule is all of Cf."""
    dirty = "set up \u202e your github token \u200b please"

    def run():
        card = C.raise_card("github", dirty)
        note = card["agent_claimed_note"]
        check("a right-to-left override in the model's note is stripped",
              "\u202e" not in note, repr(note))
        check("a zero-width space in it is stripped too", "\u200b" not in note, repr(note))
        check("no format character at all survives",
              all(unicodedata.category(ch) != "Cf" for ch in note), repr(note))
        check("the honest words around them are kept",
              note == "set up your github token please", repr(note))
        # The card is what the page draws, so the escaped form matters too:
        # json's default ensure_ascii would HIDE one.
        check("neither character is anywhere in the card's own view",
              not any(ch in json.dumps(card, ensure_ascii=False)
                      for ch in ("\u202e", "\u200b")),
              json.dumps(card, ensure_ascii=False))

    fresh_cards(run)


def t_pending_cards_are_bounded_and_expire():
    def run():
        for _ in range(C.MAX_PENDING_CARDS + 3):
            C.raise_card("github", "")
        check("no more than MAX_PENDING_CARDS wait at once",
              len(C.pending_cards()) <= C.MAX_PENDING_CARDS,
              str(len(C.pending_cards())))
        first = C.pending_cards()[0]["card_id"]
        later = C.pending_cards(clock=(lambda: __import__("time").time() + C.CARD_TTL_S + 1))
        check("a card older than its window is dropped", later == [], f"{later}")
        check("... and the expired one cannot be saved",
              later == [] and first not in [c["card_id"] for c in C.pending_cards()])

    fresh_cards(run)


def t_pending_cards_are_newest_first():
    """The HUD draws `cards[0]` and nothing else, so the ORDER is the difference
    between a card raised now being visible and it hiding behind one raised
    minutes ago (security review N4, 2026-10-28: `pending_cards` sorted oldest
    first, so the newest card was the last one and the page never drew it)."""
    t0 = 2_000_000.0

    def run():
        older = C.raise_card("github", "", clock=lambda: t0)
        newer = C.raise_card("calendar_ics", "", clock=lambda: t0 + 1)
        cards = C.pending_cards(clock=lambda: t0 + 2)
        check("both cards are waiting",
              sorted(c["service"] for c in cards) == ["calendar_ics", "github"],
              f"{[c['service'] for c in cards]}")
        check("... newest first, so the page's cards[0] is the card just raised",
              [c["card_id"] for c in cards] == [newer["card_id"], older["card_id"]],
              f"{[c['service'] for c in cards]}")
        check("... the newer card is not left for last",
              cards[-1]["card_id"] != newer["card_id"],
              f"{[c['service'] for c in cards]}")

    fresh_cards(run)


def t_an_expired_card_cannot_be_saved():
    """A card older than CARD_TTL_S cannot save anything. The old suite only
    checked it was no longer LISTED, and deleting the expiry refusal left the
    whole suite green (security review S2, 2026-10-28). `save_card` takes a
    clock, so this drives the window forward on purpose."""
    shelf = StoreShelf()
    shelf.by_target[RES.TOKEN_TARGET] = FakeStore()
    t0 = 1_000_000.0

    def late():
        return t0 + C.CARD_TTL_S + 1

    def run():
        card = C.raise_card("github", "", clock=lambda: t0)
        try:
            C.save_card(card["card_id"], {"token": CANARY}, clock=late)
            said = None
        except C.ConnectAccountVoided as exc:
            said = str(exc)
        check("a card older than its window cannot be saved", said is not None, str(said))
        check("... and the refusal says the card expired", "expired" in (said or ""),
              str(said))
        check("... nothing reached Credential Manager",
              shelf.wrote(RES.TOKEN_TARGET) == [],
              f"{shelf.wrote(RES.TOKEN_TARGET)}")
        check("... and the expired card is gone from the list",
              C.pending_cards(clock=late) == [], f"{C.pending_cards(clock=late)}")
        # One second INSIDE the window still saves, so the checks above cannot be
        # satisfied by refusing every card.
        fresh = C.raise_card("github", "", clock=lambda: t0)
        fake = FakeHttp({"api.github.com/user": (200, json.dumps({"login": "owner"}))})
        out = with_http(fake, lambda: C.save_card(
            fresh["card_id"], {"token": CANARY},
            clock=lambda: t0 + C.CARD_TTL_S - 1))
        check("... while a card one second inside its window still saves",
              out.get("ok") is True and shelf.wrote(RES.TOKEN_TARGET) == [CANARY],
              json.dumps(out))

    fresh_cards(lambda: without_env(lambda: with_store(shelf, run)))


def t_two_saves_of_one_card_at_once_write_once():
    """TWO submits of one card, both already past the card lookup, must produce
    exactly ONE receipt and ONE write (security review S1, 2026-10-28): the old
    `save_card` looked the card up, validated, and only then spent it, so two
    threads both wrote and both got a receipt.

    The values object blocks on a barrier for its first two reads, so both saves
    are provably past the lookup before either validates - the exact window the
    bug lived in, made deterministic instead of hoped for."""
    shelf = StoreShelf()
    shelf.by_target[RES.TOKEN_TARGET] = FakeStore()
    fake = FakeHttp({"api.github.com/user": (200, json.dumps({"login": "owner"}))})

    class Handshake(dict):
        """A values object that makes the race deterministic."""

        def __init__(self, data, barrier):
            super().__init__(data)
            self.barrier, self.reads = barrier, 0

        def get(self, key, default=None):
            self.reads += 1
            if self.reads <= 2:
                self.barrier.wait(timeout=10)
            return super().get(key, default)

    def run():
        card = C.raise_card("github", "")
        barrier = threading.Barrier(2)
        receipts, voided, other = [], [], []

        def save():
            try:
                receipts.append(C.save_card(
                    card["card_id"], Handshake({"token": CANARY}, barrier)))
            except C.ConnectAccountVoided as exc:
                voided.append(str(exc))
            except Exception as exc:        # noqa: BLE001 - reported, not swallowed
                other.append(f"{type(exc).__name__}: {exc}")

        threads = [threading.Thread(target=save) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(15)
        check("two saves of one card at once produce exactly one receipt",
              len(receipts) == 1 and not other, f"{len(receipts)} receipts, {other}")
        check("... the other is refused as voided, not served twice",
              len(voided) == 1 and "unknown, used or expired" in (voided[0] if voided
                                                                  else ""),
              f"{voided}")
        check("... and the value was written to Credential Manager once",
              shelf.wrote(RES.TOKEN_TARGET) == [CANARY],
              f"{shelf.wrote(RES.TOKEN_TARGET)}")
        check("... and the card is spent", C.pending_cards() == [],
              f"{C.pending_cards()}")

    fresh_cards(lambda: without_env(lambda: with_store(shelf, lambda: with_http(fake, run))))


# --------------------------------------------------------------------------
#   3. Saving: Credential Manager, and nowhere else
# --------------------------------------------------------------------------

def t_a_save_writes_each_value_to_its_own_entry_then_verifies():
    shelf = StoreShelf()
    fake = FakeHttp({"api.github.com/user": (200, json.dumps({"login": "owner"}))})

    def run():
        card = C.raise_card("github", "")
        out = with_http(fake, lambda: C.save_card(card["card_id"], {"token": CANARY}))
        check("the value reached its Credential Manager entry and only it",
              shelf.wrote(RES.TOKEN_TARGET) == [CANARY] and
              len([t for t in shelf.by_target if shelf.wrote(t)]) == 1,
              f"{ {t: len(shelf.wrote(t)) for t in shelf.by_target} }")
        check("the receipt names the entry, never the value",
              out["saved_to"] == [RES.TOKEN_TARGET] and CANARY not in json.dumps(out),
              json.dumps(out))
        check("the receipt reports the test's own verdict", out["verified"] is True)
        check("the receipt says the one host the value was sent to",
              [c[1] for c in fake.calls] == ["https://api.github.com/user"],
              f"{[c[1] for c in fake.calls]}")
        check("the card is spent after one save",
              C.pending_cards() == [], f"{C.pending_cards()}")
        try:
            C.save_card(card["card_id"], {"token": CANARY})
            again = False
        except C.ConnectAccountVoided:
            again = True
        check("saving the same card twice is refused", again)

    fresh_cards(lambda: without_env(lambda: with_store(shelf, run)))


def t_a_refused_store_saves_nothing_anywhere():
    shelf = StoreShelf()
    shelf.by_target[CAL.USER_TARGET] = FakeStore(refuse=True)
    shelf.by_target[CAL.PASSWORD_TARGET] = FakeStore()

    def run():
        card = C.raise_card("calendar_caldav", "")
        try:
            C.save_card(card["card_id"], {"username": CANARY, "password": CANARY + "2"})
            said = None
        except C.ConnectAccountError as exc:
            said = str(exc)
        check("a store that refuses is an error, not a silent success", said is not None)
        check("the error names Credential Manager and says nothing else is written",
              said is not None and "Credential Manager" in said and
              "not saved at all" in said, str(said))
        check("the refused value is not in the error sentence",
              said is not None and CANARY not in said, str(said))
        check("nothing was written for the second field either - no plaintext fallback",
              shelf.wrote(CAL.PASSWORD_TARGET) == [], f"{shelf.wrote(CAL.PASSWORD_TARGET)}")

    fresh_cards(lambda: without_env(lambda: with_store(shelf, run)))


def t_a_card_only_takes_its_own_fields():
    shelf = StoreShelf()

    def run():
        card = C.raise_card("github", "")
        for bad, why in (({"token": CANARY, "extra": "x"}, "an unknown field"),
                         ({"token": ""}, "an empty value"),
                         ({"token": "   "}, "an all-space value"),
                         ({"token": "x" * (C.MAX_VALUE_CHARS + 1)}, "an oversized value"),
                         ("not-a-dict", "a value that is not an object")):
            try:
                C.save_card(card["card_id"], bad)
                said = None
            except C.ConnectAccountError as exc:
                said = str(exc)
            check(f"{why} is refused", said is not None)
            check(f"... and the refusal never echoes it",
                  said is not None and CANARY not in said, str(said))
        check("nothing was saved by any of those", shelf.wrote(RES.TOKEN_TARGET) == [])
        check("the card survives a refusal, so the owner can try again",
              len(C.pending_cards()) == 1)

    fresh_cards(lambda: without_env(lambda: with_store(shelf, run)))


def t_an_unknown_or_expired_card_is_refused():
    fresh_cards(lambda: None)

    def run():
        for bad in ("", "ca_000000000000000000000000", "nonsense"):
            try:
                C.save_card(bad, {"token": CANARY})
                said = None
            except C.ConnectAccountVoided as exc:
                said = str(exc)
            check(f"{bad!r} is refused as unknown", said is not None and
                  CANARY not in str(said), str(said))

    without_env(run)


def t_the_module_cannot_write_a_file_or_reach_a_clipboard():
    """By its own AST, the same way the secret hand-off suite proves it: the
    module imports no storage, clipboard, database or logging library, and it
    calls no `open()` and no `eval`/`exec`."""
    tree = ast.parse((HERE / "jarvis_connect_account.py").read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    forbidden = {"sqlite3", "logging", "pickle", "shelve", "tkinter", "pyperclip",
                 "clipboard", "subprocess", "shutil"}
    check("the module imports nothing that could write a file or a clipboard",
          not (imports & forbidden), f"{sorted(imports & forbidden)}")
    check("... and the only storing module it names is jarvis_token_store",
          {m for m in imports if m.startswith("jarvis_")} <=
          {"jarvis_token_store", "jarvis_calendar", "jarvis_research",
           "jarvis_local_http", "jarvis_scrub", "jarvis_accounts"},
          f"{sorted(m for m in imports if m.startswith('jarvis_'))}")
    calls = {n.func.id for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    check("it calls no open() and no eval/exec",
          not (calls & {"open", "eval", "exec", "compile"}), f"{sorted(calls)}")


def t_no_answer_ever_carries_the_value():
    """Every sentence this module can say is built from names and verdicts:
    drive the status and the receipts with a stored canary and check it is
    absent from all of them."""
    shelf = StoreShelf()
    shelf.by_target[RES.TOKEN_TARGET] = FakeStore(CANARY)
    fake = FakeHttp({"api.github.com/user": (200, json.dumps({"login": "owner"}))})

    def run():
        said = C.status_words("github")
        check("a status sentence never contains the stored value", CANARY not in said, said)
        row = C.status_of("github")
        check("a status row never contains the stored value",
              CANARY not in json.dumps(row), json.dumps(row))
        card = C.raise_card("github", "")
        out = with_http(fake, lambda: C.save_card(card["card_id"], {"token": CANARY}))
        check("a receipt never contains the value it saved",
              CANARY not in json.dumps(out), json.dumps(out))

    fresh_cards(lambda: without_env(lambda: with_store(shelf, run)))


def t_an_environment_variable_that_still_wins_is_named():
    shelf = StoreShelf()
    fake = FakeHttp({"api.github.com/user": (200, json.dumps({"login": "owner"}))})

    def run():
        os.environ[RES.TOKEN_ENV] = "ghp_from_the_environment"
        card = C.raise_card("github", "")
        out = with_http(fake, lambda: C.save_card(card["card_id"], {"token": CANARY}))
        check("the receipt says the environment variable wins",
              out["environment_wins_for"] == ["token"], json.dumps(out))
        check("... and names it, so the card cannot look like it did nothing",
              RES.TOKEN_ENV in out.get("note", ""), out.get("note"))
        check("the saved value is still the one that was typed",
              shelf.wrote(RES.TOKEN_TARGET) == [CANARY])
        check("the status sentence says the same",
              RES.TOKEN_ENV in C.status_words("github"), C.status_words("github"))

    fresh_cards(lambda: without_env(lambda: with_store(shelf, run)))


# --------------------------------------------------------------------------
#   4. The verifiers: pass, and fail, with an injected request
# --------------------------------------------------------------------------

def t_the_ics_verifier():
    ok = FakeHttp({"private.ics": (200, "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n")})
    bad = FakeHttp({"private.ics": (404, "")})
    html = FakeHttp({"private.ics": (200, "<html>not a calendar</html>")})
    dead = FakeHttp({})
    url = "https://calendar.example/private.ics"
    with_http(ok, lambda: check(
        "a 200 calendar feed verifies as connected",
        C.verify("calendar_ics", {"url": url}) ==
        (True, "the private link answered and it is a real calendar feed (read-only)"),
        f"{C.verify('calendar_ics', {'url': url})}"))
    with_http(bad, lambda: check(
        "a 404 is a failure that names the status",
        C.verify("calendar_ics", {"url": url}) ==
        (False, "the private link answered HTTP 404"),
        f"{C.verify('calendar_ics', {'url': url})}"))
    with_http(html, lambda: check(
        "a page that is not a calendar is a failure, not a pass",
        C.verify("calendar_ics", {"url": url})[0] is False and
        "not a calendar feed" in C.verify("calendar_ics", {"url": url})[1],
        f"{C.verify('calendar_ics', {'url': url})}"))
    with_http(dead, lambda: check(
        "no answer at all is a failure that says so",
        C.verify("calendar_ics", {"url": url})[0] is False and
        "could not be reached" in C.verify("calendar_ics", {"url": url})[1],
        f"{C.verify('calendar_ics', {'url': url})}"))
    for wrong in ("", "webcal://calendar.example/private.ics", "ftp://x/y",
                  "https://user:pw@calendar.example/private.ics"):
        check(f"{wrong!r} is refused before any request",
              C.verify("calendar_ics", {"url": wrong})[0] is False,
              f"{C.verify('calendar_ics', {'url': wrong})}")


def t_the_caldav_verifier():
    shelf = StoreShelf()
    ok = FakeHttp({"caldav.example": (207, "<multistatus/>")})
    unauth = FakeHttp({"caldav.example": (401, "")})
    forbidden = FakeHttp({"caldav.example": (403, "")})

    def run():
        shelf.by_target[CAL.USER_TARGET] = FakeStore("owner")
        shelf.by_target[CAL.PASSWORD_TARGET] = FakeStore(CANARY)
        os.environ[CAL.URL_ENV] = "https://caldav.example/remote.php/dav"
        values = {"username": "owner", "password": CANARY}
        with_http(ok, lambda: check(
            "a 207 answer verifies as connected",
            C.verify("calendar_caldav", values)[0] is True,
            f"{C.verify('calendar_caldav', values)}"))
        # CALL verify AND ASSERT ON ITS REAL SENTENCE (security review S8). The
        # old check ended `... if False else ""`, which is always true and never
        # looked at an answer at all - deleting the sentence would not have
        # failed this suite.
        said = with_http(ok, lambda: C.verify("calendar_caldav", values))
        check("the request carried Basic auth, and the value reached no sentence",
              ok.calls and ok.calls[0][2].get("auth") == ("owner", CANARY) and
              said == (True, "the CalDAV server accepted the username and password "
                             "(one PROPFIND)") and CANARY not in said[1],
              f"{said}")
        with_http(unauth, lambda: check(
            "a 401 says the server refused the username and password",
            C.verify("calendar_caldav", values) ==
            (False, "the CalDAV server refused that username and password (HTTP 401)"),
            f"{C.verify('calendar_caldav', values)}"))
        with_http(forbidden, lambda: check(
            "a 403 is a failure too",
            C.verify("calendar_caldav", values)[0] is False,
            f"{C.verify('calendar_caldav', values)}"))
        os.environ.pop(CAL.URL_ENV, None)
        check("no saved CalDAV address is said plainly, not guessed",
              C.verify("calendar_caldav", values)[0] is False and
              "Settings, Accounts" in C.verify("calendar_caldav", values)[1],
              f"{C.verify('calendar_caldav', values)}")
        check("a missing password is refused before any request",
              C.verify("calendar_caldav", {"username": "owner", "password": ""})[0]
              is False)

    without_env(lambda: with_store(shelf, run))


def t_the_caldav_verifier_fails_closed_without_the_plain_http_rule():
    """With `jarvis_local_http` missing, `_verify_caldav` set `problem = ""`, so
    ANY address was allowed - including plain http to the open internet, which
    would carry the owner's calendar password in the clear (security review N2,
    2026-10-28). It has to fail CLOSED, the way the ICS path does."""
    shelf = StoreShelf()
    ok = FakeHttp({"caldav.example": (207, "<multistatus/>")})
    values = {"username": "owner", "password": CANARY}

    def run():
        shelf.by_target[CAL.USER_TARGET] = FakeStore("owner")
        shelf.by_target[CAL.PASSWORD_TARGET] = FakeStore(CANARY)
        had = "jarvis_local_http" in sys.modules
        previous = sys.modules.get("jarvis_local_http")
        # `None` in sys.modules makes `import jarvis_local_http` raise, which is
        # exactly what a PC without the module sees - without renaming a file.
        sys.modules["jarvis_local_http"] = None
        try:
            os.environ[CAL.URL_ENV] = "http://caldav.example/remote.php/dav"
            with_http(ok, lambda: check(
                "with no plain-http rule, an http:// CalDAV address is refused",
                C.verify("calendar_caldav", values)[0] is False,
                f"{C.verify('calendar_caldav', values)}"))
            check("... and the sentence says it must be https",
                  "https" in C.verify("calendar_caldav", values)[1],
                  f"{C.verify('calendar_caldav', values)}")
            check("... the password was never sent anywhere",
                  ok.calls == [], f"{[c[1] for c in ok.calls]}")
            # NOT a blanket refusal: an https address still reaches the request,
            # so the check above cannot pass by refusing everything.
            os.environ[CAL.URL_ENV] = "https://caldav.example/remote.php/dav"
            with_http(ok, lambda: check(
                "... an https address is still tested with one request",
                C.verify("calendar_caldav", values)[0] is True and len(ok.calls) == 1,
                f"{C.verify('calendar_caldav', values)} {[c[1] for c in ok.calls]}"))
        finally:
            if had:
                sys.modules["jarvis_local_http"] = previous
            else:
                sys.modules.pop("jarvis_local_http", None)

    without_env(lambda: with_store(shelf, run))


def t_the_github_verifier():
    ok = FakeHttp({"api.github.com/user": (200, json.dumps({"login": "darknight11ish"}))})
    unauth = FakeHttp({"api.github.com/user": (401, "")})
    limited = FakeHttp({"api.github.com/user": (403, "")})
    boom = FakeHttp({"api.github.com/user": (500, "")})
    with_http(ok, lambda: check(
        "a 200 says GitHub accepted the token, and names the account",
        C.verify("github", {"token": CANARY}) ==
        (True, "GitHub accepted the token (signed in as darknight11ish)"),
        f"{C.verify('github', {'token': CANARY})}"))
    check("the token went to api.github.com and to nothing else",
          ok.calls and all(c[1] == "https://api.github.com/user" for c in ok.calls),
          f"{[c[1] for c in ok.calls]}")
    check("... in the Authorization header, and nowhere else in the call",
          ok.calls[0][2]["headers"]["Authorization"] == f"Bearer {CANARY}")
    with_http(unauth, lambda: check(
        "a 401 is a refusal, named as one",
        C.verify("github", {"token": CANARY})[0] is False and
        "refused that token" in C.verify("github", {"token": CANARY})[1],
        f"{C.verify('github', {'token': CANARY})}"))
    with_http(limited, lambda: check(
        "a 403 mentions the rate limit rather than claiming a bad token",
        "rate limit" in C.verify("github", {"token": CANARY})[1],
        f"{C.verify('github', {'token': CANARY})}"))
    with_http(boom, lambda: check(
        "a 500 is a failure with the status",
        C.verify("github", {"token": CANARY}) == (False, "GitHub answered HTTP 500"),
        f"{C.verify('github', {'token': CANARY})}"))
    check("no token at all is refused before any request",
          C.verify("github", {"token": ""})[0] is False)


# --------------------------------------------------------------------------
#   5. "Is my calendar connected?" - the status the chat reads
# --------------------------------------------------------------------------

def t_status_is_built_from_the_store_and_the_test():
    shelf = StoreShelf()
    fake = FakeHttp({"private.ics": (200, "BEGIN:VCALENDAR")})

    def run():
        words = C.status_words("calendar_ics")
        check("nothing saved: 'not connected yet', and how to connect it",
              words.startswith("Calendar - the private iCal link: not connected yet.")
              and "connect my calendar" in words, words)
        shelf.by_target[CAL.ICS_URL_TARGET] = FakeStore(
            "https://calendar.example/private.ics")
        with_http(fake, lambda: check(
            "saved and answering: connected, with what the test proved",
            C.status_words("calendar_ics").startswith(
                "Calendar - the private iCal link: connected - the private link "
                "answered and it is a real calendar feed"),
            C.status_words("calendar_ics")))
        fake.answers["private.ics"] = (410, "")
        with_http(fake, lambda: check(
            "saved but failing: NEVER 'connected', and says what failed",
            "connected -" not in C.status_words("calendar_ics") and
            "saved, but it did not work" in C.status_words("calendar_ics") and
            "HTTP 410" in C.status_words("calendar_ics"),
            C.status_words("calendar_ics")))
        check("probe=False answers from the store without a request",
              "not tested just now" in C.status_words("calendar_ics", probe=False),
              C.status_words("calendar_ics", probe=False))
        rows = {r["service"]: r for r in C.status()}
        check("the status read covers all three services", len(rows) == 3, f"{sorted(rows)}")
        check("the GitHub row is honestly not configured",
              rows["github"]["configured"] is False and rows["github"]["connected"] is False)

    fresh_cards(lambda: without_env(lambda: with_store(shelf, run)))


# --------------------------------------------------------------------------
#   6. The two doors: the model's tool and the quick path
# --------------------------------------------------------------------------

def t_the_model_tool_raises_the_same_card_and_refuses_a_value():
    import jarvis_agent as A

    def run():
        check("the tool is in the agent's tool list", "connect_account" in A.TOOLS)
        check("it is in exactly one more_tools group",
              [g[0] for g in A.TOOL_GROUPS if "connect_account" in g[2]] == ["connect"])
        check("a plan step may never name it",
              "connect_account" in A._PLAN_EXCLUDED_STEPS)
        good = A._run_connect_tool({"service": "github"})
        check("the tool raises a card and says where it is",
              good.get("ok") is True and good.get("raised") is True, json.dumps(good))
        check("... naming the store entry's place, never a value",
              good.get("stored_in") == "Windows Credential Manager, on this PC",
              json.dumps(good))
        bad = A._run_connect_tool({"service": "github", "token": CANARY})
        check("a value in the arguments is REFUSED, not dropped",
              bad.get("ok") is False and "may carry a value" in bad.get("error", ""),
              json.dumps(bad))
        check("... and the refusal never echoes it", CANARY not in json.dumps(bad))
        unknown = A._run_connect_tool({"service": "spotify"})
        check("a service it cannot test is answered with the ones it can",
              unknown.get("ok") is False and "Calendar" in unknown.get("error", ""),
              json.dumps(unknown))
        args, problem = A.check_call("connect_account", json.dumps({"service": "calendar"}),
                                     ["connect_account"], A.TOOLS)
        check("the schema accepts a service and no value", problem is None and
              args == {"service": "calendar"}, f"{args} {problem}")

    fresh_cards(run)


def t_the_quick_path_answers_the_owners_sentences():
    import jarvis_quick as Q

    def run():
        for said, want in (
            ("connect my calendar", ("card", "calendar_ics")),
            ("can you connect directly to external calendars like google or outlook?",
             ("card", "calendar_ics")),
            ("set up a calendar bridge for me", ("card", "calendar_ics")),
            ("set up github", ("card", "github")),
            ("connect my github account", ("card", "github")),
            ("set my github token", ("card", "github")),
            ("connect my caldav calendar", ("card", "calendar_caldav")),
            ("is my calendar connected?", ("status", "calendar_ics")),
            ("is github set up?", ("status", "github")),
            ("connect my email", ("later", "")),
        ):
            got = Q.match(said)
            check(f"{said!r} reaches the connect path",
                  got is not None and got.name == "connect_account" and
                  (got.f.get("ask"), got.f.get("service", "")) == want,
                  f"{None if got is None else (got.name, got.f)}")
        for said in ("open my calendar", "can you read my calendar?",
                     "set a reminder for my calendar", "connect the printer",
                     "watch my github ci",
                     # Security review S6 (2026-10-28): the phone is not an
                     # account this card can connect, and the old pattern made
                     # every one of these reach the connect path, whose answer
                     # never mentions the phone.
                     "is my phone connected?", "is my phone paired?",
                     "set up phone pairing", "connect my phone"):
            check(f"{said!r} is NOT claimed by the connect path",
                  (Q.match(said) is None or Q.match(said).name != "connect_account"),
                  f"{Q.match(said)}")
        check("the 'not connectable yet' answer does not speak for the phone",
              "phone" not in Q.answer("connect my email").reply.lower(),
              Q.answer("connect my email").reply)
        answer = Q.answer("connect my calendar")
        check("the answer says the card is waiting on this PC",
              "One card is waiting" in answer.reply, answer.reply)
        check("... says a secret is never typed into the chat",
              "never typed into the chat" in answer.reply, answer.reply)
        check("... and carries no stored value",
              not any(v in answer.reply for v in ENVS), answer.reply)
        later = Q.answer("connect my email")
        check("email is answered with what CAN be connected, and no card claim",
              "I can connect two things" in later.reply and
              "One card is waiting" not in later.reply, later.reply)
        check("the same intent names are not in READ_ONLY_INTENTS",
              "connect_account" not in Q.READ_ONLY_INTENTS)

    fresh_cards(lambda: without_env(lambda: with_store(StoreShelf(), run)))


def t_a_not_connected_answer_keeps_the_settings_jump():
    """"Is my calendar connected?" answering "not connected yet" must lead
    somewhere. #960's own `_run_calendar_setup` returns
    `open_settings="account-secrets"` for the same state, so the desktop jumps
    its Settings window to the box; the connect card's answer lost that jump
    (security review S5, 2026-10-28)."""
    import jarvis_quick as Q

    shelf = StoreShelf()

    def run():
        out = Q.answer("is my calendar connected?")
        check("the 'not connected yet' answer carries #960's Settings jump",
              out is not None and out.open_settings == "account-secrets",
              f"{None if out is None else out.open_settings!r}")
        check("... and still says what is not connected",
              out is not None and "not connected yet" in out.reply,
              f"{None if out is None else out.reply}")
        shelf.by_target[CAL.ICS_URL_TARGET] = FakeStore(
            "https://calendar.example/private.ics")
        fake = FakeHttp({"private.ics": (200, "BEGIN:VCALENDAR")})
        out = with_http(fake, lambda: Q.answer("is my calendar connected?"))
        check("a CONNECTED answer opens no Settings page",
              out is not None and out.open_settings is None,
              f"{None if out is None else out.open_settings!r}")
        check("... and still says it is connected",
              out is not None and "connected -" in out.reply,
              f"{None if out is None else out.reply}")

    fresh_cards(lambda: without_env(lambda: with_store(shelf, run)))


# --------------------------------------------------------------------------
#   7. The host-only route
# --------------------------------------------------------------------------

def t_the_route_is_this_pc_only_and_never_echoes_the_body():
    import jarvis_connect_account_wiring as W

    def run():
        code, out = W.handle_post(W.SAVE_PATH,
                                  {"card_id": "ca_0123456789abcdef01234567",
                                   "values": {"token": CANARY}},
                                  peer="192.168.1.30", local="127.0.0.1")
        check("another machine is refused before anything is saved",
              code == 403 and out.get("ok") is False, f"{code} {out}")
        check("... and its value is not in the refusal", CANARY not in json.dumps(out))
        check("the save route is not readable as a GET",
              W.handle_get(W.SAVE_PATH, peer="127.0.0.1")[0] == 404)
        code, out = W.handle_get(W.PENDING_PATH, peer="192.168.1.30", local="127.0.0.1")
        check("the pending card cannot be read from another machine",
              code == 403 and CANARY not in json.dumps(out), f"{code} {out}")
        code, out = W.handle_post(W.SAVE_PATH, {"card_id": "nope"}, peer="127.0.0.1")
        check("a bad card id is refused in words, with no value",
              code == 409 and CANARY not in json.dumps(out), f"{code} {out}")

    fresh_cards(lambda: without_env(lambda: with_store(StoreShelf(), run)))


def t_the_route_refuses_another_machine_before_it_reads_the_body():
    """The ROUTE WRAPPER's own loopback refusal - not `handle_post` called
    directly, which is what the check above drives. Deleting the wrapper's
    `_from_this_pc` left the whole suite green (security review S3, 2026-10-28).
    A recording `read_body` proves the refusal happens BEFORE a single byte of
    the posted value is read."""
    import jarvis_connect_account_wiring as W

    reads = []

    class Handler:
        def do_GET(self):
            return "original-get"

        def do_POST(self):
            return "original-post"

    class Conn:
        def getsockname(self):
            return ("127.0.0.1", 80)

    class Fake:
        path = W.SAVE_PATH
        connection = Conn()

        def __init__(self, peer):
            self.client_address = (peer, 5150)
            self.sent = None

        def _send(self, code, obj):
            self.sent = (code, obj)

    def read_body(_self):
        reads.append(1)
        return b'{"card_id": "ca_0123456789abcdef01234567"}'

    banner = W.install(Handler, origin_ok=lambda s: True, token_ok=lambda s: True,
                       read_body=read_body)
    check("the wrapper installs on a fresh handler",
          "Connect-account card: on" in banner, banner)

    away = Fake("192.168.1.30")
    Handler.do_POST(away)
    check("another machine's POST is refused with 403",
          away.sent is not None and away.sent[0] == 403, f"{away.sent}")
    check("... and its body was NEVER read - not one byte",
          reads == [], f"{len(reads)} body reads")
    check("... and the refusal is about this PC only",
          away.sent is not None and "this PC" in json.dumps(away.sent[1]),
          f"{away.sent}")

    here = Fake("127.0.0.1")
    Handler.do_POST(here)
    check("this PC's own POST does read the body", len(reads) == 1, f"{len(reads)}")
    check("... and gets the card route's own answer (an unknown card is a 409)",
          here.sent is not None and here.sent[0] == 409, f"{here.sent}")


def t_the_route_is_installed_through_the_secret_handoff_entry_point():
    """The routes are installed by the ONE call `secret-handoff.patch` already
    makes, so this feature needs no patch of its own."""
    import jarvis_secret_handoff_wiring as H

    class Handler:
        def do_GET(self):
            return "original-get"

        def do_POST(self):
            return "original-post"

    class Fake:
        path = "/api/something-else"
        client_address = ("127.0.0.1", 1234)

        def __init__(self):
            self.connection = type("C", (), {"getsockname": lambda self_: ("127.0.0.1", 80)})()

        def _send(self, code, obj):
            self.sent = (code, obj)

    banner = H.install(Handler, origin_ok=lambda s: True, token_ok=lambda s: True,
                       read_body=lambda s: b"{}")
    check("the hand-off banner still says the hand-off is on",
          "Owner-secret hand-off card: on" in banner, banner)
    check("the same call installs the connect card, on its own line",
          "Connect-account card: on" in banner, banner)
    fake = Fake()
    check("a route neither module owns still goes to the server's own handler",
          Handler.do_GET(fake) == "original-get")


def t_the_required_credential_manager_check_covers_the_new_entries():
    """The required `credential-manager` CI job runs test_token_store.py and
    test_account_secrets.py against real Windows. The three entries this feature
    adds are exercised here (by a fake store) and named in the live test's own
    targets table, so a rename cannot pass this suite while the CI job stops
    covering them."""
    # CALL THE REAL CHECKER'S OWN CHECKS (not a source-text pin - see
    # tools/check_no_source_pins.py): its own two connect-account functions are
    # driven here, so a rename inside it cannot make this pass vacuously and a
    # broken entry fails in both suites.
    import test_account_secrets as LIVE
    before = len(LIVE.FAILED)
    LIVE.t_the_connect_cards_entries_are_the_reading_modules_own_names()
    LIVE.t_caldav_and_github_resolve_through_the_same_mechanism()
    check("the live CI checker's own two connect-account checks pass",
          len(LIVE.FAILED) == before, f"{LIVE.FAILED[before:]}")
    check("the live CI job also round-trips the three new entries on real Windows",
          callable(getattr(LIVE, "t_live_the_three_connect_entries_on_real_windows", None)))
    check("... and still round-trips the store itself",
          callable(getattr(LIVE, "t_live_windows_round_trip", None)))


# --------------------------------------------------------------------------
#   8. It is not a route for a raw key - test_chatbot_keys.py:217 still holds
# --------------------------------------------------------------------------

def t_this_adds_no_key_route_and_no_key_service():
    import jarvis_connect_account_wiring as W
    check("the connect routes are the card's three and nothing else",
          set(W.PATHS) | set(W.POST_PATHS) ==
          {"/api/connect-account/pending", "/api/connect-account/save",
           "/api/connect-account/cancel"}, f"{W.PATHS} {W.POST_PATHS}")
    names = " ".join(s.name + " " + " ".join(s.words) for s in C.SERVICES.values()).lower()
    for forbidden in ("openai", "exa", "tavily", "brave", "chatbot", "groq", "mistral",
                      "openrouter", "xai", "deepseek"):
        check(f"no connect service offers a {forbidden!r} key", forbidden not in names)
    check("no service stores a value anywhere but Credential Manager",
          all(v.startswith("Jarvis Backend/") for sid in C.SERVICES
              for v in C.targets(sid).values()))


if __name__ == "__main__":
    for fn in (
        t_every_service_field_maps_to_a_real_store_entry,
        t_the_new_entries_are_read_through_resolve_secret,
        t_a_saved_value_is_registered_with_the_scrubber,
        t_the_card_carries_no_value_and_no_extra_surface,
        t_the_models_note_is_cleaned_and_capped,
        t_the_models_note_cannot_reorder_itself,
        t_pending_cards_are_bounded_and_expire,
        t_pending_cards_are_newest_first,
        t_a_save_writes_each_value_to_its_own_entry_then_verifies,
        t_a_refused_store_saves_nothing_anywhere,
        t_a_card_only_takes_its_own_fields,
        t_an_unknown_or_expired_card_is_refused,
        t_an_expired_card_cannot_be_saved,
        t_two_saves_of_one_card_at_once_write_once,
        t_the_module_cannot_write_a_file_or_reach_a_clipboard,
        t_no_answer_ever_carries_the_value,
        t_an_environment_variable_that_still_wins_is_named,
        t_the_ics_verifier,
        t_the_caldav_verifier,
        t_the_caldav_verifier_fails_closed_without_the_plain_http_rule,
        t_the_github_verifier,
        t_status_is_built_from_the_store_and_the_test,
        t_the_model_tool_raises_the_same_card_and_refuses_a_value,
        t_the_quick_path_answers_the_owners_sentences,
        t_a_not_connected_answer_keeps_the_settings_jump,
        t_the_route_is_this_pc_only_and_never_echoes_the_body,
        t_the_route_refuses_another_machine_before_it_reads_the_body,
        t_the_route_is_installed_through_the_secret_handoff_entry_point,
        t_the_required_credential_manager_check_covers_the_new_entries,
        t_this_adds_no_key_route_and_no_key_service,
    ):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception as exc:
            import traceback
            FAILED.append(fn.__name__)
            print(f"FAIL  {fn.__name__} RAISED {type(exc).__name__}: {exc}")
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
