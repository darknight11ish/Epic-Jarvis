"""Two refinements taken from projects that hit the problem first.

    python3 test_memory_noise.py

No pytest, no network, no model. Real sqlite stores in a temp dir.

1. A DISCARDED PROPOSAL MUST STAY DISCARDED. propose() deduped against
   state='pending' only. The learner re-reads the whole conversation on each
   pass, and the transcript grows every turn, so the "nothing new was said"
   guard does not stop it: the model proposes the same fact from the same
   sentence again and it is back within the minute. A review queue that
   re-asks what you just declined trains you to stop reading it. Open WebUI
   #18603 is users asking to switch memory off entirely for adjacent reasons.

2. RECALLED FACTS CARRY THEIR DATE. Khoj injects memories as
   `- [{friendly_dt}]: {raw}`. Undated, a fact is asserted flatly - the model
   cannot know "Mario lives in Lisbon" was true eighteen months ago. Worth
   more here than to Khoj, because this store retires rather than deletes.
"""
import sys, tempfile, time, traceback, types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-noise-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
sys.modules.setdefault("jarvis_framework", fw)

import jarvis_memory as M
import jarvis_extract as X

HUD = HERE / "jarvis_hud.py"
FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def fresh():
    d = Path(tempfile.mkdtemp(prefix="jarvis-noise-db-"))
    s = M.MemoryStore(path=d / "memory.db")
    M._store = s
    return s


def propose(texts):
    """Run one extraction pass with the model stubbed to return `texts`."""
    import json as _j
    # The keyword is `llm`, not `ask`. propose() takes the model call as an
    # argument precisely so a test can replace it - no Ollama, no network.
    return X.propose(
        [{"role": "user", "content": " ".join(texts)}],
        llm=lambda _prompt: _j.dumps(
            {"facts": [{"text": t, "confidence": 0.9} for t in texts]}),
    )


def t_a_discarded_proposal_does_not_come_back():
    fresh()
    n = propose(["Mario drives a 1998 Volvo"])
    pend = X.pending()
    check("the first pass proposes it", len(pend) == 1, f"proposed {n}, pending {pend}")
    if not pend:
        return

    X.decide(pend[0]["id"], False)          # the owner says no
    check("discarding empties the queue", X.pending() == [])

    # The same sentence comes round again, which is what actually happens:
    # the learner re-reads the whole transcript on the next pass.
    propose(["Mario drives a 1998 Volvo"])
    back = X.pending()
    check("and it does NOT come back", back == [],
          f"re-proposed: {[p['text'] for p in back]}")


def t_a_different_fact_still_gets_through():
    """CONTROL. Suppressing everything would pass the test above."""
    fresh()
    propose(["Mario drives a 1998 Volvo"])
    pend = X.pending()
    if not pend:
        check("a different fact still gets through", False, "nothing proposed")
        return
    X.decide(pend[0]["id"], False)
    propose(["Mario is allergic to penicillin"])
    got = [p["text"] for p in X.pending()]
    check("a different fact still gets through",
          any("penicillin" in t for t in got), f"pending {got}")


def t_an_accepted_fact_is_not_suppressed_forever():
    """`accepted` is deliberately NOT in the dedupe.

    An accepted proposal became a fact, and propose() already checks the
    current facts. Adding 'accepted' would wrongly suppress a re-propose after
    the owner retires that fact and genuinely wants it back.
    """
    s = fresh()
    propose(["Mario's main editor is Vim"])
    pend = X.pending()
    if not pend:
        check("an accepted fact can be re-proposed after it is retired", False,
              "nothing proposed")
        return
    X.decide(pend[0]["id"], True)           # accepted -> becomes a fact
    live = [f["text"] for f in s.current_facts()]
    check("accepting stores the fact", any("Vim" in t for t in live), f"{live}")

    # Now retire it, as the owner would from the Memory pane, and say it again.
    for f in s.current_facts():
        if "Vim" in f["text"]:
            s.retire(f["id"])
    propose(["Mario's main editor is Vim"])
    got = [p["text"] for p in X.pending()]
    check("an accepted fact can be re-proposed after it is retired",
          any("Vim" in t for t in got),
          f"pending {got} - 'accepted' must not be in the dedupe")


def t_recalled_facts_carry_a_date():
    if not HUD.is_file():
        check("the helper exists", False, f"no {HUD}")
        return
    src = HUD.read_text(encoding="utf-8")
    check("the helper exists", "def _dated_fact(" in src)
    check("and the prompt uses it", "_dated_fact(f) for f in chosen_facts" in src)
    check("and `created` is carried through the search path",
          '"created": h.get("created")' in src,
          "chosen_facts used to drop every column but text and id")
    check("and the block says what the date MEANS",
          "when Jarvis was told" in src,
          "an unexplained date invites the model to read it as when it became true")

    # Execute the helper rather than only grepping it.
    ns = {"time": time}
    start = src.index("def _dated_fact(")
    end = src.index("def _models_view()")
    exec(compile(src[start:end], "<helper>", "exec"), ns)
    dated = ns["_dated_fact"]

    when = time.time() - 400 * 86400
    stamp = time.strftime("%Y-%m-%d", time.localtime(when))
    check("a dated fact is stamped",
          dated({"text": "Mario lives in Lisbon", "created": when})
          == f"- [{stamp}] Mario lives in Lisbon")
    check("it falls back to valid_from",
          dated({"text": "x", "valid_from": when}) == f"- [{stamp}] x")
    for bad in ({"text": "x"}, {"text": "x", "created": None},
                {"text": "x", "created": "yesterday"},
                {"text": "x", "created": 0}, {"text": "x", "created": -5}):
        check(f"no date is better than a wrong one ({bad!r:38.38})",
              dated(bad) == "- x", f"got {dated(bad)!r}")


def main():
    for fn in (t_a_discarded_proposal_does_not_come_back,
               t_a_different_fact_still_gets_through,
               t_an_accepted_fact_is_not_suppressed_forever,
               t_recalled_facts_carry_a_date):
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
