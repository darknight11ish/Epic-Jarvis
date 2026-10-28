"""test_calendar_answer.py - "can you connect to my calendar?" gets the real
steps, not "Jarvis cannot connect ... without a bridge".

    python3 backend/test_calendar_answer.py

WHY THIS EXISTS. On 2026-10-28 the owner asked, in the HUD chat:

    "can you connect directly to external calendars like google or outlook?"

and Jarvis answered that it *"cannot connect directly ... without you manually
granting permissions and setting up a bridge"*, then offered to explain
exporting the calendar to an ICS file. On "set up a calendar bridge for me" it
refused again. Every sentence of that is wrong about this PC, and wrong in the
direction that hides a built feature:

  * `jarvis_calendar.py` really reads Google Calendar through its private iCal
    link, and any CalDAV calendar - read-only, no OAuth, no bridge (its own
    docstring says so). The link is typed in Settings, Accounts and kept in
    Windows Credential Manager; the model is offered a `calendar_read` tool.
  * What was missing was any fast-path sentence for the words the owner used:
    16 of 16 phrasings returned None from `match()` (the probe is in
    `.dsh-scratch/CALENDAR-CHAT-2026-10-28/`), so the 8B model answered, and
    its system prompt says nothing about a calendar at all.

So `jarvis_quick.py` now answers instead - `quick: "calendar_setup"`, no model,
no connection, no card - and this suite holds it to the truth:

  1. the owner's exact sentence and close phrasings are answered without the
     model, and both of his 2026-10-28 sentences are;
  2. near misses keep their own answer - a reminder is still a reminder, "open
     my calendar" still opens it, a plain "what's on my calendar today" still
     goes to the model (unchanged), and one more condition still falls through;
  3. every step it names is real: the Accounts card's section id, the
     Credential Manager entry's name, the Google path `jarvis_calendar`'s own
     docstring documents, the reading-tool sentence's own grammar, and the
     shipped `enable_reading_tool` tier;
  4. a calendar that IS set up is named from the reader's own words, and the
     private link itself is never in the answer;
  5. it changes nothing: read-only, no card, no scheduler write, and the only
     action is the cardless Settings jump to the Accounts card.

No network, no model, no calendar read.
"""
from __future__ import annotations

import inspect
import os
import sys
import tempfile
import tomllib
import traceback
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-calendar-answer-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
(_TMP / "config").mkdir(parents=True, exist_ok=True)

#: A machine that already has a calendar configured must still run this suite:
#: the "not set up" checks are the default, and the "already set up" branch is
#: exercised explicitly below with a fake link and a fake address.
for _var in ("JARVIS_CALENDAR_ICS_SECRET_URL", "JARVIS_CALDAV_URL",
             "JARVIS_CALDAV_USER", "JARVIS_CALDAV_PASSWORD"):
    os.environ.pop(_var, None)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py", "jarvis_calendar.py", "jarvis_accounts.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_quick as Q  # noqa: E402
import jarvis_calendar as CAL  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402

PASSED, FAILED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


class _Sched:
    """The fast path asks the scheduler two things: note that a command was
    understood, and (for anything not read-only) forget what "cancel that"
    would take back. Both are spies here - nothing is written."""

    def __init__(self):
        self.commands = []
        self.forgotten = []

    def mark_command(self, text):
        self.commands.append(text)

    def note_set(self, *a, **k):
        pass

    def forget_set(self, conversation):
        self.forgotten.append(conversation)


OWNER_SAID = "can you connect directly to external calendars like google or outlook?"
OWNER_SAID_2 = "set up a calendar bridge for me"

#: The model's answer in the screenshot, which this fix exists to replace. Only
#: the false claims are quoted - "bridge" itself is in the honest answer too
#: ("there is no bridge to set up"), so the test looks for the refusal shapes.
BAD_CLAIMS = (
    "cannot connect", "can't connect", "unable to connect",
    "not able to connect", "without you manually granting",
    "set up a bridge", "would you like instructions", "exporting your calendar",
    "I cannot access", "I do not have access",
)

#: Steps the answer must name, each tied to the real thing in the next test.
WANTED = (
    "read-only",
    "Settings, Accounts",
    "Calendar iCal link",
    "Integrate calendar",
    "Secret address in iCal format",
)

#: What it must never say: nothing was connected, and no link was taken.
FORBIDDEN = (
    "I have connected", "I connected", "I've connected", "Done",
    "I have set it up", "synced", "I signed in", "I have signed in",
)


def _answer(text=OWNER_SAID_2):
    return Q.answer(text, sched=_Sched())


def t_the_owners_two_sentences_are_answered_without_the_model():
    for said in (OWNER_SAID, OWNER_SAID_2):
        i = Q.match(said)
        check(f"{said!r} is the fast path's own answer",
              i is not None and i.name == "calendar_setup", i)
        r = Q.answer(said, sched=_Sched(), conversation="c-calendar")
        check("... and it is answered here, not by the model", r is not None, r)
        if r is None:
            continue
        check("... with the route naming this answer", r.intent == "calendar_setup", r.intent)
        for want in WANTED:
            check(f"... it says {want!r}", want in r.reply)
        for bad in BAD_CLAIMS:
            check(f"... it does not repeat the model's claim {bad!r}", bad not in r.reply)
        for bad in FORBIDDEN:
            check(f"... it does not say {bad!r}", bad not in r.reply)
        check("... it is one short answer, not a page", len(r.reply) <= 900,
              f"{len(r.reply)} characters")


def t_close_phrasings():
    said = (
        "can you connect to my google calendar?",
        "connect my calendar",
        "set up my calendar",
        "set up my calendar please",
        "add my google calendar",
        "link my outlook calendar",
        "hook up my calendar to jarvis",
        "sync my calendar with jarvis",
        "import my ics file into jarvis",
        "how do I connect my calendar",
        "how do I set up a calendar connection",
        "can you set up a calendar connection",
        "give jarvis access to my calendar",
        "connect a calendar",
        "calendar setup",
        "is my calendar connected?",
    )
    for s in said:
        i = Q.match(s)
        check(f"{s!r} is answered without the model",
              i is not None and i.name == "calendar_setup", i)


def t_near_misses_keep_their_own_answer():
    # (sentence, the intent it must not become)
    misses = (
        ("open my calendar", "calendar_setup"),
        ("remind me to connect my calendar at 5pm", "calendar_setup"),
        ("remind me to set up my calendar at 5pm", "calendar_setup"),
        ("set up a reminder for my calendar appointment", "calendar_setup"),
        ("add a calendar event at 5pm", "calendar_setup"),
        ("delete my calendar", "calendar_setup"),
        ("what's on my calendar today", "calendar_setup"),
        ("what's on my calendar this week", "calendar_setup"),
        ("how do I set up my calendar", "calendar_setup"),
        ("set up my calendar tomorrow at 5", "calendar_setup"),
        ("add my calendar to my phone", "calendar_setup"),
    )
    for s, not_this in misses:
        i = Q.match(s)
        check(f"{s!r} is not this answer", i is None or i.name != not_this, i)
    check("'open my calendar' still opens it in the app",
          getattr(Q.match("open my calendar"), "name", None) == "open_app")
    check("a reminder that mentions a calendar is still a reminder",
          getattr(Q.match("remind me to set up my calendar at 5pm"), "name", None)
          == "reminder_set")
    # The reading question is deliberately NOT claimed by this answer: it goes
    # to the model, exactly as before this fix, and this suite does not pretend
    # otherwise.
    check("a plain 'what's on my calendar today' is still the model's",
          Q.match("what's on my calendar today") is None)


def t_the_test_would_have_caught_the_old_answer():
    """The pre-fix tree had no matcher: with this one disabled, the owner's
    sentence produces no intent and reaches the model - the defect itself."""
    old = Q._calendar_setup
    Q._calendar_setup = lambda s: None
    try:
        check("with this answer disabled the owner's sentence reaches the model",
              Q.match(OWNER_SAID) is None)
        check("... and so does the second one", Q.match(OWNER_SAID_2) is None)
    finally:
        Q._calendar_setup = old


def t_every_step_the_answer_names_is_real():
    # 1. The box it sends the owner to is a real Settings card, by the id both
    #    apps' own Settings screens use.
    section = R.section_by_id("account-secrets")
    check("jarvis_settings_registry has the Accounts card", section is not None, section)
    check("... its id is the one the answer opens",
          section is not None and Q._run_calendar_setup(Q.Intent("calendar_setup")).open_settings
          == section.id)
    check("... and the owner's word 'accounts' is one of its names",
          section is not None and "accounts" in section.names, section and section.names)

    # 2. The box's name is the Credential Manager entry the reader really reads.
    entry = CAL.ICS_URL_TARGET.split("/")[-1]
    check("the calendar link's Credential Manager entry is 'Calendar iCal link'",
          entry == "Calendar iCal link", CAL.ICS_URL_TARGET)
    check("... and the answer names that same box", entry in Q.CALENDAR_SETUP_WORDS)

    # 3. The Google steps are the reader's own documented ones, not invented.
    doc = inspect.getdoc(CAL) or ""
    for want in ("Secret address in iCal format", "Integrate calendar"):
        check(f"jarvis_calendar's own docstring says {want!r}", want in doc)
        check(f"... and so does the answer", want in Q.CALENDAR_SETUP_WORDS)
    check("the reader really takes an iCal link",
          CAL.ICS_URL_ENV == "JARVIS_CALENDAR_ICS_SECRET_URL", CAL.ICS_URL_ENV)
    check("... and a CalDAV address, stored by jarvis_accounts",
          R is not None and "caldav_url" in __import__("jarvis_accounts").FIELDS)

    # 4. The one sentence the answer tells the owner to say is one this module
    #    really understands - and it asks for the calendar tool, with a card.
    said = "let the AI model read my calendar"
    i = Q.match(said)
    check(f"{said!r} really is the reading-tool switch",
          i is not None and i.name == "settings_tool"
          and i.f == {"tool": "calendar_read", "on": True}, i)
    check("... and the answer quotes it word for word", said in Q.CALENDAR_TOOL_STEP)

    # 5. "One card" is the shipped tier, not a promise made up here - and the
    #    tool really is not offered today, which is why the sentence is needed.
    with open(HERE / "rebuilt" / "jarvis-framework.toml", "rb") as fh:
        cfg = tomllib.load(fh)
    check("the shipped jarvis-framework.toml asks on a card for that action",
          cfg["autonomy"]["tiers"].get("enable_reading_tool") == "ask",
          cfg["autonomy"]["tiers"].get("enable_reading_tool"))
    check("... and the answer says one card", "one card" in Q.CALENDAR_TOOL_STEP)
    check("the shipped [tools].enabled list does not offer calendar_read",
          "calendar_read" not in (cfg.get("tools") or {}).get("enabled", []),
          (cfg.get("tools") or {}).get("enabled"))

    # 6. The desktop's own Accounts card names the same label and the same
    #    Google path. Skipped (never passed) where that tree is not present.
    acc = HERE.parent / "jarvis-desktop" / "src" / "account-secrets.js"
    if acc.is_file():
        text = acc.read_text(encoding="utf-8")
        check("the Accounts card's label is the one the answer names",
              f'"{entry}"' in text)
        check("... and its help line documents the same Google path",
              "Integrate calendar" in text and "Secret address in iCal format" in text)
    else:
        skip("jarvis-desktop/src/account-secrets.js is not in this tree")

    # 7. The briefing really reads the calendar without the tool switch, which
    #    is what the answer says when the tool is off.
    brief = HERE / "jarvis_briefing.py"
    if brief.is_file():
        btext = brief.read_text(encoding="utf-8")
        check("jarvis_briefing reads the calendar itself", "jarvis_calendar" in btext)
    else:
        skip("jarvis_briefing.py is not in this tree")


def t_already_set_up_names_the_source_and_never_the_link():
    check("no calendar is set up in this test's own environment",
          CAL.source() == "", CAL.source())
    link = ("https://calendar.google.com/calendar/ical/owner%40example.com/"
            "private-6f1c9a2b4d/basic.ics")
    try:
        os.environ["JARVIS_CALENDAR_ICS_SECRET_URL"] = link
        r = _answer("set up my calendar")
        check("a set-up calendar is answered as already set up", r is not None)
        if r is None:
            return
        check("... named from the reader's own words",
              "your Google Calendar (private link)" in r.reply, r.reply)
        check("... the link itself never appears", link not in r.reply
              and "private-6f1c9a2b4d" not in r.reply, r.reply)
        check("... and it does not send the owner to set it up again",
              "1. In Google Calendar" not in r.reply)
        check("... nor open the Accounts card", r.open_settings is None, r.open_settings)
    finally:
        os.environ.pop("JARVIS_CALENDAR_ICS_SECRET_URL", None)

    try:
        os.environ["JARVIS_CALDAV_URL"] = "https://cloud.example.com/remote.php/dav/calendars/o/p/"
        r = _answer("set up my calendar")
        check("a CalDAV address is answered as already set up",
              r is not None and "over CalDAV" in r.reply, r and r.reply)
        check("... with no address in the answer",
              r is not None and "cloud.example.com" not in r.reply)
        check("... and says a username is missing, because none is set",
              r is not None and "no CalDAV username" in r.reply, r and r.reply)
    finally:
        os.environ.pop("JARVIS_CALDAV_URL", None)


def t_it_changes_nothing_and_opens_only_the_accounts_card():
    check("the answer is in READ_ONLY_INTENTS", "calendar_setup" in Q.READ_ONLY_INTENTS)
    sched = _Sched()
    r = Q.answer(OWNER_SAID_2, sched=sched, conversation="c-calendar")
    check("... answering it runs", r is not None)
    check("... it does not clear what 'cancel that' would take back",
          sched.forgotten == [], sched.forgotten)
    check("... it opens no card and reads no facts",
          r is not None and not r.made and not r.facts, r and (r.made, r.facts))
    check("... the only action is the cardless jump to the Accounts card",
          r is not None and r.open_settings == "account-secrets", r and r.open_settings)

    # The same words typed into a chat arrive through answer_turn; pasted text
    # is not the owner's own words and still goes to the model (JARVIS-API
    # section 156), exactly like every other fixed answer.
    typed = {"messages": [{"role": "user", "content": OWNER_SAID_2, "provenance": "typed"}],
             "conversation_id": "c-calendar"}
    got = Q.answer_turn(typed, sched=_Sched())
    check("... typed into a chat: answered here too",
          getattr(got, "intent", None) == "calendar_setup", got)
    pasted = {"messages": [{"role": "user", "content": OWNER_SAID_2, "provenance": "pasted"}],
              "conversation_id": "c-calendar"}
    check("... but pasted text goes to the model",
          Q.answer_turn(pasted, sched=_Sched()) is None)


def main():
    for fn in (t_the_owners_two_sentences_are_answered_without_the_model,
               t_close_phrasings,
               t_near_misses_keep_their_own_answer,
               t_the_test_would_have_caught_the_old_answer,
               t_every_step_the_answer_names_is_real,
               t_already_set_up_names_the_source_and_never_the_link,
               t_it_changes_nothing_and_opens_only_the_accounts_card):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
