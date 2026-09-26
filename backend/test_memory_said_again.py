"""test_memory_said_again.py - memory idea 3: "said again" counts.

    python3 backend/test_memory_said_again.py

When the owner says something Jarvis already knows, the learner's proposal
is dropped as before - and now the day they said it is kept, for good, in
the memory file (MemoryStore.said_again), and shown as "said again N times"
under a fact in both apps' "Saved automatically" list.

What it proves:

1. The store's rules: one row per turn (the learner re-reading a
   conversation is the same row), only after the fact was saved, only for
   a fact still in use whose words are not erased, never a future time,
   only "typed" or "voice".
2. No words: the table holds a fact id, a time and typed/voice. Erasing
   the fact's words leaves no trace of them in the file, and the dates stay
   like the fact's own dates.
3. Who counts: the owner's own live words only - the same checks as
   automatic learning (every said_again case in backend/eval/
   learner_cases.jsonl, run through the real jarvis_intake.propose wrapper
   and "Remember:"): pasted, shared, tool-tainted, unchecked voice, a
   dropped "not", a correction, different words and a forgotten fact are
   never counted.
4. It never breaks learning: a failure in the count leaves the learner's
   answer exactly as it was.
5. Where it shows: GET /api/memory/auto's `said_again` {count, last}, only
   for a fact said again; setup status says how many, with no words.
"""
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

require_shipped("rebuilt/jarvis_memory.py", "jarvis_intake.py", "jarvis_auto_learn.py",
                "jarvis_chat_log.py", "jarvis_sensitive.py")
sys.path.insert(0, str(HERE / "rebuilt"))
os.environ.setdefault("JARVIS_NO_EMBED", "1")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-said-again-"))
os.environ["JARVIS_MEMORY_DB"] = str(_TMP / "memory.db")
_fw = sys.modules.get("jarvis_framework")
if _fw is None:
    _fw = types.ModuleType("jarvis_framework")
    _fw.LOG_DIR = _TMP
    _fw.audit_log = lambda *a, **k: None
    _fw.load_framework = lambda *a, **k: {}
    _fw.action_tier = lambda action: "ask"
    sys.modules["jarvis_framework"] = _fw
_fw.CONFIG_DIR = _TMP

import jarvis_memory as M  # noqa: E402
import jarvis_intake as I  # noqa: E402
import jarvis_auto_learn as A  # noqa: E402
import eval_learner as E  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


_n = [0]


def store():
    _n[0] += 1
    return M.MemoryStore(_TMP / f"m{_n[0]}.db", embedder=M.HashEmbedder())


# ========================================================= 1. the store ==

def t_the_stores_rules():
    st = store()
    fid = st.add("Owner prefers tea to coffee", source="auto")
    made = st.get(fid)["created"]
    later = made + 1
    check("a turn after the fact was saved: recorded", st.said_again(fid, later, "typed"))
    check("the same turn again (the learner re-reading): not a second row",
          not st.said_again(fid, later, "typed")
          and st.said_again_counts([fid])[fid]["count"] == 1)
    check("another turn: a second row, and `last` is the newest",
          st.said_again(fid, later + 2, "voice")
          and st.said_again_counts([fid])[fid] == {"count": 2, "last": later + 2})
    check("the turn it was learned from (before it was saved): not a repeat",
          not st.said_again(fid, made - 1, "typed"))
    check("a time in the future: refused", not st.said_again(fid, time.time() + 3600, "typed"))
    check("only typed or voice", not st.said_again(fid, later + 9, "pasted")
          and not st.said_again(fid, later + 9, None))
    check("not a number: refused", not st.said_again(fid, "yesterday", "typed")
          and not st.said_again(fid, float("nan"), "typed"))
    check("no such fact: refused", not st.said_again(fid + 99, later, "typed"))
    other = st.add("Owner likes jazz", source="auto")
    st.retire(other)
    check("a forgotten fact: refused", not st.said_again(other, time.time(), "typed"))
    check("counts only for facts said again", st.said_again_counts([fid, other, 12345])
          == {fid: {"count": 2, "last": later + 2}})
    check("status() says how many", st.status()["said_again"] == 2, st.status())
    # A fact that ends later (a lease to December) is still in use.
    lease = st.add("Owner rents the flat on Micklegate", source="auto")
    c = st._connect()
    try:
        c.execute("UPDATE facts SET valid_to=? WHERE id=?", (time.time() + 86400 * 60, lease))
    finally:
        c.close()
    check("a fact that ends in the future is still in use: recorded",
          st.said_again(lease, time.time(), "typed"))


# ============================================================ 2. words ==

def t_no_words_and_erase_leaves_none():
    st = store()
    c = st._connect()
    try:
        cols = [r["name"] for r in c.execute("PRAGMA table_info(fact_repeats)")]
    finally:
        c.close()
    check("the table holds a fact id, a time and typed/voice - nothing else",
          cols == ["fact_id", "said_at", "how"], cols)
    fid = st.add("Owner's secret word is zanzibarquux", source="auto")
    st.said_again(fid, st.get(fid)["created"] + 30, "typed")
    out = st.erase(fid)
    blob = b"".join(p.read_bytes() for p in st.path.parent.glob(st.path.name + "*")
                    if p.is_file())
    check("erased: the words are nowhere in the file", out and b"zanzibarquux" not in blob)
    check("... and the dates stay, like the fact's own dates",
          st.said_again_counts([fid]).get(fid, {}).get("count") == 1)
    check("an erased fact is never counted again",
          not st.said_again(fid, time.time(), "typed"))


# ======================================================= 3. who counts ==

def t_only_the_owners_own_live_words_count():
    cases = [c for c in E.load_cases() if c["kind"] == "said_again"]
    check("at least 12 cases", len(cases) >= 12, len(cases))
    A._reset_for_tests()
    keep = getattr(sys.modules.get("jarvis_sensitive"), "ASK_MODEL", None)
    w = E.World(M, _TMP / "world")
    try:
        for case in cases:
            r = E._said_again(w, I, A, case)
            check(f"{case['id']}: {case['what']}", r["ok"], r["got"])
    finally:
        w.close()
        if "jarvis_sensitive" in sys.modules:
            sys.modules["jarvis_sensitive"].ASK_MODEL = keep


def t_proposed_texts_leave_corrections_out():
    raw = ('Here you go: {"facts": [{"text": "Owner likes tea"}, '
           '{"text": "Owner lives in York", "replaces": 0}, {"text": "  "}, "junk"]}')
    check("the model's facts, minus corrections and blanks",
          I.proposed_texts(raw) == ["Owner likes tea"], I.proposed_texts(raw))
    check("not JSON: nothing", I.proposed_texts("no facts here") == [])


# ================================================ 4. never breaks learning ==

def t_a_failure_never_touches_the_learning_pass():
    def boom(*a, **k):
        raise RuntimeError("count broke")
    keep = I.note_said_again
    I.note_said_again = boom
    try:
        extract = types.SimpleNamespace(
            propose=lambda messages, llm=None, source="": (llm("p"), ["the pass"])[1])
        got = I.propose(extract, [{"role": "user", "content": "I like tea"}],
                        lambda p, *a, **k: '{"facts": [{"text": "Owner likes tea"}]}',
                        store=store())
    finally:
        I.note_said_again = keep
    check("the learner's answer comes back exactly as it was", got == ["the pass"], got)
    check("note_said_again itself never raises",
          I.note_said_again(["x y z"], [object(), None], store=object()) == 0)


# ====================================================== 5. where it shows ==

def t_the_list_and_status_show_it():
    st = store()
    keep = M._store if hasattr(M, "_store") else None
    M._store = st
    try:
        a = st.add("Owner prefers tea to coffee", source="auto",
                   meta={"provenance": "typed", "device": "phone"})
        b = st.add("Owner likes jazz", source="auto", meta={"provenance": "typed"})
        t = st.get(a)["created"]
        st.said_again(a, t + 10, "typed")
        st.said_again(a, t + 20, "voice")
        facts = {f["id"]: f for f in A.list_auto(store=st)["facts"]}
        check("GET /api/memory/auto: said_again {count, last} on a fact said again",
              facts[a].get("said_again") == {"count": 2, "last": int(t + 20)}, facts[a])
        check("... and no said_again on one never said again", "said_again" not in facts[b],
              facts[b])
        s = I.status(st)
        check("setup status: how many, and that no words are kept",
              s.get("said_again") == 2 and "No words" in s.get("said_again_note", ""), s)
    finally:
        M._store = keep


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
