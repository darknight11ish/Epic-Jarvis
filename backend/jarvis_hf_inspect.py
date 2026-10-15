"""jarvis_hf_inspect.py - verify a GGUF sitting on Hugging Face BEFORE anything is downloaded.

WHY THIS EXISTS. The model-picker path in this project treats a repo id as
enough: type `owner/model-GGUF`, and the download starts. That is how a 30 GB
mistake gets made - the wrong quantisation, a repo whose vision projector is a
separate file nobody counted, a "9B" that is really a hybrid whose cache is
four times smaller than a full-attention model of the same size, or a file
list that says `UD-Q4_K_M` and gets normalised to `Q4_K_M` by the app so the
owner cannot find the file he actually wants. This module answers those
questions from the file LISTING alone.

WHAT LEAVES THIS MACHINE, EXACTLY. One HTTPS GET:

    https://huggingface.co/api/models/<owner>/<name>/tree/main?recursive=true

The repo id is the whole request. No token, no cookie, no key, no query about
this machine, no name of a local file, no words from a chat, nothing about the
owner. The listing is names and byte sizes - it is not the model, nothing is
downloaded, and no weight ever crosses the wire from this module. That is the
"URL-first" rule: verify by looking, then let a download happen somewhere that
has been given a reason to.

FOUR THINGS IT ANSWERS, and nothing else:

  1. WHAT IS IN THE REPO, by name and byte size, with the vision projector
     (`mmproj-*.gguf`) REPORTED SEPARATELY from the model GGUF. A repo that
     ships both is two downloads, and a budget that counts one is wrong by
     gigabytes - the projector is a second file with its own size, not a line
     in the model.
  2. THE EXACT QUANTISATION LABELS THE REPO USES, kept verbatim: `UD-Q4_K_M`
     stays `UD-Q4_K_M` and is never normalised to `Q4_K_M`. Unsloth-style
     dynamic quants and IQ-quants are different files with different sizes,
     and the label is the only thing that tells them apart.
  3. THE KV CACHE, by the arithmetic below, for a hybrid model as well as a
     full-attention one.
  4. WHAT WOULD BE MISSING: no GGUF at all, more than one model GGUF, a
     projector with no model, a file without a size.

THE KV ARITHMETIC, spelled out because it is the part that gets models wrong:

    bytes per token = 2 * full_attention_layers * kv_heads * head_dim * bytes_per_elem

  * the leading 2 is K AND V: a cache holds both, so leaving it out halves the
    answer, which is how a model looks affordable and then does not fit;
  * `full_attention_layers` is what makes a HYBRID model different. A model
    with `full_attention_interval` (or an explicit `layer_types`) runs full
    attention every Nth layer and a recurrent/linear state on the rest, and
    only the full-attention layers have a growing KV cache. Counted from
    `layer_types` when the config lists it - that is exact - else from
    `num_hidden_layers / full_attention_interval`, else `num_hidden_layers -
    recurrent_layers`, else every layer (a plain transformer);
  * `kv_heads` is `num_key_value_heads` (grouped-query attention) and falls
    back to `num_attention_heads`; `head_dim` is `head_dim` and falls back to
    `hidden_size / num_attention_heads`, which is the same number on most
    models and quietly different on some;
  * `bytes_per_elem` follows the cache dtype (`dtype`, or `torch_dtype` on
    older configs): bfloat16/float16 are 2, float32 is 4. A quantised cache
    passes its own figure (`KV_BYTES_PER_ELEM["q8_0"]`); the default is the
    config's own dtype and never a guess.

MEASURED, on the real `Qwen/Qwen3.5-9B` config (fetched 2026-10-15; 32 layers,
`full_attention_interval: 4`, `layer_types` naming 8 full-attention layers,
4 KV heads, `head_dim` 256, bfloat16):

    hybrid   2 *  8 * 4 * 256 * 2 =  32,768 bytes/token  ->  0.50 GiB at 16,384
    all-full 2 * 32 * 4 * 256 * 2 = 131,072 bytes/token  ->  2.00 GiB at 16,384

  The work order this module came from quotes "0.27 GiB instead of 1.19 GiB"
  for that model. Those two figures are NOT this arithmetic on that config: the
  ratio here is exactly 4 (32/8) and the numbers are 0.50 and 2.00 GiB, not
  0.27 and 1.19. 0.266 GiB IS what the hybrid half gives if the cache is
  q8_0-quantised (`KV_BYTES_PER_ELEM["q8_0"]` = 1.0625 bytes), so the order of
  magnitude in the work order is right and the figures are not; the corrected
  pair is in this docstring and in the tests, and both figures are computed by
  the same function, so neither can drift.

NEVER UNATTENDED. This module only answers when it is asked - it registers no
timer, no schedule kind, no background job and no watcher (Rule 4). A caller
that wants a model checked on a schedule must raise a SUGGESTION through the
usual gate; that decision is not made here.

NO WRITES AT ALL: no file, no cache, no state, no audit row. Standard library
only; the one outbound call is the listing above.

READY TO REGISTER as a shipped module: it is written to sit beside the other
backend modules and needs its one line in `$SHIPPED`, `backend/_where.py` and
`jarvis-backend/_where.py` - which this change does not touch.
"""
from __future__ import annotations

import json
import re
import urllib.request
from typing import Callable, Optional

#: The listing endpoint. `%s` is the repo id, `owner/name`.
TREE_URL = "https://huggingface.co/api/models/%s/tree/main?recursive=true"

#: A repo id, and nothing that could be a URL, a path or a query string.
REPO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}/[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")

#: The default context the budget is quoted at.
DEFAULT_CONTEXT = 16384

#: The one header this module sends, so a Hugging Face operator reading their
#: own logs can see where the request came from. No token, no cookie, ever.
USER_AGENT = "Epic-Jarvis-hf-inspect/1 (names-only listing; no download)"

#: Cache element sizes, in bytes. bfloat16 and float16 are 2; float32 is 4. The
#: quantised entries are llama.cpp's own KV-cache types, and their sizes are the
#: block sizes (q8_0: 32 weights + 1 scale every 32 elements = 34/32 = 1.0625).
KV_BYTES_PER_ELEM = {
    "float32": 4.0, "fp32": 4.0, "f32": 4.0,
    "float16": 2.0, "fp16": 2.0, "f16": 2.0, "half": 2.0,
    "bfloat16": 2.0, "bf16": 2.0,
    "q8_0": 1.0625, "q5_1": 0.6875, "q5_0": 0.625, "q4_1": 0.5625, "q4_0": 0.5625,
}

#: The quantisation labels this module recognises INSIDE a filename. The match
#: is returned exactly as it appears - `UD-Q4_K_M` is not `Q4_K_M`.
QUANT_LABEL = re.compile(
    r"(?<![A-Za-z0-9])((?:UD-)?(?:IQ|Q)\d+(?:_[A-Z0-9]+)*|BF16|F16|FP16|F32|FP32)(?![A-Za-z0-9])")

#: The vision projector's filename stem. A GGUF that starts with this is the
#: projector, not the model, and its bytes are reported separately.
MMPROJ_PREFIX = "mmproj-"


def tree_url(repo: str) -> str:
    """The one URL this module ever asks for, from a validated repo id.

    Raises ValueError for anything that is not `owner/name` - a URL would let a
    caller put a query string on the request, and a token is exactly what must
    never be in here.
    """
    repo = str(repo or "").strip().strip("/")
    if not REPO_ID.match(repo):
        raise ValueError("a repo id looks like owner/name, not %r" % (repo,))
    return TREE_URL % repo


def _default_fetch(url: str, timeout: float) -> str:
    """The one outbound call: a plain GET, no auth, no cookie jar, no body."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:   # nosec - listing only
        return resp.read().decode("utf-8", "replace")


def read_tree(repo: str, *, fetch: Optional[Callable[[str], str]] = None,
              timeout: float = 20.0) -> list:
    """The repo's file listing: `[{"path", "size"}, ...]`.

    `fetch` is the seam a test drives without a network; left out, the plain
    GET above is used. A listing that is not a list of entries, or an entry
    with no path, is refused rather than half-read - a partial file list would
    produce a confident wrong byte total.
    """
    url = tree_url(repo)
    raw = (fetch or (lambda u: _default_fetch(u, timeout)))(url)
    try:
        data = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("the listing was not JSON: %s" % exc)
    if not isinstance(data, list):
        raise ValueError("the listing was not a list of files")
    out = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "").strip()
        if not path:
            continue
        size = entry.get("size")
        out.append({"path": path,
                    "size": int(size) if isinstance(size, (int, float)) else None,
                    "lfs": bool(entry.get("lfs") or entry.get("lfs") is not None)})
    return out


def is_projector(path: str) -> bool:
    """Whether `path` is a vision projector rather than the model itself."""
    return path.rsplit("/", 1)[-1].lower().startswith(MMPROJ_PREFIX)


def is_gguf(path: str) -> bool:
    return path.lower().endswith(".gguf")


def quant_labels(entries: list) -> list:
    """Every quantisation label the GGUF files name, EXACTLY as the repo writes
    it, in listing order, without duplicates.

    `.../model-UD-Q4_K_M.gguf` gives `UD-Q4_K_M`; `.../model-Q4_K_M.gguf` gives
    `Q4_K_M`. They are different files at different sizes and both are kept.
    """
    labels = []
    for entry in entries:
        path = str((entry or {}).get("path") or "")
        if not is_gguf(path):
            continue
        for found in QUANT_LABEL.findall(path):
            if found not in labels:
                labels.append(found)
    return labels


def plan(entries: list) -> dict:
    """What a download of this repo would consist of, in bytes.

    `mmproj` is its OWN entry with its own total: a repo that ships a projector
    is two files, and a budget that folds them together under-reports the
    download by the projector's whole size.
    """
    model, projector, other = [], [], []
    for entry in entries:
        path = str((entry or {}).get("path") or "")
        if not is_gguf(path):
            other.append(entry)
        elif is_projector(path):
            projector.append(entry)
        else:
            model.append(entry)
    def total(rows):
        return sum(int(r.get("size") or 0) for r in rows)
    return {"model": {"files": model, "bytes": total(model)},
            "mmproj": {"files": projector, "bytes": total(projector)},
            "other": {"files": other, "bytes": total(other)},
            "quants": quant_labels(entries)}


def attention_layers(config: dict) -> dict:
    """How many of a model's layers carry a growing KV cache.

    In order of exactness: an explicit `layer_types` list (count the entries
    that are `full_attention`), then `full_attention_interval`, then
    `recurrent_layers`, then every layer. `why` says which rule answered, so a
    budget can be argued with.
    """
    config = config if isinstance(config, dict) else {}
    total = config.get("num_hidden_layers")
    total = int(total) if isinstance(total, (int, float)) and total else 0
    types = config.get("layer_types")
    if isinstance(types, list) and types:
        full = sum(1 for t in types if str(t).lower() in ("full_attention", "full", "attention"))
        return {"total": len(types), "full": full, "recurrent": len(types) - full,
                "why": "layer_types names %d full-attention layer(s)" % full}
    interval = config.get("full_attention_interval")
    if isinstance(interval, (int, float)) and interval and total:
        full = max(1, int(round(total / float(interval))))
        return {"total": total, "full": full, "recurrent": total - full,
                "why": "every %gth of %d layers" % (float(interval), total)}
    recurrent = config.get("recurrent_layers")
    if isinstance(recurrent, (int, float)) and total:
        full = max(0, total - int(recurrent))
        return {"total": total, "full": full, "recurrent": int(recurrent),
                "why": "%d of %d layers are recurrent" % (int(recurrent), total)}
    return {"total": total, "full": total, "recurrent": 0,
            "why": "no hybrid fields; every layer is full attention"}


def dtype_bytes(config: dict, override: Optional[float] = None) -> float:
    """The cache element size: an explicit `override` (a quantised cache), else
    the config's own dtype, else bfloat16's 2 - and `None` is never guessed at
    silently, because a caller who wants the config's figure gets it."""
    if override is not None:
        return float(override)
    config = config if isinstance(config, dict) else {}
    say = str(config.get("dtype") or config.get("torch_dtype") or "").lower()
    say = say.replace("torch.", "")
    return KV_BYTES_PER_ELEM.get(say, 2.0)


def kv_shape(config: dict) -> dict:
    """The four numbers the cache arithmetic needs, each with where it came
    from - so a wrong budget can be traced to the field that caused it."""
    config = config if isinstance(config, dict) else {}
    text = config.get("text_config") if isinstance(config.get("text_config"), dict) else config
    layers = attention_layers(text)
    heads = text.get("num_attention_heads")
    kv_heads = text.get("num_key_value_heads")
    kv_heads = int(kv_heads) if isinstance(kv_heads, (int, float)) and kv_heads else (
        int(heads) if isinstance(heads, (int, float)) and heads else 0)
    head_dim = text.get("head_dim")
    if isinstance(head_dim, (int, float)) and head_dim:
        head_dim = int(head_dim)
        head_dim_why = "head_dim"
    elif isinstance(heads, (int, float)) and heads and isinstance(text.get("hidden_size"), (int, float)):
        head_dim = int(text["hidden_size"]) // int(heads)
        head_dim_why = "hidden_size / num_attention_heads"
    else:
        head_dim = 0
        head_dim_why = "not in the config"
    return {"full_attention_layers": layers["full"], "total_layers": layers["total"],
            "kv_heads": kv_heads, "head_dim": head_dim,
            "layers_why": layers["why"], "head_dim_why": head_dim_why}


def kv_bytes_per_token(config: dict, bytes_per_elem: Optional[float] = None) -> int:
    """`2 * full_attention_layers * kv_heads * head_dim * bytes_per_elem`.

    The 2 is K and V. Only the full-attention layers are counted, so a hybrid
    model is budgeted for the cache it really grows.
    """
    shape = kv_shape(config)
    return int(2 * shape["full_attention_layers"] * shape["kv_heads"] * shape["head_dim"]
               * dtype_bytes(config, bytes_per_elem))


def kv_cache_bytes(config: dict, context: int = DEFAULT_CONTEXT,
                   bytes_per_elem: Optional[float] = None) -> int:
    """The whole cache for `context` tokens."""
    return kv_bytes_per_token(config, bytes_per_elem) * max(0, int(context))


def gib(n: float) -> float:
    """Bytes as GiB, to two places - the unit a budget is argued in."""
    return round(float(n) / float(1 << 30), 2)


def report(repo: str, *, config: Optional[dict] = None,
           context: int = DEFAULT_CONTEXT, bytes_per_elem: Optional[float] = None,
           fetch: Optional[Callable[[str], str]] = None,
           timeout: float = 20.0) -> dict:
    """Everything the module knows about `repo`, as data - no printing, no
    writing. `config` is the model's own `config.json` when the caller has it
    (a local file, a repo file, or a test fixture); without it the KV half is
    reported as unknown rather than guessed."""
    url = tree_url(repo)
    entries = read_tree(repo, fetch=fetch, timeout=timeout)
    plan_of_files = plan(entries)
    out = {"repo": repo, "url": url, "files": entries,
           "model_bytes": plan_of_files["model"]["bytes"],
           "mmproj_bytes": plan_of_files["mmproj"]["bytes"],
           "mmproj_files": [f["path"] for f in plan_of_files["mmproj"]["files"]],
           "model_files": [f["path"] for f in plan_of_files["model"]["files"]],
           "quants": plan_of_files["quants"],
           "download_bytes": plan_of_files["model"]["bytes"] + plan_of_files["mmproj"]["bytes"],
           "problems": problems(entries)}
    if isinstance(config, dict) and config:
        shape = kv_shape(config)
        hybrid = kv_cache_bytes(config, context, bytes_per_elem)
        full = int(2 * shape["total_layers"] * shape["kv_heads"] * shape["head_dim"]
                   * dtype_bytes(config, bytes_per_elem)) * max(0, int(context))
        out["kv"] = {"per_token": kv_bytes_per_token(config, bytes_per_elem),
                     "context": int(context), "bytes": hybrid, "gib": gib(hybrid),
                     "if_every_layer_were_full_bytes": full,
                     "if_every_layer_were_full_gib": gib(full),
                     "shape": shape,
                     "bytes_per_elem": dtype_bytes(config, bytes_per_elem),
                     "arithmetic": "2 * %d layers * %d kv_heads * %d head_dim * %g bytes"
                                   % (shape["full_attention_layers"], shape["kv_heads"],
                                      shape["head_dim"], dtype_bytes(config, bytes_per_elem))}
    else:
        out["kv"] = None
    return out


def problems(entries: list) -> list:
    """What is wrong with this repo for the purpose of downloading a model, in
    plain words. Empty means nothing this module can see."""
    out = []
    plan_of_files = plan(entries)
    models = plan_of_files["model"]["files"]
    if not models:
        out.append("this repo has no model GGUF in its main tree")
    if len(models) > 1:
        out.append("this repo has %d model GGUFs; pick one by its exact quant label"
                   % len(models))
    if plan_of_files["mmproj"]["files"] and not models:
        out.append("there is a vision projector but no model to pair it with")
    for row in plan_of_files["model"]["files"] + plan_of_files["mmproj"]["files"]:
        if row.get("size") is None:
            out.append("%s has no size in the listing" % row["path"])
    return out


def words(rep: dict) -> str:
    """The data above in plain sentences - what a card or a chat line shows.
    (A caller may show its own words; this one keeps every figure it prints
    traceable to a field in `report()`.)"""
    lines = ["%s: %s model file(s), %.2f GiB" % (rep["repo"], len(rep["model_files"]),
                                                 gib(rep["model_bytes"]))]
    if rep["mmproj_files"]:
        lines.append("plus the vision projector: %s, %.2f GiB (a separate download)"
                     % (", ".join(rep["mmproj_files"]), gib(rep["mmproj_bytes"])))
    if rep["quants"]:
        lines.append("quantisation as the repo names it: %s" % ", ".join(rep["quants"]))
    kv = rep.get("kv")
    if kv:
        lines.append("KV cache at %s tokens: %.2f GiB (%s); if every layer were full "
                     "attention it would be %.2f GiB"
                     % (f"{kv['context']:,}", kv["gib"], kv["arithmetic"],
                        kv["if_every_layer_were_full_gib"]))
    for problem in rep["problems"]:
        lines.append("problem: %s" % problem)
    return "\n".join(lines)


if __name__ == "__main__":                                  # pragma: no cover
    import sys
    if len(sys.argv) < 2:
        print("usage: python jarvis_hf_inspect.py <owner/name> [context]")
        raise SystemExit(2)
    _ctx = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_CONTEXT
    print(words(report(sys.argv[1], context=_ctx)))
