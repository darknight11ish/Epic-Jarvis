"""test_memory_models.py - the memory-search model switches ("Model tryouts",
2026-09-28): JARVIS_MEMORY_EMBED_MODEL and JARVIS_MEMORY_RERANK_MODEL.

    python3 backend/test_memory_models.py

What it proves, with a stand-in fastembed (no model is downloaded here):

1. Unset, nothing changes: the same model (bge-small-en-v1.5), the same name
   in the store, no prefix on a fact or a question.
2. A model that needs prefixes gets its maker's prefixes - one for facts,
   another for questions - and a store name that says so.
3. A model the installed fastembed does not have is REFUSED in plain words,
   before anything loads: the default is used instead (never a silent drop
   to words only), and status() says why.
4. A different model at the SAME vector width still makes the store embed
   every fact again: the old vectors are never mixed with the new.
5. The re-ranker switch: unset is the default model; an unknown name is
   refused in plain words, never loaded.

WHAT IT DOES NOT PROVE: whether a new model finds facts better. That is
tools/model_tryout/memory_tryout.py's job, on the PC.
"""
import os
import subprocess
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("rebuilt/jarvis_memory.py")
sys.path.insert(0, str(HERE / "rebuilt"))
os.environ.pop("JARVIS_MEMORY_EMBED_MODEL", None)
os.environ.pop("JARVIS_MEMORY_RERANK_MODEL", None)
os.environ.pop("JARVIS_NO_EMBED", None)

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-memmodels-"))
_fw = types.ModuleType("jarvis_framework")
_fw.CONFIG_DIR = _TMP
_fw.LOG_DIR = _TMP
_fw.audit_log = lambda *a, **k: None
_fw.load_framework = lambda *a, **k: {}
sys.modules.setdefault("jarvis_framework", _fw)

# ---- a stand-in fastembed: lists three models, remembers every text -------
SEEN = []
DIMS = {"BAAI/bge-small-en-v1.5": 8, "google/embeddinggemma-300m": 8,
        "Qwen/Qwen3-Embedding-0.6B-Q": 8}
LOADED = []


class _TextEmbedding:
    def __init__(self, model_name, cache_dir=None):
        LOADED.append(model_name)
        self.model = model_name

    @staticmethod
    def list_supported_models():
        return [{"model": m, "dim": d} for m, d in DIMS.items()]

    def embed(self, texts):
        for t in texts:
            SEEN.append((self.model, t))
            v = [0.0] * DIMS[self.model]
            v[(len(t) + len(self.model)) % DIMS[self.model]] = 1.0
            yield v


class _CrossEncoder:
    def __init__(self, model_name, cache_dir=None):
        LOADED.append(model_name)

    @staticmethod
    def list_supported_models():
        return [{"model": "Xenova/ms-marco-MiniLM-L-6-v2"},
                {"model": "Xenova/ms-marco-MiniLM-L-12-v2"}]

    def rerank(self, q, texts):
        return [1.0 for _ in texts]


fe = types.ModuleType("fastembed")
fe.TextEmbedding = _TextEmbedding
fe_r = types.ModuleType("fastembed.rerank")
fe_rc = types.ModuleType("fastembed.rerank.cross_encoder")
fe_rc.TextCrossEncoder = _CrossEncoder
sys.modules["fastembed"] = fe
sys.modules["fastembed.rerank"] = fe_r
sys.modules["fastembed.rerank.cross_encoder"] = fe_rc

import jarvis_memory as M  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def t_unset_changes_nothing():
    os.environ.pop("JARVIS_MEMORY_EMBED_MODEL", None)
    SEEN.clear()
    e = M._make_embedder()
    check("unset: the model Jarvis has always used", e.name == "BAAI/bge-small-en-v1.5",
          e.name)
    check("... which is the default the code names",
          M.EMBED_MODEL_DEFAULT == "BAAI/bge-small-en-v1.5")
    e.embed(["Owner is vegetarian"])
    e.embed_query(["what should I cook?"])
    texts = [t for _m, t in SEEN if t != "probe"]
    check("... and no prefix on a fact or a question",
          texts == ["Owner is vegetarian", "what should I cook?"], texts)
    check("... and the store's search asks with the same words",
          M._embed_query(e, "hello") == e.embed(["hello"])[0])


def t_a_model_with_prefixes_gets_them():
    os.environ["JARVIS_MEMORY_EMBED_MODEL"] = "google/embeddinggemma-300m"
    try:
        SEEN.clear()
        e = M._make_embedder()
        check("the model asked for is used", isinstance(e, M.FastEmbedder)
              and e.name.startswith("google/embeddinggemma-300m"), e.name)
        check("... and its name in the store says it uses prefixes (a change of "
              "prefixes is a change of model)", e.name.endswith("+prefixes-1"), e.name)
        SEEN.clear()
        e.embed(["Owner is vegetarian"])
        e.embed_query(["what should I cook?"])
        texts = [t for _m, t in SEEN]
        check("a fact gets the maker's document prefix, a question the query prefix",
              texts == ["title: none | text: Owner is vegetarian",
                        "task: search result | query: what should I cook?"], texts)
    finally:
        os.environ.pop("JARVIS_MEMORY_EMBED_MODEL", None)
    os.environ["JARVIS_MEMORY_EMBED_MODEL"] = "Qwen/Qwen3-Embedding-0.6B-Q"
    try:
        SEEN.clear()
        e = M._make_embedder()
        e.embed(["x"])
        e.embed_query(["y"])
        texts = [t for _m, t in SEEN if t not in ("probe",)]
        check("Qwen3-Embedding: an instruction before a question, nothing before a fact",
              texts == ["x", "Instruct: Given a question, retrieve the saved facts that "
                             "answer it\nQuery:y"], texts)
    finally:
        os.environ.pop("JARVIS_MEMORY_EMBED_MODEL", None)


def t_an_unknown_model_is_refused_in_plain_words():
    os.environ["JARVIS_MEMORY_EMBED_MODEL"] = "someone/not-a-model"
    M._embed_refused = ""
    LOADED.clear()
    try:
        e = M._make_embedder()
    finally:
        os.environ.pop("JARVIS_MEMORY_EMBED_MODEL", None)
    check("refused before anything is loaded", "someone/not-a-model" not in LOADED, LOADED)
    check("the default is used instead - not words only",
          isinstance(e, M.FastEmbedder) and e.name == M.EMBED_MODEL_DEFAULT, e.name)
    why = M._embed_refused
    check("the reason is plain words that name the model and fastembed",
          "someone/not-a-model" in why and "fastembed" in why and "not used" in why, why)
    st = M.MemoryStore(_TMP / "refused.db", embedder=e)
    check("status() says why", st.status().get("embedder_refused") == why)
    M._embed_refused = ""
    check("and says nothing when nothing was refused",
          "embedder_refused" not in st.status())
    try:
        M.FastEmbedder("someone/not-a-model")
        check("FastEmbedder itself refuses it too", False)
    except M.EmbedModelUnavailable as exc:
        check("FastEmbedder itself refuses it too", "0.8.1" in str(exc), str(exc))


class _Stub(M.Embedder):
    semantic = True
    dim = 8

    def __init__(self, name, slot):
        self.name, self.slot, self.calls = name, slot, 0

    def embed(self, texts):
        self.calls += len(texts)
        out = []
        for _ in texts:
            v = [0.0] * 8
            v[self.slot] = 1.0
            out.append(v)
        return out


def t_same_width_other_model_embeds_everything_again():
    db = _TMP / "swap.db"
    a = _Stub("model-a", 1)
    st = M.MemoryStore(db, embedder=a)
    for t in ("Owner likes tea", "Owner lives in Leeds", "Owner has a dog"):
        st.add(t, source="test")
    st.backfill_embeddings(batch=64)
    if not st._vec_ok:
        # CI has no sqlite-vec (on purpose), so nothing is ever embedded
        # there: mark the facts done by hand, which is all the rebuild reads.
        import sqlite3
        c = sqlite3.connect(str(db))
        c.execute("UPDATE facts SET embedded=1")
        c.commit()
        c.close()
    check("the first model's facts count as embedded", st.status()["unembedded"] == 0,
          st.status())
    b = _Stub("model-b", 2)          # the SAME width (8), another model
    st2 = M.MemoryStore(db, embedder=b)
    s = st2.status()
    check("a different model at the same width: every fact is waiting to be embedded again",
          s["unembedded"] == 3 and s["embedder"] == "model-b", s)
    st3 = M.MemoryStore(db, embedder=_Stub("model-b", 2))
    check("... and opening it again with that same model starts nothing new",
          st3.status()["embedder"] == "model-b")
    if st2._vec_ok:
        st2.backfill_embeddings(batch=64)
        check("... and is embedded again, by the new model",
              st2.status()["unembedded"] == 0 and b.calls >= 3, (st2.status(), b.calls))
        import sqlite3
        c = sqlite3.connect(str(db))
        try:
            c.enable_load_extension(True)
            import sqlite_vec
            sqlite_vec.load(c)
            rows = c.execute("SELECT embedding FROM facts_vec").fetchall()
        finally:
            c.close()
        import struct
        vecs = [struct.unpack("8f", r[0]) for r in rows]
        check("no vector of the old model is left beside the new ones",
              len(vecs) == 3 and all(v[2] == 1.0 and v[1] == 0.0 for v in vecs), vecs)
    else:
        print("   (sqlite-vec not here: the vector table itself is not checked)")


def t_the_reranker_switch():
    check("unset: the default re-ranker",
          M.RERANK_MODEL == M.RERANK_MODEL_DEFAULT == "Xenova/ms-marco-MiniLM-L-6-v2")
    LOADED.clear()
    try:
        M.FastReranker("someone/not-a-reranker")
        check("an unknown re-ranker is refused", False)
    except M.EmbedModelUnavailable as exc:
        check("an unknown re-ranker is refused, in plain words, before loading",
              "someone/not-a-reranker" in str(exc) and not LOADED, (str(exc), LOADED))
    r = M.FastReranker("Xenova/ms-marco-MiniLM-L-12-v2")
    check("a listed one loads", r.name == "Xenova/ms-marco-MiniLM-L-12-v2")
    # The setting is read when the module is imported, as the backend does.
    code = ("import os,sys,types;sys.path.insert(0,sys.argv[1]);"
            "fw=types.ModuleType('jarvis_framework');fw.CONFIG_DIR=fw.LOG_DIR=sys.argv[2];"
            "fw.audit_log=lambda *a,**k:None;fw.load_framework=lambda *a,**k:{};"
            "sys.modules['jarvis_framework']=fw;import jarvis_memory as M;print(M.RERANK_MODEL)")
    env = dict(os.environ, JARVIS_MEMORY_RERANK_MODEL="Xenova/ms-marco-MiniLM-L-12-v2")
    out = subprocess.run([sys.executable, "-c", code, str(Path(M.__file__).parent), str(_TMP)],
                         env=env, capture_output=True, text=True, timeout=120)
    check("JARVIS_MEMORY_RERANK_MODEL names the model the self-test and recall load",
          out.stdout.strip().endswith("Xenova/ms-marco-MiniLM-L-12-v2"),
          out.stdout + out.stderr)


def main() -> int:
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception as exc:
                traceback.print_exc()
                check(f"{name} raised {type(exc).__name__}: {exc}", False)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
