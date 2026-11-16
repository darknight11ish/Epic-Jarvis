"""test_phone_fact_answers.py - the two phone questions answered from the phone.

    python3 backend/test_phone_fact_answers.py

THE GAP THIS CLOSES (2026-11-16). The awareness audit of 2026-11-15 ran
nineteen questions through the live backend and checked each answer against
the machine. Two of them still had no deterministic answer and fell to the 8B
model, which cannot measure either:

    "what model of phone am I using right now"
    "are you connected to my phone"

The phone already sends its own facts on every request:

    X-Jarvis-Device: model=CPH2419;android=15;sdk=35;screen=1080x2400;app=0.2.4295

`jarvis_surface.remember` reads it once at the gate, and since 2026-11-16 it
also keeps WHEN the facts arrived (this request, or the newest stored report).
`jarvis_quick.py` answers the two questions from that one rule:

  * a fact that arrived with THIS request is live, and the answer says so;
  * a stored fact is returned WITH ITS AGE ("43 minutes ago") and never
    presented as a live check;
  * with no facts at all the answer says it does not know yet and names no
    phone - it does not borrow a pairing record;
  * from the desktop the link question reads the pairing records, with the age
    of their own last check-in, and says a record is not a live connection.

THE TRAP THIS SUITE GUARDS. PR #1292 removed a "connected right now" claim that
had been built from a roster row: the roster's `reach` flag is a capability,
not a liveness probe, and a pairing record is not a connection. That old
answer must not come back through either new lane - the bite below feeds a
roster heard from ten seconds ago and demands that the answer still calls it a
record.

WHY A SEPARATE SUITE. `test_phone_facts.py` proves the header's parse and the
model's system sentence. This one proves the two CHAT answers, their four
states (live / aged / none / a record naming a different phone), the near
misses that stay the model's, and that both answers are read-only. The twins
of both changed modules are checked byte-identical at the end.
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parent

#: Hermetic: a throwaway config folder and schedule database, so a read here can
#: never touch the owner's own files. `JARVIS_BACKEND` must not decide which copy
#: this suite tests (`_where.require_shipped` refuses on a mid-change worktree).
_WORK = Path(tempfile.mkdtemp(prefix="jarvis-phone-fact-answers-"))
os.environ.setdefault("JARVIS_SCHEDULE_DB", str(_WORK / "schedule.db"))
os.environ.setdefault("OPENJARVIS_HOME", str(_WORK))
os.environ.setdefault("OPENJARVIS_CONFIG_DIR", str(_WORK / "cfg"))
os.environ.setdefault("JARVIS_CONFIG_DIR", str(_WORK / "cfg"))
os.environ.pop("JARVIS_BACKEND", None)

PASSED, FAILED = [], []

#: The phone's own line, exactly as `DeviceFacts.kt` builds it.
FACTS = ("model=CPH2419;android=15;sdk=35;screen=1080x2400;app=0.2.4295")

#: The owner's two questions, and the close shapes a person types. Whole
#: sentences only - a near miss keeps its old path (the model).
OWN_FACTS_ASKED = (
    "what model of phone am i using right now",
    "what model of phone am i using",
    "what model of phone do i have",
    "what phone model am i using",
    "what phone model do i have",
    "which phone am i using",
    "what phone am i using",
    "what phone am i on",
    "what model is my phone",
    "what model does my phone use",
    "what is my phone model",
    "whats my phone model",
    "what is my phone",
    "what phone do i have",
    "which phone do i have",
    "what phone is this",
)
LINK_ASKED = (
    "are you connected to my phone",
    "are you connected to my phone right now",
    "are you still connected to my phone",
    "is jarvis connected to my phone",
    "are you linked to my phone",
    "are you linked with the phone",
    "do you have a connection to my phone",
    "do you have my phone connected",
    "are you connected to the phone at the moment",
)

#: Must NOT be answered by either lane. The first eight belong to existing
#: answers (the roster's phone-state read, the timer answer, the surface
#: question); the rest are ordinary language that must keep going to the model.
NEAR_MISSES = (
    "is my phone connected",
    "is my phone connected to jarvis",
    "can you see my phone",
    "what phone is paired",
    "which phone is connected",
    "what timer is on my phone",
    "where am i talking from",
    "what devices are connected",
    "what model of car do i have",
    "what phone do i have paired",
    "what is my phone number",
    "what is my phone doing",
    "what model is your phone",
    "are you connected to the internet",
    "are you connected to the wifi",
)

#: The honest no-facts sentence, pinned: it must name no phone and must say it
#: does not know yet.
UNKNOWN_WORDS = (
    "I do not know which phone you are using yet: no request from a phone has "
    "carried its own model details to this PC, so I will not guess. Ask me from "
    "the Jarvis app on the phone and I will answer from what it sends.")

#: The old roster-based answer's live-connection words. No state may reuse
#: them: PR #1292 removed them because a pairing record is not a connection.
ROSTER_LIVE_WORDS = ("connected to Jarvis right now", "reachable now",
                     "reachable right now")

#: On a request that is not the phone's, no live-connection claim at all.
LINK_LIVE_WORDS = ROSTER_LIVE_WORDS + ("link is live right now",)


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok   " if cond else "FAIL ") + name
          + (("\n        " + detail) if detail and not cond else ""))


class _Headers:
    """A headers mapping, as the gate hands it to `remember`."""

    def __init__(self, values):
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)


def headers(surface=None, device=None):
    values = {}
    if surface is not None:
        values["X-Jarvis-Surface"] = surface
    if device is not None:
        values["X-Jarvis-Device"] = device
    return _Headers(values)


def ask(text):
    """What the REAL fast path answers for this sentence, or None."""
    intent = Q.match(text)
    if intent is None:
        return None
    return Q.run(intent, None, time.time())


def reply(text):
    got = ask(text)
    return "" if got is None else str(got.reply or "")


class _Roster:
    """Stand in for `jarvis_devices.paired_status()` for one block."""

    def __init__(self, rows, readable=True, why=""):
        self.state = {"devices": list(rows), "readable": readable, "why": why}
        self.old = None

    def __enter__(self):
        self.old = D.paired_status
        D.paired_status = lambda: self.state
        return self

    def __exit__(self, *exc):
        D.paired_status = self.old
        return False


def phone_row(name, age_s, reach=True, row_id="d1"):
    return {"id": row_id, "name": name, "kind": "phone",
            "last_seen": time.time() - age_s, "reach": reach}


def main():
    global Q, S, D
    import jarvis_quick as Q
    import jarvis_surface as S

    try:
        import jarvis_devices as D
    except Exception:                       # pragma: no cover - shipped beside it
        D = None

    S.reset()

    # --- 1. The matchers claim exactly the two questions, whole-sentence. ---
    for said in OWN_FACTS_ASKED:
        got = Q.match(said)
        check(f"matcher: {said!r} is the phone-facts question",
              getattr(got, "name", None) == "phone_own_facts",
              f"got {getattr(got, 'name', None)!r}")
    for said in LINK_ASKED:
        got = Q.match(said)
        check(f"matcher: {said!r} is the phone-link question",
              getattr(got, "name", None) == "phone_link",
              f"got {getattr(got, 'name', None)!r}")

    # The regexes themselves, so a renamed function cannot hide a widened one.
    for said in OWN_FACTS_ASKED:
        check(f"regex: {said!r} is phone_own_facts",
              Q._phone_own_facts(Q.normalize_spoken_command(said)) is not None)
    for said in LINK_ASKED:
        check(f"regex: {said!r} is phone_link",
              Q._phone_link(Q.normalize_spoken_command(said)) is not None)

    # A leading "hey"/"jarvis" and a trailing "?" are the same question.
    for said in ("Hey Jarvis, what model of phone am I using right now?",
                 "jarvis are you connected to my phone?",
                 "Are you connected to my phone?"):
        got = Q.match(said)
        check(f"same question: {said!r}",
              getattr(got, "name", None) in ("phone_own_facts", "phone_link"),
              f"got {getattr(got, 'name', None)!r}")

    # Near misses keep their old path: either an existing lane, or the model.
    for said in NEAR_MISSES:
        got = Q.match(said)
        check(f"near-miss: {said!r} is neither new lane",
              getattr(got, "name", None) not in ("phone_own_facts", "phone_link"),
              f"got {getattr(got, 'name', None)!r}")
        check(f"near-miss: {said!r} is not matched by the phone regexes",
              Q._phone_own_facts(Q.normalize_spoken_command(said)) is None
              and Q._phone_link(Q.normalize_spoken_command(said)) is None)

    # --- 2. Facts from THIS request are live. ------------------------------
    S.reset()
    S.remember(headers(S.PHONE, FACTS))
    live_model = reply("what model of phone am i using right now")
    check("live: the model answer names the phone's own model",
          "CPH2419" in live_model, live_model)
    check("live: ... and the rest of its facts",
          all(bit in live_model for bit in
              ("Android 15", "screen 1080x2400", "app 0.2.4295")), live_model)
    check("live: ... and says these came with this message",
          "with this message" in live_model and "current" in live_model,
          live_model)
    check("live: ... and never calls it a stored report",
          "last report" not in live_model and "stored" not in live_model,
          live_model)

    live_link = reply("are you connected to my phone")
    check("live: the link answer is a yes, from this message",
          live_link.startswith("Yes") and "this message came from your phone" in live_link,
          live_link)
    check("live: ... and says the link is live right now",
          "the link is live right now" in live_link, live_link)
    check("live: ... and names the phone that sent it", "CPH2419" in live_link,
          live_link)
    check("live: ... without the roster's old live-connection words",
          all(word not in live_link for word in ROSTER_LIVE_WORDS), live_link)

    # The live answer does not depend on the roster: a raising read still gets
    # the yes, because the request itself is the evidence.
    if D is not None:
        old = D.paired_status
        try:
            D.paired_status = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
            said = reply("are you connected to my phone")
            check("live: a phone request answers yes even if the roster cannot be read",
                  "Yes" in said and "the link is live right now" in said, said)
            check("live: ... and says the records could not be read",
                  "cannot read this PC's pairing records" in said, said)
        finally:
            D.paired_status = old

        # A roster whose newest row MATCHES the live phone says nothing extra;
        # one whose newest row is a different name says so, as a record.
        with _Roster([phone_row("CPH2419", 43 * 60)]):
            said = reply("are you connected to my phone")
            check("live: a matching record adds no mismatch clause",
                  "different name" not in said, said)
        with _Roster([phone_row("Pixel 9", 43 * 60)]):
            said = reply("what model of phone am i using right now")
            check("live: the model answer never borrows a roster name",
                  "Pixel 9" not in said, said)

    # --- 3. A stored report is AGED, and says its age. ----------------------
    S.reset()
    S.set_current(S.DESKTOP)
    S.set_last(FACTS, at=time.time() - 43 * 60)
    aged_model = reply("what model of phone am i using right now")
    check("aged: the model answer gives the age of the last report",
          "43 minutes ago" in aged_model, aged_model)
    check("aged: ... names the phone the report described", "CPH2419" in aged_model,
          aged_model)
    check("aged: ... calls it stored, not live, and refuses to call it current",
          "stored, not live" in aged_model and "You are using" not in aged_model,
          aged_model)

    # The same state can come from this thread's own facts gone old.
    S.reset()
    S.set_current(S.PHONE)
    S.set_device(FACTS, at=time.time() - 43 * 60)
    old_thread = reply("what model of phone am i using right now")
    check("aged: facts held on the phone's own thread are aged too",
          "43 minutes ago" in old_thread and "You are using" not in old_thread,
          old_thread)
    # ... and the link is still live from the request, but the phone is not
    # named as live from facts that are not this message's.
    old_link = reply("are you connected to my phone")
    check("aged: a phone request proves the link, not an aged model",
          "the link is live right now" in old_link
          and "not from this message" in old_link
          and "CPH2419" not in old_link, old_link)
    S.reset()

    if D is not None:
        with _Roster([phone_row("Pixel 9", 43 * 60)]):
            S.reset()
            S.set_current(S.DESKTOP)
            aged_link = reply("are you connected to my phone")
            check("aged: the desktop link answer gives the record's age",
                  "43 minutes ago" in aged_link, aged_link)
            check("aged: ... says plainly that a record is not a live connection",
                  "not a live connection" in aged_link, aged_link)
            check("aged: ... and never claims a connection",
                  all(word not in aged_link for word in LINK_LIVE_WORDS),
                  aged_link)
            check("aged: ... and tells the owner where the real check is",
                  "Open the Jarvis app on the phone" in aged_link, aged_link)

        # Ages are words, and the words do not guess: minutes, hours, days.
        check("ages: 30 seconds reads as 'just now'",
              Q._phone_facts_age_words(30) == "just now")
        check("ages: 43 minutes reads as '43 minutes ago'",
              Q._phone_facts_age_words(43 * 60) == "43 minutes ago",
              Q._phone_facts_age_words(43 * 60))
        check("ages: 2 hours reads as '2 hours ago'",
              Q._phone_facts_age_words(2 * 3600 + 60) == "2 hours ago")
        check("ages: 2 days reads as '2 days ago'",
              Q._phone_facts_age_words(2 * 86400 + 60) == "2 days ago")

    # --- 4. No facts at all: it says it does not know, and names no phone. --
    S.reset()
    S.set_current(S.DESKTOP)
    none_model = reply("what model of phone am i using right now")
    check("none: the model answer is the pinned honest sentence",
          none_model == Q.PHONE_FACTS_UNKNOWN, none_model)
    check("none: ... it is the pinned text", Q.PHONE_FACTS_UNKNOWN == UNKNOWN_WORDS,
          Q.PHONE_FACTS_UNKNOWN)
    check("none: ... it says it does not know yet",
          "I do not know which phone" in none_model, none_model)
    check("none: ... and names no phone at all",
          "CPH2419" not in none_model and "Pixel 9" not in none_model, none_model)

    if D is not None:
        # A pairing record is NOT a model: a roster with a named phone and no
        # facts must still say it does not know which phone is in use.
        with _Roster([phone_row("Pixel 9", 60)]):
            said = reply("what model of phone am i using right now")
            check("none: a pairing record does not become a phone model",
                  said == Q.PHONE_FACTS_UNKNOWN and "Pixel 9" not in said, said)
        with _Roster([]):
            said = reply("are you connected to my phone")
            check("none: no phone paired says exactly that",
                  "No phone is paired with Jarvis on this PC yet." in said, said)
            check("none: ... and names the real pairing doors",
                  "Settings, Devices" in said and "Pair a phone" in said
                  and "Pair with your PC" in said, said)
        with _Roster([], readable=False, why="the devices registry could not be read"):
            said = reply("are you connected to my phone")
            check("none: an unreadable roster says it cannot read it",
                  "cannot read the paired devices on this PC right now" in said, said)

    # --- 5. The roster's newest row names a DIFFERENT phone. ----------------
    # The live request wins; the record is named only as a record, with its
    # age, and the answer says it is going by the message.
    if D is not None:
        S.reset()
        S.remember(headers(S.PHONE, FACTS))
        with _Roster([phone_row("Pixel 9", 43 * 60)]):
            said = reply("are you connected to my phone")
            check("different: the live phone is the one this message came from",
                  "CPH2419" in said and "this message came from your phone" in said,
                  said)
            check("different: ... the roster name is a record, with its age",
                  "Pixel 9" in said and "43 minutes ago" in said, said)
            check("different: ... and the answer says it is going by the message",
                  "different name from the model this phone reports" in said
                  and "going by this message" in said, said)
            check("different: ... and never claims a connection",
                  all(word not in said for word in ROSTER_LIVE_WORDS), said)

    # --- 6. The bite: the old roster-based live answer must not return. -----
    # A roster row heard from TEN SECONDS ago, on a desktop request: the old
    # answer called that "connected to Jarvis right now". A fresh check-in is
    # still a record, so the answer must give the age and say so.
    if D is not None:
        S.reset()
        S.set_current(S.DESKTOP)
        with _Roster([phone_row("Pixel 9", 10, reach=True)]):
            said = reply("are you connected to my phone")
            check("bite: a row heard from 10 seconds ago is still not a connection",
                  all(word not in said for word in LINK_LIVE_WORDS), said)
            check("bite: ... it gives the real age instead",
                  "just now" in said and "not a live connection" in said, said)
            check("bite: ... and never turns `reach` into reachability",
                  "reachable" not in said.lower(), said)

        # The old answer is the rostered `devices_list` one; the new question
        # must not be answered by it.
        got = Q.match("are you connected to my phone")
        check("bite: the sentence is the new lane, not the roster answer",
              getattr(got, "name", None) == "phone_link",
              f"got {getattr(got, 'name', None)!r}")

    # Registration bite: with the matcher removed the sentence is no longer
    # claimed, so these checks cannot pass by another lane answering instead.
    old_link = Q._phone_link
    try:
        Q._phone_link = lambda _s: None
        got = Q.match("are you connected to my phone")
        check("bite: without its matcher the link question is not this lane",
              getattr(got, "name", None) != "phone_link",
              f"got {getattr(got, 'name', None)!r}")
    finally:
        Q._phone_link = old_link
    old_facts = Q._phone_own_facts
    try:
        Q._phone_own_facts = lambda _s: None
        got = Q.match("what model of phone am i using right now")
        check("bite: without its matcher the model question is not this lane",
              getattr(got, "name", None) != "phone_own_facts",
              f"got {getattr(got, 'name', None)!r}")
    finally:
        Q._phone_own_facts = old_facts

    # --- 7. Read-only, deterministic, and no card. --------------------------
    check("read-only: both intents are listed read-only",
          {"phone_own_facts", "phone_link"} <= set(Q.READ_ONLY_INTENTS))
    S.reset()
    S.remember(headers(S.PHONE, FACTS))
    one = ask("what model of phone am i using right now")
    two = ask("what model of phone am i using right now")
    check("deterministic: the same request answers the same twice",
          one is not None and two is not None and one.reply == two.reply,
          f"{getattr(one, 'reply', None)!r} vs {getattr(two, 'reply', None)!r}")
    check("read-only: the answer made nothing, opened nothing, raised nothing",
          one is not None and one.made == [] and one.ids == []
          and one.open_settings is None and one.open_app is None,
          f"made={getattr(one, 'made', None)!r} ids={getattr(one, 'ids', None)!r} "
          f"open={getattr(one, 'open_settings', None)!r}")

    # --- 8. The module keeps the age, and a desktop request cannot erase it. -
    S.reset()
    S.set_device(FACTS, at=time.time() - 3600)
    age = S.device_age()
    check("module: a fact's age is its own stored time",
          age is not None and 3595 <= age <= 3610, f"got {age!r}")
    facts, at = S.last()
    check("module: the newest report is kept with when it arrived",
          facts.get("model") == "CPH2419" and at > 0, (facts, at))
    S.remember(headers(S.DESKTOP, None))
    check("module: a later desktop request does not erase the last report",
          S.last()[0].get("model") == "CPH2419")
    S.set_last("")
    check("module: an empty report is ignored, not a clear",
          S.last()[0].get("model") == "CPH2419")
    S.reset()
    check("module: reset clears this thread and the newest report",
          S.device() == {} and S.last() == ({}, 0.0))
    S.set_current(S.PHONE)
    S.set_device("")
    check("module: no facts means no age to give", S.device_age() is None)

    # --- 9. Twins, byte for byte. ------------------------------------------
    for name in ("jarvis_quick.py", "jarvis_surface.py"):
        a = (REPO / "backend" / name).read_bytes()
        b = (REPO / "jarvis-backend" / name).read_bytes()
        check(f"twin: {name} is identical in both copies", a == b,
              hashlib.sha256(a).hexdigest() + " vs " + hashlib.sha256(b).hexdigest())
        print(f"     sha256 {name}: {hashlib.sha256(a).hexdigest().upper()}")

    S.reset()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        FAILED.append("the suite itself raised")
    print()
    if FAILED:
        print(f"{len(PASSED)} passed, {len(FAILED)} FAILED")
        for name in FAILED:
            print(f"  FAIL {name}")
        sys.exit(1)
    print(f"{len(PASSED)} passed, 0 failed")
