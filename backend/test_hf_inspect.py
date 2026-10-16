"""jarvis_hf_inspect.py: verifying a GGUF by its LISTING, before any download.

    python3 test_hf_inspect.py

What it holds:

  1. the one URL is the names-only listing, and a repo id that is not
     `owner/name` is refused (a URL in there is how a token would get in);
  2. nothing but that URL leaves this machine: the call takes one argument,
     and the module has no token, cookie, key or auth header anywhere;
  3. the vision projector's bytes are reported SEPARATELY from the model's;
  4. quantisation labels are kept exactly as the repo writes them - `UD-Q4_K_M`
     is not `Q4_K_M`;
  5. the KV arithmetic, on the REAL `Qwen/Qwen3.5-9B` config: 8 full-attention
     layers of 32, 4 KV heads, head_dim 256, bfloat16 => 32,768 bytes/token,
     0.50 GiB at 16,384 tokens hybrid, 2.00 GiB if every layer were full;
  6. hybrid layer counting: `layer_types` first, then `full_attention_interval`,
     then `recurrent_layers`, then every layer;
  7. it writes nothing, and it runs nothing unattended (Rule 4).

Every check below drives the `fetch=` seam with a fixture. Nothing here opens a
socket, and the suite is standard library only.

The suite discovers its `t_` functions from `globals()`, so there is no
hand-written tuple at the bottom to keep in step (checked 2026-10-15).
"""
import hashlib
import inspect
import json
import re
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jarvis_hf_inspect as H  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def source() -> str:
    return (HERE / "jarvis_hf_inspect.py").read_text(encoding="utf-8")


#: The real config, fetched from
#: https://huggingface.co/Qwen/Qwen3.5-9B/raw/main/config.json on 2026-10-15.
QWEN35_9B = {
    "text_config": {
        "num_hidden_layers": 32,
        "full_attention_interval": 4,
        "num_attention_heads": 16,
        "num_key_value_heads": 4,
        "head_dim": 256,
        "hidden_size": 4096,
        "dtype": "bfloat16",
        "layer_types": (["linear_attention"] * 3 + ["full_attention"]) * 8,
    }
}

#: A listing shaped like a real GGUF repo's: two model quants, a projector,
#: and a file that is neither.
TREE = [
    {"path": "Qwen3.5-9B-UD-Q4_K_M.gguf", "size": 5_500_000_000},
    {"path": "Qwen3.5-9B-Q4_K_M.gguf", "size": 5_400_000_000},
    {"path": "mmproj-F16.gguf", "size": 1_200_000_000},
    {"path": "README.md", "size": 1_000},
]


def _fetch(entries=TREE, seen=None):
    def fetch(url):
        if seen is not None:
            seen.append(url)
        return json.dumps(entries)
    return fetch


def t_the_url_is_the_names_only_listing_and_a_bad_repo_id_is_refused():
    check("the listing URL is exactly the names-only one",
          H.tree_url("Qwen/Qwen3.5-9B") ==
          "https://huggingface.co/api/models/Qwen/Qwen3.5-9B/tree/main?recursive=true",
          H.tree_url("Qwen/Qwen3.5-9B"))
    for bad in ("", "no-slash", "https://huggingface.co/api/models/x/y", "a/b?token=1",
                "owner/name/../../etc", "owner//name"):
        refused = False
        try:
            H.tree_url(bad)
        except ValueError:
            refused = True
        check("refused: %r" % (bad,), refused, "it was accepted")
    seen = []
    H.read_tree("Qwen/Qwen3.5-9B", fetch=_fetch(seen=seen))
    check("the call carries the URL and nothing else",
          seen == ["https://huggingface.co/api/models/Qwen/Qwen3.5-9B/tree/main?recursive=true"],
          seen)
    # The one-argument shape above IS the proof: read_tree passes no headers,
    # no body and no second argument. The source is checked too, so a later
    # edit cannot start sending a token.
    src = source()
    for forbidden in ("Authorization", "Cookie", "token=", "api_key", "HF_TOKEN",
                      "os.environ", "netrc"):
        check("the module never sends %s" % forbidden, forbidden not in src)
    check("the request sets only a User-Agent",
          src.count("urllib.request.Request(") == 1 and 'headers={"User-Agent"' in src)


def t_the_vision_projector_is_reported_separately_from_the_model():
    plan = H.plan(TREE)
    check("the model's bytes total only the model GGUFs",
          plan["model"]["bytes"] == 5_500_000_000 + 5_400_000_000, plan["model"]["bytes"])
    check("the projector has its own entry and its own bytes",
          plan["mmproj"]["bytes"] == 1_200_000_000
          and [f["path"] for f in plan["mmproj"]["files"]] == ["mmproj-F16.gguf"],
          plan["mmproj"])
    check("a file that is neither is not counted as either",
          plan["other"]["bytes"] == 1_000 and H.gib(plan["other"]["bytes"]) == 0.0)
    rep = H.report("Qwen/Qwen3.5-9B", fetch=_fetch())
    check("the report keeps the two figures apart",
          rep["model_bytes"] == 10_900_000_000 and rep["mmproj_bytes"] == 1_200_000_000,
          rep)
    check("the download total is both files",
          rep["download_bytes"] == 12_100_000_000, rep["download_bytes"])


def t_quantisation_labels_are_kept_exactly_as_the_repo_writes_them():
    labels = H.quant_labels(TREE)
    check("UD-Q4_K_M is kept verbatim, not normalised to Q4_K_M",
          labels == ["UD-Q4_K_M", "Q4_K_M", "F16"], labels)
    check("a dynamic quant and a plain one are different labels",
          "UD-Q4_K_M" in labels and "Q4_K_M" in labels and len(set(labels)) == len(labels))
    more = H.quant_labels([{"path": "x-IQ3_XXS.gguf"}, {"path": "y-BF16.gguf"},
                           {"path": "z-Q4_K_M.gguf"}])
    check("IQ-quants and BF16 are recognised as written", more == ["IQ3_XXS", "BF16", "Q4_K_M"], more)
    check("a label split by a dot is not invented",
          H.quant_labels([{"path": "model.gguf"}]) == [])
    check("the projector's own label counts too",
          H.quant_labels([{"path": "mmproj-F16.gguf"}]) == ["F16"])


def t_the_kv_arithmetic_on_the_real_qwen35_9b_config():
    """2 * full_attention_layers * kv_heads * head_dim * bytes_per_elem, on the
    config Hugging Face serves for Qwen/Qwen3.5-9B today."""
    shape = H.kv_shape(QWEN35_9B)
    check("8 of the 32 layers carry a growing cache",
          shape["full_attention_layers"] == 8 and shape["total_layers"] == 32, shape)
    check("4 KV heads and head_dim 256 come from the config",
          shape["kv_heads"] == 4 and shape["head_dim"] == 256, shape)
    check("bfloat16 is 2 bytes", H.dtype_bytes(QWEN35_9B) == 2.0)
    check("32,768 bytes per token",
          H.kv_bytes_per_token(QWEN35_9B) == 32768, H.kv_bytes_per_token(QWEN35_9B))
    check("0.50 GiB at 16,384 tokens (hybrid)",
          H.kv_cache_bytes(QWEN35_9B, 16384) == 536_870_912
          and H.gib(H.kv_cache_bytes(QWEN35_9B, 16384)) == 0.5,
          H.kv_cache_bytes(QWEN35_9B, 16384))
    check("2.00 GiB at 16,384 if every layer were full attention",
          H.gib(2 * 32 * 4 * 256 * 2 * 16384) == 2.0)
    check("a q8_0 cache is 0.27 GiB, which is where the work order's first figure comes from",
          H.gib(H.kv_cache_bytes(QWEN35_9B, 16384, H.KV_BYTES_PER_ELEM["q8_0"])) == 0.27,
          H.gib(H.kv_cache_bytes(QWEN35_9B, 16384, H.KV_BYTES_PER_ELEM["q8_0"])))
    check("the report carries the arithmetic it used",
          "2 * 8 layers * 4 kv_heads * 256 head_dim * 2 bytes"
          in H.report("Qwen/Qwen3.5-9B", config=QWEN35_9B, fetch=_fetch())["kv"]["arithmetic"])


def t_hybrid_layers_are_counted_by_the_most_exact_rule_available():
    types = {"num_hidden_layers": 32, "num_key_value_heads": 4, "head_dim": 128,
             "layer_types": ["full_attention"] + ["linear_attention"] * 31}
    check("layer_types wins when it is there",
          H.attention_layers(types)["full"] == 1, H.attention_layers(types))
    by_interval = {"num_hidden_layers": 32, "full_attention_interval": 4}
    check("full_attention_interval is used when there is no layer_types",
          H.attention_layers(by_interval)["full"] == 8, H.attention_layers(by_interval))
    by_recurrent = {"num_hidden_layers": 32, "recurrent_layers": 24}
    check("recurrent_layers is used when there is no interval",
          H.attention_layers(by_recurrent)["full"] == 8, H.attention_layers(by_recurrent))
    plain = {"num_hidden_layers": 32}
    check("a plain transformer counts every layer",
          H.attention_layers(plain)["full"] == 32, H.attention_layers(plain))
    fallback = {"num_hidden_layers": 32, "num_attention_heads": 16, "hidden_size": 2048}
    check("head_dim falls back to hidden_size / heads",
          H.kv_shape(fallback)["head_dim"] == 128, H.kv_shape(fallback))
    no_kv = {"num_hidden_layers": 4, "num_attention_heads": 8, "head_dim": 128}
    check("KV heads fall back to the attention heads",
          H.kv_shape(no_kv)["kv_heads"] == 8, H.kv_shape(no_kv))


def t_what_a_repo_is_missing_is_said_in_words():
    check("a repo with no GGUF at all says so",
          H.problems([{"path": "README.md", "size": 1}]) ==
          ["this repo has no model GGUF in its main tree"],
          H.problems([{"path": "README.md", "size": 1}]))
    check("two model GGUFs are one named problem",
          any("2 model GGUFs" in p for p in H.problems(TREE)), H.problems(TREE))
    check("a projector with no model says so",
          any("no model to pair it with" in p
              for p in H.problems([{"path": "mmproj-F16.gguf", "size": 5}])),
          H.problems([{"path": "mmproj-F16.gguf", "size": 5}]))
    check("a file with no size in the listing says so",
          any("no size in the listing" in p
              for p in H.problems([{"path": "a.gguf", "size": None}])),
          H.problems([{"path": "a.gguf", "size": None}]))
    check("a clean repo has no problems",
          H.problems([{"path": "a-Q4_K_M.gguf", "size": 5}]) == [],
          H.problems([{"path": "a-Q4_K_M.gguf", "size": 5}]))


def code_only(text: str) -> str:
    """The module's CODE: docstrings, comments and the `__main__` block removed.

    The read-only checks below ask "does the code DO this", and prose that says
    the word (a docstring explaining that it holds no schedule) is not the code
    doing it. `urlopen(` is a read, so it is not `open(` either."""
    text = re.sub(r'"""(?:.|\n)*?"""', "", text)
    text = re.sub(r"#[^\n]*", "", text)
    return text.split('if __name__ == "__main__":')[0]


def t_it_writes_nothing_and_runs_nothing_unattended():
    """Two rules at once: this module may not write (no file, no cache, no
    state, no audit row), and nothing about it may run on its own (Rule 4 -
    an unattended model check would have to raise a SUGGESTION, not run)."""
    src = source()
    code = code_only(src)
    for verb in (".write(", "write_text", "mkdir", "sqlite3", "subprocess",
                 "tempfile", "shutil", "atexit"):
        check("the code does not call %s" % verb, verb not in code, "found in the code")
    check("the code does not call open() itself (urlopen is a read and is not matched)",
          re.search(r"(?<![\w.])open\s*\(", code) is None,
          "found: %r" % (re.search(r"(?<![\w.])open\s*\(", code) or ""))
    check("nothing under __main__ is required: print() appears only there",
          re.search(r"(?<![\w.])print\s*\(", code) is None
          and "print(" in src.split('if __name__ == "__main__":')[-1])
    for unattended in ("threading", "Timer", "schedule", "register_kind", "daemon",
                       "while True", "sleep("):
        check("nothing HERE is unattended: no %s" % unattended, unattended not in code)
    check("the module is importable with no network and no arguments", callable(H.report))
    check("twin exists and matches",
          hashlib.sha256((HERE / "jarvis_hf_inspect.py").read_bytes()).hexdigest() ==
          hashlib.sha256((HERE.parent / "jarvis-backend" / "jarvis_hf_inspect.py").read_bytes()).hexdigest())


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
    sys.exit(1 if FAILED else 0)
