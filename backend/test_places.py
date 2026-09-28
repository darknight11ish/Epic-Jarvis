"""test_places.py - "Where did I put ...?" (2026-09-28; JARVIS-API section 77).

    python3 backend/test_places.py

What is proved here, against a real MemoryStore in a temporary folder:

  * place_of() reads where a thing is from a fact's words, with fixed
    rules - and says NO to a person, a pet, an event, a date or time ("the
    wedding is in May"), the owner's own home ("moved back to Leeds"), and
    things that only look like places ("keeps fit by running", "on silent");
  * where_question() is the fast path's grammar: whole questions with
    "my"/"the"/"our" only - never "where is Paris?", never a statement;
  * lookup() finds the place IN USE: never a forgotten, erased or ended one,
    the newest said first, and "where are my keys?" finds each key;
  * apply_move() ends the older place as history (not a Forget), and OLDER
    NEWS - a place the owner's own words date earlier - is filed as history
    instead, leaving the newer place in use;
  * the fast path (jarvis_quick) answers from memory WITHOUT the model, with
    when it was said, says in X-Jarvis-Route that it used memory ("mem:<id>"
    ids, and how many are sensitive), and hands the question to the model
    when there is no place saved, in a temporary chat, and with memory off;
  * the learner does not learn the QUESTION ("where is my passport?" is a
    command, jarvis_quick.is_command), while a statement is never ours.

No pytest, no network, no model.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_places.py", "jarvis_quick.py", "rebuilt/jarvis_memory.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-places-"))
os.environ.setdefault("OPENJARVIS_CONFIG_DIR", str(_TMP / "config"))
try:
    import jarvis_memory as M
except ImportError:
    sys.path.append(str(REPO / "backend" / "rebuilt"))
    import jarvis_memory as M
import jarvis_places as P  # noqa: E402
import jarvis_quick as Q  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


_n = [0]


def store():
    _n[0] += 1
    st = M.MemoryStore(_TMP / f"memory-{_n[0]}.db", embedder=M.HashEmbedder())
    M._store = st
    return st


def at(when, fn):
    real = M.time
    M.time = types.SimpleNamespace(**{k: getattr(real, k) for k in dir(real)
                                      if not k.startswith("_")})
    M.time.time = lambda: when
    try:
        return fn()
    finally:
        M.time = real


class Sched:
    """What jarvis_quick.answer() needs of the scheduler for a question."""
    def mark_command(self, text):
        pass

    def note_set(self, *a, **k):
        pass

    def forget_set(self, c):
        pass


# ------------------------------------------------------------------ parsing

def t_place_of():
    good = {
        "Owner's passport is in the top drawer": ("passport", "in the top drawer"),
        "The spare key is under the blue pot": ("spare key", "under the blue pot"),
        "Owner put the spare key under the blue pot.": ("spare key", "under the blue pot"),
        "Owner keeps their glasses on the hall table": ("glasses", "on the hall table"),
        "Owner's car keys are with Dave": ("car keys", "with Dave"),
        "Owner left their umbrella at work": ("umbrella", "at work"),
        "Owner moved the passport to the filing cabinet": ("passport", "in the filing cabinet"),
        "Owner moved the sofa into the lounge": ("sofa", "in the lounge"),
        "Owner's passport is in the top drawer now (2026-09-22)": ("passport", "in the top drawer"),
        "Owner put the winter coats in the loft in January 2026": ("winter coats", "in the loft"),
        "Owner put the keys on the hook yesterday": ("keys", "on the hook"),
    }
    for text, (thing, where) in good.items():
        p = P.place_of(text)
        check(f"a place: {text!r}", p is not None and p["thing"] == thing
              and p["where"] == where, p)
    for text in ("Owner's wedding is in May", "Owner's sister is in Lisbon",
                 "Owner keeps fit by running", "Owner's phone is on silent",
                 "Owner keeps a diary in the evenings", "Owner lives in Leeds",
                 "Owner is in the kitchen", "Owner moved back to Leeds", "Owner works at Initech",
                 "Owner's cat is in the garden", "Owner's job is in London", "", "   "):
        check(f"not a place: {text!r}", P.place_of(text) is None, P.place_of(text))
    check("keys and key are the same thing", P.thing_key("my car keys") == "car key")
    check("moved(): the same thing somewhere else",
          P.moved("Owner's passport is in the desk", "Owner's passport is in the top drawer"))
    check("moved(): not the same place said twice",
          not P.moved("Owner's passport is in the top drawer",
                      "Owner put the passport in the top drawer"))
    check("moved(): not a different thing",
          not P.moved("Owner's car key is on the hook", "Owner's spare key is on the hook"))


def t_where_question():
    asked = {
        "where is my passport": "passport",
        "where's my passport": "passport",
        "where did i put the spare key": "spare key",
        "where are my car keys": "car keys",
        "do you know where my glasses are": "glasses",
        "remind me where i put my keys": "keys",
        "where did i leave my phone again": "phone",
        "where do i keep the passport": "passport",
    }
    for q, thing in asked.items():
        check(f"a where-question: {q!r}", P.where_question(q) == thing, P.where_question(q))
    for q in ("where is paris", "where is the nearest pharmacy", "where is it",
              "where is my sister", "where is the party", "i put my passport in the safe",
              "the passport is in the top drawer", "where do i live"):
        check(f"not ours: {q!r}", P.where_question(q) is None, P.where_question(q))


def t_when_said():
    now = time.mktime((2026, 9, 28, 12, 0, 0, 0, 0, -1))   # a Monday
    day = 86400.0
    check("today", P.when_said(now - 3600, now) == "today")
    check("yesterday", P.when_said(now - day, now) == "yesterday")
    check("a weekday in the last week", P.when_said(now - 6 * day, now) == "on Tuesday",
          P.when_said(now - 6 * day, now))
    check("a date this year", P.when_said(now - 20 * day, now) == "on 8 September",
          P.when_said(now - 20 * day, now))
    check("a date last year", P.when_said(now - 400 * day, now).endswith("2025"))

# ------------------------------------------------------------------- lookup


def t_lookup_and_moves():
    st = store()
    now = time.time()
    a = at(now - 40 * 86400, lambda: st.add("Owner's passport is in the top drawer", source="t"))
    b = at(now - 5 * 86400, lambda: st.add("Owner's passport is in the desk drawer", source="t"))
    check("before the move, the newest place said comes first",
          [r["id"] for r in P.lookup(st, "passport")] == [b])
    prev = P.older_place(st, "Owner's passport is in the desk drawer", exclude=(b,))
    check("older_place() finds the place it moves", prev is not None and prev["id"] == a)
    check("apply_move(): moved", P.apply_move(st, b, a) == "moved")
    old = st.get(a)
    check("the older place is history, replaced by the newer one",
          old["valid_to"] is not None and old["retired_by"] == b)
    check("... and NOT forgotten (a past question may still find it)",
          "forgotten_at" not in json.loads(old["meta"] or "{}"))
    check("the newer place is in use", st.get(b)["valid_to"] is None)
    check("apply_move() again does nothing", P.apply_move(st, b, a) == "")

    # Older news, by the owner's own dates.
    c = at(now - 9 * 86400, lambda: st.add("Owner put the winter coats in the spare room in "
                                           "March 2026", source="t"))
    d = at(now - 2 * 86400, lambda: st.add("Owner put the winter coats under the stairs in "
                                           "February 2026", source="t"))
    check("both dates are the owner's own", M.said_from(st.get(c)["meta"])
          and M.said_from(st.get(d)["meta"]))
    check("apply_move(): older news", P.apply_move(st, d, c) == "older_news")
    check("older news is history; the newer place stays in use",
          st.get(d)["valid_to"] is not None and st.get(c)["valid_to"] is None
          and st.get(d)["retired_by"] == c)

    # Forgotten and erased places are never the answer.
    e = st.add("Owner's glasses are on the hall table", source="t")
    st.retire(e)
    check("a forgotten place is not found", P.lookup(st, "glasses") == [])
    f = st.add("Owner's umbrella is at work", source="t")
    st.erase(f)
    check("an erased place is not found", P.lookup(st, "umbrella") == [])

    # "keys" finds each key; one exact thing finds only that one.
    st.add("Owner's car key is on the hook by the door", source="t")
    st.add("Owner's spare key is with Dave", source="t")
    keys = P.lookup(st, "keys")
    check("\"keys\" finds the car key and the spare key",
          sorted(r["place"]["thing"] for r in keys) == ["car key", "spare key"], keys)
    check("\"spare key\" finds only the spare key",
          [r["place"]["thing"] for r in P.lookup(st, "spare key")] == ["spare key"])
    words = P.answer_words(keys, time.time())
    check("the answer names each thing and where it is",
          "the car key, on the hook by the door" in words and "with Dave" in words, words)

def t_two_moves_in_one_pass():
    """The learner reads a whole conversation: "in the drawer", then "in the
    desk" can both be proposed in one pass, both aimed at the place stored
    when the pass began. Each must replace the one before it."""
    import jarvis_auto_learn as A
    st = store()
    now = time.time()
    old = at(now - 9 * 86400, lambda: st.add("Owner's passport is in the safe", source="t"))
    moved = {"id": old, "text": "Owner's passport is in the safe"}
    # Saved one after the other, as after_pass saves them.
    a = at(now - 60, lambda: st.add("Owner's passport is in the drawer", source="t"))
    check("the first move ends the stored place", A._apply_move(st, a, moved) == "moved"
          and st.get(old)["retired_by"] == a)
    b = st.add("Owner's passport is in the desk", source="t")
    check("the second ends the FIRST move, not the stored place again",
          A._apply_move(st, b, moved) == "moved" and st.get(a)["retired_by"] == b)
    check("one place in use: the last one said",
          [r["id"] for r in P.lookup(st, "passport")] == [b]
          and st.get(b)["valid_to"] is None)


# ---------------------------------------------------------------- fast path


def t_fast_path():
    st = store()
    import jarvis_sensitive as S
    keep = getattr(S, "ASK_MODEL", None)
    S.ASK_MODEL = lambda prompt: '{"sensitive": false, "category": "none"}'
    try:
        now = time.time()
        fid = at(now - 86400, lambda: st.add("Owner's passport is in the top drawer", source="t"))
        res = Q.answer("Where is my passport?", sched=Sched(), now=now)
        check("answered without the model", res is not None and res.intent == "where_put", res)
        check("... plainly, with when it was said",
              res is not None and res.reply == "You said yesterday: in the top drawer.",
              res and res.reply)
        f = Q.route_fields(res)
        check("X-Jarvis-Route says memory was used, by id",
              f["inject_memory"] is True and f["injected_facts"] == 1
              and f["injected_ids"] == [f"mem:{fid}"], f)
        check("... and how many were sensitive (none)", f["injected_sensitive"] == 0, f)
        check("... and that no model answered", f["lane"] == Q.LANE and f["quick"] == "where_put")

        # A sensitive place stays on screen like any memory answer.
        st.add("Owner's spare key is under the flowerpot", source="t")
        S.ASK_MODEL = lambda prompt: '{"sensitive": true, "category": "location"}'
        res2 = Q.answer("where did I put the spare key", sched=Sched(), now=now)
        f2 = Q.route_fields(res2) if res2 else {}
        check("a sensitive place is counted as sensitive", f2.get("injected_sensitive") == 1, f2)
        S.ASK_MODEL = lambda prompt: '{"sensitive": false, "category": "none"}'

        check("no place saved: the model answers, as before",
              Q.answer("where did I leave my phone?", sched=Sched(), now=now) is None)
        check("a temporary chat uses no memory: the model answers",
              Q.run(Q.match("where is my passport", now), Sched(), now, temporary=True) is None)
        os.environ["JARVIS_MEMORY_K"] = "0"
        try:
            check("memory off (JARVIS_MEMORY_K=0): the model answers",
                  Q.answer("where is my passport", sched=Sched(), now=now) is None)
        finally:
            os.environ.pop("JARVIS_MEMORY_K", None)
        check("a statement is never ours (the learner learns it)",
              Q.match("I put my passport in the safe", now) is None
              and not Q.is_command("the passport is in the desk now"))
        check("the question is a command, so the learner never learns it as a fact",
              Q.is_command("where is my passport?"))
        # The same answer from the whole chat turn, as /api/chat calls it.
        body = {"messages": [{"role": "user", "content": "where is my passport?",
                              "provenance": "typed"}], "conversation_id": "conv-places-01"}
        got = Q.answer_turn(body, sched=Sched(), now=now)
        check("answer_turn: the owner's typed question is answered",
              got is not None and "top drawer" in got.reply)
        body["messages"][0]["provenance"] = "pasted"
        check("answer_turn: a pasted question goes to the model",
              Q.answer_turn(body, sched=Sched(), now=now) is None)
        body["messages"][0]["provenance"] = "typed"
        body["temporary"] = True
        check("answer_turn: a temporary chat goes to the model",
              Q.answer_turn(body, sched=Sched(), now=now) is None)
    finally:
        S.ASK_MODEL = keep


def t_sayable_and_shipping():
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("jarvis_places.py is shipped", "'jarvis_places.py'" in ps1)
    import _where
    check("... and in _where.SHIPPED", "jarvis_places.py" in _where.SHIPPED)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            try:
                fn()
            except Exception:
                FAILED.append(name)
                print(f"FAIL {name} raised")
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    sys.exit(1 if FAILED else 0)
