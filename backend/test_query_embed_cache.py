"""The one query-embedding cache: a question is embedded once per model.

    python -B backend/test_query_embed_cache.py

WHY THIS EXISTS (Gemini's 2026-10-20 work order, Layer 5, Opt 5.1). A turn can
ask several stores the SAME question - memory first, then the folders - and
each store ran the question through the memory model again. The model
does not change between those asks, so the second and third were paid for
nothing. `jarvis_memory._embed_query()` now keeps an `lru_cache(256)` of the
question's vector, keyed by the model's own identity, and
`jarvis_documents`' query path goes through that same cache (one cache, not two
- two caches cannot dedupe across stores, which is the whole point).

What these checks pin, with counting stand-ins (no model is downloaded here):

  * a repeated question is embedded once, and the answer is a copy;
  * whitespace differences are the same question;
  * a DIFFERENT model is never served the old model's vector (and a new
    embedder - which is how the model is chosen - clears the cache);
  * an embedder that has not opted in is never cached or shared, so a caller's
    own object (a test's table, a future embedder) keeps its own behaviour;
  * the cache is bounded at 256 distinct questions;
  * a documents search after a memory search of the same question does NOT
    embed it again - the cross-store win, measured by call counts, not timing.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("rebuilt/jarvis_memory.py", "jarvis_documents.py")
sys.path.insert(0, str(HERE / "rebuilt"))
#: A real model is never loaded here; the embedders are injected.
os.environ["JARVIS_NO_EMBED"] = "1"

import jarvis_documents as D  # noqa: E402
import jarvis_memory as M  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def _scratch_root() -> Path:
    """A disposable folder `jarvis_documents` will accept (the OS temp folder
    can sit under AppData, which Jarvis refuses on purpose)."""
    root = Path(tempfile.mkdtemp(prefix="jarvis-qcache-"))
    try:
        D.check_folder(str(root))
        return root
    except ValueError:
        shutil.rmtree(root, ignore_errors=True)
    return Path(tempfile.mkdtemp(prefix=".jarvis-qcache-", dir=str(Path.home())))


TMP = _scratch_root()


class CountingEmbedder(M.Embedder):
    """A model stand-in that remembers every text it was asked to embed.

    It carries the two things the cache keys on - a `name` that identifies the
    model (the `Embedder` contract below says so) and the opt-in flag the real
    `FastEmbedder` sets - so two instances with the same name are two stores
    using one model, exactly like memory and documents on this PC.
    """

    semantic = True
    dim = 4
    cache_query_vectors = True

    def __init__(self, name="counting-model", vector=(1.0, 0.0, 0.0, 0.0)):
        self.name = name
        self.vector = [float(x) for x in vector]
        self.calls = []

    def embed(self, texts):
        for text in texts:
            self.calls.append(text)
        return [list(self.vector) for _ in texts]


class PlainEmbedder:
    """A caller's own embedder object: no opt-in, so never cached."""

    semantic = True
    dim = 4
    name = "plain-model"

    def __init__(self):
        self.calls = []

    def embed(self, texts):
        for text in texts:
            self.calls.append(text)
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


# --------------------------------------------------------------------------
#   The cache itself
# --------------------------------------------------------------------------

def t_a_repeated_question_is_embedded_once_and_the_answer_is_a_copy():
    M._clear_query_cache()
    emb = CountingEmbedder(vector=(0.0, 1.0, 0.0, 0.0))
    first = M._embed_query(emb, "when was the boiler serviced")
    second = M._embed_query(emb, "when was the boiler serviced")
    check("a repeated question reaches the model once",
          emb.calls == ["when was the boiler serviced"], emb.calls)
    check("both answers are the same vector", first == second == [0.0, 1.0, 0.0, 0.0],
          (first, second))
    first[0] = 99.0
    third = M._embed_query(emb, "when was the boiler serviced")
    check("the caller gets a COPY - mutating it cannot corrupt the cache",
          third == [0.0, 1.0, 0.0, 0.0], third)
    check("...and the copy did not make the model run again",
          len(emb.calls) == 1, emb.calls)


def t_whitespace_differences_are_the_same_question():
    M._clear_query_cache()
    emb = CountingEmbedder()
    M._embed_query(emb, "where is my passport")
    got = M._embed_query(emb, "  where   is my   passport  ")
    check("extra whitespace is the same normalized question",
          len(emb.calls) == 1 and got == [1.0, 0.0, 0.0, 0.0], emb.calls)


def t_a_different_model_is_never_served_the_old_vector():
    M._clear_query_cache()
    old = CountingEmbedder(name="model-a", vector=(1.0, 0.0, 0.0, 0.0))
    new = CountingEmbedder(name="model-b", vector=(0.0, 0.0, 1.0, 0.0))
    got_old = M._embed_query(old, "same words, new model")
    got_new = M._embed_query(new, "same words, new model")
    check("the first model computed the question", len(old.calls) == 1, old.calls)
    check("a different model computes it for itself, never reusing the old vector",
          len(new.calls) == 1 and got_new == [0.0, 0.0, 1.0, 0.0],
          (new.calls, got_new))
    check("...and the two answers really came from the two models",
          got_old == [1.0, 0.0, 0.0, 0.0], got_old)


def t_choosing_a_new_embedder_clears_the_cache():
    """The model is chosen in `_make_embedder()`; a new one must not inherit
    the old model's cached question vectors."""
    M._clear_query_cache()
    M._embed_query(CountingEmbedder(), "a question before the model changed")
    before = M._query_cache_info()
    M._make_embedder()          # JARVIS_NO_EMBED is set, so this is a stand-in
    after = M._query_cache_info()
    check("a question vector was cached before the model was chosen again",
          before[2] == 1, before)
    check("choosing the embedder cleared the cached question vectors",
          after[2] == 0, after)


def t_an_embedder_that_has_not_opted_in_is_never_cached():
    M._clear_query_cache()
    plain = PlainEmbedder()
    M._embed_query(plain, "a question with no model identity")
    M._embed_query(plain, "a question with no model identity")
    check("an embedder with no opt-in computes every ask",
          len(plain.calls) == 2, plain.calls)
    check("...and puts nothing in the shared cache",
          M._query_cache_info()[2] == 0, M._query_cache_info())


def t_the_cache_is_bounded_at_256_questions():
    M._clear_query_cache()
    emb = CountingEmbedder()
    for n in range(300):
        M._embed_query(emb, f"question number {n}")
    info = M._query_cache_info()
    check("the cache is an lru_cache of 256", info[3] == 256, info)
    check("...and it holds at most 256 questions after 300 distinct ones",
          info[2] == 256, info)
    check("...with every one of the 300 computed once",
          len(emb.calls) == 300, len(emb.calls))
    M._embed_query(emb, "question number 299")
    check("the most recent question is still a hit",
          len(emb.calls) == 300, len(emb.calls))


# --------------------------------------------------------------------------
#   The cross-store win: documents reuses what memory computed
# --------------------------------------------------------------------------

def _document_index(name: str):
    root = TMP / name
    root.mkdir(parents=True, exist_ok=True)
    page = root / "note.md"
    page.write_text("The boiler was serviced in March. The radiator was replaced.",
                    encoding="utf-8")
    idx = D.TextIndex(TMP / (name + "-index.db"))
    check(f"the {name} index took the file", idx.reconcile([os.path.realpath(str(root))]),
          idx.status())
    return idx


def t_a_documents_search_reuses_the_vector_memory_already_computed():
    M._clear_query_cache()
    idx = _document_index("shared")
    mem = CountingEmbedder(name="one-model", vector=(0.0, 1.0, 0.0, 0.0))
    doc = CountingEmbedder(name="one-model", vector=(0.0, 1.0, 0.0, 0.0))
    idx.embed_missing(doc)                 # the files' own meaning vectors
    doc.calls.clear()
    question = "when was the boiler serviced"

    first = M._embed_query(mem, question)  # the memory store asks first
    check("the memory store embedded the question once", len(mem.calls) == 1, mem.calls)

    ranked = idx.query(question, embedder=doc)   # then the folders are searched
    check("the documents search answered with its meaning half",
          isinstance(ranked, dict) and ranked.get("meaning") is True, ranked)
    check("...and did NOT embed the same question a second time",
          doc.calls == [] and len(mem.calls) == 1, (doc.calls, mem.calls))
    check("...using the same vector memory computed", list(first) == [0.0, 1.0, 0.0, 0.0],
          first)


def t_a_documents_search_repeats_the_question_for_free():
    M._clear_query_cache()
    idx = _document_index("repeat")
    emb = CountingEmbedder(name="documents-only", vector=(0.0, 1.0, 0.0, 0.0))
    idx.embed_missing(emb)
    emb.calls.clear()
    idx.query("when was the boiler serviced", embedder=emb)
    check("the first documents search embeds the question once",
          len(emb.calls) == 1, emb.calls)
    idx.query("when was the boiler serviced", embedder=emb)
    check("a repeated documents search embeds nothing",
          len(emb.calls) == 1, emb.calls)


def main() -> int:
    tests = (t_a_repeated_question_is_embedded_once_and_the_answer_is_a_copy,
             t_whitespace_differences_are_the_same_question,
             t_a_different_model_is_never_served_the_old_vector,
             t_choosing_a_new_embedder_clears_the_cache,
             t_an_embedder_that_has_not_opted_in_is_never_cached,
             t_the_cache_is_bounded_at_256_questions,
             t_a_documents_search_reuses_the_vector_memory_already_computed,
             t_a_documents_search_repeats_the_question_for_free)
    for fn in tests:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    M._clear_query_cache()
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
