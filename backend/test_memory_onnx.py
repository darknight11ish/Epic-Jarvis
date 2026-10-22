"""The memory search's direct ONNX path: the parts that can be proven without
a model, a download, or a network.

    python3 test_memory_onnx.py

WHY THIS EXISTS. Until 2026-10-21 the meaning model and the re-ranker were run
by the `fastembed` library; `rebuilt/jarvis_memory.py` now runs the same ONNX
files directly (the Pillow 13 security fixes need fastembed gone). That is a
lot of new mechanism around one old promise - "search degrades to words, never
fails" - so the mechanism is checked here, on a machine with no model:

1. **The engine is loaded the same way fastembed loaded it.** A fake
   `tokenizers` module records what the loader asks for; the truncation length
   is the model's own `min(model_max_length, max_length)`, padding is the
   model's own pad token and id, and the special tokens are added. The engine
   is only imported inside the backend, never at module import.
2. **The pieces ONNX Runtime never sees are right.** Cls and mean pooling and
   the L2 divide (_pool_and_normalize) are checked on synthetic arrays, and a
   NaN or wrong-width vector is turned into zeros rather than stored.
3. **A model this build cannot run is refused in plain words**, before
   anything is downloaded, and the default is used instead (never a silent
   drop to words only). The default model's NAME is unchanged - the one
   property that stops the store re-embedding every saved fact.
4. **A cached model is used without a network call, and a pinned model whose
   bytes changed is refused.** The cache layout is fastembed's, so a model
   this PC already has is found; a corrupt file is refused with a plain
   sentence rather than loaded.
5. **Offline is words-only, not a hang.** With no cache and HF_HUB_OFFLINE
   set, the loader refuses at once instead of waiting for a network timeout.
6. **The two entry points quiet ONNX Runtime's trace events first, and the
   re-ranker still fails soft** (a load that cannot happen leaves recall on
   the merged order and says why, once).
7. **No shipped module imports fastembed any more.** The library is gone from
   the lock; an import left behind would be an ImportError in the backend's
   window with meaning search silently off.

WHAT IT DOES NOT PROVE: that the vectors match fastembed's - that needs the
models and is `tools/check_onnx_parity.py` plus
`backend/memory_embed_golden.json` on the owner's PC (NOT RUN is not a pass).
"""
import ast
import os
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

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-mem-onnx-"))
_fw = types.ModuleType("jarvis_framework")
_fw.CONFIG_DIR = _TMP
_fw.LOG_DIR = _TMP
_fw.audit_log = lambda *a, **k: None
_fw.load_framework = lambda *a, **k: {}
sys.modules.setdefault("jarvis_framework", _fw)

import jarvis_memory as M  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    SKIPPED.append(name)
    print(f"skip  {name} ({why})")


class _FakeBackend:
    """Stands in for the loaded ONNX model; records what it is asked to do."""

    def __init__(self, dim=4, fail_embed=False):
        self.dim = dim
        self.seen = []
        self.fail_embed = fail_embed

    def embed_texts(self, texts):
        self.seen.append(list(texts))
        if self.fail_embed:
            return [[float("nan")] * self.dim for _ in texts]
        return [[float(len(t)) + i] * self.dim for i, t in enumerate(texts)]

    def score_pairs(self, query, texts):
        self.seen.append((query, list(texts)))
        return [float(i) for i, _ in enumerate(texts)]


class _BackendFactory:
    """Replaces M._backend_for for the length of one test."""

    def __init__(self, dim=4, fail_embed=False):
        self.backend = _FakeBackend(dim=dim, fail_embed=fail_embed)
        self.calls = []

    def __call__(self, model, spec, *, rerank):
        self.calls.append((model, dict(spec), bool(rerank)))
        return self.backend


def _with_backend(factory):
    """Temporarily replace the seam; returns the saved original."""
    saved = M._backend_for
    M._backend_for = factory
    return saved


def t_registry_and_pins():
    """The tables the loader trusts: complete, consistent, and honest about
    the two models it deliberately does not run."""
    check("the default meaning model is in the registry",
          M.EMBED_MODEL_DEFAULT in M.ONNX_EMBED_MODELS,
          str(M.EMBED_MODEL_DEFAULT))
    check("the default re-ranker is in the registry",
          M.RERANK_MODEL_DEFAULT in M.ONNX_RERANK_MODELS,
          str(M.RERANK_MODEL_DEFAULT))
    bad = []
    for name, spec in M.ONNX_EMBED_MODELS.items():
        if not (isinstance(spec.get("source"), str) and spec["source"]
                and isinstance(spec.get("file"), str) and spec["file"]
                and isinstance(spec.get("dim"), int) and spec["dim"] > 0):
            bad.append(name)
        if spec.get("pool") not in (None, "cls", "mean"):
            bad.append(name)
        if "normalize" in spec and not isinstance(spec["normalize"], bool):
            bad.append(name)
    check("every embedding model entry has a source, a file, a width and a "
          "known pooling", not bad, ", ".join(bad))
    bad = [name for name, spec in M.ONNX_RERANK_MODELS.items()
           if not (isinstance(spec.get("source"), str) and spec["source"]
                   and isinstance(spec.get("file"), str) and spec["file"])]
    check("every re-ranker entry has a source and a file", not bad, ", ".join(bad))
    check("the two models this project ships are the two that are pinned",
          set(M.MODEL_PINS) == {M.EMBED_MODEL_DEFAULT, M.RERANK_MODEL_DEFAULT},
          str(sorted(M.MODEL_PINS)))
    pin = M.MODEL_PINS[M.EMBED_MODEL_DEFAULT]
    check("the embedder's pin names the registry's own file and a SHA-256",
          pin["file"] == M.ONNX_EMBED_MODELS[M.EMBED_MODEL_DEFAULT]["file"]
          and len(pin["sha256"]) == 64, str(pin))
    # The two fastembed 0.8.1 models are deliberately absent: they need a
    # recipe this build does not implement, and the pinned install never had
    # them either. A refusal in plain words is the honest answer.
    check("the two models that need a bespoke recipe are NOT listed",
          "jinaai/jina-embeddings-v3" not in M.ONNX_EMBED_MODELS
          and "Qdrant/clip-ViT-B-32-text" not in M.ONNX_EMBED_MODELS)
    check("the batch sizes are positive whole numbers",
          all(isinstance(n, int) and n > 0 for n in (M.EMBED_BATCH, M.RERANK_BATCH)),
          f"{M.EMBED_BATCH}, {M.RERANK_BATCH}")


def t_default_model_name_is_unchanged():
    """The one property that stops the store re-embedding: same model, same name."""
    factory = _BackendFactory()
    saved = _with_backend(factory)
    try:
        e = M.OnnxEmbedder()
        check("the default embedder's name is still fastembed's model name",
              e.name == "BAAI/bge-small-en-v1.5", e.name)
        check("its width comes from the loaded model", e.dim == 4, str(e.dim))
        check("it is marked semantic and may share question vectors",
              e.semantic is True and e.cache_query_vectors is True)
    finally:
        M._backend_for = saved


def t_a_model_that_needs_no_prefix_gets_none():
    factory = _BackendFactory()
    saved = _with_backend(factory)
    try:
        e = M.OnnxEmbedder()
        e.embed(["a", "bb"])
        check("facts are embedded exactly as written",
              factory.backend.seen[-1] == ["a", "bb"], str(factory.backend.seen))
        e.embed_query(["question"])
        check("a question is embedded exactly as written",
              factory.backend.seen[-1] == ["question"], str(factory.backend.seen))
    finally:
        M._backend_for = saved


def t_a_model_that_needs_prefixes_gets_them_and_its_name_is_versioned():
    """The prefix machinery is kept for the model that needs it, and the name
    carries the prefix version so a change of prefixes re-embeds."""
    model = "test/prefix-model"
    factory = _BackendFactory()
    saved = _with_backend(factory)
    M.ONNX_EMBED_MODELS[model] = {"source": "test/prefix-source",
                                  "file": "model.onnx", "dim": 4}
    M.EMBED_PREFIXES[model] = ("Q: ", "D: ")
    try:
        e = M.OnnxEmbedder(model)
        check("a prefixed model's name carries the prefix version",
              e.name == f"{model}+prefixes-{M.EMBED_PREFIX_VERSION}", e.name)
        e.embed(["fact"])
        check("a stored fact gets the document prefix",
              factory.backend.seen[-1] == ["D: fact"], str(factory.backend.seen))
        e.embed_query(["question"])
        check("a question gets the query prefix",
              factory.backend.seen[-1] == ["Q: question"], str(factory.backend.seen))
    finally:
        M._backend_for = saved
        M.ONNX_EMBED_MODELS.pop(model, None)
        M.EMBED_PREFIXES.pop(model, None)


def t_an_unknown_model_is_refused_in_plain_words():
    factory = _BackendFactory()
    saved = _with_backend(factory)
    try:
        try:
            M.OnnxEmbedder("someone/not-a-model")
            check("an unknown meaning model is refused", False)
        except M.EmbedModelUnavailable as exc:
            check("an unknown meaning model is refused", True)
            text = str(exc)
            check("the refusal is a plain sentence naming the model",
                  "someone/not-a-model" in text and "not one this build can run" in text,
                  text)
            check("the refusal names the default to go back to",
                  M.EMBED_MODEL_DEFAULT in text, text)
        try:
            M.OnnxReranker("someone/not-a-reranker")
            check("an unknown re-ranker is refused", False)
        except M.EmbedModelUnavailable as exc:
            check("an unknown re-ranker is refused", True)
            check("its refusal names the re-ranker default",
                  M.RERANK_MODEL_DEFAULT in str(exc), str(exc))
    finally:
        M._backend_for = saved


def t_a_refused_env_model_still_falls_back_to_the_default():
    factory = _BackendFactory()
    saved = _with_backend(factory)
    os.environ["JARVIS_MEMORY_EMBED_MODEL"] = "someone/not-a-model"
    saved_refused = M._embed_refused
    M._embed_refused = ""
    try:
        e = M._make_embedder()
        check("a refused env model still returns a working default embedder",
              isinstance(e, M.OnnxEmbedder) and e.name == M.EMBED_MODEL_DEFAULT,
              type(e).__name__)
        check("and status() can say why the model asked for was not used",
              "someone/not-a-model" in M._embed_refused, M._embed_refused[:120])
    finally:
        os.environ.pop("JARVIS_MEMORY_EMBED_MODEL", None)
        M._embed_refused = saved_refused
        M._backend_for = saved


def t_bad_vectors_become_zeros_never_stored():
    """A NaN or a short vector from a backend is zeroed; the guard is the
    caller's contract (_usable_vector), so it is exercised through embed()."""
    factory = _BackendFactory(dim=4, fail_embed=True)
    saved = _with_backend(factory)
    try:
        e = M.OnnxEmbedder()
        vecs = e.embed(["a", "b"])
        check("a NaN vector is replaced by zeros",
              all(v == [0.0, 0.0, 0.0, 0.0] for v in vecs), str(vecs[:2]))
    finally:
        M._backend_for = saved


def t_pooling_and_normalizing():
    """Cls and mean pooling and the L2 divide, checked on known arrays."""
    try:
        import numpy as np
    except Exception:
        skip("t_pooling_and_normalizing", "numpy is not installed here")
        return
    raw = np.array([[[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]],
                    [[7.0, 8.0], [9.0, 10.0], [11.0, 12.0]]])
    mask = np.array([[1, 1, 0], [1, 0, 0]])
    cls = M._pool_and_normalize(raw, mask, {"pool": "cls", "normalize": True})
    check("cls pooling takes the first token", np.allclose(cls[0], [1.0, 2.0] / np.linalg.norm([1.0, 2.0])),
          str(cls[0]))
    mean = M._pool_and_normalize(raw, mask, {"pool": "mean", "normalize": False})
    check("mean pooling averages only the unmasked tokens",
          np.allclose(mean[0], [(1 + 3) / 2, (2 + 4) / 2]), str(mean[0]))
    check("and the second row uses its own single unmasked token",
          np.allclose(mean[1], [7.0, 8.0]), str(mean[1]))
    two_d = np.array([[3.0, 4.0]])
    flat = M._pool_and_normalize(two_d, None, {"normalize": True})
    check("a 2-D output is used as it is and normalized",
          np.allclose(flat[0], [0.6, 0.8]), str(flat[0]))
    norms = np.linalg.norm(cls, axis=1)
    check("cls rows come out unit length", np.allclose(norms, 1.0), str(norms))
    try:
        M._pool_and_normalize(np.zeros((2, 2, 2)), None, {"pool": "mean"})
        check("mean pooling without a mask is refused, never guessed", False)
    except ValueError:
        check("mean pooling without a mask is refused, never guessed", True)


def t_the_tokenizer_is_configured_the_way_fastembed_configured_it():
    """A fake `tokenizers` module records exactly what the loader asks for."""
    import json

    class _FakeTokenizer:
        def __init__(self):
            self.truncation = None
            self.padding = None
            self.added = []
            self.path = ""

        @classmethod
        def from_file(cls, path):
            made = cls()
            made.path = str(path)
            return made

        def enable_truncation(self, max_length):
            self.truncation = max_length

        def enable_padding(self, pad_id=None, pad_token=None):
            self.padding = (pad_id, pad_token)

        def add_special_tokens(self, tokens):
            self.added.extend(tokens)

    fake = types.ModuleType("tokenizers")
    fake.Tokenizer = _FakeTokenizer
    saved = sys.modules.get("tokenizers")
    sys.modules["tokenizers"] = fake
    try:
        folder = _TMP / "tok-model"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "config.json").write_text(json.dumps({"pad_token_id": 0}))
        (folder / "tokenizer_config.json").write_text(json.dumps(
            {"model_max_length": 512, "max_length": 200, "pad_token": "[PAD]"}))
        (folder / "special_tokens_map.json").write_text(json.dumps(
            {"pad_token": "[PAD]"}))
        (folder / "tokenizer.json").write_text("{}")
        tok = M._load_tokenizer(folder)
        check("truncation is the smaller of the model's two length settings",
              tok.truncation == 200, str(tok.truncation))
        check("padding is the model's own pad token and id",
              tok.padding == (0, "[PAD]"), str(tok.padding))
        check("the model's special tokens are added", tok.added == ["[PAD]"],
              str(tok.added))
        check("the tokenizer is loaded from the model's own tokenizer.json",
              tok.path.endswith("tokenizer.json"), tok.path)
    finally:
        if saved is not None:
            sys.modules["tokenizers"] = saved
        else:
            sys.modules.pop("tokenizers", None)


def t_a_cached_model_is_found_and_used_with_no_download():
    """Build a fake Hugging Face cache and prove the loader reads it offline."""
    fake_root = _TMP / "cache"
    model = "test/cache-model"
    spec = {"source": "test/source", "file": "model.onnx", "dim": 4}
    folder = (fake_root / "models--test--source" / "snapshots" / "abc123")
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("config.json", "tokenizer.json", "tokenizer_config.json",
                 "special_tokens_map.json"):
        (folder / name).write_text("{}")
    (folder / "model.onnx").write_bytes(b"not really a model")
    saved_env = os.environ.get("FASTEMBED_CACHE_PATH")
    saved_pin = M.MODEL_PINS.get(model)
    M.MODEL_PINS[model] = {"source": spec["source"], "file": spec["file"],
                           "sha256": M._sha256_file(folder / "model.onnx")}
    os.environ["FASTEMBED_CACHE_PATH"] = str(fake_root)
    try:
        found = M._cached_snapshot(spec)
        check("a cached model with every side file is found", found == folder,
              str(found))
        check("and the cache root is found regardless of the name's case",
              M._hf_cache_root("TEST/SOURCE").name.lower()
              == "models--test--source")
        check("the pinned bytes are accepted", M._ensure_snapshot(model, spec) == folder)
        (folder / "model.onnx").write_bytes(b"tampered")
        try:
            M._ensure_snapshot(model, spec)
            check("a pinned model whose bytes changed is refused", False)
        except M.EmbedModelUnavailable as exc:
            check("a pinned model whose bytes changed is refused", True)
            check("the refusal says the SHA-256 does not match",
                  "pinned SHA-256" in str(exc), str(exc))
    finally:
        if saved_env is None:
            os.environ.pop("FASTEMBED_CACHE_PATH", None)
        else:
            os.environ["FASTEMBED_CACHE_PATH"] = saved_env
        if saved_pin is None:
            M.MODEL_PINS.pop(model, None)
        else:
            M.MODEL_PINS[model] = saved_pin


def t_offline_means_words_not_a_wait():
    """No cache and HF_HUB_OFFLINE set: refuse at once, in plain words."""
    model = "test/offline-model"
    spec = {"source": "test/never-cached", "file": "model.onnx", "dim": 4}
    fake_root = _TMP / "empty-cache"
    fake_root.mkdir(parents=True, exist_ok=True)
    saved_env = os.environ.get("FASTEMBED_CACHE_PATH")
    saved_offline = os.environ.get("HF_HUB_OFFLINE")
    os.environ["FASTEMBED_CACHE_PATH"] = str(fake_root)
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        try:
            M._ensure_snapshot(model, spec)
            check("offline with no cached model refuses instead of waiting", False)
        except M.EmbedModelUnavailable as exc:
            check("offline with no cached model refuses instead of waiting", True)
            check("the refusal says downloads are switched off",
                  "downloads are switched off" in str(exc), str(exc))
    finally:
        if saved_env is None:
            os.environ.pop("FASTEMBED_CACHE_PATH", None)
        else:
            os.environ["FASTEMBED_CACHE_PATH"] = saved_env
        if saved_offline is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = saved_offline


def t_trace_events_are_quieted_before_the_engine_loads():
    """Both entry points call quiet_onnxruntime() before they build a backend."""
    order = []
    saved_quiet = M.quiet_onnxruntime
    saved_backend = M._backend_for
    factory = _BackendFactory()

    def quiet():
        order.append("quiet")

    def backend_for(model, spec, *, rerank):
        order.append("backend")
        return factory.backend

    M.quiet_onnxruntime = quiet
    M._backend_for = backend_for
    try:
        M.OnnxEmbedder()
        check("the meaning model quiets trace events before loading",
              order[:2] == ["quiet", "backend"], str(order))
        order.clear()
        M.OnnxReranker()
        check("the re-ranker quiets trace events before loading",
              order[:2] == ["quiet", "backend"], str(order))
    finally:
        M.quiet_onnxruntime = saved_quiet
        M._backend_for = saved_backend


def t_the_reranker_still_fails_soft():
    """A load that cannot happen leaves recall exactly as it was, and says why."""
    class _Broken:
        def __init__(self, *a, **k):
            raise M.EmbedModelUnavailable("the re-ranker could not be loaded (test)")

    saved_cls = M.OnnxReranker
    saved_on = M._RERANK_ON
    M.OnnxReranker = _Broken
    M._RERANK_ON = True
    M._rr.update(state="not started", model=None, why="", said=False)
    try:
        got = M.reranker(wait=True)
        check("a re-ranker that cannot load returns None", got is None)
        check("and the state says off, with the reason",
              M._rr["state"] == "off" and "test" in M._rr["why"], str(M._rr))
        check("and only one set with set_reranker() is used",
              M.reranker() is None)
    finally:
        M.OnnxReranker = saved_cls
        M._RERANK_ON = saved_on
        M._rr.update(state="not started", model=None, why="", said=False)


def t_no_shipped_module_imports_fastembed():
    """The library is gone from the lock: an import left behind is words-only
    search in the owner's window. Checked with the AST, not by reading text."""
    offenders = []
    for path in sorted(HERE.rglob("*.py")):
        if path.name.startswith("test_"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name == "fastembed" or name.startswith("fastembed."):
                    offenders.append(f"{path.name}:{node.lineno}")
    check("no shipped module imports fastembed", not offenders, ", ".join(offenders))
    # And the engines are imported lazily, inside the backend, never at import.
    tree = ast.parse((HERE / "rebuilt" / "jarvis_memory.py").read_text(encoding="utf-8"))
    top = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            top.add(node.module or "")
    check("onnxruntime and tokenizers are not imported at module import time",
          not ({"onnxruntime", "tokenizers", "huggingface_hub"} & top),
          str(sorted(top)))


if __name__ == "__main__":
    for fn in (t_registry_and_pins, t_default_model_name_is_unchanged,
               t_a_model_that_needs_no_prefix_gets_none,
               t_a_model_that_needs_prefixes_gets_them_and_its_name_is_versioned,
               t_an_unknown_model_is_refused_in_plain_words,
               t_a_refused_env_model_still_falls_back_to_the_default,
               t_bad_vectors_become_zeros_never_stored, t_pooling_and_normalizing,
               t_the_tokenizer_is_configured_the_way_fastembed_configured_it,
               t_a_cached_model_is_found_and_used_with_no_download,
               t_offline_means_words_not_a_wait,
               t_trace_events_are_quieted_before_the_engine_loads,
               t_the_reranker_still_fails_soft,
               t_no_shipped_module_imports_fastembed):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        sys.exit(1)
