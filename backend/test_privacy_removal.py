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
11. NO EMAIL AND NO NETWORK. The module's own source is read: it imports
   nothing outside the standard library and calls no `urllib`, `socket`,
   `http` or `smtplib` function in this slice.

A SKIP IS NEVER A PASS here: `skip()` counts on its own line and is printed as
SKIPPED, and the run fails if every check skipped.
"""
from __future__ import annotations

import ast
import json
import os
import re
import sqlite3
import sys
import tempfile
import traceback
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
    """An empty temporary folder: no mode file, no profile, no tracker."""
    for path in (PR.mode_path(), PR.profile_path(), PR.tracker_path()):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    PR._reset_for_tests()
    PR.gmail_state = lambda: {"address": False, "password": False, "ready": False}
    PR.optery_state = lambda: {"set": False, "env": PR.OPTERY_ENV}


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
#   11. Stdlib only, and no network at all in this slice
# ---------------------------------------------------------------------------


def t_no_email_and_no_network_in_this_slice():
    src = Path(PR.__file__).read_text(encoding="utf-8")
    imports = set(re.findall(r"^\s*(?:import|from)\s+([a-zA-Z_][\w.]*)", src, re.M))
    allowed = {"json", "os", "re", "sqlite3", "threading", "time", "pathlib",
               "typing", "__future__", "sys", "jarvis_framework", "jarvis_gate",
               "jarvis_email", "jarvis_token_store"}
    extra = sorted(imports - allowed)
    check("the module imports the standard library only, and only these guarded "
          "house modules", not extra, str(extra))
    banned = [word for word in ("urllib", "smtplib", "imaplib", "http.client",
                                "socket", "requests")
              if re.search(rf"^\s*(?:import|from)\s+{re.escape(word)}", src, re.M)]
    check("... and nothing that could reach the network in this slice",
          not banned, str(banned))
    check("... so PR 1 sends no email and calls no API",
          "no email is ever sent" in src.lower())
    check("... and no credential value is ever read into a sentence: the two "
          "readers return booleans only",
          '"ready": False' in src and "bool(str(raw or \"\").strip())" in src)


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
               t_no_email_and_no_network_in_this_slice):
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
