#!/usr/bin/env python3
"""Capture the memory-search vectors and re-ranker scores ONCE, as a fixture.

    python3 tools/gen_memory_embed_golden.py [--out backend/memory_embed_golden.json]

WHY THIS EXISTS, AND WHY IT IS THE ONLY TOOL HERE THAT WANTS fastembed.
Until 2026-10-21 the meaning model and the re-ranker were run by the
`fastembed` library; the backend now runs the same ONNX files directly (the
Pillow 13 security fixes need fastembed gone - every release of it forbids
Pillow 13). Replacing a model runner is the kind of change that quietly
changes every vector, and a store whose vectors changed without its model
name changing would mix two kinds of vector and rank nothing usefully.

So this tool was run ONCE, on 2026-10-21, while fastembed was still
installed and the two models were still in the cache: it writes down the
answers fastembed gave for a fixed corpus, and `tools/check_onnx_parity.py`
(+ `backend/test_memory_onnx.py`'s PC half) checks the direct path against
them. The fixture is the evidence that the vectors did not move, and it is
kept so the claim can be re-checked on any PC that has the models.

DON'T RUN IT AGAIN to "refresh" the fixture. A new capture would record
whatever the CURRENT code produces and would then agree with itself - it
would prove nothing. If the model or its prefix version genuinely changes,
that is a new, versioned model name (see EMBED_PREFIX_VERSION in
backend/rebuilt/jarvis_memory.py) and a new fixture, deliberately.

The corpus and the inputs are part of the fixture, so the check re-runs the
exact same texts in the exact same order.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "rebuilt"))

import jarvis_memory as M  # noqa: E402

#: The fixed corpus. Short facts, a question-shaped sentence, an empty
#: string, a text that truncates at the model's 512-token limit, punctuation
#: and numbers, and non-ASCII - the cases where a tokenizer or a pooling
#: difference would show first.
CORPUS = [
    "The owner is vegetarian.",
    "Priya's wedding is in June, in Lisbon.",
    "My car is a blue Skoda Octavia.",
    "a",
    "",
    "The quick brown fox jumps over the lazy dog.",
    "Jarvis remembers facts from the owner's own words only.",
    "Numbers: 12, 34.5, and the 6th of June 2026.",
    "Unicode: naive cafe, resume, 5 EUR, 20%.",
    "x" * 900,
]

#: (query, candidate facts) - the re-ranker's fixed cases.
RERANK_CASES = [
    ("what should I cook for dinner?",
     ["Owner is vegetarian.", "Priya's wedding is in June.",
      "My car is a blue Skoda Octavia.", "Owner does not eat meat."]),
    ("where is my sister getting married?",
     ["Priya's wedding is in June.", "Owner is vegetarian.",
      "The wedding is in Lisbon.", "Owner keeps a spreadsheet of bills."]),
    ("what do I drive?",
     ["My car is a blue Skoda Octavia.", "Owner is vegetarian.",
      "Priya's wedding is in June."]),
]


def capture() -> dict:
    """Run fastembed's own models over the fixed inputs and record the answers."""
    from fastembed import TextEmbedding
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    embedder = TextEmbedding(model_name=M.EMBED_MODEL_DEFAULT,
                             cache_dir=M.model_cache_dir())
    vectors = [[float(x) for x in v] for v in embedder.embed(CORPUS)]

    reranker = TextCrossEncoder(model_name=M.RERANK_MODEL_DEFAULT,
                                cache_dir=M.model_cache_dir())
    cases = []
    for query, texts in RERANK_CASES:
        scores = [float(x) for x in reranker.rerank(query, list(texts))]
        cases.append({"query": query, "texts": list(texts), "scores": scores})

    onnx_sha = M._sha256_file(
        M._ensure_snapshot(M.EMBED_MODEL_DEFAULT,
                           M.ONNX_EMBED_MODELS[M.EMBED_MODEL_DEFAULT])
        / M.MODEL_PINS[M.EMBED_MODEL_DEFAULT]["file"])
    return {
        "why": (
            "Captured from fastembed 0.8.0 on 2026-10-21, before the backend "
            "moved to running the same ONNX files directly. The direct path "
            "must reproduce these numbers (bit-identical on the capture PC); "
            "the model name is unchanged, so no stored fact is re-embedded. "
            "Do not regenerate this file to make a mismatch pass."
        ),
        "captured": "2026-10-21",
        "embed": {
            "model": M.EMBED_MODEL_DEFAULT,
            "name": M.EMBED_MODEL_DEFAULT,
            "dim": len(vectors[0]),
            "onnx_sha256": onnx_sha,
            "texts": list(CORPUS),
            "vectors": vectors,
        },
        "rerank": {
            "model": M.RERANK_MODEL_DEFAULT,
            "cases": cases,
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture the memory search models' answers as a fixture.")
    parser.add_argument("--out", default=str(ROOT / "backend" / "memory_embed_golden.json"))
    args = parser.parse_args(argv)
    try:
        data = capture()
    except ImportError as exc:
        print(f"NOT RUN: this tool needs fastembed installed to capture from it ({exc}).")
        print("It was run once on 2026-10-21; the fixture beside it is the record.")
        return 2
    out = Path(args.out)
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"wrote {out} ({len(text):,} bytes, {len(CORPUS)} vectors of "
          f"{data['embed']['dim']}, {len(RERANK_CASES)} re-rank cases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
