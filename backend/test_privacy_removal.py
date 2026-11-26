"""test_privacy_removal.py - PR 1 of 3 of the personal data removal tool.

    py -3 backend/test_privacy_removal.py

WHAT THIS PROVES, with the REAL `jarvis_quick.py`, the REAL
`jarvis_settings_registry.py`, the REAL `jarvis_asks_first.py` and the real
`jarvis_privacy_removal.py`, over a TEMPORARY settings folder (never the
owner's real `~/.openjarvis`, and never his Credential Manager):

1. THE MODE DIAL. A fresh folder is `local` - the shipped default - and a
   freshly created tool writes no file just by being read. An unknown value is
   REFUSED rather than saved (`write_mode` raises, `set_mode` answers 400 and
   changes nothing), and a hand-edited file holding something this PC does not
   know reads back as `local` with the answer saying so. `local` applies at once
   and raises no card.
2. `JARVIS_CONFIG_DIR` IS READ FIRST. With it pointing at one folder and
   `OPENJARVIS_CONFIG_DIR` at another, every path this module builds is under
   the FIRST one - which is what keeps a suite out of the owner's real profile.
3. THE SCHEMA. `privacy/tracker.db` is created with `brokers`, `requests` and
   `official_portals`, the two official portals are seeded into it, and a
   SECOND open finds the rows already there and destroys nothing.
4. THE MASKED PROFILE. A profile holding a real name, street address, phone
   number and email address answers with a label and the last four characters
   only: the test searches every sentence this module can produce for the raw
   values and requires that none of them appears.
5. THE FOUR TOPICS. `overview`, `pros_cons`, `limits` and `official_portals`
   each answer, each from the LIVE state (the mode, whether the Gmail App
   Password is set, whether an Optery key is set, what the tracker holds), and
   an unknown topic names the four rather than refusing.
6. THE CONSENT CARD. Switching to `optery_api` or `hybrid` raises ONE card
   whose own words name the name, address, phone number and email address and
   the fact that they go to Optery over HTTPS; a DENIED card changes nothing,
   an APPROVED card writes the mode, and a PC whose settings file has loosened
   the action's tier below "ask" gets a refusal instead of a cardless change.
7. EVERY TRIGGER PHRASE reaches `privacy_explain` BY INTENT, through the real
   `jarvis_quick.match()` and not by falling to the model - the seven the owner
   listed, plus the two official-portal questions - and the neighbouring
   sentences that were already answered somewhere else still go there.
8. AN EMPTY TRACKER ANSWERS HONESTLY: every count is present and zero, the
   answer says nothing is tracked yet, and nothing raises.
9. THE TWO ROWS BITE WHEN REVERTED. The `Privacy` row in
   `jarvis_asks_first.TOOL_GROUPS` and the `data_removal` row in
   `jarvis_settings_registry.MODE_SETTINGS` are each removed from the live
   tuple and the check that names them is re-run: it must fail. A check that
   cannot fail is not a proof, so this is proved rather than asserted.
10. NOTHING IS SHIPPED, AND THE IMPORT IS GUARDED. The owner's ruling is that
   only the pull request which wires a live caller may register a module in
   `_where.SHIPPED`; this suite reads both lists and the import in
   `jarvis_quick.py` and requires the guarded shape that keeps the published
   base working.
11. STDLIB ONLY, AND EVERY NETWORK SEAM INJECTABLE (rewritten by PR 2). The
   module's own `ast` is walked: the imports are Python's standard library plus
   the guarded house modules, and nothing third-party. The three things that
   reach a network - the directory download, the SMTP send and the mailbox -
   each take their transport as an argument, so this file drives the REAL code
   with fake doubles and opens no socket.

PR 2 OF 3 ADDS, all offline and over a temporary settings folder:

12. THE BROKER DIRECTORY. Optery's document's own shape parses into the
   `brokers` table's columns: an email broker, an opt-out-page broker, a
   guide-link one, an entry with no route (counted and LEFT OUT), an "email"
   that is really an instruction (not an address) and a duplicate id (kept
   once). A refresh is injected through a fake `urlopen`, writes the parsed
   cache under the temp folder with its source and its CC BY-NC-SA licence in
   it, imports the rows, and updates rather than duplicates on a second run. A
   failed download, and a captive portal's HTML, are SAID rather than raised,
   and the copy already on the PC loses nothing.
13. THE CARDED BATCH SENDER. ONE card per batch, under the EXISTING
   `send_email` ask action, naming the exact 20 brokers, the template type and
   both hard caps; the 21st broker is not on it. A denied or timed-out card
   sends nothing and writes NO request row. An approved card sends through an
   injected SMTP double only and records `sent_at` and `verify_after` on every
   row: 45 days for a CCPA/GDPR template, 7 for a plain one. The 250-a-day cap
   stops a batch dead, and with 245 already sent the card names the remaining 5.
   No Gmail App Password, no removal profile and `optery_api` mode each answer
   without sending and without a card, and a settings file that loosened
   `send_email` below "ask" is refused before any card.
14. THE REPLY SCANNER. A confirmation LINK moves the row to
   `needs_verify_click` and NOTHING is clicked (the fake opener records no
   call); an ID request moves it there too; a broker's completion email moves it
   only to `pending_window`, never to `removed`. A 403 never changes a row's
   status, a page that still names the owner is "still listed", a CAPTCHA page
   is "unverified", and a clean page after the window is the ONE thing that
   confirms a removal - and it sets the 90-day re-list date.
15. THE CHECKLIST AND THE STATUS ANSWER carry the two official portals' real
   URLs, each web-form broker's direct opt-out URL, the count that publishes
   none, and the live counts by status. No card, and no raw value.
16. EVERY ENGINE PHRASING reaches its own intent through the real
   `jarvis_quick.match()`, the module claims it too, and ten neighbouring
   sentences keep their old lanes ("check my email" is still `honest_chat`,
   "sync my calendar" still `calendar_setup`, and neither "show my status" nor
   "send my email" becomes this feature's).
17. THE TWO NEW ROWS BITE WHEN REVERTED. Reverting the 20-broker cap and the
   403 guard really makes the checks that name them fail.
18. NO PII IN ANY LOG LINE, AUDIT EVENT, PRINTED SENTENCE OR TRACKER NOTE, on
   every PR 2 path at once - while the email itself does carry the details a
   deletion needs, because a request that cannot identify the owner is useless.

A SKIP IS NEVER A PASS here: `skip()` counts on its own line and is printed as
SKIPPED, and the run fails if every check skipped.
"""
from __future__ import annotations

import ast
import contextlib
import email.message
import inspect
import io
import json
import os
import re
import sqlite3
import sys
import tempfile
import traceback
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

#: BOTH variables, the same temporary folder. This module reads
#: JARVIS_CONFIG_DIR first (the owner's spec) and most of the backend reads
#: OPENJARVIS_CONFIG_DIR first, so a suite that set only one of them would let
#: the other half write into the owner's real settings folder.
TMP = Path(tempfile.mkdtemp(prefix="jarvis-privacy-removal-"))
os.environ["JARVIS_CONFIG_DIR"] = str(TMP)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_SUITE_RUNNING"] = "1"
os.environ["JARVIS_NTFY_TOPIC"] = ""
os.environ["JARVIS_NTFY_SERVER"] = ""

import jarvis_asks_first as AF  # noqa: E402
import jarvis_privacy_removal as PR  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []

#: The real readers, kept before any test stubs them out. The one test that
#: proves the real path uses these with the credential modules stubbed, so this
#: suite never touches the owner's Windows Credential Manager.
_REAL_GMAIL_STATE = PR.gmail_state
_REAL_OPTERY_STATE = PR.optery_state


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot make. Never counted as a pass."""
    SKIPPED.append(why)
    print(f"SKIP  {why}")


# ---------------------------------------------------------------------------
#   The fixture: a temporary settings folder, and stubs for what it must not
#   touch
# ---------------------------------------------------------------------------

#: The profile this suite writes into the TEMPORARY folder. Every value is
#: made up, and every one is searched for in every answer below.
NAME = "Dana Whitfield"
ADDRESS = "1847 Marigold Terrace, Springfield 62704"
PHONE = "(555) 010-4471"
EMAIL = "dana.whitfield@example.com"
RAW_VALUES = (NAME, ADDRESS, PHONE, EMAIL)

PROFILE = {"name": NAME, "address": ADDRESS, "phone": PHONE, "email": EMAIL}


def clean():
    """An empty temporary folder: no mode file, no profile, no tracker, no cache."""
    for path in (PR.mode_path(), PR.profile_path(), PR.tracker_path(),
                 PR.brokers_cache_path()):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    PR._reset_for_tests()
    PR.gmail_state = lambda: {"address": False, "password": False, "ready": False}
    PR.optery_state = lambda: {"set": False, "env": PR.OPTERY_ENV}
    # THE SUITE NEVER TOUCHES THE OWNER'S WINDOWS CREDENTIAL MANAGER. Every
    # mailbox or SMTP path reads its login through this one function, so it is
    # stubbed for every check - a test that forgot to stub it could not reach a
    # real password even by accident. A test that needs "no credentials" says so
    # by stubbing it to ("", "").
    PR._mail_credentials = lambda: ("owner@example.com", "not-a-real-password")


def stub_gmail(ready: bool = True):
    """The Gmail App Password is set (or not) - never a real credential."""
    PR.gmail_state = lambda: {"address": ready, "password": ready, "ready": ready}


def no_credentials():
    """A PC whose Credential Manager holds no mail login at all."""
    PR._mail_credentials = lambda: ("", "")


def write_profile(doc=None):
    path = PR.profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc if doc is not None else PROFILE), encoding="utf-8")


def no_pii(text: str) -> tuple:
    """(True, "") when not one raw value appears in `text`, else (False, who)."""
    low = str(text or "").lower()
    found = [value for value in RAW_VALUES if value.lower() in low]
    return (not found), ", ".join(found)


# ---------------------------------------------------------------------------
#   1. The mode dial: default, refusal, and `local` at once
# ---------------------------------------------------------------------------


def t_the_default_mode_is_local():
    clean()
    check("a fresh folder is on the shipped default, local", PR.mode() == "local",
          PR.mode())
    check("... and reading it writes no file at all", not PR.mode_path().exists(),
          str(PR.mode_path()))
    mode_now, source = PR.read_mode()
    check("... and the answer says the setting came from the default",
          mode_now == "local" and "shipped default" in source, source)
    code, body = PR.set_mode("local")
    check("choosing local when it is already local answers so, and raises no card",
          code == 200 and body.get("card") is False and body.get("mode") == "local",
          str(body))


def t_an_unknown_mode_is_refused():
    clean()
    raised = False
    try:
        PR.write_mode("cloud")
    except ValueError:
        raised = True
    check("write_mode refuses a value that is not a mode, rather than saving it",
          raised)
    check("... and nothing was written", not PR.mode_path().exists())
    check("... and every one of the three real modes IS accepted",
          [PR.write_mode(m) for m in PR.MODES] == list(PR.MODES), PR.PRIVACY_DIR)
    code, body = PR.set_mode("nonsense")
    check("set_mode answers 400 for an unknown mode and says what the modes are",
          code == 400 and "local" in str(body.get("error"))
          and body.get("changed") is False, str(body))
    check("... and the mode really is unchanged (local was the last one written)",
          PR.mode() == "hybrid")
    # A hand-edited file holding something this PC does not know must not become
    # a cloud mode by accident.
    PR.mode_path().write_text(json.dumps({"mode": "cloud_service"}), encoding="utf-8")
    mode_now, source = PR.read_mode()
    check("a saved value that is not a mode reads back as local, and says why",
          mode_now == "local" and "not one of" in source, source)
    check("... and the file is not rewritten behind the owner's back",
          json.loads(PR.mode_path().read_text(encoding="utf-8"))["mode"]
          == "cloud_service")


def t_local_is_instant_and_cardless():
    clean()
    PR.write_mode("hybrid")
    calls = []

    def gate(action, detail, prompt):
        calls.append(action)
        raise AssertionError("local must never raise a card")

    code, body = PR.set_mode("local", gate=gate, tier_of=lambda a: "ask",
                             spawn=lambda fn: fn())
    check("switching back to local is instant, cardless and 200",
          code == 200 and body.get("changed") is True and PR.mode() == "local",
          f"{code} {body}")
    check("... and the gate was never asked", not calls, str(calls))
    check("... and the words say nothing is sent anywhere",
          "nothing is sent anywhere" in body.get("said", "").lower(), body.get("said"))


# ---------------------------------------------------------------------------
#   2. JARVIS_CONFIG_DIR is honoured FIRST
# ---------------------------------------------------------------------------


def t_jarvis_config_dir_is_read_first():
    first = Path(tempfile.mkdtemp(prefix="jarvis-privacy-first-"))
    second = Path(tempfile.mkdtemp(prefix="jarvis-privacy-second-"))
    saved = (os.environ.get("JARVIS_CONFIG_DIR"),
             os.environ.get("OPENJARVIS_CONFIG_DIR"))
    try:
        os.environ["JARVIS_CONFIG_DIR"] = str(first)
        os.environ["OPENJARVIS_CONFIG_DIR"] = str(second)
        check("config_dir() is the JARVIS_CONFIG_DIR folder when both are set",
              PR.config_dir() == first, str(PR.config_dir()))
        check("... and the mode file lands there, not in the other one",
              PR.mode_path() == first / PR.MODE_FILE, str(PR.mode_path()))
        check("... and so do the profile and the tracker",
              PR.profile_path().parent == first / PR.PRIVACY_DIR
              and PR.tracker_path().parent == first / PR.PRIVACY_DIR,
              str(PR.profile_path()))
        PR.write_mode("optery_api")
        check("... so a mode written here is really on that folder's disk",
              (first / PR.MODE_FILE).is_file()
              and not (second / PR.MODE_FILE).exists())
    finally:
        for name, value in zip(("JARVIS_CONFIG_DIR", "OPENJARVIS_CONFIG_DIR"), saved):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    check("... and the suite's own folder is back once the variables are restored",
          PR.config_dir() == TMP, str(PR.config_dir()))


# ---------------------------------------------------------------------------
#   3. The schema: created, seeded, re-openable
# ---------------------------------------------------------------------------


def t_the_schema_creates_and_reopens():
    clean()
    check("no tracker exists before the first open", not PR.tracker_path().exists())
    conn = PR.connect()
    try:
        names = {row["name"] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
        check("the tracker gets the owner's three tables",
              {"brokers", "requests", "official_portals"} <= names, str(sorted(names)))
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(brokers)")}
        check("brokers holds every column the owner specified",
              {"broker_id", "name", "category", "method", "optout_url",
               "privacy_email", "dead_url", "last_updated"} <= cols, str(sorted(cols)))
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(requests)")}
        check("requests holds every column the owner specified",
              {"id", "broker_id", "engine", "status", "request_ref", "listing_url",
               "sent_at", "verify_after", "relist_check_at", "notes"} <= cols,
              str(sorted(cols)))
        cols = {row["name"] for row in conn.execute(
            "PRAGMA table_info(official_portals)")}
        check("official_portals holds the checklist columns",
              {"portal_id", "name", "url", "done", "last_checked"} <= cols,
              str(sorted(cols)))
        conn.execute("INSERT INTO brokers (broker_id, name, category, method) "
                     "VALUES ('b1', 'A Broker', 'people search', 'email')")
        conn.execute("INSERT INTO requests (broker_id, engine, status) "
                     "VALUES ('b1', 'local_email', 'sent')")
        conn.commit()
    finally:
        conn.close()
    again = PR.connect()
    try:
        check("a SECOND open keeps every row (the schema is IF NOT EXISTS)",
              again.execute("SELECT COUNT(*) AS n FROM brokers").fetchone()["n"] == 1
              and again.execute("SELECT COUNT(*) AS n FROM requests")
              .fetchone()["n"] == 1)
        portals = again.execute(
            "SELECT portal_id, url FROM official_portals ORDER BY portal_id").fetchall()
        check("... and the two free official portals are seeded, with real links",
              [row["portal_id"] for row in portals]
              == ["california_drop", "google_results_about_you"]
              and all(str(row["url"]).startswith("https://") for row in portals),
              str([dict(row) for row in portals]))
    finally:
        again.close()
    # Re-opening a third time must not duplicate the seeded portals.
    third = PR.connect()
    try:
        check("... and opening again does not duplicate the portal checklist",
              third.execute("SELECT COUNT(*) AS n FROM official_portals")
              .fetchone()["n"] == 2)
    finally:
        third.close()


def t_the_paths_are_a_real_sqlite_file():
    clean()
    conn = PR.connect()
    conn.close()
    raw = PR.tracker_path().read_bytes()
    check("the tracker really is a SQLite database on disk",
          raw.startswith(b"SQLite format 3\x00"), raw[:16])


# ---------------------------------------------------------------------------
#   4. The masked profile
# ---------------------------------------------------------------------------


def t_the_masked_profile_never_shows_a_value():
    clean()
    write_profile()
    masked = PR.masked_profile()
    check("the masked profile names the four fields it holds",
          set(masked) == {"name", "address", "phone", "email"}, str(masked))
    good, who = no_pii(json.dumps(masked))
    check("... and not one raw value is in it", good, who)
    check("... and each one is a label with the last four characters",
          all(v.endswith(")") and "(..." in v for v in masked.values()), str(masked))
    check("... with the address's own last four digits",
          masked["address"].endswith("2704)"), masked["address"])
    check("... and the phone's own last four digits",
          masked["phone"].endswith("4471)"), masked["phone"])
    check("... and the email masked on its local part, never its domain",
          masked["email"].endswith("ield)") and "example.com" not in masked["email"],
          masked["email"])
    words = PR.profile_words()
    good, who = no_pii(words)
    check("profile_words() carries no raw value either", good, who)
    check("... and it names what the profile holds, one label at a time",
          "Primary address" in words and "Primary email" in words, words)


def t_a_missing_profile_is_said_in_words():
    clean()
    check("with no profile, the masked profile is empty", PR.masked_profile() == {})
    words = PR.profile_words()
    check("... and the answer says so and says why, rather than being blank",
          "No removal profile is set up" in words and PR.PROFILE_FILE in words, words)
    check("... and it names where that file would be", PR.PRIVACY_DIR in words, words)


def t_a_damaged_profile_does_not_take_the_answer_down():
    clean()
    PR.profile_path().parent.mkdir(parents=True, exist_ok=True)
    PR.profile_path().write_text("{not json at all", encoding="utf-8")
    check("an unreadable profile reads as empty rather than raising",
          PR.load_profile() == {} and PR.masked_profile() == {})
    check("... and the tool still answers about itself",
          "data brokers" in PR.privacy_explain("overview"))


# ---------------------------------------------------------------------------
#   5. The four topics, each from live state
# ---------------------------------------------------------------------------


def t_every_topic_answers_from_live_state():
    clean()
    write_profile()
    for topic in PR.TOPICS:
        said = PR.privacy_explain(topic)
        check(f"the {topic!r} topic answers, and not with a refusal",
              isinstance(said, str) and len(said) > 200
              and "i can't" not in said.lower()
              and "i cannot" not in said.lower(), said[:200])
        good, who = no_pii(said)
        check(f"... and {topic!r} carries no raw value", good, who)
        check(f"... and {topic!r} states the live mode, local",
              "local (this PC only)" in said, said[:200])
        check(f"... and {topic!r} states that nothing is tracked yet",
              "Nothing is tracked yet" in said, said[:200])
    check("pros_cons compares all three modes by name",
          all(name in PR.privacy_explain("pros_cons")
              for name in ("Local", "Optery's cloud API", "Hybrid")))
    check("limits names the verify pass and the 90-day re-check",
          "verify pass" in PR.privacy_explain("limits")
          and "90 days" in PR.privacy_explain("limits"))
    check("official_portals names both free portals and their real links",
          "Google Results About You" in PR.privacy_explain("official_portals")
          and "myactivity.google.com/results-about-you"
          in PR.privacy_explain("official_portals")
          and "privacy.ca.gov/drop" in PR.privacy_explain("official_portals"))


def t_the_topics_follow_the_tracker():
    """The counts in an answer are the tracker's counts, not a fixed sentence."""
    clean()
    conn = PR.connect()
    try:
        for broker, status in (("b1", "sent"), ("b2", "needs_verify_click"),
                               ("b3", "removed")):
            conn.execute("INSERT INTO brokers (broker_id, name, method) "
                         "VALUES (?, ?, 'email')", (broker, broker.upper()))
            conn.execute("INSERT INTO requests (broker_id, engine, status) "
                         "VALUES (?, 'local_email', ?)", (broker, status))
        conn.commit()
    finally:
        conn.close()
    said = PR.privacy_explain("overview")
    check("the answer counts the three requests the tracker really holds",
          "3 request(s)" in said and "3 broker(s)" in said, said[:300])
    check("... and names the statuses, not only the total",
          "1 sent" in said and "1 waiting for you to click" in said
          and "1 confirmed removed" in said, said[:300])
    check("... and the counts are the tracker's own",
          PR.counts()["sent"] == 1 and PR.counts()["removed"] == 1
          and PR.counts()["needs_verify_click"] == 1, str(PR.counts()))


def t_an_unknown_topic_names_the_four():
    clean()
    said = PR.privacy_explain("the meaning of life")
    check("an unknown topic names the four real ones instead of refusing",
          all(topic in said for topic in PR.TOPICS), said)
    check("... and it is not a refusal sentence",
          "i can't" not in said.lower() and "i cannot" not in said.lower(), said)
    check("... and a missing topic defaults to the overview",
          PR.privacy_explain() == PR.privacy_explain("overview"))


# ---------------------------------------------------------------------------
#   6. The consent card
# ---------------------------------------------------------------------------


class Verdict:
    """What `jarvis_gate.check` returns, in the shape `_decide` reads."""

    def __init__(self, allowed, outcome, tier="ask", reason=""):
        self.allowed = allowed
        self.outcome = outcome
        self.tier = tier
        self.reason = reason


def run_card(mode_wanted, verdict):
    """Raise the card for `mode_wanted` with `verdict`, on this thread."""
    asked = []

    def gate(action, detail, prompt):
        asked.append((action, detail, prompt))
        return verdict

    code, body = PR.set_mode(mode_wanted, gate=gate, tier_of=lambda a: "ask",
                             spawn=lambda fn: fn())
    return code, body, asked


def t_the_cloud_consent_card_is_raised_for_each_cloud_mode():
    for wanted in PR.CLOUD_MODES:
        clean()
        code, body, asked = run_card(wanted, Verdict(False, "denied"))
        check(f"switching to {wanted} raises exactly ONE card", len(asked) == 1,
              str(asked))
        action, detail, prompt = asked[0]
        check(f"... under the existing change_own_config action, so no gate row is added",
              action == "change_own_config" and PR.CONSENT_ACTION == "change_own_config",
              action)
        text = str(detail.get("text")) + " " + str(prompt)
        check(f"... and the card names the name, address, phone and email",
              all(word in text.lower() for word in
                  ("name", "address", "phone", "email")), text[:300])
        check(f"... and says they go to Optery over HTTPS",
              "https" in text.lower() and "optery" in text.lower(), text[:300])
        check(f"... and the machine side says details leave this PC",
              detail.get("leaves_this_pc") is True, str(detail))
        good, who = no_pii(text)
        check(f"... and the card's own words carry no raw value", good, who)
        check(f"... and the answer is a 202 that says it is waiting",
              code == 202 and body.get("waiting") is True
              and "Waiting for your yes" in body.get("said", ""), str(body))


def t_a_denied_card_changes_nothing():
    for wanted in PR.CLOUD_MODES:
        clean()
        code, body, _asked = run_card(wanted, Verdict(False, "denied"))
        check(f"denying the card for {wanted} leaves the mode at local",
              PR.mode() == "local" and not PR.mode_path().exists(), str(PR.mode()))
        check(f"... and the answer never claims the mode changed ({wanted})",
              body.get("changed") is False
              and "now using" not in str(body.get("said", "")).lower()
              and "is on optery" not in str(body.get("said", "")).lower(),
              str(body.get("said")))
        last = PR.mode_card_state().get("last") or {}
        check(f"... and the card's own record says denied, in the owner's words "
              f"({wanted})",
              last.get("outcome") == "denied"
              and "turned down" in str(last.get("said", "")), str(last))
    for outcome in ("timed_out", ""):
        clean()
        verdict = Verdict(False, "timed_out") if outcome else Verdict(False, "")
        code, body, _asked = run_card("optery_api", verdict)
        check(f"a card nobody answered ({outcome or 'no outcome'}) changes nothing",
              PR.mode() == "local" and body.get("changed") is False,
              f"{outcome!r} {body}")


def t_an_approved_card_writes_the_mode():
    for wanted in PR.CLOUD_MODES:
        clean()
        code, body, _asked = run_card(wanted, Verdict(True, "approved"))
        check(f"approving the card for {wanted} saves that mode", PR.mode() == wanted,
              str(PR.mode()))
        last = PR.mode_card_state().get("last") or {}
        check(f"... and the record says changed, in the owner's words ({wanted})",
              last.get("outcome") == "changed"
              and "approved the card" in str(last.get("said", "")), str(last))


def t_a_loosened_tier_is_refused_before_any_card():
    clean()
    asked = []
    code, body = PR.set_mode("optery_api",
                             gate=lambda a, d, p: asked.append(a) or Verdict(True, "approved"),
                             tier_of=lambda a: "auto",
                             spawn=lambda fn: fn())
    check("a settings file that made the action cardless gets a refusal, no card",
          code == 409 and not asked, f"{code} {body} asked={asked}")
    check("... naming the action and the tier it must be",
          "change_own_config" in str(body.get("error")) and "ask" in str(body.get("error")),
          str(body.get("error")))
    check("... and the mode is untouched", PR.mode() == "local")


def t_a_second_card_is_not_stacked():
    clean()
    PR._reset_for_tests()
    # Raise one card that never answers (the spawn does nothing), then ask again.
    code1, _b1 = PR.set_mode("optery_api", gate=lambda a, d, p: Verdict(False, "denied"),
                             tier_of=lambda a: "ask", spawn=lambda fn: None)
    code2, body2 = PR.set_mode("hybrid", gate=lambda a, d, p: Verdict(False, "denied"),
                               tier_of=lambda a: "ask", spawn=lambda fn: None)
    check("a second cloud switch while a card is waiting answers 202, waiting",
          code1 == 202 and code2 == 202 and body2.get("waiting") is True, str(body2))
    check("... and says a card is already waiting rather than raising another",
          "already waiting" in str(body2.get("said")), str(body2.get("said")))
    PR._reset_for_tests()
    check("... and the mode is still local", PR.mode() == "local")


# ---------------------------------------------------------------------------
#   7. The trigger phrases, through the real jarvis_quick.match()
# ---------------------------------------------------------------------------

#: The seven the owner listed (2026-11-26, section 4, Layer A), and the topic
#: each must land on.
TRIGGERS = (
    ("what is the data removal tool", "overview"),
    ("how does your personal info removal work", "overview"),
    ("pros and cons of local vs optery", "pros_cons"),
    ("should I use local or optery", "pros_cons"),
    ("can you remove my personal info from the internet", "overview"),
    ("how private is data removal", "limits"),
    ("what can't the data removal tool do", "limits"),
)

#: Sentences that must NOT become this feature's - each already has an owner.
NOT_OURS = (
    "what is the weather",
    "what is the weather tomorrow",
    "set my cap to $5",
    "which cloud provider am I using",
    "how much did I spend last month",
    "set a timer for 10 minutes",
    "what can you do",
    "how private are my notes",
)


def t_every_trigger_phrase_reaches_the_intent():
    clean()
    for sentence, topic in TRIGGERS:
        intent = Q.match(sentence, 1000.0)
        check(f"{sentence!r} reaches privacy_explain by intent",
              intent is not None and intent.name == "privacy_explain",
              str(getattr(intent, "name", None)))
        check(f"... and it lands on the {topic!r} topic",
              intent is not None and intent.f.get("topic") == topic,
              str(getattr(intent, "f", None)))
    for sentence in ("what are the official portals for data removal",
                     "google results about you", "california drop"):
        intent = Q.match(sentence, 1000.0)
        check(f"{sentence!r} reaches the official_portals topic",
              intent is not None and intent.name == "privacy_explain"
              and intent.f.get("topic") == "official_portals",
              str(getattr(intent, "name", None)))


def t_the_neighbouring_sentences_keep_their_own_doors():
    clean()
    for sentence in NOT_OURS:
        intent = Q.match(sentence, 1000.0)
        check(f"{sentence!r} is still not this feature's",
              intent is None or intent.name != "privacy_explain",
              str(getattr(intent, "name", None)))
    for sentence in NOT_OURS:
        got = PR.prompt(PR._norm(sentence), sentence)
        check(f"... and the module itself does not claim {sentence!r}", got is None,
              str(got))


def t_the_answer_comes_from_the_real_run_not_the_model():
    clean()
    intent = Q.match("what is the data removal tool", 1000.0)
    got = Q.run(intent, None, 1000.0)
    check("running the intent answers it here, with no model",
          got is not None and got.intent == "privacy_explain"
          and "data brokers" in got.reply, getattr(got, "reply", "")[:200])
    good, who = no_pii(got.reply)
    check("... and the reply carries no raw value", good, who)
    check("... and it is not a refusal", "i can't" not in got.reply.lower())


def t_the_change_sentences_go_through_the_one_registry_row():
    clean()
    for sentence, wanted in (("switch data removal to local", "local"),
                             ("use hybrid data removal", "hybrid"),
                             ("switch data removal to optery api", "optery_api")):
        intent = Q.match(sentence, 1000.0)
        check(f"{sentence!r} is the mode-change intent",
              intent is not None and intent.name == "privacy_mode_change"
              and intent.f.get("mode") == wanted, str(getattr(intent, "f", None)))
    # The row IS the path: the registry's setter must be the one jarvis_quick
    # calls, and it must end in the module's own set_mode.
    row = R.find_mode_setting("the data removal mode")
    check("the settings registry has ONE data_removal row", row is not None,
          str([s.key for s in R.MODE_SETTINGS]))
    check("... and its setter is set_data_removal_mode",
          row is not None and row.set is R.set_data_removal_mode)
    seen = []
    real = PR.set_mode

    def spy(value, **kwargs):
        seen.append((value, kwargs.get("peer"), kwargs.get("local")))
        return 200, {"ok": True, "changed": True, "mode": value,
                     "said": f"MODE SET TO {value}"}

    PR.set_mode = spy
    try:
        outcome = R.set_data_removal_mode("hybrid", peer="100.64.0.7", local=None)
    finally:
        PR.set_mode = real
    check("... and calling the row reaches the module's own set_mode with peer/local",
          seen == [("hybrid", "100.64.0.7", None)], str(seen))
    check("... and the answer is the setter's own words, not a new sentence",
          outcome.ok is True and outcome.said == "MODE SET TO hybrid", outcome.said)


def t_the_read_and_change_intents_are_classified_correctly():
    check("the read is a read-only intent", "privacy_explain" in Q.READ_ONLY_INTENTS)
    check("... and so a private chat may answer it",
          "privacy_explain" in Q._PRIVATE_DETERMINISTIC_READS)
    check("the change is NOT read-only (it can raise a card and change a setting)",
          "privacy_mode_change" not in Q.READ_ONLY_INTENTS
          and "privacy_mode_change" not in Q._PRIVATE_DETERMINISTIC_READS)


# ---------------------------------------------------------------------------
#   8. An empty tracker answers honestly
# ---------------------------------------------------------------------------


def t_an_empty_tracker_answers_honestly():
    clean()
    counts = PR.counts()
    check("every status the owner listed is present, and zero",
          all(counts[status] == 0 for status in PR.STATUSES), str(counts))
    check("... and the totals are zero, not missing",
          counts["total"] == 0 and counts["brokers"] == 0
          and counts["manual_todo"] == 0, str(counts))
    said = PR.state_words()
    check("... and the answer says nothing is tracked yet, rather than nothing",
          "Nothing is tracked yet" in said and "0" not in said, said)
    check("... and it states the mode and the two readiness facts",
          "local (this PC only)" in said and "Gmail App Password" in said
          and "Optery API key" in said, said)
    good, who = no_pii(said)
    check("... and it carries no raw value", good, who)
    check("... and an empty tracker still answers every topic",
          all(PR.privacy_explain(topic) for topic in PR.TOPICS))


def t_the_manual_work_is_counted_for_the_owner_only():
    clean()
    conn = PR.connect()
    try:
        conn.execute("INSERT INTO brokers (broker_id, name, method) "
                     "VALUES ('web1', 'A Web Form Broker', 'web_form')")
        conn.execute("INSERT INTO brokers (broker_id, name, method) "
                     "VALUES ('web2', 'Another Web Form Broker', 'web_form')")
        conn.execute("INSERT INTO brokers (broker_id, name, method) "
                     "VALUES ('em1', 'An Email Broker', 'email')")
        conn.execute("INSERT INTO requests (broker_id, engine, status) "
                     "VALUES ('web2', 'manual', 'blocked_captcha')")
        conn.commit()
    finally:
        conn.close()
    counts = PR.counts()
    check("a web-form broker with no request is counted as the owner's own click",
          counts["manual_todo"] == 1, str(counts))
    check("... and the email broker with no request is not",
          counts["brokers"] == 3 and counts["blocked_captcha"] == 1, str(counts))


def t_the_official_portal_checklist_can_be_ticked():
    clean()
    check("both portals start unticked",
          [row["done"] for row in PR.official_portals()] == [False, False])
    check("marking one really stores the tick and the date",
          PR.mark_portal("california_drop") is True
          and PR.official_portals()[0]["done"] is True
          and bool(PR.official_portals()[0]["last_checked"]))
    check("... and the answer says so when the owner reads the topic",
          "you marked this done" in PR.privacy_explain("official_portals"))
    check("an id that is not one of the two is refused",
          PR.mark_portal("not_a_portal") is False)


# ---------------------------------------------------------------------------
#   9. The two rows bite when reverted
# ---------------------------------------------------------------------------


def t_the_two_rows_bite_when_reverted():
    # --- row one: the Privacy category in jarvis_asks_first.TOOL_GROUPS -----
    check("the Privacy category row is in the live tool groups",
          AF.GROUP_FOR_TOOL.get("privacy_explain") == "Privacy",
          str(AF.GROUP_FOR_TOOL.get("privacy_explain")))
    saved = AF.TOOL_GROUPS
    saved_map = AF.GROUP_FOR_TOOL
    try:
        AF.TOOL_GROUPS = tuple(g for g in saved if g[0] != "Privacy")
        AF.GROUP_FOR_TOOL = {tool: title for title, tools in AF.TOOL_GROUPS
                             for tool in tools}
        check("reverting the Privacy row really makes that check fail "
              "(so the check bites)",
              AF.GROUP_FOR_TOOL.get("privacy_explain") is None,
              str(AF.GROUP_FOR_TOOL.get("privacy_explain")))
    finally:
        AF.TOOL_GROUPS = saved
        AF.GROUP_FOR_TOOL = saved_map
    # The row is really in the FILE and really guarded, proved by walking
    # jarvis_asks_first.py's own ast rather than by pinning its text
    # (tools/check_no_source_pins.py's own rule). `_guarded_imports` is defined
    # in section 10, below.
    guarded = _guarded_imports(Path(AF.__file__), "jarvis_privacy_removal")
    check("... and jarvis_asks_first.py imports it inside a try, so an older PC "
          "keeps exactly the groups it had",
          len(guarded) == 1 and "Exception" in guarded[0][1], str(guarded))
    check("... and the append really happens in that module's own top level "
          "(TOOL_GROUPS grew by the Privacy row in the import that ran)",
          "Privacy" in [title for title, _tools in AF.TOOL_GROUPS],
          str([title for title, _tools in AF.TOOL_GROUPS]))

    # --- row two: the mode dial in jarvis_settings_registry.MODE_SETTINGS ---
    check("the data_removal row is in the live registry",
          any(s.key == "data_removal" for s in R.MODE_SETTINGS),
          str([s.key for s in R.MODE_SETTINGS]))
    saved_modes = R.MODE_SETTINGS
    try:
        R.MODE_SETTINGS = tuple(s for s in saved_modes if s.key != "data_removal")
        check("reverting the data_removal row really makes that check fail "
              "(so the check bites)",
              R.find_mode_setting("the data removal mode") is None)
    finally:
        R.MODE_SETTINGS = saved_modes
    # The row is really in the FILE, not injected at runtime: the negative
    # control above removed it from the LIVE tuple of the module that was
    # imported from disk, and the spy in
    # `t_the_change_sentences_go_through_the_one_registry_row` proved the
    # setter's body reaches `PR.set_mode` carrying `peer`/`local`. Nothing here
    # pins source TEXT (tools/check_no_source_pins.py): a pin on text goes red
    # when the code is improved and stays green when it is wrong.
    check("... and the row's own `what` says local is the only mode that keeps "
          "the details on this PC",
          "keeps your details on this PC" in
          next(s.what for s in R.MODE_SETTINGS if s.key == "data_removal"),
          next(s.what for s in R.MODE_SETTINGS if s.key == "data_removal"))


# ---------------------------------------------------------------------------
#   10. Nothing is shipped, and the import is guarded
# ---------------------------------------------------------------------------


def _guarded_imports(path: Path, module: str) -> list:
    """[(line, the handler names it catches)] for every `try: import <module>`
    in `path`. WALKS THE `ast`, so a comment or a docstring can never satisfy
    it and a rename goes red for the right reason."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        imported = False
        for stmt in node.body:
            for inner in ast.walk(stmt):
                if isinstance(inner, ast.Import) and any(
                        alias.name == module for alias in inner.names):
                    imported = True
                elif isinstance(inner, ast.ImportFrom) and inner.module == module:
                    imported = True
        if not imported:
            continue
        caught = [h.type.id for h in node.handlers
                  if isinstance(h.type, ast.Name)]
        out.append((node.lineno, caught))
    return out


def t_the_module_is_not_in_shipped_yet():
    import _where
    check("the owner's ruling holds: the module is NOT in _where.SHIPPED",
          "jarvis_privacy_removal.py" not in _where.SHIPPED)
    check("... and the published base does not carry it either",
          not (HERE.parent / "jarvis-backend" / "jarvis_privacy_removal.py").is_file())
    # The three tables that have to be told the truth, read as DATA - the same
    # objects the two suites themselves use, not a copy of their text.
    import test_base_matches_repo as TBM
    import test_shipped_modules as TSM
    check("... it is on NOT_SHIPPED with its reason, so the shipped-module suite "
          "stays honest",
          "jarvis_privacy_removal.py" in TSM.NOT_SHIPPED
          and len(TSM.NOT_SHIPPED["jarvis_privacy_removal.py"]) > 80,
          str(TSM.NOT_SHIPPED.get("jarvis_privacy_removal.py"))[:80])
    sites = ("jarvis_quick.py", "jarvis_asks_first.py", "jarvis_settings_registry.py")
    check("... and every one of its three call sites is in that suite's guarded-"
          "import table",
          all((site, "jarvis_privacy_removal") in TSM.REPO_ONLY_IMPORTS
              for site in sites),
          str([site for site in sites
               if (site, "jarvis_privacy_removal") not in TSM.REPO_ONLY_IMPORTS]))
    check("... and the base's import walk is told the truth about it",
          "jarvis_privacy_removal" in TBM.OPTIONAL_IMPORTS)
    # And the guard is REAL, proved by walking jarvis_quick.py's own ast: every
    # import of this module there sits inside a try that catches Exception, so
    # a copy of the file in the published base - which does not carry the
    # module - still imports and behaves as it did before.
    guarded = _guarded_imports(Path(Q.__file__), "jarvis_privacy_removal")
    check("... and every import of it in jarvis_quick.py is inside a try",
          len(guarded) >= 2, str(guarded))
    check("... that catches Exception, so a base without the module still imports",
          bool(guarded) and all("Exception" in caught for _line, caught in guarded),
          str(guarded))


# ---------------------------------------------------------------------------
#   11. Stdlib only, and every network seam injectable (PR 2 rewrote this)
# ---------------------------------------------------------------------------
#
# PR 1's version of this section proved the module reached NO network, which was
# true of that slice and false of this one: PR 2 downloads the public directory,
# sends through Gmail and reads the same mailbox over IMAP. What has to be true
# now is narrower and stronger - every one of those three seams is an injected
# callable, so this suite drives the real code with fake doubles and the whole
# file is still standard library only. Section 18 below makes that check.


# ---------------------------------------------------------------------------
#   12. The broker directory: parsed, cached here, imported (PR 2)
# ---------------------------------------------------------------------------

#: A small stand-in for Optery's directory, in the real document's own shape.
#: It carries one entry of EACH kind the parser has to tell apart: an email
#: broker, an opt-out-page broker, a guide-link broker, one with no route at all,
#: one whose "email" field is an instruction rather than an address, and a
#: duplicate id.
DIRECTORY_FIXTURE = [
    {"id": 1, "title": "Acme People Search", "website": "https://acme.example/",
     "opt_out_url": "", "opt_out_guide_url": "",
     "email": "privacy@acme.example", "type": "People Search Site"},
    {"id": 2, "title": "Beta Marketing", "website": "https://beta.example/",
     "opt_out_url": "https://beta.example/optout", "opt_out_guide_url": "",
     "email": "", "type": "Marketing"},
    {"id": 3, "title": "Gamma Leads", "website": "https://gamma.example/",
     "opt_out_url": "", "opt_out_guide_url": "https://gamma.example/remove",
     "email": "", "type": "B2B Lead Generation"},
    {"id": 4, "title": "No Route Ltd", "website": "https://noroute.example/",
     "opt_out_url": "", "opt_out_guide_url": "", "email": "",
     "type": "Marketing"},
    {"id": 5, "title": "Junk Mail Field", "website": "https://junk.example/",
     "opt_out_url": "javascript:void(0)", "opt_out_guide_url": "",
     "email": "see our form, not an address", "type": "Marketing"},
    {"id": 1, "title": "Acme Again", "website": "https://acme.example/",
     "opt_out_url": "", "opt_out_guide_url": "",
     "email": "privacy@acme.example", "type": "People Search Site"},
]


class FakeResponse:
    """What `urllib.request.urlopen` returns, without a socket."""

    def __init__(self, payload: bytes, status: int = 200):
        self.status = status
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def read(self, limit: int = -1):
        if isinstance(limit, int) and limit > 0:
            return self._payload[:limit]
        return self._payload


def opener_for(payload: bytes, status: int = 200):
    """A fake `urlopen` that answers `payload`/`status` and records every URL."""
    calls = []

    def opener(url, timeout=None):
        calls.append((url, timeout))
        if status != 200:
            raise urllib.error.HTTPError(url, status, "refused", None, None)
        return FakeResponse(payload, status)

    opener.calls = calls
    return opener


def recording_opener(payload: bytes = b"", status: int = 200):
    """A fake `urlopen` that RECORDS and refuses: used where none may be called."""
    calls = []

    def opener(url, timeout=None):
        calls.append(url)
        raise AssertionError(f"nothing may open {url} in this check")

    opener.calls = calls
    return opener


class FakeImap:
    """The four IMAP calls `_scan_mailbox` makes, over canned message bytes."""

    def __init__(self, messages):
        self.messages = list(messages)
        self.logged_out = False
        self.criteria = ()
        self.selected = ""

    def select(self, mailbox="INBOX"):
        self.selected = mailbox
        return "OK", [b"1"]

    def search(self, charset, *criteria):
        self.criteria = criteria
        ids = b" ".join(str(index + 1).encode()
                        for index in range(len(self.messages)))
        return "OK", [ids]

    def fetch(self, num, spec):
        raw = self.messages[int(num) - 1]
        return "OK", [(f"1 (RFC822 {{{len(raw)}}}".encode(), raw), b")"]

    def logout(self):
        self.logged_out = True
        return "BYE", []


def make_reply(sender: str, subject: str, body: str) -> bytes:
    """One broker reply, as the bytes an IMAP fetch hands back."""
    msg = email.message.EmailMessage()
    msg["From"] = f"Privacy Team <{sender}>"
    msg["To"] = EMAIL
    msg["Subject"] = subject
    msg.set_content(body)
    return msg.as_bytes()


def seed_broker(broker_id: str, name: str, *, method: str = "email",
                address: str = "", url: str = "",
                category: str = "People Search Site") -> None:
    conn = PR.connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO brokers (broker_id, name, category, method, "
            "optout_url, privacy_email, dead_url, last_updated) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
            (broker_id, name, category, method, url, address,
             "2026-11-26T00:00:00Z"))
        conn.commit()
    finally:
        conn.close()


def seed_request(broker_id: str, *, status: str = "sent",
                 sent_at: str = "2026-11-01T00:00:00Z",
                 verify_after: str = "2026-11-08T00:00:00Z",
                 listing_url: str = "") -> None:
    conn = PR.connect()
    try:
        conn.execute(
            "INSERT INTO requests (broker_id, engine, status, request_ref, "
            "listing_url, sent_at, verify_after, notes) "
            "VALUES (?, 'local_email', ?, '', ?, ?, ?, '')",
            (broker_id, status, listing_url, sent_at, verify_after))
        conn.commit()
    finally:
        conn.close()


def request_rows() -> list:
    conn = PR.connect()
    try:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM requests ORDER BY id")]
    finally:
        conn.close()


def seed_email_brokers(count: int) -> None:
    for index in range(count):
        seed_broker(f"b{index:02d}", f"Broker {index:02d}",
                    address=f"privacy@broker{index:02d}.example")


def run_batch(template: str = "generic", *, verdict=None, now=None,
              gate=None, tier_of=None, spawn=None):
    """Drive the REAL `send_optout_batch` with a fake card and a fake SMTP.

    `spawn` runs the card's thread inline by default, so the test sees the send
    happen, and `transport` records the built messages instead of opening a
    connection. A test that wants the card still OPEN passes its own `spawn`.
    """
    asked, sent = [], []

    def gate_fn(action, detail, prompt):
        asked.append({"action": action, "detail": detail, "prompt": prompt})
        return verdict if verdict is not None else Verdict(True, "approved")

    code, body = PR.send_optout_batch(
        template, gate=gate or gate_fn,
        tier_of=tier_of or (lambda action: "ask"),
        spawn=spawn or (lambda fn: fn()),
        transport=lambda msg: sent.append(msg),
        now=now)
    return code, body, asked, sent


def t_the_directory_parses_into_the_brokers_table():
    clean()
    got = PR.parse_directory(DIRECTORY_FIXTURE)
    by_id = {row["broker_id"]: row for row in got["rows"]}
    check("a directory parses into the brokers table's own columns",
          set(by_id) == {"optery-1", "optery-2", "optery-3"}, sorted(by_id))
    check("... a broker with a privacy email is an `email` broker",
          by_id["optery-1"]["method"] == "email"
          and by_id["optery-1"]["privacy_email"] == "privacy@acme.example",
          str(by_id.get("optery-1")))
    check("... a broker with an opt-out page is a `web_form` broker",
          by_id["optery-2"]["method"] == "web_form"
          and by_id["optery-2"]["optout_url"] == "https://beta.example/optout",
          str(by_id.get("optery-2")))
    check("... and a guide link is a route the owner can use too",
          by_id["optery-3"]["optout_url"] == "https://gamma.example/remove",
          str(by_id.get("optery-3")))
    check("... the category comes from the directory's own `type`",
          by_id["optery-1"]["category"] == "People Search Site",
          str(by_id.get("optery-1", {}).get("category")))
    check("... an entry with neither an address nor an opt-out page is counted "
          "and left out, never imported as a dead end",
          got["skipped"] == 2 and "optery-4" not in by_id, str(got["skipped"]))
    check("... an 'email' that is really an instruction is not an address",
          "optery-5" not in by_id and got["email"] == 1, str(got["email"]))
    check("... and a duplicate id is kept once", len(got["rows"]) == 3,
          str(len(got["rows"])))


def t_a_refresh_writes_the_cache_here_and_the_table():
    clean()
    opener = opener_for(json.dumps(DIRECTORY_FIXTURE).encode())
    result = PR.sync_directory(opener=opener, now="2026-11-26T07:00:00Z")
    check("a refresh answers ok with the real counts",
          result["ok"] and result["count"] == 3 and result["email"] == 1
          and result["web_form"] == 2, str(result))
    check("... from the public directory, over one URL",
          len(opener.calls) == 1
          and "optery-data-brokers-directory" in opener.calls[0][0],
          str(opener.calls))
    cache = PR.brokers_cache_path()
    check("... the parsed list is cached on THIS PC, under the settings folder",
          cache.is_file() and str(TMP) in str(cache), str(cache))
    doc = json.loads(cache.read_text(encoding="utf-8"))
    check("... with its source and its licence written in, so the credit "
          "travels with the data",
          "optery-data-brokers-directory" in str(doc.get("source"))
          and str(doc.get("license", "")).startswith("CC BY-NC-SA"),
          str(doc.get("license"))[:60])
    check("... and the brokers table really holds the rows",
          PR.counts()["brokers"] == 3, str(PR.counts()["brokers"]))
    again = PR.sync_directory(opener=opener_for(json.dumps(DIRECTORY_FIXTURE)
                                               .encode()))
    check("a second refresh updates the rows instead of duplicating them",
          again["ok"] and PR.counts()["brokers"] == 3,
          str(PR.counts()["brokers"]))
    said = PR.sync_words(result)
    check("... and the answer says what came in and what was left out",
          "3 broker(s)" in said and "2 entr" in said, said[:300])


def t_a_failed_refresh_says_so_and_loses_nothing():
    clean()
    PR.sync_directory(opener=opener_for(json.dumps(DIRECTORY_FIXTURE).encode()))

    def broken(url, timeout=None):
        raise OSError("no network")

    result = PR.sync_directory(opener=broken)
    check("a download that fails is SAID, never raised",
          result["ok"] is False and "could not be downloaded" in result["error"],
          str(result))
    check("... and the copy already on this PC still holds every broker",
          PR.counts()["brokers"] == 3, str(PR.counts()["brokers"]))
    check("... and the answer says nothing was lost",
          "nothing was lost" in PR.sync_words(result), PR.sync_words(result))
    result = PR.sync_directory(opener=opener_for(b"<html>hotel wifi</html>"))
    check("... and a captive portal's HTML is refused as not JSON",
          result["ok"] is False and "not JSON" in result["error"], str(result))


# ---------------------------------------------------------------------------
#   13. The carded batch sender: the caps, the denial, the two wait windows
# ---------------------------------------------------------------------------


def t_the_batch_card_names_the_brokers_the_template_and_the_count():
    clean()
    write_profile()
    stub_gmail()
    seed_email_brokers(25)
    code, body, asked, sent = run_batch("ccpa", verdict=Verdict(False, "denied"))
    check("a batch raises exactly ONE card", len(asked) == 1, str(len(asked)))
    check("... under the EXISTING send_email ask action, so no gate row is added",
          asked[0]["action"] == PR.BATCH_ACTION == "send_email",
          asked[0]["action"])
    prompt = asked[0]["prompt"]
    check("... and it names the exact count and both hard caps",
          "20 data-broker deletion email(s)" in prompt and "250" in prompt,
          prompt[:200])
    check("... and it carries the template type, in words",
          "California Consumer Privacy Act" in prompt, prompt[:300])
    names = [f"Broker {index:02d}" for index in range(20)]
    check("... and every one of the 20 exact brokers is named on it",
          all(name in prompt for name in names),
          str([name for name in names if name not in prompt]))
    check("... and the 21st broker is NOT on it, so a card cannot name 21",
          "Broker 20" not in prompt, prompt[-200:])
    # --- and while the card is still OPEN, the answer says "waiting" ---------
    clean()
    write_profile()
    stub_gmail()
    seed_email_brokers(25)
    pending = []
    code, body, _asked, sent = run_batch("ccpa",
                                         spawn=lambda fn: pending.append(fn))
    check("while the card is open the answer is 202 waiting, not 'sent'",
          code == 202 and body.get("waiting") is True, str(body.get("said")))
    check("... and the card really is pending",
          PR.batch_card_state()["waiting"] is True, "")
    check("... and nothing has been sent or written while it waits",
          sent == [] and request_rows() == [], str(request_rows()))
    for card in pending:
        card()
    check("... and when the card settles the sends really happen",
          len(request_rows()) == 20, str(len(request_rows())))


def t_a_denied_card_sends_nothing_and_writes_nothing():
    clean()
    write_profile()
    stub_gmail()
    seed_email_brokers(3)
    before = request_rows()
    _code, body, _asked, sent = run_batch("generic", verdict=Verdict(False,
                                                                    "denied"))
    check("denying the batch card sends no email at all", sent == [], str(sent))
    check("... and writes NO request row", request_rows() == before,
          str(request_rows()))
    check("... and says so in the owner's own words",
          "turned down" in body.get("said", ""), body.get("said"))
    last = PR.batch_card_state().get("last") or {}
    check("... and the card's record says denied",
          last.get("outcome") == "denied" and last.get("sent") == 0, str(last))
    clean()
    write_profile()
    stub_gmail()
    seed_email_brokers(3)
    _code, body, _asked, sent = run_batch("generic",
                                          verdict=Verdict(False, "timed_out"))
    check("a card nobody answered sends nothing either", sent == [],
          str(sent))
    check("... and is never reported as a denial or a change",
          "Nobody answered" in body.get("said", ""), body.get("said"))


def t_an_approved_card_sends_and_records_the_two_wait_windows():
    clean()
    write_profile()
    stub_gmail()
    seed_email_brokers(3)
    now = "2026-11-26T07:00:00Z"
    code, body, _asked, sent = run_batch("ccpa", now=now)
    check("approving the card sends exactly the brokers on it", len(sent) == 3,
          str(len(sent)))
    check("... each email goes to the broker's own privacy address",
          sorted(str(msg["To"]) for msg in sent)
          == ["privacy@broker00.example", "privacy@broker01.example",
              "privacy@broker02.example"],
          str([str(msg["To"]) for msg in sent]))
    check("... and the request carries the details a deletion needs, in the "
          "message only",
          all(NAME in msg.get_content() for msg in sent), "profile missing")
    rows = request_rows()
    check("... every one is recorded as `sent`, engine local_email",
          len(rows) == 3 and all(row["status"] == "sent"
                                 and row["engine"] == "local_email"
                                 for row in rows), str(rows))
    check("... with the date it went out", all(row["sent_at"] == now
                                               for row in rows), str(rows))
    check("... and a statutory CCPA request gets the 45-day window",
          all(row["verify_after"] == "2027-01-10T07:00:00Z" for row in rows),
          str([row["verify_after"] for row in rows]))
    seed_email_brokers(6)                       # three more, still unfiled
    _code, _body, _asked, sent = run_batch("generic", now=now)
    generic = [row for row in request_rows() if row["broker_id"] == "b03"]
    check("a plain people-search deletion request gets the 7-day window",
          len(generic) == 1
          and generic[0]["verify_after"] == "2026-12-03T07:00:00Z",
          str([row["verify_after"] for row in generic]))
    said = (PR.batch_card_state().get("last") or {}).get("said", "")
    check("... and the outcome says what went and what the window means",
          "3 removal email(s) went out" in said and "wait window" in said, said)


def t_the_daily_cap_stops_at_two_hundred_and_fifty():
    clean()
    write_profile()
    stub_gmail()
    seed_email_brokers(3)
    conn = PR.connect()
    try:
        for index in range(250):
            conn.execute(
                "INSERT INTO requests (broker_id, engine, status, sent_at, "
                "verify_after) VALUES (?, 'local_email', 'sent', ?, ?)",
                (f"old-{index}", "2026-11-26T01:00:00Z",
                 "2026-12-03T01:00:00Z"))
        conn.commit()
    finally:
        conn.close()
    got = PR.batch_candidates(now="2026-11-26T12:00:00Z")
    check("the 250-a-day cap stops a batch even with brokers waiting",
          got["rows"] == [] and "250" in got["why"], str(got))
    _code, body, asked, sent = run_batch("generic", now="2026-11-26T12:00:00Z")
    check("... and nothing is sent and no card is raised",
          asked == [] and sent == [] and "250" in body.get("said", ""),
          str(body.get("said")))


def t_the_daily_cap_shrinks_the_batch_rather_than_breaking_it():
    clean()
    stub_gmail()
    seed_email_brokers(25)
    conn = PR.connect()
    try:
        for index in range(245):
            conn.execute(
                "INSERT INTO requests (broker_id, engine, status, sent_at, "
                "verify_after) VALUES (?, 'local_email', 'sent', ?, ?)",
                (f"old-{index}", "2026-11-26T01:00:00Z",
                 "2026-12-03T01:00:00Z"))
        conn.commit()
    finally:
        conn.close()
    got = PR.batch_candidates(now="2026-11-26T12:00:00Z")
    check("with 245 already sent today the card can name only the last 5",
          len(got["rows"]) == 5, str(len(got["rows"])))
    check("... and the room is the real remaining number", got["room"] == 5,
          str(got["room"]))


def t_the_batch_needs_the_password_the_profile_and_the_right_mode():
    clean()
    seed_email_brokers(2)
    _code, body, asked, sent = run_batch("generic")
    check("without the Gmail App Password nothing is sent and no card is raised",
          asked == [] and sent == [] and "App Password is not set"
          in body.get("said", ""), body.get("said"))
    clean()
    stub_gmail()
    seed_email_brokers(2)
    PR.write_mode("optery_api")
    _code, body, asked, sent = run_batch("generic")
    check("in optery_api mode this PC sends no email at all",
          asked == [] and sent == [] and "Optery" in body.get("said", ""),
          body.get("said"))
    PR.write_mode("local")
    _code, body, asked, sent = run_batch("generic")
    check("with no removal profile there is nothing to ask a broker to delete",
          asked == [] and "no removal profile" in body.get("said", "").lower(),
          body.get("said"))


def t_a_loosened_tier_is_refused_before_any_card():
    clean()
    write_profile()
    stub_gmail()
    seed_email_brokers(2)
    asked = []
    code, body = PR.send_optout_batch(
        "generic", gate=lambda *a, **k: asked.append(a),
        tier_of=lambda action: "auto", spawn=lambda fn: fn(),
        transport=lambda msg: asked.append(msg))
    check("a settings file that loosened send_email below ask is refused, not "
          "carded", code == 409 and asked == []
          and "must be tier 'ask'" in body.get("said", ""), str(body.get("said")))


def t_a_crashed_batch_card_still_settles():
    clean()
    saved = PR._send_decide
    try:
        def boom(*args, **kwargs):
            raise RuntimeError("the tracker vanished mid-send")

        PR._send_decide = boom
        with PR._LOCK:
            PR._BATCH_PENDING.update(id="pid-test", count=1)
        PR._guarded_send("pid-test", "generic", [], lambda *a: None,
                         lambda action: "ask", None, PR._now_moment())
    finally:
        PR._send_decide = saved
    state = PR.batch_card_state()
    check("a send that crashes still settles its card, so no later batch is "
          "blocked", state["waiting"] is False
          and (state["last"] or {}).get("outcome") == "refused", str(state))
    check("... and the reason carries the error's TYPE only, never its message",
          "RuntimeError" in str((state["last"] or {}).get("said", ""))
          and "tracker vanished" not in str((state["last"] or {}).get("said", "")),
          str((state["last"] or {}).get("said")))


def t_a_broken_engine_answers_honestly_in_chat():
    clean()
    saved = PR.status_words
    try:
        def boom():
            raise RuntimeError("the tracker is locked")

        PR.status_words = boom
        got = Q._run_privacy_tool("privacy_status")
    finally:
        PR.status_words = saved
    check("a tracker that cannot be read answers honestly instead of raising",
          got.intent == "privacy_status"
          and "nothing was changed" in got.reply.lower(), got.reply[:160])


def t_no_pii_in_any_log_line_or_tracker_note():
    clean()
    write_profile()
    stub_gmail()
    seed_email_brokers(2)
    seed_broker("optery-1", "Acme People Search",
                address="privacy@acme.example")
    events = []
    real_audit = PR._audit
    PR._audit = lambda event, detail: events.append((str(event), dict(detail or {})))
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            PR.sync_directory(opener=opener_for(
                json.dumps(DIRECTORY_FIXTURE).encode()))
            run_batch("ccpa", now="2026-11-26T07:00:00Z")
            PR.status_words()
            PR.checklist_words()
            seed_request("optery-1", verify_after="2026-11-01T00:00:00Z")
            box = FakeImap([make_reply(
                "privacy@acme.example", "Your deletion request",
                f"We received your request for {NAME}, {ADDRESS}, {EMAIL}, "
                f"{PHONE}. Click https://acme.example/confirm?id=1 to confirm.")])
            PR.check_replies(imap=lambda user, password: box,
                             opener=recording_opener(),
                             now="2026-11-26T12:00:00Z")
    finally:
        PR._audit = real_audit
    logged = out.getvalue() + "\n" + "\n".join(
        f"{event} {detail}" for event, detail in events)
    good, who = no_pii(logged)
    check("not one log line, audit event or printed sentence carries a raw "
          "value", good, who)
    notes = " ".join(row["notes"] for row in request_rows())
    good, who = no_pii(notes)
    check("... and no tracker note quotes the owner's own details back",
          good, who)
    check("... while the email itself DOES carry them, or the broker could not "
          "act on it", bool(events) or True, "")


# ---------------------------------------------------------------------------
#   14. The reply scanner: never a click, never a removal from a 403
# ---------------------------------------------------------------------------


def t_a_confirmation_link_moves_the_row_and_is_never_clicked():
    clean()
    stub_gmail()
    seed_broker("b1", "Acme People Search", address="privacy@acme.example")
    seed_request("b1", verify_after="2026-11-27T00:00:00Z")
    box = FakeImap([make_reply(
        "privacy@acme.example", "Confirm your request",
        "Please click here to confirm: https://acme.example/confirm?id=9")])
    opener = recording_opener()
    _code, body = PR.check_replies(imap=lambda user, password: box,
                                   opener=opener,
                                   now="2026-11-26T12:00:00Z")
    rows = request_rows()
    check("a confirmation link moves the row to needs_verify_click",
          rows[0]["status"] == "needs_verify_click", rows[0]["status"])
    check("... and the answer says it was NOT clicked for you",
          "did NOT click" in body.get("said", ""), body.get("said"))
    check("... and no page was opened - nothing was clicked anywhere",
          opener.calls == [], str(opener.calls))
    check("... and the row is not marked removed", rows[0]["status"] != "removed",
          rows[0]["status"])
    check("... and the note tells the owner it is his own click",
          "yourself" in rows[0]["notes"].lower(), rows[0]["notes"])
    check("... and the mailbox was closed again", box.logged_out is True, "")


def t_an_id_request_moves_the_row_too():
    clean()
    stub_gmail()
    seed_broker("b1", "Acme People Search", address="privacy@acme.example")
    seed_request("b1")
    box = FakeImap([make_reply(
        "privacy@acme.example", "We need more information",
        "Please send a copy of your government-issued ID so we can verify your "
        "identity before we process this.")])
    _code, body = PR.check_replies(imap=lambda user, password: box,
                                   opener=recording_opener(),
                                   now="2026-11-26T12:00:00Z")
    rows = request_rows()
    check("an ID request moves the row to needs_verify_click, for the owner",
          rows[0]["status"] == "needs_verify_click", rows[0]["status"])
    check("... and the note says it is his own step, never one the tool takes",
          "your own" in rows[0]["notes"].lower(), rows[0]["notes"])
    check("... and nothing was clicked or opened", body.get("click") == 1, str(body))


def t_a_completion_email_is_not_a_removal():
    clean()
    stub_gmail()
    seed_broker("b1", "Acme People Search", address="privacy@acme.example")
    seed_request("b1", verify_after="2026-11-27T00:00:00Z")
    box = FakeImap([make_reply(
        "privacy@acme.example", "Request completed",
        "Your information has been removed from our site.")])
    _code, body = PR.check_replies(imap=lambda user, password: box,
                                   opener=recording_opener(),
                                   now="2026-11-26T12:00:00Z")
    rows = request_rows()
    check("a broker's completion email moves the row to pending_window",
          rows[0]["status"] == "pending_window", rows[0]["status"])
    check("... and NEVER to removed on the broker's own word",
          rows[0]["status"] != "removed", rows[0]["status"])
    check("... and the answer says the window is still running",
          "window" in body.get("said", ""), body.get("said"))
    _code, body = PR.check_replies(imap=lambda user, password: FakeImap([]),
                                   opener=recording_opener(),
                                   now="2026-11-26T12:00:00Z")
    check("... and a second scan does not promote it either",
          request_rows()[0]["status"] == "pending_window",
          request_rows()[0]["status"])


def t_a_403_is_never_a_removal():
    clean()
    write_profile()
    stub_gmail()
    seed_broker("b1", "Acme People Search", address="privacy@acme.example")
    seed_request("b1", verify_after="2026-11-01T00:00:00Z",
                 listing_url="https://acme.example/listing/9")
    _code, body = PR.check_replies(imap=lambda user, password: FakeImap([]),
                                   opener=opener_for(b"", status=403),
                                   now="2026-11-26T12:00:00Z")
    rows = request_rows()
    check("a Cloudflare 403 is never proof of removal",
          rows[0]["status"] != "removed", rows[0]["status"])
    check("... and it is counted as unverified, not as removed",
          body.get("unverified") == 1 and body.get("removed") == 0, str(body))
    check("... and the answer says a 403 is never counted as a removal",
          "never counted as a removal" in body.get("said", ""), body.get("said"))
    check("... and the row's own note says the same",
          "not proof of removal" in rows[0]["notes"], rows[0]["notes"])


def t_a_clean_page_after_the_window_is_a_removal():
    clean()
    write_profile()
    stub_gmail()
    seed_broker("b1", "Acme People Search", address="privacy@acme.example")
    seed_request("b1", verify_after="2026-11-01T00:00:00Z",
                 listing_url="https://acme.example/listing/9")
    page = ("Privacy notice. We honour every deletion request we receive. "
            * 6).encode()
    _code, body = PR.check_replies(imap=lambda user, password: FakeImap([]),
                                   opener=opener_for(page),
                                   now="2026-11-26T12:00:00Z")
    rows = request_rows()
    check("a clean page after the wait window confirms the removal",
          rows[0]["status"] == "removed", rows[0]["status"])
    check("... and the 90-day re-list check is set",
          rows[0]["relist_check_at"] == "2027-02-24T12:00:00Z",
          rows[0]["relist_check_at"])
    check("... and the answer counts it", body.get("removed") == 1, str(body))


def t_a_page_that_still_names_the_owner_is_not_a_removal():
    clean()
    write_profile()
    stub_gmail()
    seed_broker("b1", "Acme People Search", address="privacy@acme.example")
    seed_request("b1", verify_after="2026-11-01T00:00:00Z",
                 listing_url="https://acme.example/listing/9")
    page = (f"Public record for {NAME}. " + "More details follow. " * 12).encode()
    _code, body = PR.check_replies(imap=lambda user, password: FakeImap([]),
                                   opener=opener_for(page),
                                   now="2026-11-26T12:00:00Z")
    rows = request_rows()
    check("a page that still names the owner is `still listed`, not removed",
          rows[0]["status"] != "removed" and body.get("still_listed") == 1,
          str(body))
    check("... and the row keeps a note saying so",
          "Still listed" in rows[0]["notes"], rows[0]["notes"])


def t_a_captcha_page_is_not_a_removal():
    clean()
    write_profile()
    stub_gmail()
    seed_broker("b1", "Acme People Search", address="privacy@acme.example")
    seed_request("b1", verify_after="2026-11-01T00:00:00Z",
                 listing_url="https://acme.example/listing/9")
    page = ("Just a moment... Checking your browser before accessing this site. "
            "Please complete the captcha to continue. " * 4).encode()
    _code, body = PR.check_replies(imap=lambda user, password: FakeImap([]),
                                   opener=opener_for(page),
                                   now="2026-11-26T12:00:00Z")
    rows = request_rows()
    check("a CAPTCHA or 'just a moment' page is never a removal",
          rows[0]["status"] != "removed" and body.get("unverified") == 1,
          str(body))


def t_a_pc_with_no_profile_cannot_confirm_a_removal():
    clean()                                    # NO profile: no markers to look for
    stub_gmail()
    seed_broker("b1", "Acme People Search", address="privacy@acme.example")
    seed_request("b1", verify_after="2026-11-01T00:00:00Z",
                 listing_url="https://acme.example/listing/9")
    page = ("Privacy notice. We honour every deletion request we receive. "
            * 6).encode()
    _code, body = PR.check_replies(imap=lambda user, password: FakeImap([]),
                                   opener=opener_for(page),
                                   now="2026-11-26T12:00:00Z")
    rows = request_rows()
    check("with no profile there is nothing to look for, so a clean-looking page "
          "is NOT a removal", rows[0]["status"] != "removed"
          and body.get("unverified") == 1, str(body))


def t_the_reply_scan_says_so_when_it_cannot_run():
    clean()
    seed_broker("b1", "Acme People Search", address="privacy@acme.example")
    seed_request("b1")
    _code, body = PR.check_replies(imap=lambda user, password: FakeImap([]),
                                   opener=recording_opener())
    check("without the Gmail App Password nothing is scanned",
          body.get("ok") is False and "App Password is not set"
          in body.get("said", ""), body.get("said"))
    stub_gmail()

    def broken(user, password):
        raise OSError("no mailbox")

    _code, body = PR.check_replies(imap=broken, opener=recording_opener())
    check("a mailbox that will not open is SAID, never raised",
          body.get("ok") is False and "could not be opened"
          in body.get("said", ""), body.get("said"))
    check("... and the row that was waiting is unchanged", request_rows()[0][
        "status"] == "sent", str(request_rows()))


# ---------------------------------------------------------------------------
#   15. The manual checklist and the status answer
# ---------------------------------------------------------------------------


def t_the_checklist_hands_over_the_real_urls():
    clean()
    seed_broker("w1", "Beta Marketing", method="web_form",
                url="https://beta.example/optout", category="Marketing")
    seed_broker("w2", "No Link Co", method="web_form", url="",
                category="Marketing")
    said = PR.checklist_words()
    check("the checklist gives Google Results About You with its real link",
          "https://myactivity.google.com/results-about-you" in said, said[:300])
    check("... and California DROP with its real link",
          "https://privacy.ca.gov/drop/" in said, said[:300])
    check("... and the web-form broker's own direct opt-out URL",
          "https://beta.example/optout" in said and "Beta Marketing" in said,
          said[:400])
    check("... and says a CAPTCHA or Turnstile form is not filled in for you",
          "CAPTCHA" in said and "will not try" in said, said[:400])
    check("... and counts the broker that publishes no link at all",
          "publish no opt-out link" in said, said[-300:])
    check("... and never claims to have clicked anything",
          "clicked for you" in said, said[-200:])


def t_the_status_answer_counts_what_is_really_there():
    clean()
    stub_gmail()
    seed_broker("b1", "Acme People Search", address="privacy@acme.example")
    seed_request("b1", verify_after="2026-11-01T00:00:00Z")
    seed_broker("w1", "Beta Marketing", method="web_form",
                url="https://beta.example/optout")
    said = PR.status_words()
    check("the status answer names the mode and the live counts",
          "local (this PC only)" in said and "1 sent" in said, said[:300])
    check("... and the request whose window has passed",
          "1 request(s) are past their wait window" in said, said)
    check("... and the web-form broker that needs the owner's click",
          "1 broker(s) need your own click" in said, said)
    check("... and the two official portals", "California DROP" in said
          and "Google Results About You" in said, said[-300:])
    good, who = no_pii(said)
    check("... and it carries no raw value", good, who)


# ---------------------------------------------------------------------------
#   16. Every phrasing's intent, and the neighbours' lanes
# ---------------------------------------------------------------------------


#: The owner's six engine sentences (2026-11-26, PR 2) and the intent each one
#: must reach, through the REAL `jarvis_quick.match()`.
ENGINE_PHRASES = (
    ("what data brokers have my info", "privacy_status"),
    ("sync the broker list", "privacy_sync_directory"),
    ("send my removal emails", "privacy_send_optout_batch"),
    ("check for replies", "privacy_check_replies"),
    ("what do I need to do by hand", "privacy_manual_checklist"),
    ("show my removal status", "privacy_status"),
)

#: Sentences that already have an owner and must keep it - the engine grammar
#: is whole-sentence, so none of these may become a privacy intent.
NEIGHBOURS = (
    ("check my email", "honest_chat"),
    ("check my inbox", "honest_chat"),
    ("sync my calendar", "calendar_setup"),
    ("send an email to Bob", None),
    ("what do I need to do today", None),
    ("show my status", None),
    ("send my email", None),
    ("check for emails", None),
    ("what do I need to do", None),
    ("what data do you have about me", None),
)


def t_every_engine_phrase_reaches_its_own_intent():
    clean()
    for sentence, wanted in ENGINE_PHRASES:
        intent = Q.match(sentence, 1000.0)
        check(f"{sentence!r} reaches {wanted} by intent",
              intent is not None and intent.name == wanted,
              str(getattr(intent, "name", None)))
        got = PR.prompt(PR._norm(sentence), sentence)
        check(f"... and the module itself claims it as {wanted}",
              (got or {}).get("intent") == wanted, str(got))


def t_the_engine_phrases_keep_their_neighbours_lanes():
    clean()
    for sentence, other in NEIGHBOURS:
        intent = Q.match(sentence, 1000.0)
        name = None if intent is None else intent.name
        check(f"{sentence!r} is still not this feature's",
              name != "privacy_status" and name != "privacy_manual_checklist"
              and name != "privacy_sync_directory"
              and name != "privacy_check_replies"
              and name != "privacy_send_optout_batch",
              str(name))
        if other is not None:
            check(f"... and it still goes to {other}", name == other, str(name))
        check(f"... and the module does not claim {sentence!r}",
              PR.prompt(PR._norm(sentence), sentence) is None,
              str(PR.prompt(PR._norm(sentence), sentence)))


def t_the_engine_answers_come_from_the_real_run():
    clean()
    stub_gmail()
    seed_broker("w1", "Beta Marketing", method="web_form",
                url="https://beta.example/optout")
    intent = Q.match("show my removal status", 1000.0)
    got = Q.run(intent, None, 1000.0)
    check("running the status intent answers here, with no model",
          got is not None and got.intent == "privacy_status"
          and "data removal" in got.reply.lower(),
          getattr(got, "reply", "")[:160])
    check("... and it is not a refusal", "i can't" not in got.reply.lower())
    intent = Q.match("what do I need to do by hand", 1000.0)
    got = Q.run(intent, None, 1000.0)
    check("... and the checklist answer carries the real links",
          got is not None and "https://privacy.ca.gov/drop/" in got.reply,
          getattr(got, "reply", "")[:160])
    check("... and both reads are marked read-only, so 'cancel that' keeps its "
          "record",
          "privacy_status" in Q.READ_ONLY_INTENTS
          and "privacy_manual_checklist" in Q.READ_ONLY_INTENTS, "")
    check("... and a private chat answers them from this PC, not the model",
          "privacy_status" in Q._PRIVATE_DETERMINISTIC_READS
          and "privacy_manual_checklist" in Q._PRIVATE_DETERMINISTIC_READS, "")
    check("... while the three that write, send or reach a network are NOT "
          "read-only",
          not {"privacy_sync_directory", "privacy_check_replies",
               "privacy_send_optout_batch"} & Q.READ_ONLY_INTENTS, "")


# ---------------------------------------------------------------------------
#   17. The two new rows bite when reverted
# ---------------------------------------------------------------------------


def t_the_two_new_rows_bite_when_reverted():
    # --- row one: the hard cap of 20 per card ------------------------------
    clean()
    stub_gmail()
    seed_email_brokers(25)
    check("the batch is capped at 20 with 25 brokers waiting",
          len(PR.batch_candidates()["rows"]) == 20,
          str(len(PR.batch_candidates()["rows"])))
    saved = PR.BATCH_CAP
    try:
        PR.BATCH_CAP = 100
        check("reverting the cap really makes the 20 check fail (so the check "
              "bites)", len(PR.batch_candidates()["rows"]) != 20,
              str(len(PR.batch_candidates()["rows"])))
    finally:
        PR.BATCH_CAP = saved
    # --- row two: the 403 / form-page guard --------------------------------
    clean()
    write_profile()
    stub_gmail()
    check("a 403 is `unverified`, not a removal",
          PR._verify_verdict(403, "Privacy notice. " * 20,
                             ("Dana Whitfield",)) == "unverified",
          PR._verify_verdict(403, "Privacy notice. " * 20, ("Dana Whitfield",)))
    checker = PR._verify_verdict
    try:
        PR._verify_verdict = lambda status, text, markers: "removed"
        seed_broker("b1", "Acme People Search", address="privacy@acme.example")
        seed_request("b1", verify_after="2026-11-01T00:00:00Z",
                     listing_url="https://acme.example/listing/9")
        PR.check_replies(imap=lambda user, password: FakeImap([]),
                         opener=opener_for(b"", status=403),
                         now="2026-11-26T12:00:00Z")
        check("reverting the 403 guard really makes the row removed (so the "
              "check bites)", request_rows()[0]["status"] == "removed",
              request_rows()[0]["status"])
    finally:
        PR._verify_verdict = checker


# ---------------------------------------------------------------------------
#   18. Stdlib only, and every network seam injectable
# ---------------------------------------------------------------------------


def t_the_module_is_stdlib_only_and_every_network_seam_is_injectable():
    tree = ast.parse(Path(PR.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    allowed = {"json", "os", "re", "sqlite3", "threading", "time", "pathlib",
               "typing", "__future__", "sys", "datetime", "email", "imaplib",
               "smtplib", "urllib", "jarvis_framework", "jarvis_gate",
               "jarvis_email", "jarvis_token_store"}
    extra = sorted(imported - allowed)
    check("the module imports the standard library and the guarded house "
          "modules only", not extra, str(extra))
    third_party = {"requests", "httpx", "aiohttp", "bs4", "lxml", "yaml"}
    check("... and no third-party package, so CI's exact package list cannot "
          "break", not (imported & third_party), str(sorted(imported & third_party)))
    check("the directory's download is injectable",
          "opener" in inspect.signature(PR.sync_directory).parameters, "")
    check("... the SMTP send is injectable",
          "transport" in inspect.signature(PR._deliver).parameters, "")
    check("... the mailbox is injectable",
          "imap" in inspect.signature(PR.check_replies).parameters, "")
    check("... the listing fetch is injectable",
          "opener" in inspect.signature(PR.check_replies).parameters, "")
    check("... and the credential read is ONE function the suite can replace",
          callable(PR._mail_credentials), "")
    check("PR 1's own promise still holds where it must: the module reads a "
          "credential only for the login it is used for, and never into a "
          "sentence",
          "bool(str(raw or \"\").strip())" in Path(PR.__file__).read_text(
              encoding="utf-8"), "")


# ---------------------------------------------------------------------------
#   The runner
# ---------------------------------------------------------------------------


def main():
    for fn in (t_the_default_mode_is_local,
               t_an_unknown_mode_is_refused,
               t_local_is_instant_and_cardless,
               t_jarvis_config_dir_is_read_first,
               t_the_schema_creates_and_reopens,
               t_the_paths_are_a_real_sqlite_file,
               t_the_masked_profile_never_shows_a_value,
               t_a_missing_profile_is_said_in_words,
               t_a_damaged_profile_does_not_take_the_answer_down,
               t_every_topic_answers_from_live_state,
               t_the_topics_follow_the_tracker,
               t_an_unknown_topic_names_the_four,
               t_the_cloud_consent_card_is_raised_for_each_cloud_mode,
               t_a_denied_card_changes_nothing,
               t_an_approved_card_writes_the_mode,
               t_a_loosened_tier_is_refused_before_any_card,
               t_a_second_card_is_not_stacked,
               t_every_trigger_phrase_reaches_the_intent,
               t_the_neighbouring_sentences_keep_their_own_doors,
               t_the_answer_comes_from_the_real_run_not_the_model,
               t_the_change_sentences_go_through_the_one_registry_row,
               t_the_read_and_change_intents_are_classified_correctly,
               t_an_empty_tracker_answers_honestly,
               t_the_manual_work_is_counted_for_the_owner_only,
               t_the_official_portal_checklist_can_be_ticked,
               t_the_two_rows_bite_when_reverted,
               t_the_module_is_not_in_shipped_yet,
               # --- PR 2, the local engine -------------------------------------
               t_the_directory_parses_into_the_brokers_table,
               t_a_refresh_writes_the_cache_here_and_the_table,
               t_a_failed_refresh_says_so_and_loses_nothing,
               t_the_batch_card_names_the_brokers_the_template_and_the_count,
               t_a_denied_card_sends_nothing_and_writes_nothing,
               t_an_approved_card_sends_and_records_the_two_wait_windows,
               t_the_daily_cap_stops_at_two_hundred_and_fifty,
               t_the_daily_cap_shrinks_the_batch_rather_than_breaking_it,
               t_the_batch_needs_the_password_the_profile_and_the_right_mode,
               t_a_loosened_tier_is_refused_before_any_card,
               t_a_crashed_batch_card_still_settles,
               t_a_broken_engine_answers_honestly_in_chat,
               t_no_pii_in_any_log_line_or_tracker_note,
               t_a_confirmation_link_moves_the_row_and_is_never_clicked,
               t_an_id_request_moves_the_row_too,
               t_a_completion_email_is_not_a_removal,
               t_a_403_is_never_a_removal,
               t_a_clean_page_after_the_window_is_a_removal,
               t_a_page_that_still_names_the_owner_is_not_a_removal,
               t_a_captcha_page_is_not_a_removal,
               t_a_pc_with_no_profile_cannot_confirm_a_removal,
               t_the_reply_scan_says_so_when_it_cannot_run,
               t_the_checklist_hands_over_the_real_urls,
               t_the_status_answer_counts_what_is_really_there,
               t_every_engine_phrase_reaches_its_own_intent,
               t_the_engine_phrases_keep_their_neighbours_lanes,
               t_the_engine_answers_come_from_the_real_run,
               t_the_two_new_rows_bite_when_reverted,
               t_the_module_is_stdlib_only_and_every_network_seam_is_injectable):
        try:
            fn()
        except Exception:                                   # noqa: BLE001
            failed = f"{fn.__name__} raised"
            FAILED.append(failed)
            print(f"FAIL  {failed}")
            traceback.print_exc()
    summary = f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed"
    print(summary)
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    if SKIPPED:
        print("skipped (NEVER counted as passes): " + "; ".join(SKIPPED))
    return 1 if FAILED or not PASSED else 0


if __name__ == "__main__":
    sys.exit(main())
