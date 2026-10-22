#!/usr/bin/env python3
"""Check the direct ONNX path against the answers fastembed gave, on this PC.

    python3 tools/check_onnx_parity.py

WHY THIS EXISTS. Until 2026-10-21 the memory meaning model and the re-ranker
were run by the `fastembed` library; the backend now runs the same ONNX files
directly. `backend/memory_embed_golden.json` holds the vectors and re-ranker
scores fastembed produced for a fixed corpus on 2026-10-21, and this tool
re-runs the direct path over the same inputs and compares.

A mismatch here is not cosmetic: the store identifies its vectors by the
model NAME, so if the direct path produced different vectors under the same
name, old and new facts would be mixed and ranked against each other. The
change shipped only because the answers were identical (measured bit-for-bit
on the capture PC); this is how that claim is re-checked.

WHAT IT DOES NOT DO. No network, no writes, no model downloads: if either
model is not already in the cache on this PC it prints NOT RUN and exits 2 -
**and NOT RUN is never a pass**, the project's BLOCKED-is-never-a-pass rule.
It does not import fastembed (it is gone); the fixture is the only record of
fastembed's answers it needs.

Exit: 0 the direct path reproduces the fixture, 1 it does not, 2 NOT RUN.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "rebuilt"))

#: Per-row cosine must be at least this. The capture PC measured 1.0 exactly,
#: but a different CPU (AVX-512 vs AVX2) may move the last bits, so the check
#: is "the same vector for any practical purpose", not bit equality.
MIN_COSINE = 0.999999
#: A re-ranker score is a bare logit; float rearrangements are below this.
MAX_SCORE_DELTA = 1e-4


def cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def fail(message: str) -> int:
    print(f"FAIL  {message}")
    return 1


def main() -> int:
    fixture_path = ROOT / "backend" / "memory_embed_golden.json"
    if not fixture_path.is_file():
        return fail(f"{fixture_path} is missing; the parity claim has no evidence")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    embed_spec = fixture["embed"]
    rerank_spec = fixture["rerank"]

    import jarvis_memory as M  # noqa: E402 - imported here so --help stays cheap

    # NOT RUN is not a pass: both models must already be on this PC.
    for label, model, registry in (
            ("meaning model", embed_spec["model"], M.ONNX_EMBED_MODELS),
            ("re-ranker", rerank_spec["model"], M.ONNX_RERANK_MODELS)):
        spec = registry.get(model)
        if spec is None:
            return fail(f"the {label} {model!r} is not in this build's registry")
        if M._cached_snapshot(spec) is None:
            print(f"NOT RUN: the {label} {model!r} is not in the cache on this PC.")
            print("        The parity claim cannot be checked here; this is NOT a pass.")
            return 2

    embedder = M.OnnxEmbedder(embed_spec["model"])
    if embedder.name != embed_spec["name"]:
        return fail(f"the embedder's name changed ({embedder.name!r} != "
                    f"{embed_spec['name']!r}); the store would re-embed every fact")
    if embedder.dim != embed_spec["dim"]:
        return fail(f"the embedder's width changed ({embedder.dim} != {embed_spec['dim']})")

    vectors = embedder.embed(embed_spec["texts"])
    worst_cos, worst_at = 1.0, -1
    worst_abs = 0.0
    for i, (got, want) in enumerate(zip(vectors, embed_spec["vectors"])):
        if len(got) != len(want):
            return fail(f"text {i}: width {len(got)} != {len(want)}")
        c = cosine(got, want)
        if c < worst_cos:
            worst_cos, worst_at = c, i
        for x, y in zip(got, want):
            if abs(x - y) > worst_abs:
                worst_abs = max(worst_abs, abs(x - y))
    if len(vectors) != len(embed_spec["vectors"]):
        return fail(f"got {len(vectors)} vectors for {len(embed_spec['vectors'])} texts")
    if worst_cos < MIN_COSINE:
        return fail(f"the vectors moved: worst cosine {worst_cos:.9f} at text "
                    f"{worst_at} (need >= {MIN_COSINE})")
    print(f"ok    meaning model: {len(vectors)} vectors, worst cosine "
          f"{worst_cos:.9f}, largest component change {worst_abs:.3e}")
    if worst_abs == 0.0:
        print("      (bit-identical to what fastembed gave on 2026-10-21)")

    reranker = M.OnnxReranker(rerank_spec["model"])
    worst_delta, worst_case = 0.0, ""
    for case in rerank_spec["cases"]:
        got = reranker.score(case["query"], case["texts"])
        if len(got) != len(case["scores"]):
            return fail(f"re-ranker returned {len(got)} scores for "
                        f"{len(case['scores'])} texts ({case['query']!r})")
        for i, (a, b) in enumerate(zip(got, case["scores"])):
            if abs(a - b) > worst_delta:
                worst_delta, worst_case = abs(a - b), f"{case['query']!r} doc {i}"
    if worst_delta > MAX_SCORE_DELTA:
        return fail(f"the re-ranker's scores moved: {worst_delta:.3e} at "
                    f"{worst_case} (allowed {MAX_SCORE_DELTA:.0e})")
    print(f"ok    re-ranker: {len(rerank_spec['cases'])} case(s), largest score "
          f"change {worst_delta:.3e}")
    print("\nonnx parity OK: the direct path reproduces fastembed's answers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
