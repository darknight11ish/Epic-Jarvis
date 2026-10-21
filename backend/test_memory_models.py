"""test_memory_models.py - the memory-search model switches ("Model tryouts",
2026-09-28): JARVIS_MEMORY_EMBED_MODEL and JARVIS_MEMORY_RERANK_MODEL.

    python3 backend/test_memory_models.py

What it proves, with a stand-in ONNX backend behind jarvis_memory's one test
seam `_backend_for` (no model is downloaded and no engine is run here):

1. Unset, nothing changes: the same model (bge-small-en-v1.5), the same name
   in the store, no prefix on a fact or a question.
2. A model that needs prefixes gets its maker's prefixes - one for facts,
   another for questions - and a store name that says so.
3. A model this build does not run is REFUSED in plain words, before anything
   loads: the default is used instead (never a silent drop to words only), and
   status() says why. The message names the model, not fastembed or its
   version (the library is gone, 2026-10-21).
4. A different model at the SAME vector width still makes the store embed
   every fact again: the old vectors are never mixed with the new.
5. The re-ranker switch: unset is the default model; an unknown name is
   refused in plain words, never loaded.
6. The supply-chain pins (security audit M8), against a TEMP fake cache: a
   cached model file that does not match its SHA-256 in MODEL_PINS is refused
   before anything is loaded, and one that matches is accepted. No real cache
   is read and nothing downloads.

WHAT IT DOES NOT PROVE: whether a new model finds facts better. That is
tools/model_tryout/memory_tryout.py's job, on the PC.
"""
import hashlib
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

import jarvis_memory as M  # noqa: E402

# ---- a stand-in ONNX backend: the ONE seam the module offers ---------------#: Every (model, text) an embed pass was asked for. OnnxEmbedder's own width
#: probe is in here too; the tests clear SEEN after building an embedder.
SEEN = []
#: Every (model, rerank) `_backend_for` was asked for, so a refusal can be
#: shown to happen before anything loads.
LOADED = []


class _Backend:
    """What `_backend_for` returns: the two calls the two classes make."""

    def __init__(self, model, spec, *, rerank):
        LOADED.append((model, bool(rerank)))
        self.model = model
        self.rerank = bool(rerank)
        # OnnxEmbedder takes its width from the probe's answer, so this is the
        # width the store would declare.
        self.dim = 0 if self.rerank else int(spec.get("dim") or 8)

    def embed_texts(self, texts):
        for t in texts:
            SEEN.append((self.model, t))
        out = []
        for t in texts:
            v = [0.0] * self.dim
            v[(len(t) + len(self.model)) % self.dim] = 1.0
            out.append(v)
        return out

    def score_pairs(self, query, texts):
        return [1.0 for _ in texts]


def _fake_backend_for(model, spec, *, rerank):
    return _Backend(model, spec, rerank=rerank)


M._backend_for = _fake_backend_for

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class _Listed:
    """A model this build lists for the length of a with-block.

    The two prefixed models were in fastembed 0.8.1's list, which the lock
    deliberately never took; the direct path does not carry them. Their
    EMBED_PREFIXES entries are kept so a store written by a build that did run
    one still names its vectors correctly. This block is that build, so the
    prefix path is exercised exactly as it would be there.
    """

    def __init__(self, model, dim=8):
        self.model, self.dim = model, dim
        self.spec = {"source": model, "file": "onnx/model.onnx", "dim": dim}

    def __enter__(self):
        self.kept = M.ONNX_EMBED_MODELS.get(self.model)
        M.ONNX_EMBED_MODELS[self.model] = self.spec
        return self

    def __exit__(self, *exc):
        if self.kept is None:
            M.ONNX_EMBED_MODELS.pop(self.model, None)
        else:
            M.ONNX_EMBED_MODELS[self.model] = self.kept


def t_unset_changes_nothing():
    os.environ.pop("JARVIS_MEMORY_EMBED_MODEL", None)
    LOADED.clear()
    SEEN.clear()
    e = M._make_embedder()
    check("unset: the model Jarvis has always used", e.name == "BAAI/bge-small-en-v1.5",
          e.name)
    check("... which is the default the code names",
          M.EMBED_MODEL_DEFAULT == "BAAI/bge-small-en-v1.5")
    check("... loaded through the one ONNX seam, as an embedder",
          LOADED == [(M.EMBED_MODEL_DEFAULT, False)], LOADED)
    SEEN.clear()
    e.embed(["Owner is vegetarian"])
    e.embed_query(["what should I cook?"])
    texts = [t for _m, t in SEEN]
    check("... and no prefix on a fact or a question",
          texts == ["Owner is vegetarian", "what should I cook?"], texts)
    check("... and the store's search asks with the same words",
          M._embed_query(e, "hello") == e.embed(["hello"])[0])


def t_a_model_with_prefixes_gets_them():
    for model, fact_prefix, query_prefix in (
            ("google/embeddinggemma-300m", "title: none | text: ",
             "task: search result | query: "),
            ("Qwen/Qwen3-Embedding-0.6B-Q", "",
             "Instruct: Given a question, retrieve the saved facts that "
             "answer it\nQuery:")):
        with _Listed(model):
            os.environ["JARVIS_MEMORY_EMBED_MODEL"] = model
            try:
                LOADED.clear()
                e = M._make_embedder()
                check(f"{model}: the model asked for is used",
                      isinstance(e, M.OnnxEmbedder) and e.name.startswith(model), e.name)
                check(f"{model}: ... and its name in the store says it uses prefixes "
                      "(a change of prefixes is a change of model)",
                      e.name == f"{model}+prefixes-{M.EMBED_PREFIX_VERSION}"
                      and M.EMBED_PREFIX_VERSION == 1, e.name)
                SEEN.clear()
                e.embed(["Owner is vegetarian"])
                e.embed_query(["what should I cook?"])
                texts = [t for _m, t in SEEN]
                check(f"{model}: a fact gets the maker's document prefix, a question "
                      "the query prefix",
                      texts == [fact_prefix + "Owner is vegetarian",
                                query_prefix + "what should I cook?"], texts)
            finally:
                os.environ.pop("JARVIS_MEMORY_EMBED_MODEL", None)
    check("the prefix entries the store's names carry are still the module's own",
          "google/embeddinggemma-300m" in M.EMBED_PREFIXES
          and "Qwen/Qwen3-Embedding-0.6B-Q" in M.EMBED_PREFIXES, sorted(M.EMBED_PREFIXES))


def t_an_unknown_model_is_refused_in_plain_words():
    os.environ["JARVIS_MEMORY_EMBED_MODEL"] = "someone/not-a-model"
    M._embed_refused = ""
    LOADED.clear()
    try:
        e = M._make_embedder()
    finally:
        os.environ.pop("JARVIS_MEMORY_EMBED_MODEL", None)
    check("refused before the model asked for is loaded",
          all(m != "someone/not-a-model" for m, _r in LOADED), LOADED)
    check("the default is used instead - not words only",
          isinstance(e, M.OnnxEmbedder) and e.name == M.EMBED_MODEL_DEFAULT, e.name)
    why = M._embed_refused
    check("the reason is plain words that name the model and say it was not used",
          "someone/not-a-model" in why and "not one this build can run" in why
          and "not used" in why and M.EMBED_MODEL_DEFAULT in why, why)
    check("... and it no longer talks about fastembed or its version",
          "fastembed" not in why.lower() and "0.8.1" not in why, why)
    st = M.MemoryStore(_TMP / "refused.db", embedder=e)
    check("status() says why", st.status().get("embedder_refused") == why)
    M._embed_refused = ""
    check("and says nothing when nothing was refused",
          "embedder_refused" not in st.status())
    try:
        M.OnnxEmbedder("someone/not-a-model")
        check("OnnxEmbedder itself refuses it too", False)
    except M.EmbedModelUnavailable as exc:
        check("OnnxEmbedder itself refuses it too",
              "someone/not-a-model" in str(exc) and "not one this build can run" in str(exc)
              and "0.8.1" not in str(exc), str(exc))


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
    check("... which is one of the ONNX re-rankers this build runs",
          M.RERANK_MODEL_DEFAULT in M.ONNX_RERANK_MODELS, sorted(M.ONNX_RERANK_MODELS))
    LOADED.clear()
    try:
        M.OnnxReranker("someone/not-a-reranker")
        check("an unknown re-ranker is refused", False)
    except M.EmbedModelUnavailable as exc:
        check("an unknown re-ranker is refused, in plain words, before loading",
              "someone/not-a-reranker" in str(exc) and not LOADED
              and "not one this build can run" in str(exc), (str(exc), LOADED))
    check("the second model the tryout names is listed",
          "Xenova/ms-marco-MiniLM-L-12-v2" in M.ONNX_RERANK_MODELS,
          sorted(M.ONNX_RERANK_MODELS))
    LOADED.clear()
    r = M.OnnxReranker("Xenova/ms-marco-MiniLM-L-12-v2")
    check("a listed one loads, through the ONNX seam as a re-ranker",
          isinstance(r, M.OnnxReranker) and r.name == "Xenova/ms-marco-MiniLM-L-12-v2"
          and LOADED == [("Xenova/ms-marco-MiniLM-L-12-v2", True)], (r.name, LOADED))
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


def t_pinned_onnx_weights_are_checked_before_they_are_used():
    """Supply-chain M8, against the direct ONNX path: a cached model file that
    does not match its SHA-256 in MODEL_PINS is refused before anything is
    loaded, in plain words; the matching file is accepted.

    A TEMP cache is built by hand under FASTEMBED_CACHE_PATH (the folder name
    the installed base already uses), so the real model cache is never read;
    the downloader is replaced by one that fails the test, so nothing can
    reach the network. The matching case swaps in the fake file's own hash,
    and restores the real pin afterwards, so no pin is weakened for anything
    else.
    """
    old_env = os.environ.get("FASTEMBED_CACHE_PATH")
    old_download = M._download_snapshot

    def no_download(model, spec):
        raise AssertionError(
            f"{model!r} was not found in the TEMP test cache, so it would have "
            "been downloaded - this suite must never touch the network")
    M._download_snapshot = no_download
    built, real_pins = {}, {}
    try:
        with tempfile.TemporaryDirectory(prefix="jarvis-pins-") as d:
            os.environ["FASTEMBED_CACHE_PATH"] = d
            root = Path(d)
            for label, model, models in (
                    ("memory", M.EMBED_MODEL_DEFAULT, M.ONNX_EMBED_MODELS),
                    ("re-rank", M.RERANK_MODEL_DEFAULT, M.ONNX_RERANK_MODELS)):
                spec = models[model]
                snapshot = (root / f"models--{spec['source'].replace('/', '--')}"
                            / "snapshots" / "rev1")
                model_file = snapshot / spec["file"]
                model_file.parent.mkdir(parents=True, exist_ok=True)
                model_file.write_bytes(b"not the measured model")
                for name in M._MODEL_SIDE_FILES:
                    (snapshot / name).write_text("{}", encoding="utf-8")
                built[label] = (model, spec, snapshot)
                real_pins[label] = M.MODEL_PINS[model]
                pin = real_pins[label]
                check(f"the {label} model has a pin naming the file and source the "
                      "loader uses",
                      pin["file"] == spec["file"] and pin["source"] == spec["source"]
                      and len(pin["sha256"]) == 64, (pin, spec))
            for label, (model, spec, _snapshot) in built.items():
                try:
                    M._ensure_snapshot(model, spec)
                    check(f"a wrong {label} model file is refused, not loaded", False)
                except M.EmbedModelUnavailable as exc:
                    check(f"a wrong {label} model file is refused, in plain words",
                          "pinned SHA-256" in str(exc) and model in str(exc)
                          and "not used" in str(exc)
                          and "fastembed" not in str(exc).lower(), str(exc))
            try:
                for label, (model, _spec, snapshot) in built.items():
                    pin = real_pins[label]
                    M.MODEL_PINS[model] = dict(
                        pin, sha256=hashlib.sha256(
                            (snapshot / pin["file"]).read_bytes()).hexdigest())
                for label, (model, spec, snapshot) in built.items():
                    got = M._ensure_snapshot(model, spec)
                    check(f"a {label} model file that matches its pin is accepted",
                          got == snapshot, (got, snapshot))
            finally:
                for label, (model, _spec, _snapshot) in built.items():
                    M.MODEL_PINS[model] = real_pins[label]
    finally:
        for label, (model, _spec, _snapshot) in built.items():
            if label in real_pins:
                M.MODEL_PINS[model] = real_pins[label]
        M._download_snapshot = old_download
        if old_env is None:
            os.environ.pop("FASTEMBED_CACHE_PATH", None)
        else:
            os.environ["FASTEMBED_CACHE_PATH"] = old_env


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
