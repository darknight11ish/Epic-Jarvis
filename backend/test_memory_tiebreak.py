"""test_memory_tiebreak.py - milestone 12: "said again" as a small tie-breaker.

    python3 backend/test_memory_tiebreak.py

When chat recall's merged ranking gives two of the facts it chose exactly
the same score, the one the owner has said again more often may go first
(jarvis_memory.py, "Said again as a tie-breaker"). Off by default.

What it proves, words only (no model):

1. OFF (the default): search, and chat recall, return exactly what they
   returned before - the same facts in the same order - even with "said
   again" rows in the file.
2. ON: a fact said again wins a real tie (two facts the fusion scored the
   same), and nothing else moves: a fact said again many times never passes
   one that scored higher, and the tie-break never undoes the re-ranker.
3. ON never adds, drops or hides a fact: for every question here, the set
   of facts and their number are the same as with it off.
4. Only chat recall asks for it (search(said_again=True), through
   jarvis_past.recall); a plain search and find_one() never do.

WHAT IT DOES NOT PROVE: that it helps. That is the memory self-test's job
(`python backend/eval_memory.py`, the "said again" line), with the real
embedding model on the PC.
"""
import os
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("rebuilt/jarvis_memory.py", "jarvis_past.py")
sys.path.insert(0, str(HERE / "rebuilt"))
os.environ.setdefault("JARVIS_NO_EMBED", "1")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-tiebreak-"))
os.environ["JARVIS_MEMORY_DB"] = str(_TMP / "memory.db")
_fw = types.ModuleType("jarvis_framework")
_fw.CONFIG_DIR = _TMP
_fw.LOG_DIR = _TMP
_fw.audit_log = lambda *a, **k: None
_fw.load_framework = lambda *a, **k: {}
sys.modules.setdefault("jarvis_framework", _fw)

import jarvis_memory as M  # noqa: E402
import jarvis_past as P    # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


_n = [0]

FACTS = ["Owner's sister is called Priya", "Priya plays the violin",
         "Priya plays the cello", "Owner plays the piano",
         "Owner drinks tea, not coffee", "Owner lives in York"]
QUESTIONS = ["what does Priya play?", "what does my sister play?", "Priya",
             "what do I play?", "where do I live?", "tea or coffee?", "why is the sky blue?"]


def store():
    _n[0] += 1
    st = M.MemoryStore(_TMP / f"m{_n[0]}.db", embedder=M.HashEmbedder())
    ids = [st.add(t, source="test") for t in FACTS]
    return st, ids


def ids_of(hits):
    return [h["id"] for h in hits]


def say_again(st, fid, times):
    """`times` turns after the fact was saved (said_again() counts only
    those), each one a row."""
    created = float(st.get(fid)["created"])
    for i in range(times):
        assert st.said_again(fid, created + 1 + i, "typed"), (fid, i)
    assert st.said_again_counts([fid]).get(fid, {}).get("count", 0) >= times


class _Switch:
    """JARVIS_MEMORY_SAID_AGAIN_TIEBREAK for the length of a with-block."""

    def __init__(self, on):
        self.on = on

    def __enter__(self):
        self.keep = M._SAID_AGAIN_TIEBREAK
        M._SAID_AGAIN_TIEBREAK = self.on

    def __exit__(self, *exc):
        M._SAID_AGAIN_TIEBREAK = self.keep


def everything(st):
    """Every question, as chat recall and as the eval's direct search ask it."""
    out = {}
    for q in QUESTIONS:
        out[("recall", q)] = ids_of(P.recall(st, q, k=5))
        out[("search", q)] = ids_of(st.search(q, k=5, entities=True, said_again=True))
        out[("k2", q)] = ids_of(st.search(q, k=2, entities=True, said_again=True))
    return out


# ============================================================ 1. off ==

def t_off_by_default():
    check("off unless JARVIS_MEMORY_SAID_AGAIN_TIEBREAK is 1",
          os.environ.get("JARVIS_MEMORY_SAID_AGAIN_TIEBREAK") is not None
          or M._SAID_AGAIN_TIEBREAK is False, M._SAID_AGAIN_TIEBREAK)


def t_off_is_the_old_order():
    st, ids = store()
    with _Switch(False):
        before = everything(st)
        say_again(st, ids[2], 3)             # the cello, tied with the violin
        say_again(st, ids[3], 5)             # the piano, scored lower
        after = everything(st)
    check("off: every question, the same facts in the same order with 'said again' rows",
          before == after, [(k, before[k], after[k]) for k in before if before[k] != after[k]])
    plain = {q: ids_of(st.search(q, k=5, entities=True)) for q in QUESTIONS}
    check("off: said_again=True is exactly a search without it",
          all(plain[q] == after[("search", q)] for q in QUESTIONS))


# ============================================================= 2. on ==

def t_on_a_repeated_fact_wins_a_tie():
    st, ids = store()
    violin, cello = ids[1], ids[2]
    q = "what does Priya play?"
    hits = st.search(q, k=5, entities=True)
    score = {h["id"]: h["score"] for h in hits}
    check("setup: the fusion scores the violin and the cello the same, violin first",
          ids_of(hits)[:2] == [violin, cello] and score[violin] == score[cello], hits)
    say_again(st, cello, 2)
    with _Switch(True):
        got = ids_of(st.search(q, k=5, entities=True, said_again=True))
        check("on: the cello, said again twice, now comes before the violin",
              got[:2] == [cello, violin], got)
        check("... through chat recall too", ids_of(P.recall(st, q, k=5))[:2] == [cello, violin])
        say_again(st, violin, 3)
        got = ids_of(st.search(q, k=5, entities=True, said_again=True))
        check("on: said again more often wins (violin 3 > cello 2)",
              got[:2] == [violin, cello], got)


def t_on_never_passes_a_higher_score():
    st, ids = store()
    q = "what does Priya play?"
    base = st.search(q, k=5, entities=True)
    lowest = base[-1]["id"]
    say_again(st, lowest, 9)
    with _Switch(True):
        got = st.search(q, k=5, entities=True, said_again=True)
    check("a fact said again nine times but scored lower stays where it was",
          ids_of(got)[-1] == lowest and len(got) == len(base), (ids_of(base), ids_of(got)))
    s = [h["score"] for h in got]
    check("the list is still in score order (ties only moved within themselves)",
          s == sorted(s, reverse=True), s)


def t_on_never_undoes_the_reranker():
    st, ids = store()
    violin, cello = ids[1], ids[2]
    say_again(st, cello, 4)

    class Prefer(M.Reranker):
        name = "prefer violin"

        def score(self, query, texts):
            return [1.0 if "violin" in t else 0.0 for t in texts]
    M.set_reranker(Prefer())
    try:
        with _Switch(True):
            got = ids_of(st.search("what does Priya play?", k=5, entities=True,
                                   rerank=True, said_again=True))
        check("the re-ranker put the violin first; the cello's repeats do not undo that",
              got[0] == violin, got)
    finally:
        M.set_reranker(None)


# ============================================================ 3. same set ==

def t_on_never_adds_or_drops():
    st, ids = store()
    for fid, n in zip(ids, (1, 3, 2, 5, 4, 6)):
        say_again(st, fid, n)
    with _Switch(False):
        off = everything(st)
    with _Switch(True):
        on = everything(st)
    check("on: every question, the same facts and the same number as off",
          all(sorted(off[k]) == sorted(on[k]) for k in off),
          [(k, off[k], on[k]) for k in off if sorted(off[k]) != sorted(on[k])])
    check("... including at k=2, where a tie could straddle the cut",
          all(sorted(off[("k2", q)]) == sorted(on[("k2", q)]) for q in QUESTIONS))
    check("... and 'why is the sky blue?' is still none at all",
          on[("recall", "why is the sky blue?")] == [])
    check("... and something did move (the test is not vacuous)",
          any(off[k] != on[k] for k in off))


# ============================================================ 4. who asks ==

def t_only_chat_recall_asks():
    st, ids = store()
    violin, cello = ids[1], ids[2]
    say_again(st, cello, 2)
    q = "what does Priya play?"
    with _Switch(True):
        check("a plain search does not use it",
              ids_of(st.search(q, k=5, entities=True))[:2] == [violin, cello])
        one = st.find_one("Priya plays the violin")
        check("find_one still finds the same fact", one and one["id"] == violin, one)
    seen = []

    class Rec:
        def search(self, q, k=8, **kw):
            seen.append(dict(kw))
            return []
    P.recall(Rec(), "what does Priya play?", k=5)
    check("jarvis_past.recall asks for it", seen and seen[0].get("said_again") is True, seen)

    class Old:
        """A store from before it."""
        def search(self, q, k=8, entities=False, rerank=False, **kw):
            if kw:
                raise TypeError("unexpected keyword")
            return [{"id": 1, "text": "Owner lives in York", "current": True}]
    got = P.recall(Old(), "Where do I live?", k=5)
    check("a store from before it: the search without it, same facts",
          [h["text"] for h in got] == ["Owner lives in York"], got)


def t_a_failure_is_the_old_order():
    st, ids = store()
    say_again(st, ids[2], 2)
    q = "what does Priya play?"
    base = ids_of(st.search(q, k=5, entities=True))
    real = st.said_again_counts

    def boom(_ids):
        raise RuntimeError("disk")
    st.said_again_counts = boom
    try:
        with _Switch(True):
            got = ids_of(st.search(q, k=5, entities=True, said_again=True))
        check("a failure reading the counts: the order as it was", got == base, (base, got))
    finally:
        st.said_again_counts = real


def main():
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            try:
                fn()
            except Exception:
                FAILED.append(name)
                print(f"FAIL  {name} raised")
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
