"""One human decision must write at most one fact, and a full queue must say so.

    python3 test_decide_once.py

No pytest, no network, no model. Real sqlite stores in a temp dir, real
threads.

1. decide(id, True) USED TO BE A PLAIN CHECK-THEN-ACT: SELECT the row, see it
   is pending, then act - nothing claims it in between. Two concurrent calls
   for the same id (a double-tap, a retried request, two devices open on the
   same review card) could both pass the SELECT before either committed its
   UPDATE, and both would then write a fact. Nothing crashed - MemoryStore
   already serialises its own writers - it just silently duplicated a memory
   the owner decided about exactly once. Fixed by making the UPDATE the
   claim: only the caller whose UPDATE actually changes a row proceeds.

2. A PROPOSAL DROPPED FOR A FULL QUEUE USED TO LEAVE NO RECORD. propose()
   folded `pending_n >= cap` into the same `continue` as the dedupe check, so
   once the queue filled, every further proposal that pass produced went on
   the floor with nothing to show for it - `queue_full` stayed a boolean, and
   a client watching it could not tell "nothing new to learn" from "still
   learning things, and losing all of them". Counted now, in `setup_status`.
"""
import sys, tempfile, threading, time, traceback, types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# BACKEND is where the modules under test actually live - this folder
# in the dev container, $JARVIS_BACKEND on a real install. REPO is this
# repository. They used to be the same path and are not on the machine
# that runs Jarvis.
from _where import BACKEND, REPO, missing, explain

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-decide-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
sys.modules.setdefault("jarvis_framework", fw)

import jarvis_memory as M
import jarvis_extract as X

HUD = BACKEND / "jarvis_hud.py"
FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def fresh():
    d = Path(tempfile.mkdtemp(prefix="jarvis-decide-db-"))
    s = M.MemoryStore(path=d / "memory.db")
    M._store = s
    # _dropped_full is a module-level running total, by design (it counts
    # across the whole process, not per store) - reset it here so each test
    # starts from a known state instead of inheriting a prior test's count.
    X._dropped_full = 0
    return s


def propose_one(text):
    import json as _j
    return X.propose(
        [{"role": "user", "content": text}],
        llm=lambda _p: _j.dumps({"facts": [{"text": text, "confidence": 0.9}]}))


def t_concurrent_accepts_write_one_fact():
    """A `threading.Barrier` releases every thread in the same instant,
    forcing the interleaving the original bug depended on rather than hoping
    `t.start()`'s natural stagger happens to produce it. Without the barrier
    this test passed even against the unpatched code on a fast local sqlite
    file - not because the race was fixed, but because ten threads starting
    in a loop rarely land inside the actual window. With it, the unpatched
    code fails this every time (12 threads, 12 duplicate facts, measured)."""
    fresh()
    propose_one("Mario drives a 1998 Volvo, a fact with enough words in it")
    pend = X.pending()
    if not pend:
        return check("a fact was proposed to decide on", False, "nothing proposed")
    pid = pend[0]["id"]

    n = 12
    barrier = threading.Barrier(n)
    results = []
    lock = threading.Lock()

    def worker():
        barrier.wait()
        r = X.decide(pid, True)
        with lock:
            results.append(r)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    winners = [r for r in results if r]
    check("exactly one caller wins the decision", len(winners) == 1,
          f"results={results}")
    check(f"every loser sees None, like an already-decided proposal",
          results.count(None) == n - 1, f"results={results}")
    check("exactly one fact was actually written",
          M._store.status()["facts"] == 1,
          f"facts={M._store.status()['facts']}")


def t_a_rejected_proposal_cannot_be_raced_into_acceptance():
    """decide(id, False) then decide(id, True) on the same id: the second
    call must not resurrect a proposal that is no longer pending."""
    fresh()
    propose_one("Mario prefers tabs over spaces in every language he touches")
    pid = X.pending()[0]["id"]
    check("reject succeeds", X.decide(pid, False) == 0)
    check("a later accept on the same id is refused, not honoured",
          X.decide(pid, True) is None)
    check("nothing was written", M._store.status()["facts"] == 0)


def t_a_full_queue_is_counted_not_just_flagged():
    fresh()
    keep = X._cfg
    X._cfg = lambda k, d=None: {"enabled": True, "review_queue_max": 1}.get(k, d)
    try:
        propose_one("Mario's first fact, safely under the cap of one")
        check("the first proposal is queued", len(X.pending()) == 1)
        st = X.setup_status()
        check("queue_full is true at the cap", st["queue_full"] is True)
        check("no drops yet - the cap was not exceeded", "dropped_full" not in st,
              f"status={st}")

        propose_one("Mario's second fact, which the full queue must drop")
        st = X.setup_status()
        check("the second proposal is not queued", len(X.pending()) == 1)
        check("the drop is counted", st.get("dropped_full") == 1, f"status={st}")
        check("and explained in words",
              "review queue was already full" in str(st.get("dropped_full_note", "")))

        propose_one("Mario's third fact, a second drop for the same reason")
        st = X.setup_status()
        check("the counter accumulates rather than resetting",
              st.get("dropped_full") == 2, f"status={st}")
    finally:
        X._cfg = keep


def t_dropped_full_is_quiet_when_nothing_was_dropped():
    fresh()
    propose_one("Mario's only fact, nowhere near any cap")
    st = X.setup_status()
    check("no dropped_full key when nothing was dropped",
          "dropped_full" not in st, f"status={st}")


def main():
    for fn in (t_concurrent_accepts_write_one_fact,
               t_a_rejected_proposal_cannot_be_raced_into_acceptance,
               t_a_full_queue_is_counted_not_just_flagged,
               t_dropped_full_is_quiet_when_nothing_was_dropped):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
