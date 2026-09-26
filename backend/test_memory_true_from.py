"""test_memory_true_from.py - memory idea 4: real "true from" dates, and
older news never replaces newer news. Plus the bug fixed with it.

    python3 backend/test_memory_true_from.py

What it proves:

1. THE BUG (verified before the fix, 2026-09-26): retire() and
   add(supersedes=...) matched `valid_to IS NULL` only, so a fact whose
   valid_to is in the FUTURE - still in use, like a lease that ends in
   December - could never be forgotten, corrected or retired by a "stop
   using this fact?" card. They now match `valid_to IS NULL OR valid_to >
   now`, the rule every reader uses. (edit() had the same test and is fixed
   too.) The three checks marked "the bug" fail on the code before.
2. true_from(): the owner's words say WHEN something became true -
   "I moved to Leeds in January", told in March - read by fixed rules, no
   model. A plan, a future date, a fact that only mentions a date, two
   dates: none. NEVER a future date.
3. add() stores it: valid_from is that date (meta true_from "said"), and a
   correction with a real date ends the old fact on that date, not on the
   day Jarvis was told.
4. Older news never replaces newer news (Graphiti's rule): a correction
   whose words date it BEFORE the fact it would replace (both dates from
   the owner's words) is saved as history - it ended when the newer one
   began - and the newer fact stays in use. The card says so first.
5. Questions about the past use the real dates ("what phone did I have in
   June?"), through jarvis_past unchanged.
"""
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
from _where import require_shipped  # noqa: E402

require_shipped("rebuilt/jarvis_memory.py", "jarvis_past.py", "jarvis_intake.py")
sys.path.insert(0, str(HERE / "rebuilt"))
os.environ.setdefault("JARVIS_NO_EMBED", "1")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-true-from-"))
_AUDIT = []
_fw = sys.modules.get("jarvis_framework")
if _fw is None:
    _fw = types.ModuleType("jarvis_framework")
    _fw.LOG_DIR = _TMP
    _fw.load_framework = lambda *a, **k: {}
    sys.modules["jarvis_framework"] = _fw
_fw.CONFIG_DIR = _TMP
_fw.audit_log = lambda event, data=None, **k: _AUDIT.append((event, data))

import jarvis_memory as M  # noqa: E402
import jarvis_past as P    # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


_n = [0]


def store():
    _n[0] += 1
    return M.MemoryStore(_TMP / f"m{_n[0]}.db", embedder=M.HashEmbedder())


def day(text, hour=12):
    y, m, d = (int(x) for x in text.split("-"))
    return time.mktime((y, m, d, hour, 0, 0, 0, 0, -1))


def midnight(text):
    return day(text, 0)


def iso(ts):
    return time.strftime("%Y-%m-%d", time.localtime(ts)) if ts else None


class Clock:
    """jarvis_memory's `time`, with time() fixed - to add a fact on a day."""

    def __init__(self, at):
        self.at = at
        self._real = M.time

    def time(self):
        return self.at

    def __getattr__(self, n):
        return getattr(self._real, n)

    def __enter__(self):
        M.time = self
        return self

    def __exit__(self, *a):
        M.time = self._real


def lease(st, text, ends_in_days=60):
    """A current fact whose valid_to is in the future."""
    fid = st.add(text, source="test")
    c = st._connect()
    try:
        c.execute("UPDATE facts SET valid_to=? WHERE id=?",
                  (time.time() + ends_in_days * 86400, fid))
    finally:
        c.close()
    return fid


# ============================================================= 1. the bug ==

def t_the_bug_a_fact_that_ends_later_can_be_retired():
    st = store()
    fid = lease(st, "Owner rents the flat on Micklegate until December")
    check("the lease is in use today (the rule every reader uses)",
          fid in [f["id"] for f in st.current_facts()])
    check("the bug: retire() retires a fact whose valid_to is in the future",
          st.retire(fid) is True, st.get(fid))
    row = st.get(fid)
    check("... it is no longer in use, and both dates are stamped now",
          fid not in [f["id"] for f in st.current_facts()]
          and row["valid_to"] <= time.time() and row["retired_at"] is not None, row)
    check("... retiring it again is still a no-op (one-way)", st.retire(fid) is False)


def t_the_bug_a_fact_that_ends_later_can_be_corrected():
    st = store()
    old = lease(st, "Owner rents the flat on Micklegate until December")
    new = st.add("Owner rents the flat on Gillygate", source="test", supersedes=old)
    row = st.get(old)
    check("the bug: add(supersedes=) retires a fact whose valid_to is in the future",
          row["valid_to"] <= time.time() and row["retired_by"] == new
          and st.last_supersede_failed is False, row)
    check("... only the correction is in use",
          [f["id"] for f in st.current_facts()] == [new])


def t_the_bug_a_fact_that_ends_later_can_be_edited():
    st = store()
    fid = lease(st, "Owner rents the flat on Micklegate until December")
    check("the bug: edit() rewords a fact that is still in use, even if it ends later",
          st.edit(fid, "Owner rents the flat on Micklegate until January")
          and st.get(fid)["text"].endswith("January"))
    st.retire(fid)
    check("... a retired fact still cannot be edited (history stays as it was)",
          st.edit(fid, "rewritten") is False)


# ========================================================= 2. true_from ==

def t_true_from_reads_the_owners_words():
    now = day("2026-03-10")
    cases = [
        ("Owner moved to Leeds in January", "2026-01-01"),
        ("Owner moved to Leeds in January (as of 2023-05-01)", "2023-01-01"),
        ("Owner has had allotment plot 14 since March 2026", "2026-03-01"),
        ("Owner got allotment plot 9 in January 2026", "2026-01-01"),
        ("Owner started a new job yesterday (2026-03-09)", "2026-03-09"),
        ("Owner moved house three months ago (around 2025-12-10)", "2025-12-10"),
        ("Owner joined a book club last month (2026-02)", "2026-02-01"),
        ("Owner went back to college last year (2025)", None),     # "went" is no change word
        ("Owner switched to Fedora last year (2025)", "2025-01-01"),
        ("Owner has worked at Ridgeline since 2019", "2019-01-01"),
        ("Owner started at Acme on 14 February 2026", "2026-02-14"),
        ("Owner started at Acme on February 14, 2026", "2026-02-14"),
        ("Owner moved to York last March", "2025-03-01"),
        ("Owner moved to York in May", "2025-05-01"),               # the May that has begun
        ("Owner is moving to Leeds in March", None),                # a plan: true now
        ("Owner will start at Acme in January", None),
        ("Owner is going to switch to Fedora in April", None),
        ("Owner may have moved to York in 2021", None),              # a maybe
        ("Owner moved to York in 2027", None),                       # never a future date
        ("Owner started at Acme in April 2026", None),               # a month still to come
        ("Owner visited Iceland in 2023", None),                     # only mentions a date
        ("Owner's passport expires in January 2028", None),
        ("Owner got married in 2019 and moved to York in 2021", None),  # two dates
        ("Owner lives in York", None),
        ("", None),
    ]
    for text, want in cases:
        got = iso(M.true_from(text, now))
        check(f"{text!r} -> {want}", got == want, got)
    check("not text: None", M.true_from(None, now) is None and M.true_from(42, now) is None)


# ======================================================= 3. add() keeps it ==

def t_add_stores_the_true_from_date():
    st = store()
    with Clock(day("2026-03-10")):
        fid = st.add("Owner moved to Leeds in January", source="test")
        plain = st.add("Owner likes jazz", source="test")
        plan = st.add("Owner is moving to Hull in April", source="test")
    row = st.get(fid)
    check("valid_from is the date the words give; created is still the day it was told",
          iso(row["valid_from"]) == "2026-01-01" and iso(row["created"]) == "2026-03-10", row)
    check("... and the fact says where the date came from (meta true_from)",
          json.loads(row["meta"]).get("true_from") == "said", row["meta"])
    for fid2, what in ((plain, "no date"), (plan, "a plan")):
        r = st.get(fid2)
        check(f"{what}: valid_from is the day it was told, as before",
              r["valid_from"] == r["created"] and "true_from" not in json.loads(r["meta"]))
    with Clock(day("2026-03-10")):
        given = st.add("Owner moved to Leeds in January", source="test",
                       valid_from=day("2025-12-01"))
    check("a caller's own valid_from always wins", st.get(given)["valid_from"] == day("2025-12-01"))
    check("erase keeps the true_from mark (a label, not words)",
          "true_from" in M.ERASE_KEEPS_META)


def t_a_dated_correction_ends_the_old_fact_on_that_date():
    st = store()
    with Clock(day("2025-06-20")):
        old = st.add("Owner lives in Harrogate", source="test")
    with Clock(day("2026-03-01")):
        new = st.add("Owner moved to York in January 2026", source="test", supersedes=old)
    row = st.get(old)
    check("the old fact stopped being true when the words say (January), and Jarvis "
          "learned it on the day it was told (March)",
          iso(row["valid_to"]) == "2026-01-01" and iso(row["retired_at"]) == "2026-03-01"
          and row["retired_by"] == new, row)
    with Clock(day("2026-03-01")):
        st2 = store()
        a = st2.add("Owner lives in Harrogate", source="test")
        b = st2.add("Owner lives in York", source="test", supersedes=a)
    check("no date in the words: ended the day it was told, exactly as before",
          st2.get(a)["valid_to"] == st2.get(a)["retired_at"] == st2.get(b)["created"])


# ========================================================= 4. older news ==

def t_older_news_never_replaces_newer_news():
    st = store()
    with Clock(day("2026-04-01")):
        newer = st.add("Owner has had allotment plot 14 since March 2026", source="test")
    _AUDIT.clear()
    with Clock(day("2026-08-01")):
        older = st.add("Owner got allotment plot 9 in January 2026", source="test",
                       supersedes=newer)
    check("the newer fact stays in use", st.get(newer)["valid_to"] is None
          and newer in [f["id"] for f in st.current_facts()], st.get(newer))
    row = st.get(older)
    check("the older news is saved as history: true from January until the newer one "
          "began (March), never in use", iso(row["valid_from"]) == "2026-01-01"
          and iso(row["valid_to"]) == "2026-03-01" and row["retired_at"] is not None
          and older not in [f["id"] for f in st.current_facts()], row)
    check("... linked to the newer fact, so its history and Erase reach it",
          row["retired_by"] == newer and older in st._earlier_wordings(newer))
    check("the store says what happened: not a failed correction, older news",
          st.last_older_news is True and st.last_supersede_failed is False)
    check("the audit log says so, with ids only",
          ("memory.older_news", {"new": older, "kept": newer}) in _AUDIT, _AUDIT)
    # Not older news when either date is only the day Jarvis was told.
    st2 = store()
    with Clock(day("2026-04-01")):
        told = st2.add("Owner has allotment plot 14", source="test")
    with Clock(day("2026-08-01")):
        corr = st2.add("Owner got allotment plot 9 in January 2026", source="test",
                       supersedes=told)
    check("the old fact's date is only when Jarvis was told: an ordinary correction",
          st2.get(told)["valid_to"] is not None and st2.last_older_news is False
          and corr in [f["id"] for f in st2.current_facts()])


def t_the_card_says_it_sounds_older_first():
    import jarvis_intake as I
    st = store()
    keep = getattr(M, "_store", None)
    M._store = st
    try:
        with Clock(day("2026-04-01")):
            newer = st.add("Owner has had allotment plot 14 since March 2026", source="test")
        row = {"id": 1, "text": "Owner got allotment plot 9 in January 2026",
               "replaces_id": newer, "created": day("2026-08-01"), "source": "conversation"}
        note = I.older_news_note(row, st)
        check("a correction card that sounds older says so, with both dates",
              "older" in note.lower() and "2026-01-01" in note and "2026-03-01" in note, note)
        plain = dict(row, text="Owner got allotment plot 9 in April 2026")
        check("a correction that is newer: nothing added", I.older_news_note(plain, st) == "")
        check("a card that replaces nothing: nothing added",
              I.older_news_note(dict(row, replaces_id=None), st) == "")
        rows = I.annotate([dict(row)])
        check("annotate() puts it where both apps already show a card's reason",
              rows[0].get("older_news") is True and note in rows[0].get("auto_reason", ""),
              rows[0])
    finally:
        M._store = keep


# ======================================================== 5. past questions ==

def t_b12_keeping_a_correction_card_on_a_fact_that_ends_later():
    """The memory review of 2026-09-27, B12: memory-safety.patch's _accept
    (as the whole patch stack leaves jarvis_extract.py) dropped the
    correction's target when its valid_to was set at all - so keeping a
    correction card on a fact that ENDS later (a lease to December) left
    the old fact in use beside the new one. Failed before the fix."""
    from contextlib import closing
    import eval_learner as E
    x = E._extract_stand_in(M)
    st = store()
    old = lease(st, "Owner rents the flat on Micklegate", ends_in_days=90)
    with closing(st._connect()) as c:
        E._proposals_table(c)
        cur = c.execute("INSERT INTO proposals (text, source, created, replaces_id,"
                        " replaces_text) VALUES (?,?,?,?,?)",
                        ("Owner rents the flat on Gillygate", "conversation", time.time(),
                         old, "Owner rents the flat on Micklegate"))
        row = dict(c.execute("SELECT * FROM proposals WHERE id=?",
                             (cur.lastrowid,)).fetchone())
        new = x._accept(c, st, row)                 # the owner keeps the card
        c.commit()
    was = st.get(old)
    check("B12: the old fact is retired by the correction (retired_by = the new fact)",
          was["retired_by"] == new, was)
    check("B12: ... and is no longer in use",
          old not in [f["id"] for f in st.current_facts()], st.current_facts())
    ended = st.add("Owner rented a garage on Clifton", source="test")
    st.retire(ended)
    with closing(st._connect()) as c:
        cur = c.execute("INSERT INTO proposals (text, source, created, replaces_id,"
                        " replaces_text) VALUES (?,?,?,?,?)",
                        ("Owner rents a garage on Bootham", "conversation", time.time(),
                         ended, "Owner rented a garage on Clifton"))
        row = dict(c.execute("SELECT * FROM proposals WHERE id=?",
                             (cur.lastrowid,)).fetchone())
        x._accept(c, st, row)
        c.commit()
    check("guard: a fact that has already ended is not re-pointed",
          st.get(ended)["retired_by"] is None, st.get(ended))


def t_questions_about_the_past_use_the_real_dates():
    st = store()
    with Clock(day("2025-08-01")):
        old = st.add("Owner's phone is an iPhone 12", source="test")
    with Clock(day("2026-07-20")):
        st.add("Owner switched from the iPhone 12 to a Pixel 8 in June 2026", source="test",
               supersedes=old)
    now = day("2026-09-24")
    june = [h["text"] for h in P.recall(st, "What phone did I have in June?", k=5, now=now)]
    check("\"what phone did I have in June?\": not the iPhone (it ended on 1 June)",
          not any("no longer true" in t and "iPhone 12\" " in t for t in june)
          and not any(t.startswith("Owner's phone is an iPhone 12") for t in june), june)
    march = [h["text"] for h in P.recall(st, "What phone did I have in March?", k=5, now=now)]
    check("\"... in March?\": the iPhone, labelled with the day it really stopped",
          "Owner's phone is an iPhone 12 (no longer true since 2026-06-01)" in march, march)


if __name__ == "__main__":
    import shutil
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        sys.exit(1)
