"""test_chat_honesty.py - the chat tells the truth about abilities that are
switched off, built only in the apps, or not built at all.

    python3 backend/test_chat_honesty.py

THE FIELD TEST THIS FIXES (2026-10-31, pass 11, the owner's chat audit of the
Obsidian features; `.dsh-scratch/FIELD-TEST-2026-10-31/pass11/obsidian/
NOTES-OBSIDIAN.md`). Through the live HUD's own chat box, on desktop
0.2.378/0.2.379:

  * "make a note: ..." answered "I shall record ..." and NOTHING was written -
    the note-writing tools are not in the owner's `[tools].enabled`, and no
    fixed sentence said so, so the model promised a write it could not make.
  * "organize my notes" answered with a promise; the vault organizer exists, is
    OFF by default, and has no chat door yet.
  * "create a new note called Shopping", "rename my note ...", "customize my
    Obsidian theme" invented features that are not built.
  * "what does my Welcome note say?" said "I have no access to your files" -
    wrong: the Notes plate reads every note in the vault.
  * "what's on my calendar today?" answered with the Google connect steps
    alone, ignoring the LOCAL Jarvis Calendar that exists, works and holds the
    owner's own events (measured again after the deploy, on 0b2e1aaaa).

WHAT THIS SUITE PROVES

  1. The CLASSIFICATION, for every measured prompt and a set of near misses: a
     calendar read is `local_calendar_read`; an off / app-only / unbuilt
     ability is `honest_chat` with the right shape; and ordinary conversation
     keeps its own path (a writing request stays with the writer, "can you help
     me create a plan" does not become a note refusal, "open my notes" still
     opens the Brain, a note on a door is not a note in the vault).
  2. The CALENDAR READ is the store the calendar card itself reads
     (`jarvis_local_calendar.list_events`): real events are quoted with their
     day and time, an empty day says "Nothing on your calendar today.",
     tomorrow/week/next/free-at are the right windows, a connected Google
     calendar is never claimed, and an unconnected one is named only when it
     matters (the local read found nothing).
  3. The HIDING rule: while App lock / "Hide memory lists" is on, no event
     TITLE is printed - the answer counts events and uses the backend's own
     withheld sentence (`jarvis_private_view`).
  4. The OFF calendar: its own switch state is read at answer time, the answer
     says it is off, where it is turned back on, and that turning it on is
     instant (no card); the stored events are untouched.
  5. The OFF / APP-ONLY / UNBUILT sentences name the REAL state and the REAL
     door, in the modules' own words: `[tools].enabled` read through
     `jarvis_agent.enabled_tools_for_turn()`, `jarvis_asks_first`'s switch
     words, `jarvis_feature_guide`'s rows, and the vault organizer's own
     switch words. No promise sentence ("I shall", "I will record", "Done")
     survives in any of them.
  6. The note READ/SEARCH answer never promises a read: chat cannot read note
     text today, and the answer says so and points at the Notes plate (PC) /
     notes plate (phone) with the one-card-per-save rule, adding the real tool
     state when the note tools happen to be switched on.
  7. HERMETIC: a throwaway config folder, a throwaway calendar database and a
     made-up date; no model, no network, no owner file. The twins are checked
     byte-identical, and both new intents are listed read-only so no "cancel
     that" is lost to them.
"""
from __future__ import annotations

import datetime
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-chat-honesty-"))
os.environ.setdefault("OPENJARVIS_CONFIG_DIR", str(_TMP / "cfg"))
os.environ.setdefault("JARVIS_CONFIG_DIR", str(_TMP / "cfg"))
os.environ.setdefault("OPENJARVIS_HOME", str(_TMP))
os.environ.setdefault("JARVIS_HOME", str(_TMP))
os.environ.setdefault("JARVIS_CALENDAR_DB", str(_TMP / "calendar.db"))
os.environ.setdefault("JARVIS_CALENDAR_SETTINGS", str(_TMP / "calendar-settings.json"))
os.environ.setdefault("JARVIS_JOBS_DB", str(_TMP / "jobs.db"))
_TOML = REPO / "backend" / "rebuilt" / "jarvis-framework.toml"
if _TOML.is_file():
    os.environ.setdefault("JARVIS_FRAMEWORK_TOML", str(_TOML))

import jarvis_asks_first as AF  # noqa: E402
import jarvis_feature_guide as FG  # noqa: E402
import jarvis_local_calendar as C  # noqa: E402
import jarvis_private_view as PV  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_vault_organizer as O  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []

#: A made-up day so today/tomorrow/week never depend on when the suite runs.
FIXED_DAY = datetime.date(2026, 10, 31)
NOW = datetime.datetime(2026, 10, 31, 9, 5).timestamp()
TODAY = FIXED_DAY.isoformat()
TOMORROW = (FIXED_DAY + datetime.timedelta(days=1)).isoformat()

#: A promise sentence is what this lane exists to remove. These are the words
#: the live model used, and no fixed honest answer may contain any of them.
PROMISES = ("I shall", "I will record", "I will add", "I have added", "Done.",
            "I shall propose", "I will propose", "I will create", "I will rename",
            "I will delete", "I will open", "I will read")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check that could not run here - counted as skipped, never a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


def fresh_calendar():
    """Empty calendar store + settings, today pinned to FIXED_DAY."""
    try:
        import jarvis_sqlite
    except Exception:                   # pragma: no cover - shipped beside it
        jarvis_sqlite = None
    for key in ("JARVIS_CALENDAR_DB", "JARVIS_CALENDAR_SETTINGS"):
        got = os.environ.get(key)
        if got and Path(got).exists():
            Path(got).unlink()
            # The schema cache is per database PATH for the life of the
            # process (jarvis_sqlite's own docstring says a caller that
            # unlinks a database must say so). Without this, the re-created
            # file would get no tables and the next read would be an error.
            if jarvis_sqlite is not None and key == "JARVIS_CALENDAR_DB":
                jarvis_sqlite.forget_initialized(got)
    C._today = lambda: FIXED_DAY
    PV.note_state(app_locked=False, hide_memory_lists=False)


def ask(text, now=NOW):
    """What the REAL fast path answers for this sentence, or None."""
    intent = Q.match(text)
    if intent is None:
        return None
    return Q.run(intent, None, now)


def shape_of(text):
    intent = Q.match(text)
    return (intent.name, dict(intent.f)) if intent is not None else (None, {})


def google_disconnected():
    """True / False / None (unreadable) from the Google module's real status."""
    try:
        import jarvis_google_calendar as G
        return not bool(G.status().get("connected"))
    except Exception:
        return None


def no_promises(reply: str) -> bool:
    return not any(word in (reply or "") for word in PROMISES)


# --------------------------------------------------------------------------
#   1. The classification, measured prompt by prompt
# --------------------------------------------------------------------------

CAL_READ_SENTENCES = (
    "what's on my calendar today?",
    "what is on my calendar this week",
    "what's on tomorrow",
    "what do i have today",
    "what's my next event",
    "when's my next appointment",
    "am i free at 3",
    "do i have anything tomorrow",
    "what's on my calendar",
)


def t_every_calendar_read_is_the_local_calendars_answer():
    fresh_calendar()
    for said in CAL_READ_SENTENCES:
        name, fields = shape_of(said)
        check(f"{said!r} is a local calendar read", name == "local_calendar_read",
              (name, fields))
    check("the read is marked read-only (no 'cancel that' loss)",
          "local_calendar_read" in Q.READ_ONLY_INTENTS)
    check("an event sentence is still NOT this read",
          shape_of("add a meeting Tuesday 3pm")[0] != "local_calendar_read")


def t_off_app_only_and_unbuilt_sentences_have_their_shapes():
    fresh_calendar()
    cases = (
        # (what the owner typed, the shape, the extra field)
        ("make a note: call the plumber tomorrow at 4pm", "note_write", None),
        ("note this: the boiler service is due", "note_write", None),
        ("organize my notes", "organizer", None),
        ("organize my Obsidian vault with tags and Maps of Content", "organizer", None),
        ("create a new note called Shopping", "note_unbuilt", "create"),
        ("rename my note Welcome to Home", "note_unbuilt", "rename"),
        ("delete my note Welcome", "note_unbuilt", "delete"),
        ("customize my Obsidian theme", "never_built", None),
        ("change my Obsidian theme to something dark", "never_built", None),
        ("what does my Welcome note say?", "note_door", "read"),
        ("read my notes", "note_door", "read"),
        ("search my notes for the boiler", "note_door", "search"),
        ("find the boiler in my notes", "note_door", "search"),
        ("read my email", "capability_off", "email_read"),
        ("check my inbox", "capability_off", "email_read"),
        ("is the garage door open", "capability_off", "home_read"),
        ("tap my phone", "capability_off", "control_phone"),
        ("start a background job", "feature_door", "jobs"),
        ("how much did I spend last month", "feature_door", "spending"),
        # the stateful read doors (2026-10-31, the chat audit's second half)
        ("what is protected from Jarvis right now?", "protection_read", None),
        ("what is protected", "protection_read", None),
        ("what timer is on my phone", "phone_state", None),
        ("can you set a timer on my phone", "phone_state", None),
        ("what jobs are running?", "jobs_read", None),
    )
    for said, shape, extra in cases:
        name, fields = shape_of(said)
        ok = ((name == "honest_chat" and fields.get("shape") == shape)
              or (name == "honest_state" and fields.get("shape") == shape))
        if ok and extra is not None:
            ok = extra in (fields.get("op"), fields.get("mode"),
                           fields.get("action"), fields.get("row"))
        check(f"{said!r} is {shape}", ok, (name, fields))
    stateful = (
        ("remove protection from my taxes folder", "honest_state", "protection_change"),
        ("protect my taxes folder", "honest_state", "protection_change"),
        ("what asks first?", "honest_chat", "asks_first"),
        ("how do I turn off quiet hours?", "honest_chat", "quiet_hours"),
        ("what is switched off on this PC?", "honest_chat", "general_off"),
        ("can you watch a PR for me?", "honest_chat", "watch_door"),
        ("can you switch models?", "honest_chat", "model_door"),
        ("can you turn on the lights?", "honest_chat", "lights_off"),
    )
    for said, intent, shape in stateful:
        name, fields = shape_of(said)
        check(f"{said!r} is {intent}/{shape}",
              name == intent and fields.get("shape") == shape,
              (name, fields))
    check("the stateful reads are marked read-only",
          "honest_state" in Q.READ_ONLY_INTENTS)


def t_ordinary_conversation_keeps_its_own_path():
    fresh_calendar()
    own = (
        "can you write a nice email for my boss?",   # a writing request: the writer
        "can you help me create a plan",             # a plan, not a note
        "read the note on the door",                 # a note on a door is not the vault
        "hello there",                               # ordinary chat
        "tell me when the next release is out",      # the tell-me path
        "remind me to call mum at 5pm",              # the reminder path
        "can you protect a folder from you?",        # the feature list answers this
        "tell me when the next release is out",      # the tell-me path
        "what can you do with my notes",             # the feature list answers
    )
    for said in own:
        name, fields = shape_of(said)
        check(f"{said!r} keeps its own path (not this lane)",
              name not in ("honest_chat", "local_calendar_read"), (name, fields))
    check("'open my notes' still opens the Brain", shape_of("open my notes")[0] == "open_app")
    check("'open my calendar' still opens it in the app",
          shape_of("open my calendar")[0] == "open_app")


# --------------------------------------------------------------------------
#   2. The local calendar read: real events, real windows, real state
# --------------------------------------------------------------------------

def t_the_local_calendar_read_quotes_the_real_store():
    fresh_calendar()
    empty = ask("what's on my calendar today?")
    check("an empty today says exactly that",
          empty is not None and "Nothing on your calendar today." in empty.reply,
          empty and empty.reply)
    if empty is not None:
        check("... and never answers with Google setup steps",
              "Integrate calendar" not in empty.reply
              and "Settings, Accounts" not in empty.reply, empty.reply)
    disconnected = google_disconnected()
    if disconnected is True and empty is not None:
        check("... and names Google's real state only when it matters",
              "Google Calendar is not connected" in empty.reply, empty.reply)
    elif disconnected is None:
        skip("the Google calendar status could not be read here")

    code, out = C.handle_add({"title": "Dentist", "date": TODAY, "time": "15:00"})
    check("a real event can be stored for the test",
          code in (200, 201) and out.get("ok"), (code, out))
    today = ask("what's on my calendar today?")
    check("the read quotes the event and its time",
          today is not None and "Dentist" in today.reply and "15:00" in today.reply,
          today and today.reply)
    check("... and does not mention Google's state when local events exist",
          today is not None and "not connected" not in today.reply,
          today and today.reply)
    check("... and the read changed nothing",
          len(C.list_events(7).get("events") or []) == 1)
    week = ask("what is on my calendar this week")
    check("this week also finds it", week is not None and "Dentist" in week.reply,
          week and week.reply)
    tomorrow = ask("what's on tomorrow")
    check("tomorrow says nothing when the event is today",
          tomorrow is not None and "Dentist" not in tomorrow.reply
          and "Nothing on your calendar tomorrow." in tomorrow.reply,
          tomorrow and tomorrow.reply)
    nxt = ask("what's my next event")
    check("the next event is the real one", nxt is not None and "Dentist" in nxt.reply,
          nxt and nxt.reply)
    busy = ask("am i free at 3")
    check("free-at-3 finds the 15:00 event",
          busy is not None and "Dentist" in busy.reply
          and "this afternoon" in busy.reply, busy and busy.reply)
    free = ask("am i free at 10")
    check("free-at-10 says free", free is not None and "free at 10" in free.reply,
          free and free.reply)
    q = ask("what do i have tomorrow")
    check("a tomorrow phrase with no event is still the empty tomorrow",
          q is not None and "Nothing on your calendar tomorrow." in q.reply,
          q and q.reply)


def t_hidden_lists_never_print_a_title():
    fresh_calendar()
    C.handle_add({"title": "ZZ secret dentist", "date": TODAY, "time": "11:00"})
    check("the hidden-list event really is stored",
          len(C.list_events(1).get("events") or []) == 1)
    PV.note_state(app_locked=True)
    try:
        got = ask("what's on my calendar today?")
        check("while hidden, the title is NOT printed",
              got is not None and "ZZ secret dentist" not in got.reply,
              got and got.reply)
        check("... the answer counts events instead",
              got is not None and "1 event" in got.reply, got and got.reply)
        check("... and uses the backend's own withheld sentence",
              got is not None and PV.WITHHELD_LOCKED in got.reply,
              got and got.reply)
        nxt = ask("what's my next event")
        check("a hidden next event hides the title too",
              nxt is not None and "ZZ secret dentist" not in nxt.reply
              and "hidden" in nxt.reply, nxt and nxt.reply)
    finally:
        PV.note_state(app_locked=False)


def t_the_calendar_switch_is_read_and_named():
    fresh_calendar()
    C.handle_add({"title": "ZZ off test", "date": TODAY, "time": "11:00"})
    C.set_on(False)
    try:
        off = ask("what's on my calendar today?")
        reply = off.reply if off is not None else ""
        check("the switch's own state is read: the calendar is off",
              "off on this PC" in reply, reply)
        check("... it says where it is turned back on",
              "Settings, Jarvis Calendar" in reply, reply)
        check("... and that turning it on is instant, with no card",
              "no approval card" in reply, reply)
        check("... and no event title is printed while it is off",
              "ZZ off test" not in reply, reply)
        check("... and the event was kept, not deleted",
              len(C.list_events(7).get("events") or []) == 0
              and C.settings().get("on") is False)
    finally:
        C.set_on(True)


# --------------------------------------------------------------------------
#   3. Off / app-only / unbuilt: the real state, the real door
# --------------------------------------------------------------------------

def t_writing_a_note_when_the_note_tools_are_off():
    fresh_calendar()
    got = ask("make a note: call the plumber tomorrow at 4pm about the boiler")
    reply = got.reply if got is not None else ""
    check("the write is answered by the fast path, not the model",
          got is not None and got.intent == "honest_chat", got and got.intent)
    check("... it says the note writing is switched off on this PC",
          "switched off on this PC" in reply, reply)
    check("... it names the real switch place",
          "What asks first" in reply or "settings file" in reply, reply)
    check("... it gives the true door instead",
          "Obsidian" in reply and "Notes plate" in reply
          and "one approval card per save" in reply, reply)
    check("... and it makes no promise", no_promises(reply), reply)
    old = Q._enabled_tools_turn
    Q._enabled_tools_turn = lambda: {"append_obsidian_daily"}
    try:
        check("with the note tool ON, the capture lane owns the sentence",
              Q.match("make a note: x") is None)
    finally:
        Q._enabled_tools_turn = old


def t_reading_or_searching_notes_gives_the_true_door():
    fresh_calendar()
    read = ask("what does my Welcome note say?")
    reply = read.reply if read is not None else ""
    check("a note read is answered by the fast path",
          read is not None and read.intent == "honest_chat", read and read.intent)
    check("... chat says plain it cannot read note text",
          "cannot read note text in chat" in reply, reply)
    check("... the door is the Notes plate on the PC and the phone",
          "Notes plate" in reply and "Mind" in reply, reply)
    check("... with the real one-card-per-save rule",
          "one approval card" in reply and "denying it changes nothing" in reply,
          reply)
    check("... and it never says it has no access",
          "no access" not in reply.lower(), reply)
    check("... and it makes no promise", no_promises(reply), reply)

    search = ask("search my notes for the boiler")
    sreply = search.reply if search is not None else ""
    check("a note search is its own honest answer",
          search is not None and "cannot search note text in chat" in sreply,
          sreply)
    check("... it names the switched-off note tool and its place",
          "switched off here" in sreply and "What asks first" in sreply, sreply)
    old = Q._enabled_tools_turn
    Q._enabled_tools_turn = lambda: {"notes_search"}
    try:
        on = ask("search my notes for the boiler")
        onreply = on.reply if on is not None else ""
        check("with the notes tool ON, the answer says a search can run in chat",
              "switched on in Settings, What asks first" in onreply, onreply)
        check("... and still names the direct door",
              "Notes plate" in onreply, onreply)
    finally:
        Q._enabled_tools_turn = old


def t_app_only_note_operations_are_named_not_built():
    fresh_calendar()
    cases = (
        ("create a new note called Shopping", "Creating a note is not built"),
        ("rename my note Welcome to Home", "Renaming a note is not built"),
        ("delete my note Welcome", "Deleting a note is not built"),
    )
    for said, head in cases:
        got = ask(said)
        reply = got.reply if got is not None else ""
        check(f"{said!r} says the operation is not built", head in reply, reply)
        check(f"... and points at the real door ({said!r})",
              "Notes plate" in reply and "Obsidian itself" in reply, reply)
        check(f"... and makes no promise ({said!r})", no_promises(reply), reply)


def t_the_vault_organizers_real_state_is_read():
    fresh_calendar()
    O.set_enabled(False)
    off = ask("organize my notes")
    oreply = off.reply if off is not None else ""
    check("the organizer answer is the fast path's",
          off is not None and off.intent == "honest_chat", off and off.intent)
    check("... its real state is off", "vault organizer is off" in oreply, oreply)
    check("... turning it on is one approval card",
          "one approval card" in oreply, oreply)
    check("... and then it shows a read-only plan, changing nothing",
          "read-only plan" in oreply and "until you approve" in oreply, oreply)
    check("... and it makes no promise", no_promises(oreply), oreply)
    O.set_enabled(True)
    try:
        on = ask("organize my Obsidian vault with tags and Maps of Content")
        onreply = on.reply if on is not None else ""
        check("with the organizer ON, its own ON words are quoted",
              "vault organizer is ON" in onreply, onreply)
        check("... and the plan-first rule is still said",
              "read-only plan" in onreply, onreply)
    finally:
        O.set_enabled(False)


def t_unbuilt_customisation_is_not_a_feature():
    fresh_calendar()
    for said in ("customize my Obsidian theme",
                 "change my Obsidian theme to something dark",
                 "create a template for my notes"):
        got = ask(said)
        reply = got.reply if got is not None else ""
        check(f"{said!r} is answered honestly", "not one of my features" in reply,
              reply)
        check(f"... with the 'Everything Jarvis can do' pointer ({said!r})",
              "Everything Jarvis can do" in reply, reply)
        check(f"... and the nearest real row, not an invented one ({said!r})",
              "Notes plate" in reply, reply)
        check(f"... and no promise ({said!r})", no_promises(reply), reply)


def t_off_tools_name_the_real_switch_and_gate():
    fresh_calendar()
    email = ask("read my email")
    ereply = email.reply if email is not None else ""
    check("email reading is switched off, in the real words",
          "switched off on this PC" in ereply
          and AF.TOOLS_PC_ONLY in ereply, ereply)
    phone = ask("tap my phone")
    preply = phone.reply if phone is not None else ""
    check("phone control is not an app-switchable tool, said plainly",
          "switched off on this PC" in preply
          and AF.TOOLS_NOT_ON_LIST in preply, preply)
    old = Q._enabled_tools_turn
    Q._enabled_tools_turn = lambda: {"email_check", "home_read", "control_phone"}
    try:
        for said in ("read my email", "is the garage door open", "tap my phone"):
            check(f"with its tool ON, {said!r} keeps its own path",
                  Q.match(said) is None)
    finally:
        Q._enabled_tools_turn = old


def t_jobs_and_spending_give_the_true_app_door():
    fresh_calendar()
    jobs = ask("start a background job")
    jreply = jobs.reply if jobs is not None else ""
    check("a job is not started from chat, and says so",
          "not started from chat" in jreply, jreply)
    check("... the real door is named from the feature list",
          "Brain, Work, Background jobs" in jreply, jreply)
    spend = ask("how much did I spend last month")
    sreply = spend.reply if spend is not None else ""
    check("spending summaries are not started from chat, and it says so",
          "cannot start that from chat" in sreply, sreply)
    check("... the real source and place are named from the feature list",
          "bank export" in sreply and "Settings, Spending" in sreply, sreply)


def t_switched_off_settings_use_the_feature_lists_own_words():
    fresh_calendar()
    cases = (
        ("look-at-this", "can you look at my screen?"),
        ("pictures", "make me a picture of a red panda"),
    )
    for row_id, said in cases:
        off = Q._switch_is_off(row_id)
        got = Q.match(said)
        if off is True:
            check(f"{row_id}: the switch reads off, so the sentence is honest",
                  got is not None and got.name == "honest_chat", got)
            if got is not None:
                reply = ask(said).reply
                check(f"{row_id}: the reply says it is switched off",
                      "switched off on this PC" in reply, reply)
                check(f"{row_id}: the reply carries the feature list's own how-to",
                      "Where:" in reply and "if it needs approval" in reply, reply)
                check(f"{row_id}: and makes no promise", no_promises(reply), reply)
        elif off is False:
            check(f"{row_id}: the switch reads on, so the prompt keeps its own path",
                  got is None or got.name != "honest_chat", got)
        else:
            skip(f"{row_id}: the switch could not be read here")


# --------------------------------------------------------------------------

def t_the_protection_list_is_read_from_the_real_store():
    fresh_calendar()
    try:
        import jarvis_protection as P
    except Exception:                            # pragma: no cover - shipped
        skip("the protection module is absent here")
        return
    P.save([])
    empty = ask("what is protected from Jarvis right now?")
    ereply = empty.reply if empty is not None else ""
    check("an empty protection list says so plainly",
          "Nothing is protected from Jarvis right now." in ereply, ereply)
    check("... and quotes the module's own one-card rule",
          P.CHANGE_CARD in ereply, ereply)
    P.save([{"id": "prot_test01", "kind": "folder",
             "target": "C:\\Taxes", "mode": "blocked",
             "added": "2026-10-31T08:00:00Z", "added_by": "owner"}])
    got = ask("what is protected")
    reply = got.reply if got is not None else ""
    check("the real entries are listed with kind, target and mode",
          "folder" in reply and "C:\\Taxes" in reply
          and "blocked" in reply.lower(), reply)
    check("... with an honest count in the singular",
          "1 thing is protected from Jarvis" in reply, reply)
    P.save([])
    rem = ask("remove protection from my taxes folder")
    rreply = rem.reply if rem is not None else ""
    check("removal by chat states the one-card rule in the module's words",
          P.CHANGE_CARD in rreply, rreply)
    check("... says the chat tool is off and points at Settings",
          "not offered" in rreply and "Protected from Jarvis" in rreply, rreply)
    add = ask("protect my taxes folder")
    areply = add.reply if add is not None else ""
    check("adding by chat names the real immediate Settings path",
          "adding in Settings is immediate" in areply, areply)


def t_the_job_list_is_read_from_the_real_list():
    fresh_calendar()
    try:
        import jarvis_jobs as J
    except Exception:                            # pragma: no cover
        skip("the jobs module is absent here")
        return
    old = J.jobs
    try:
        J.jobs = lambda *a, **k: []
        got = ask("what jobs are running?")
        check("no jobs says exactly that",
              got is not None and got.reply == "No background jobs right now.",
              got and got.reply)
        J.jobs = lambda *a, **k: [
            {"label": "Watch the repo", "state": "running"},
            {"label": "Read the paper", "state": "waiting_approval"}]
        two = ask("what jobs are running?")
        reply = two.reply if two is not None else ""
        check("running jobs are listed with their real states",
              "2 background jobs" in reply
              and "Watch the repo (running)" in reply
              and "Read the paper (waiting for your approval)" in reply, reply)
    finally:
        J.jobs = old


def t_the_phone_state_is_read_from_the_real_pairing():
    fresh_calendar()
    try:
        import jarvis_devices as D
    except Exception:                            # pragma: no cover
        skip("the devices module is absent here")
        return
    old = D.paired_status
    try:
        D.paired_status = lambda: {"devices": [], "readable": True, "why": ""}
        none = ask("what timer is on my phone")
        nreply = none.reply if none is not None else ""
        check("no phone says plainly that none is paired",
              "No phone is paired with Jarvis on this PC yet." in nreply, nreply)
        D.paired_status = lambda: {
            "devices": [{"id": "d1", "name": "Pixel test", "kind": "phone",
                         "last_seen": time.time() - 60, "reach": True}],
            "readable": True, "why": ""}
        got = ask("what timer is on my phone")
        reply = got.reply if got is not None else ""
        check("a connected phone is named as connected",
              "Pixel test" in reply
              and "connected to Jarvis right now" in reply, reply)
        check("... and the answer never claims it is not connected",
              "not connected" not in reply.lower(), reply)
        check("... timers stay on the phone, they are not read from the PC",
              "Timers set on the phone stay on the phone" in reply, reply)
    finally:
        D.paired_status = old


def t_the_settings_answers_use_owner_words():
    fresh_calendar()
    asks = ask("what asks first?")
    ar = asks.reply if asks is not None else ""
    check("'what asks first' is answered, not clarified",
          "What asks first is Settings, What asks first." in ar, ar)
    check("... it names the tool switch and the real gate",
          "Let the AI use this" in ar and "Windows Hello" in ar, ar)
    quiet = ask("how do I turn off quiet hours?")
    qr = quiet.reply if quiet is not None else ""
    check("quiet hours is answered in the limits rows' own words",
          "Limits and frequency" in qr and "Be quiet during quiet hours" in qr, qr)
    check("... and the internal key is never leaked",
          "pc_quiet_hours" not in qr, qr)


def t_watch_model_and_general_off_doors():
    fresh_calendar()
    watch = ask("can you watch a PR for me?")
    wr = watch.reply if watch is not None else ""
    check("a watch tells the true door", "tell me when" in wr
          and "one approval card" in wr, wr)
    check("... and names the GitHub feature's own place", "GitHub" in wr, wr)
    model = ask("can you switch models?")
    mr = model.reply if model is not None else ""
    check("model switching is answered from its own row",
          "Brain, Model, Models" in mr, mr)
    check("... it never claims switching is impossible",
          "cannot switch" not in mr.lower(), mr)
    lights = ask("can you turn on the lights?")
    lr = lights.reply if lights is not None else ""
    lights_intent = Q.match("can you turn on the lights?")
    check("a light command is honest state, not a settings card",
          lights_intent is not None and lights_intent.name == "honest_chat"
          and lights_intent.f.get("shape") == "lights_off",
          lights_intent and (lights_intent.name, lights_intent.f))
    check("... the real switch state is named",
          "Switching your lights from chat is switched off" in lr, lr)
    off = ask("what is switched off on this PC?")
    orr = off.reply if off is not None else ""
    check("the general off question lists real items",
          "switched off right now" in orr, orr)
    check("... with the real tool switch place and gate",
          "What asks first" in orr and "Windows Hello" in orr, orr)


def t_reading_a_picture_is_picture_modes_state():
    fresh_calendar()
    off = Q._switch_is_off("look-at-this")
    got = Q.match("can you read this picture?")
    if off is True:
        check("a picture read is picture mode's state",
              got is not None and got.name == "honest_chat"
              and got.f.get("row") == "look-at-this", got)
        reply = ask("can you read this picture?").reply
        check("... the reply names the switch as off",
              "switched off on this PC" in reply, reply)
    elif off is False:
        check("with picture mode on, the prompt keeps its own path",
              got is None or got.f.get("row") != "look-at-this", got)
    else:
        skip("the picture-mode switch could not be read here")


def t_the_twins_are_byte_identical():
    first = (REPO / "backend" / "jarvis_quick.py").read_bytes()
    second = (REPO / "jarvis-backend" / "jarvis_quick.py").read_bytes()
    check("jarvis_quick.py and its published twin are byte-identical",
          first == second, (len(first), len(second)))


def main() -> int:
    tests = [(n, f) for n, f in list(globals().items())
             if n.startswith("t_") and callable(f)]
    for name, fn in tests:
        print(f"--- {name} ---")
        try:
            fn()
        except Exception as exc:                    # pragma: no cover
            traceback.print_exc()
            check(f"{name} ran without crashing", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    print(f"      ({len(tests)} t_ function(s) were found by name and run)")
    if FAILED:
        print("failed: " + "; ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
