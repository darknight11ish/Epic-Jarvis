"""test_memory_rerank.py - memory idea 1: a small re-ranker over the top facts.

    python3 backend/test_memory_rerank.py

What it proves, with stand-in re-rankers (no model is downloaded here):

1. Chat recall (jarvis_past.recall) asks for it; nothing else does -
   find_one(), timeline(), the learner's candidates and "said again" never
   re-rank.
2. It only RE-ORDERS the facts search already found: the pool is the top
   RERANK_POOL facts that pass every filter, the first k are kept, no fact
   outside the pool, no retired or erased fact, k=0 is none at all.
3. It fails soft, every way: no re-ranker loaded (yet) is exactly the old
   order; one that raises, answers the wrong number of scores or a NaN is
   the old order; one slower than RERANK_BUDGET_S is not waited for; one
   still busy with an earlier question is skipped, not queued.
4. It is OFF by default (2026-09-26: kept only once the PC's self-test
   shows it helps) - nothing is loaded and recall is the merged order -
   and JARVIS_MEMORY_RERANK=1 turns it on. The self-test still measures it.
   When on, loading never blocks a chat: the first question starts the load
   on a background thread and gets the old order at once. A load that
   fails is said ONCE (the audit log) and recall stays as it was; status()
   says why.
5. The model is the one the research named: Xenova/ms-marco-MiniLM-L-6-v2.

WHAT IT DOES NOT PROVE: how much the real model helps, or how fast it is on
the owner's processor. The model cannot be downloaded in this container;
`python backend/eval_memory.py` on the PC measures both.
"""
import os
import sys
import tempfile
import threading
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("rebuilt/jarvis_memory.py", "jarvis_past.py")
sys.path.insert(0, str(HERE / "rebuilt"))
os.environ.setdefault("JARVIS_NO_EMBED", "1")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-rerank-"))
_AUDIT = []
_fw = types.ModuleType("jarvis_framework")
_fw.CONFIG_DIR = _TMP
_fw.LOG_DIR = _TMP
_fw.audit_log = lambda event, data=None, **k: _AUDIT.append((event, data))
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


def store(*texts):
    _n[0] += 1
    st = M.MemoryStore(_TMP / f"m{_n[0]}.db", embedder=M.HashEmbedder())
    ids = [st.add(t, source="test") for t in texts]
    return st, ids


def ids_of(hits):
    return [h["id"] for h in hits]


class Reverse(M.Reranker):
    """Scores the merged order backwards: the last candidate first."""
    name = "reverse"

    def __init__(self):
        self.calls = []

    def score(self, query, texts):
        self.calls.append((query, list(texts)))
        return [float(i) for i in range(len(texts))]


class Prefer(M.Reranker):
    """Scores a fact 1.0 when it holds `word`, else 0."""
    name = "prefer"

    def __init__(self, word):
        self.word = word

    def score(self, query, texts):
        return [1.0 if self.word in t.lower() else 0.0 for t in texts]


def _reset():
    M.set_reranker(None)
    with M._rr_lock:
        M._rr.update(state="not started", model=None, why="", said=False, slow=0, used=0)


FACTS = ["Owner plays tennis on Mondays", "Owner's tennis coach is called Rita",
         "Owner bought tennis shoes in May", "Owner watched tennis at Wimbledon",
         "Owner's tennis club is in Hull", "Owner likes tea"]


# ========================================================= 1. who asks ==

def t_chat_recall_asks_and_nothing_else_does():
    _reset()
    M.set_reranker(None)          # asked for, but nothing is loaded here
    seen = []

    class Rec:
        def search(self, q, k=8, **kw):
            seen.append(dict(kw))
            return []
    P.recall(Rec(), "who is my tennis coach?", k=5)
    check("jarvis_past.recall asks for the re-ranker (and the entity layer)",
          seen and seen[0].get("rerank") is True and seen[0].get("entities") is True, seen)

    class Old:
        """A store from before the re-ranker."""
        def search(self, q, k=8, entities=False, **kw):
            if kw:
                raise TypeError("unexpected keyword")
            return [{"id": 1, "text": "Owner lives in York", "current": True}]
    got = P.recall(Old(), "Where do I live?", k=5)
    check("a store from before it: the search without it, same facts",
          [h["text"] for h in got] == ["Owner lives in York"], got)
    st, ids = store(*FACTS)
    rr = Reverse()
    M.set_reranker(rr)
    try:
        st.find_one("Owner's tennis coach is called Rita")
        st.timeline("tennis")
        st.search("tennis", k=5)
        st.search("tennis", k=5, entities=True)
        check("find_one, timeline and a plain search never re-rank", rr.calls == [], rr.calls)
        P.recall(st, "tennis", k=5)
        check("... chat recall does", len(rr.calls) == 1, rr.calls)
    finally:
        _reset()


# ============================================= 2. only a better order ==

def t_it_only_reorders_the_pool():
    _reset()
    st, ids = store(*FACTS)
    plain = st.search("tennis", k=3, rerank=True)
    check("no re-ranker loaded: exactly the merged order",
          ids_of(plain) == ids_of(st.search("tennis", k=3)), (plain,))
    M.set_reranker(Reverse())
    try:
        full = ids_of(st.search("tennis", k=50))
        got = ids_of(st.search("tennis", k=3, rerank=True))
        check("the pool is re-ordered and the first k kept",
              len(got) == 3 and got == list(reversed(full))[:3], (full, got))
        check("never a fact search did not find", set(got) <= set(full), (full, got))
        M.set_reranker(Prefer("coach"))
        got = st.search("tennis", k=2, rerank=True)
        check("the fact the re-ranker scores best comes first",
              got[0]["text"] == "Owner's tennis coach is called Rita", got)
        check("k=0 is none at all", st.search("tennis", k=0, rerank=True) == [])
        st.retire(ids[1])
        got = [h["text"] for h in st.search("tennis", k=5, rerank=True)]
        check("a forgotten fact never comes back through it",
              "Owner's tennis coach is called Rita" not in got, got)
        st.erase(ids[2])
        got = [h["text"] for h in st.search("tennis", k=5, rerank=True)]
        check("nor an erased one", all("shoes" not in t and t != M.ERASED_TEXT for t in got),
              got)
    finally:
        _reset()


def t_the_pool_is_the_top_twenty():
    _reset()
    texts = [f"Owner has tennis racket number {i}" for i in range(30)]
    st, ids = store(*texts)
    rr = Reverse()
    M.set_reranker(rr)
    try:
        st.search("tennis racket", k=5, rerank=True)
        check(f"the re-ranker reads RERANK_POOL ({M.RERANK_POOL}) facts, not all 30",
              rr.calls and len(rr.calls[0][1]) == M.RERANK_POOL == 20, len(rr.calls[0][1]))
    finally:
        _reset()


# ============================================================ 3. soft ==

def t_it_fails_soft():
    _reset()
    st, ids = store(*FACTS)
    base = ids_of(st.search("tennis", k=3))

    class Boom(M.Reranker):
        def score(self, q, t):
            raise RuntimeError("broken model")

    class Short(M.Reranker):
        def score(self, q, t):
            return [1.0]

    class NaN(M.Reranker):
        def score(self, q, t):
            return [float("nan")] * len(t)

    class Bools(M.Reranker):
        def score(self, q, t):
            return [True] * len(t)
    try:
        for name, rr in (("one that raises", Boom()), ("the wrong number of scores", Short()),
                         ("a NaN", NaN()), ("true/false instead of numbers", Bools())):
            M.set_reranker(rr)
            check(f"{name}: the merged order", ids_of(st.search("tennis", k=3, rerank=True))
                  == base)
    finally:
        _reset()


def t_a_slow_one_is_not_waited_for():
    _reset()
    st, ids = store(*FACTS)
    base = ids_of(st.search("tennis", k=3))
    gate = threading.Event()

    class Slow(M.Reranker):
        def score(self, q, t):
            gate.wait(5)
            return [float(i) for i in range(len(t))]
    keep = M.RERANK_BUDGET_S
    M.RERANK_BUDGET_S = 0.2
    M.set_reranker(Slow())
    try:
        t0 = time.perf_counter()
        got = ids_of(st.search("tennis", k=3, rerank=True))
        took = time.perf_counter() - t0
        check("slower than the budget: the merged order, in about the budget",
              got == base and took < 1.5, (got, base, took))
        t0 = time.perf_counter()
        got = ids_of(st.search("tennis", k=3, rerank=True))
        check("still busy with the last question: skipped at once, not queued",
              got == base and time.perf_counter() - t0 < 0.15, time.perf_counter() - t0)
        check("status() counts it", M.reranker_status().get("slow") == 1,
              M.reranker_status())
    finally:
        gate.set()
        time.sleep(0.05)
        M.RERANK_BUDGET_S = keep
        _reset()


# ======================================================== 4. loading ==

class _On:
    """JARVIS_MEMORY_RERANK=1 for the length of a with-block."""

    def __enter__(self):
        self.keep = M._RERANK_ON
        M._RERANK_ON = True

    def __exit__(self, *exc):
        M._RERANK_ON = self.keep


def t_loading_never_blocks_a_chat():
    with _On():
        _loading_never_blocks_a_chat()


def _loading_never_blocks_a_chat():
    _reset()
    st, ids = store(*FACTS)
    base = ids_of(st.search("tennis", k=3))
    started = threading.Event()
    release = threading.Event()

    class SlowLoad(M.Reranker):
        name = "slow-load"

        def __init__(self):
            started.set()
            release.wait(5)

        def score(self, q, t):
            return [float(i) for i in range(len(t))]
    real = M.FastReranker
    M.FastReranker = SlowLoad
    try:
        t0 = time.perf_counter()
        got = ids_of(P.recall(st, "tennis", k=3))
        check("the first question starts the load and gets the old order at once",
              got == base and time.perf_counter() - t0 < 0.5 and started.wait(2),
              (got, time.perf_counter() - t0))
        check("... status() says it is loading", M.reranker_status()["state"] == "loading",
              M.reranker_status())
        release.set()
        for _ in range(100):
            if M.reranker_status()["state"] == "on":
                break
            time.sleep(0.02)
        got = ids_of(P.recall(st, "tennis", k=3))
        check("once loaded, recall uses it", got != base and M.reranker_status()["state"]
              == "on" and M.reranker_status()["model"] == "slow-load", (got, base))
    finally:
        release.set()
        M.FastReranker = real
        _reset()


def t_a_failed_load_is_said_once():
    with _On():
        _a_failed_load_is_said_once()


def _a_failed_load_is_said_once():
    _reset()
    st, ids = store(*FACTS)
    base = ids_of(st.search("tennis", k=3))

    def no_fastembed():
        raise ImportError("No module named 'fastembed'")
    real = M.FastReranker
    M.FastReranker = no_fastembed
    _AUDIT.clear()
    try:
        P.recall(st, "tennis", k=3)
        for _ in range(100):
            if M.reranker_status()["state"] == "off":
                break
            time.sleep(0.02)
        for _ in range(3):
            got = ids_of(P.recall(st, "tennis", k=3))
        check("no fastembed: recall is exactly as before", got == base, (got, base))
        said = [a for a in _AUDIT if a[0] == "memory.rerank_off"]
        check("said once, in the audit log", len(said) == 1, _AUDIT)
        s = st.status()["reranker"]
        check("status() says it is off, and why", s["state"] == "off"
              and "fastembed" in s["why"], s)
    finally:
        M.FastReranker = real
        _reset()


def t_it_is_off_by_default():
    """The owner's rule (CLAUDE.md, memory): a memory change is kept only
    once the self-test on the PC shows it helps. The re-ranker has only been
    measured as a stand-in, so it is off until JARVIS_MEMORY_RERANK=1."""
    import subprocess
    env = dict(os.environ)
    env.pop("JARVIS_MEMORY_RERANK", None)
    probe = ("import sys, types; sys.path[:0] = [%r, %r]; "
             "fw = types.ModuleType('jarvis_framework'); fw.CONFIG_DIR = fw.LOG_DIR = %r; "
             "fw.audit_log = lambda *a, **k: None; fw.load_framework = lambda *a, **k: {}; "
             "sys.modules['jarvis_framework'] = fw; import jarvis_memory as M; "
             "import time; M.FastReranker = lambda: time.sleep(3); "
             "print(M._RERANK_ON, M.reranker() is None, M.reranker_status()['state'])"
             % (str(HERE / "rebuilt"), str(HERE), str(_TMP)))
    for value, want in ((None, "False True off"), ("0", "False True off"),
                        ("1", "True True loading"), ("yes", "True True loading")):
        e = dict(env, JARVIS_NO_EMBED="1")
        if value is not None:
            e["JARVIS_MEMORY_RERANK"] = value
        r = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                           timeout=120, env=e, cwd=str(_TMP))
        got = (r.stdout.strip().splitlines() or [""])[-1]
        check(f"JARVIS_MEMORY_RERANK={value if value is not None else '(not set)'}: "
              f"on/none-yet/state = {want}", got == want, (got, r.stderr[-400:]))
    _reset()
    keep = M._RERANK_ON
    M._RERANK_ON = False
    try:
        st, ids = store(*FACTS)
        base = ids_of(st.search("tennis", k=3))
        check("off: no re-ranker, nothing is loaded, recall is the merged order",
              M.reranker() is None and M._rr["state"] == "not started"
              and ids_of(P.recall(st, "tennis", k=3)) == base)
        s = M.reranker_status()
        check("off: status() says so, and how to turn it on",
              s["state"] == "off" and "JARVIS_MEMORY_RERANK=1" in s["why"]
              and "self-test" in s["why"], s)
        M.set_reranker(Reverse())
        check("off: a re-ranker the self-test sets is still used (so it can be measured)",
              ids_of(P.recall(st, "tennis", k=3)) != base
              and M.reranker_status()["state"] == "on")
    finally:
        M._RERANK_ON = keep
        _reset()


# ========================================================== 5. model ==

def t_the_model_is_the_one_the_research_named():
    check("Xenova/ms-marco-MiniLM-L-6-v2 (Apache-2.0, about 80 MB)",
          M.RERANK_MODEL == "Xenova/ms-marco-MiniLM-L-6-v2")
    src = (HERE / "rebuilt" / "jarvis_memory.py").read_text(encoding="utf-8")
    check("fastembed's own cross-encoder, imported only when it is loaded",
          "from fastembed.rerank.cross_encoder import TextCrossEncoder" in src
          and src.index("from fastembed.rerank") > src.index("class FastReranker"))


def t_the_self_test_loads_it_even_though_it_is_off():
    """`eval_memory.py --reranker auto` (the default) is how the owner finds
    out whether it helps, so it must load the real model even while the
    backend keeps it off."""
    sys.path.insert(0, str(HERE))
    import eval_memory as E

    class Loaded(M.Reranker):
        name = "stand-in for the real model"

    real, keep = M.FastReranker, M._RERANK_ON
    M.FastReranker, M._RERANK_ON = Loaded, False
    _reset()
    try:
        m, what = E._pick_reranker(M, "auto")
        check("--reranker auto loads the real model while the backend has it off",
              isinstance(m, Loaded) and what == Loaded.name, (m, what))

        def no_fastembed():
            raise ImportError("No module named 'fastembed'")
        M.FastReranker = no_fastembed
        m, what = E._pick_reranker(M, "auto")
        check("... and says why when it cannot", m is None and "fastembed" in what, what)
    finally:
        M.FastReranker, M._RERANK_ON = real, keep
        _reset()


def t_the_self_test_measures_it():
    """eval_memory.py: with the stand-in (the real model cannot download
    here) the re-ranked line is measured and labelled a stand-in; with no
    re-ranker at all it says why it was not measured."""
    import json
    import subprocess
    out = _TMP / "eval-out"
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.pop("JARVIS_MEMORY_DB", None)
    r = subprocess.run([sys.executable, str(HERE / "eval_memory.py"), "--sizes", "0",
                        "--words-only", "--reranker", "stand-in", "--out", str(out)],
                       capture_output=True, text=True, timeout=600, env=env)
    check("eval_memory.py --reranker stand-in runs", r.returncode == 0, r.stderr[-800:])
    js = sorted(out.glob("memory-eval-*.json"))
    res = json.loads(js[-1].read_text(encoding="utf-8")) if js else {}
    lv = (res.get("levels") or [{}])[0]
    check("the re-ranked line is measured, beside the one without",
          res.get("reranker_measured") and "reranked" in lv and "entities" in lv
          and "search_p50_ms" in lv.get("reranked", {}), res.get("reranker"))
    md = sorted(out.glob("memory-eval-*.md"))
    text = md[-1].read_text(encoding="utf-8") if md else ""
    check("... and the report says it is a stand-in, not the real model",
          "STAND-IN" in text and "not the real model" in text)
    r = subprocess.run([sys.executable, str(HERE / "eval_memory.py"), "--sizes", "0",
                        "--words-only", "--reranker", "off", "--out", str(out / "off")],
                       capture_output=True, text=True, timeout=600, env=env)
    js = sorted((out / "off").glob("memory-eval-*.json"))
    res = json.loads(js[-1].read_text(encoding="utf-8")) if js else {}
    check("--reranker off: not measured, and it says so",
          r.returncode == 0 and res.get("reranker_measured") is False
          and "off" in str(res.get("reranker")), res.get("reranker"))


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
