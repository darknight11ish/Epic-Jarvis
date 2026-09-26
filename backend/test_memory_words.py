"""test_memory_words.py - both apps' memory words come from one fixture, and
that fixture is what the real backend says today (the memory review of
2026-09-27, I8-I11).

    python3 backend/test_memory_words.py

tools/gen_memory_words_cases.py decides the memory words and writes them,
with worked cases, into the desktop's tests/fixtures/memory-words-cases.json
and the phone's src/test/resources/contract/memory-words-cases.json. The
desktop's tests/memory-words.mjs and the phone's MemoryWordsContractTest
read them. This suite fails when:

1. either copy is not what a fresh run writes - the backend's status or its
   older-news sentence changed, or a word was changed by hand in one copy;
2. the older-news sentence no longer starts with the words both apps look
   for (they would stop putting it on its own line);
3. a status field the apps show is not one status() sends.
"""
import os
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("rebuilt/jarvis_memory.py", "jarvis_intake.py")
sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("JARVIS_NO_EMBED", "1")

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def t_both_copies_are_fresh():
    import gen_memory_words_cases as G
    doc = G.document()
    for p in G.COPIES:
        check(f"{p.relative_to(G.ROOT)} matches (python3 tools/gen_memory_words_cases.py)",
              p.exists() and p.read_text(encoding="utf-8") == doc)


def t_the_older_news_sentence_is_found():
    import gen_memory_words_cases as G
    import jarvis_intake as I
    check("the PC's older-news sentence starts with the words both apps look for",
          I.OLDER_NEWS.startswith(G.WORDS["older_news_start"]), I.OLDER_NEWS)
    note = I.OLDER_NEWS.format(new="2026-01-01", old="2026-03-01")
    lines = G.card_lines({"auto_reason": f"replaces a fact. {note}"})
    check("... and is split off onto its own line with plain dates",
          lines["reason"] == "Not saved automatically: replaces a fact"
          and "1 January 2026" in (lines["older"] or "")
          and "1 March 2026" in (lines["older"] or ""), lines)


def t_the_rows_read_only_what_status_sends():
    import gen_memory_words_cases as G
    import jarvis_memory as M
    import tempfile
    st = M.MemoryStore(Path(tempfile.mkdtemp()) / "m.db", embedder=M.HashEmbedder())
    sent = set(st.status()) | {"available", "sleep_time"}
    for need in ("current", "retired", "embedder", "semantic", "vector_search", "unembedded",
                 "reranker", "said_again"):
        check(f"status() sends `{need}`", need in sent, sorted(sent))
    check("the re-ranker reports a state the apps know",
          M.reranker_status().get("state") in ("on", "loading", "off", "not started"))
    check("... and the apps have words for every one",
          all(G.reranker_value({"state": s}) for s in ("on", "loading", "off", "not started")))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        sys.exit(1)
