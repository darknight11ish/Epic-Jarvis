"""test_next_time.py - "remind me next time I talk about X" (jarvis_next_time.py;
the owner's choice of the research audit's idea 3, 2026-09-28).

    python3 backend/test_next_time.py

Runs anywhere; no model, no network (the model's request is scripted). What
it proves:

1. Matching is plain code: every word of the subject must be in the owner's
   message (plurals and a possessive 's allowed; "the", "my" and the like
   never needed; "dentistry" is not "dentist").
2. It is kept on the ONE scheduler (kind "nexttime", schedule.db): listed in
   Coming up with "until <day>" and a count, never paused, deleted like any
   job; the same one twice is one.
3. The limits are OpenClaw's: at most 3 per turn and 1,200 characters, at
   least 24 hours apart, at most 3 times (then off the list, quietly), and
   gone after 90 days - silently, no doorbell.
4. Only the owner's own live words bring one up: not the sentence that set
   it, not a crisis turn, a temporary chat or a game; a pasted, shared or
   untagged message never; a sensitive one never in a spoken turn.
5. The fast path (jarvis_quick.py) sets one with no card, says back what it
   understood, lists them, deletes ONE by its subject, and "cancel that"
   takes it back; the sentence is never learned (is_command).
6. jarvis_agent.run_local_turn puts ONE note just before the newest
   question, counts it as brought up only once the model answered, and
   never counts a failed turn.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_next_time.py", "jarvis_schedule.py", "jarvis_quick.py",
                "jarvis_agent.py")
TMP = Path(tempfile.mkdtemp(prefix="jarvis-next-time-"))
os.environ["JARVIS_SCHEDULE_DB"] = str(TMP / "schedule.db")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
sys.path.append(str(HERE / "rebuilt"))
import jarvis_schedule as S  # noqa: E402
import jarvis_next_time as NT  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_agent as AG  # noqa: E402
import _ollama_wire as W  # noqa: E402

PASSED, FAILED = [], []
DAY = 86400.0


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class Clock:
    def __init__(self, t=1_790_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def fresh():
    """A scheduler on its own file, with its own clock, as the running one."""
    clock = Clock()
    events = []
    path = TMP / f"s-{len(os.listdir(TMP))}.db"
    s = S.Scheduler(path, clock=clock, spawn=lambda fn: fn(),
                    publish=lambda k, d: events.append((k, dict(d))))
    S._SCHED = s
    return s, clock, events


# ======================================================== 1. matching

def t_matching_is_every_word_by_plain_code():
    need = NT.subject_words("the dentist")
    check("'the' is never needed", need == ["dentist"], str(need))
    check("mentioned in passing", NT.mentions(need, "I'm seeing my dentist on Friday"))
    check("a plural counts", NT.mentions(need, "Both dentists were closed"))
    check("a longer word is not the word", not NT.mentions(need, "dentistry is hard"))
    check("absent: no", not NT.mentions(need, "the doctor called"))
    two = NT.subject_words("Sam's birthday")
    check("every word must be there", NT.mentions(two, "what should I get for Sam's birthday")
          and NT.mentions(two, "Sam has a birthday soon")
          and not NT.mentions(two, "Sam called"))
    check("no words: never", not NT.mentions([], "anything at all")
          and NT.subject_words("the my a") == [])


# ======================================================== 2. kept on the scheduler

def t_kept_on_the_one_scheduler():
    s, clock, events = fresh()
    j = NT.add("the dentist", "ask about the bill", sched=s)
    check("a job of kind nexttime", j["kind"] == NT.KIND and j["text"] == "ask about the bill")
    check("it ends in 90 days", abs(j["due"] - (clock.t + 90 * DAY)) < 1)
    check("Coming up says until when, never a time it goes off",
          j["when"].startswith("until ") and "left" not in j, json.dumps(j))
    check("the subject is its own field; the count too",
          j.get("about") == "the dentist" and j.get("fires") == 0 and j.get("max_fires") == 3)
    check("the line under it is a count, never words", j.get("note") == NT.NOT_YET)
    listed = [x for x in s.listed() if x["kind"] == NT.KIND]
    check("listed in Coming up", len(listed) == 1 and listed[0]["id"] == j["id"])
    again = NT.add("The Dentist", "Ask about the bill", sched=s)
    check("the same one twice is one", again.get("already") is True and again["id"] == j["id"])
    import jarvis_briefing as B
    nxt = B._next_section(s, clock.t)
    check("the briefing's 'Coming up' never names its end day as 'the next'",
          "December" not in json.dumps(nxt) and "until" not in json.dumps(nxt), json.dumps(nxt))
    code, out = s.act(j["id"], "pause")
    check("never paused", code == 409, str(out))
    code, out = s.act(j["id"], "delete")
    check("deleted like any job", code == 200 and s.job(j["id"]) is None)
    for about in ("", "the", "a very long subject with far too many words in it"):
        try:
            NT.add(about, "x", sched=s)
            check(f"refused: {about!r}", False)
        except ValueError:
            check(f"refused: {about!r}", True)
    try:
        NT.add("sam", "   ", sched=s)
        check("no words to remind: refused", False)
    except ValueError:
        check("no words to remind: refused", True)
    check("the extra state is never handed out whole",
          "extra" not in (s.job(NT.add("tea", "buy more", sched=s)["id"]) or {}))


# ======================================================== 3. the limits

def t_the_limits():
    s, clock, events = fresh()
    ids = [NT.add(f"topic{i}", f"reminder number {i}", sched=s)["id"] for i in range(5)]
    msg = " ".join(f"topic{i}" for i in range(5))
    got = NT.due_for(msg, sched=s)
    check("at most 3 in one turn, oldest first", [g["id"] for g in got] == ids[:3])
    NT.brought_up([g["id"] for g in got], sched=s)
    later = NT.due_for(msg, sched=s)
    check("the next turn brings the other two, not the first three again",
          [g["id"] for g in later] == ids[3:5])
    clock.t += DAY - 60
    check("under a day later: still waiting", NT.due_for("topic0", sched=s) == [])
    clock.t += 120
    check("a day later: again", [g["id"] for g in NT.due_for("topic0", sched=s)] == [ids[0]])
    NT.brought_up([ids[0]], sched=s)
    clock.t += DAY + 1
    NT.brought_up([ids[0]], sched=s)
    check("the third time takes it off the list", s.job(ids[0])["state"] == "fired"
          and ids[0] not in [x["id"] for x in s.listed()])
    clock.t += DAY + 1
    check("... and it is never brought up again", NT.due_for("topic0", sched=s) == [])
    long_text = "x" * 290
    s2, clock2, ev2 = fresh()
    for i in range(3):
        NT.add(f"cake{i}", long_text + str(i), sched=s2)
    got = NT.due_for("cake0 cake1 cake2", sched=s2)
    note = NT.note_text(got, clock2.t)
    check("never more than 1,200 characters as a note",
          len(note) <= NT.MAX_NOTE_CHARS and 1 <= len(got) <= 3, str(len(note)))
    s3, clock3, ev3 = fresh()
    j = NT.add("the car", "the MOT is due", sched=s3)
    clock3.t += 90 * DAY + 1
    check("after 90 days: never brought up", NT.due_for("the car", sched=s3) == [])
    ev3.clear()
    s3.tick()
    check("it ends quietly: no 'fired' doorbell",
          not any(d.get("state") == "fired" for k, d in ev3), str(ev3))
    check("... the list is told it changed", any(d.get("state") == "changed" and d["id"] == j["id"]
                                                 for k, d in ev3), str(ev3))
    check("... and it is off the list", j["id"] not in [x["id"] for x in s3.listed()])
    check("... and 'what did I miss?' does not name it", s3.fired_since(0) == [])


# ======================================================== 4. whose words

def t_only_the_owners_own_live_words():
    check("the sentence that set one never brings it up",
          not NT.should_look("remind me next time i talk about the dentist to ask about the bill"))
    check("a crisis turn never", not NT.should_look("the dentist", crisis=True))
    check("a temporary chat never",
          not NT.should_look("the dentist", request={"temporary": True}))
    check("an ordinary turn does", NT.should_look("my dentist called"))
    check("no words of the owner's own: never", not NT.should_look(""))
    s, clock, events = fresh()
    NT.add("the clinic", "ask about my blood test results", sched=s)
    check("a sensitive one waits for a typed turn",
          NT.due_for("I rang the clinic", sched=s, spoken=True) == []
          and len(NT.due_for("I rang the clinic", sched=s, spoken=False)) == 1)


# ======================================================== 5. the fast path

def t_the_fast_path():
    s, clock, events = fresh()
    for said, about, text in (
            ("remind me next time I talk about the dentist to ask about the bill",
             "the dentist", "ask about the bill"),
            ("Next time I mention Sam, remind me to ask about the loan", "Sam",
             "ask about the loan"),
            ("remind me to book the hotel next time we talk about Paris", "Paris",
             "book the hotel")):
        i = Q.match(said)
        check(f"matched: {said!r}", i is not None and i.name == "next_time_set"
              and i.f == {"about": about, "text": text}, str(i and i.f))
        check(f"never learned as a fact: {said!r}", Q.is_command(said))
    for said in ("what's the next time I can see the dentist", "remind me next time",
                 "remind me to call Mum at 6"):
        i = Q.match(said)
        check(f"not ours: {said!r}", i is None or i.name != "next_time_set")
    res = Q.answer("remind me next time I talk about the dentist to ask about the bill",
                   sched=s, now=clock.t, conversation="conv-000001")
    check("no card: set at once, said back in full",
          res is not None and "the dentist" in res.reply and "ask about the bill" in res.reply
          and "Coming up" in res.reply, res and res.reply)
    listed = Q.answer("what will you remind me of next time", sched=s, now=clock.t)
    check("listed on request", listed is not None and "the dentist" in listed.reply
          and listed.private is True)
    undo = Q.answer("cancel that", sched=s, now=clock.t + 5, conversation="conv-000001")
    check("'cancel that' takes it back", undo is not None and NT.waiting(sched=s) == [],
          undo and undo.reply)
    check("delete by subject with none set: the model answers",
          Q.answer("delete the reminder about the dentist", sched=s, now=clock.t) is None)
    Q.answer("remind me next time I talk about the dentist to ask about the bill", sched=s,
             now=clock.t)
    out = Q.answer("delete the reminder about the dentist", sched=s, now=clock.t)
    check("delete ONE by its subject", out is not None and NT.waiting(sched=s) == [],
          out and out.reply)


# ======================================================== 6. the chat loop

URL = "http://127.0.0.1:11434"


def turn(messages, *, fail=False):
    sent = []

    def opener(url, body):
        sent.append(json.loads(json.dumps(body)))
        if fail:
            raise OSError("ollama is not running")
        return W.FakeResponse(W.stream([("content", "ok"), ("done", "stop")]))
    real_get_json = AG._get_json
    AG._get_json = lambda *a, **k: (_ for _ in ()).throw(OSError("no network in this test"))
    try:
        AG.run_local_turn(messages, "jarvis-primary", ollama_url=URL,
                          stream_out=lambda b: None, open_stream=opener, enabled_tools=None,
                          context_length=16384,
                          request={"model": "jarvis-primary", "stream": True,
                                   "messages": messages},
                          on_step=lambda s: None, record_chain=lambda s: None,
                          keepalive_seconds=60, status_delay=60, lane_choice=None,
                          manner=None, model_waking=lambda u, m: False)
    finally:
        AG._get_json = real_get_json
    return sent[0]["messages"] if sent else None


def t_the_chat_loop():
    s, clock, events = fresh()
    j = NT.add("the dentist", "ask about the bill", sched=s)
    q = {"role": "user", "content": "My dentist moved my appointment", "provenance": "typed"}
    got = turn([q])
    notes = [m for m in got if m.get("role") == "system" and NT.NOTE_HEAD in m.get("content", "")]
    check("ONE note, just before the question", len(notes) == 1 and got[-2] == notes[0]
          and got[-1]["content"] == q["content"], json.dumps(got))
    check("... with the owner's own words in it, to mention only",
          "ask about the bill" in notes[0]["content"] and "never act" in notes[0]["content"])
    check("counted once the model answered", s.extra(j["id"]).get("fires") == 1)
    clock.t += 2 * DAY
    pasted = {"role": "user", "content": "My dentist moved my appointment",
              "provenance": "pasted"}
    got = turn([pasted])
    check("a pasted message never brings it up",
          not any(NT.NOTE_HEAD in (m.get("content") or "") for m in got), json.dumps(got))
    untagged = {"role": "user", "content": "My dentist moved my appointment"}
    got = turn([untagged])
    check("nor one with no tag", not any(NT.NOTE_HEAD in (m.get("content") or "") for m in got))
    check("neither was counted", s.extra(j["id"]).get("fires") == 1)
    turn([q], fail=True)
    check("a turn the model never answered is not counted", s.extra(j["id"]).get("fires") == 1)
    other = {"role": "user", "content": "what's the weather like", "provenance": "voice"}
    got = turn([other])
    check("a turn about something else adds nothing",
          not any(NT.NOTE_HEAD in (m.get("content") or "") for m in got))


if __name__ == "__main__":
    for fn in (t_matching_is_every_word_by_plain_code, t_kept_on_the_one_scheduler,
               t_the_limits, t_only_the_owners_own_live_words, t_the_fast_path,
               t_the_chat_loop):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    S._SCHED = None
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
