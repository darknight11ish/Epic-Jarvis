"""jarvis_model_recommendations.py - suggest a better local model, measure it, and
suggest which preset should use it. Nothing here downloads, switches or applies.

WHAT THE OWNER ASKED FOR (2026-10-28, their own words)

    "can you give jarvis the ability to recommend a change to presets (for the
     local ai models being used) with a one click check for new models button and
     it will look on hugging face for newer potentially better models, give me a
     card to approve a download and a bench mark testing locally, then it will
     recommend changing the presets based on the local gpus and what model goes
     where and i can approve or give my opinion and jarvis can change the preset
     recommendations then i approve?"

So this module is the READING half of that, and only the reading half:

    GET  /api/models/recommendations          what is cached + what is measured
    POST /api/models/check                    one click: look, cache, answer
    POST /api/models/benchmark   {"ref"}      measure an INSTALLED model here
    POST /api/presets/recommend  {}           changes justified by measurements
    POST /api/presets/recommend/opinion {"text"}  the owner's note refines them

TWO THINGS THIS MODULE NEVER DOES, and they are the point of the split:

  * It NEVER DOWNLOADS. `/api/models/check` fetches public catalogue LISTINGS;
    no weights are requested, no `/api/pull` is called, and a new model reaches
    the PC only when the owner approves the EXISTING `/api/models/install` card,
    which is `jarvis_hud.py`'s own route and `jarvis_models.install()`. There is
    no install route in this module, and `backend/test_model_recommendations.py`
    proves by reading this file that it calls none.
  * It NEVER APPLIES A PRESET. A recommendation is a sentence. Applying one is
    the EXISTING `/api/work/apply` card (`jarvis_presets.apply_preset`), which
    raises the one `switch_model` ask card, and this module has no route for it.

NO CARD, ANYWHERE IN THIS MODULE. Checking a public list, measuring a model
already on the PC, and reading the preset table are all READ-ONLY in the sense
that matters to the gate: no model is downloaded, switched or applied. A
measurement does LOAD the model on the graphics card for a few seconds - the
same thing asking it a question does - and that is said plainly in the answer.

DESKTOP-ONLY, ON PURPOSE. The owner's standing rule is that the phone must not
grow a model catalogue (CLAUDE.md; the install-from-phone amendment of
2026-09-20 allows a TYPED ref and nothing to browse). All five routes here
refuse another device with 403 before reading a body, using the project's ONE
rule: `jarvis_owner_check.from_this_pc(peer, local)` - the same call
`jarvis_brain_reads`, `jarvis_media_index` and the other PC-only routes wrap.
`docs/ARCHITECTURE.md` section 8 says so in words. The phone's existing model
routes (`/api/models/install`, `/api/models/switch`) are untouched.

WHERE THE NETWORK COMES FROM - the repo's existing capability, not a new key.

`/api/models/check` calls `jarvis_models.discover()`, the model manager's own
public-catalogue pass. That module is OWNER_ONLY (never shipped; patched by
`vram-estimate.patch` and `gpu-offload.patch`) and it documents every URL it
can fetch:

    HF_TRENDING    https://huggingface.co/api/models?pipeline_tag=text-generation
                   &filter=gguf&sort=trendingScore&direction=-1&limit=<n>
    OLLAMA_SEARCH  https://ollama.com/search?page=<n>
    EVALPLUS       https://raw.githubusercontent.com/evalplus/evalplus.github.io/
                   main/results.json
    HF_MODEL       https://huggingface.co/api/models/<repo>?expand[]=gguf
    HF_TREE        https://huggingface.co/api/models/<repo>/tree/main

No token, cookie, key, query term or word from the owner is in any of them -
they are fixed public addresses, and `jarvis_models.outbound_requests()` exists
so a person can read the list. This module adds no key and no second network
stack; the same pass enriches a candidate with its GGUF parameter count,
context and Q4_K_M file size from the public listing. `jarvis_hf_inspect.py` is
the repo's other Hugging Face reader (a repo's own file listing, also keyless);
it is not called here because the catalogue pass already answers the size and
quant question this module needs, and duplicating it would be a second reader
for one job.

If `jarvis_models` is not on the backend, the answer is an HONEST 503 naming
that module. Nothing is invented, no direct URL is opened behind its back, and
no candidate is made up.

WHAT "MEASURED" MEANS HERE, AND WHAT DOES NOT

A preset change is only ever justified by numbers this PC produced:

    tokens per second   jarvis_speed.measure() - Ollama's own `eval_count` /
                        `eval_duration` from a native /api/generate reply
    video memory        Ollama's /api/ps `size_vram` for the model while it is
                        loaded for the benchmark (jarvis_models.offload_status).
                        That is the window the benchmark ran at, NOT every
                        preset's window: a 196k conversation can need more, and
                        the evidence says so.
    context             the model's own metadata via /api/show
                        (jarvis_models.local_geometry -> train context)
    card sizes          nvidia-smi through jarvis_hardware.detect()

A candidate is never picked because it is bigger, newer or popular. If either
the preset's current model or a candidate has no local benchmark, no model
change is recommended for that preset - there is nothing to compare, and a
guess is not a measurement. The estimate used for the CANDIDATE list (will this
download fit on a card?) is labelled as an estimate in its own sentence; the
PRESET recommendations do not use it.

The "newer" half of the owner's sentence is honest about its limit: the
existing catalogue pass sorts the Hugging Face GGUF list by TRENDING, not by
creation date, and it discards `lastModified`. So this module claims "on the
public trending GGUF list", never "newer than yours". Making a real recency
claim needs that field, which is a change to `jarvis_models.py` (an owner-only
module) and belongs in its own patch rather than being routed around here.

WHERE A MEASUREMENT IS KEPT

Two places, both already the repo's shape:

  * `jarvis_speed.measure()` writes the raw `bench` row it always writes, to
    `speed.jsonl` in the config folder - the speed record's own store, with one
    row per model. This module does not duplicate it or restate its numbers.
  * this module's `model-recommendations.json` keeps the index the contract
    needs: `{ref: {tokens_per_s, vram_gb, context_tokens, measured_at}}`, plus
    the cached check and the owner's last opinion. It is written atomically,
    read defensively, and never contains a word from a conversation.

The docs shape being matched is `docs/MEASURED-2026-10-05-owner-pc.md`: one
model, its tokens a second, how much of the card it held and its context, with
the time it was measured. That document is why the hardware figures in
`docs/MODEL-TOPOLOGY.md` are trusted at all; this module cites both in every
recommendation's `evidence`.

THE SHAPES (the desktop half is built against these; JARVIS-API section 160)

    GET /api/models/recommendations
      {"checked_at": <epoch seconds or null>, "gpus": [{name, vram_gb, role}],
       "candidates": [{ref, name, family, params_b, quant, size_gb,
                       context_tokens, licence, provider, fit, source_url, why}],
       "skipped_no_size": <how many catalogue rows had no public size>,
       "recommendations": [{preset, changes: [{row, from, to, why}], evidence}],
       "benchmarked": {ref: {tokens_per_s, vram_gb, context_tokens, measured_at}}}

`row` is the FIELD of the preset row the change is about - "model", "lane" or
"context" - because `preset` already names the row of `backend/jarvis_presets.py`
(a `Preset` entry) the change belongs to. `fit` is "fits" / "tight" / "no",
from the measured card sizes and the candidate's estimated need.

**A candidate with no real public size is not a candidate.** `jarvis_models.
Model.as_dict()` writes `size_gb = 0.0` when the catalogue gave no `bytes_`
(`jarvis-backend/jarvis_models.py`), and `discover()` enriches only its first
few repos, so most rows arrive with no size at all. The 2026-10-28 field test
showed what admitting them did: every row said "size 0.00 GB from the public
file listing" and "estimated to need about 1.5 GB" - the estimator's 1500 MB
runtime floor with no weights in it - including 27B models marked FITS. So a
row with no positive size is dropped, `skipped_no_size` says how many were
dropped, and the desktop says so in words. A row that is kept quotes the size
the listing really reported, and its need must be at least that size (the
weights alone are the download) or no fit is claimed.

`provider` and `source_url` always agree: the words name the host the link
goes to ("Hugging Face" for huggingface.co, "Ollama's library" for
ollama.com). The panel may not say Hugging Face over an ollama.com link, which
is the second half of the same field test.

`licence` is the repository's own declared licence, taken from the catalogue's
`license:<id>` tag (Hugging Face publishes one) and `null` when the catalogue
reports none - the desktop says "not reported by the catalogue" there rather
than inventing one. The catalogue carries **no SHA-256** for any candidate, so
no hash is published or shown: `jarvis_models.Model` has no such field, and the
answer does not make one up.

    POST /api/models/check      {}            -> the same shape, refreshed
    POST /api/models/benchmark  {"ref": "..."}
      -> {"ref", "tokens_per_s", "vram_gb", "context_tokens", "measured_at",
          "ok", "probes", "note"} (409 not installed, 503 cannot measure)
    POST /api/presets/recommend {}
      -> {"recommendations": [...]}
    POST /api/presets/recommend/opinion {"text": "..."}
      -> {"recommendations": [...], "opinion": {text, rule, at}}

The one additive key is `opinion` on the opinion answer: the owner should be
able to see that their note was recorded and WHICH rule it applied. A failure
carries `ok: false` and a plain `error`; the shape's own keys are still there.

Standard library only. One lock around the store. No timer, no watcher, no
background job: every call is the owner's own click.
"""
from __future__ import annotations

import json
import math
import os
import re
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Callable, Optional

# --------------------------------------------------------------------------
#   The routes this module owns, and the ones it deliberately does not
# --------------------------------------------------------------------------

PATH_RECOMMENDATIONS = "/api/models/recommendations"
PATH_CHECK = "/api/models/check"
PATH_BENCHMARK = "/api/models/benchmark"
PATH_PRESET_RECOMMEND = "/api/presets/recommend"
PATH_OPINION = "/api/presets/recommend/opinion"
GET_PATHS = (PATH_RECOMMENDATIONS,)
POST_PATHS = (PATH_CHECK, PATH_BENCHMARK, PATH_PRESET_RECOMMEND, PATH_OPINION)

#: The EXISTING carded routes recommendations point AT, never through. Named
#: here so the docs and the tests can say which route a person uses next; this
#: module holds no handler for either and never calls one.
INSTALL_ROUTE = "/api/models/install"     # the download card (jarvis_models.install)
APPLY_ROUTE = "/api/work/apply"           # the preset card (jarvis_presets.apply_preset)

#: What another device is told. One plain sentence, the same shape as the other
#: PC-only refusals (`jarvis_media_index.PC_ONLY_REFUSAL`, `jarvis_documents`).
DESKTOP_ONLY_REFUSAL = (
    "Model recommendations are a PC screen: the phone has no model catalogue, "
    "so nothing was read or changed.")

#: Card fit policy. These are POLICY, not measurements: a model within 85% of a
#: measured card is called "fits" (room for the desktop and another lane), up to
#: 100% is "tight", above that "no". Said here so a number in an answer can be
#: traced to a rule rather than to taste.
FIT_ROOM = 0.85
FIT_TIGHT = 1.0

#: A model change needs this much measured gain to be worth a download and a
#: swap. 5% matches `jarvis_models`' own `min_benefit` default; the number is a
#: policy bar, not a measurement.
GAIN_BAR = 0.05

#: The opinion rules' bars. "lower" wants a smaller measured footprint that is
#: not slower; "quality" wants a bigger bar and the longest measured context
#: window, because context is the only capability figure this PC measures.
LOWER_SPEED_FLOOR = 0.95
QUALITY_GAIN_BAR = 0.10

#: One fixed prompt, nothing from any conversation (the same rule
#: `jarvis_speed.FIXED_PROMPTS` follows). `jarvis_speed.measure` caps the answer
#: at 64 tokens, so one benchmark is one short request on this PC.
BENCH_PROMPT = "List the seven days of the week, one per line."

#: The existing catalogue pass, bounded: one Ollama page and four HF repos
#: enriched, so one click cannot turn into an unbounded crawl.
CHECK_LIMIT = 16
CHECK_PAGES = 1
CHECK_ENRICH = 4

#: Where the measurements are kept, beside the other settings. The speed log's
#: raw rows stay in `speed.jsonl`; this file is the index keyed by model ref.
STORE_FILE = "model-recommendations.json"
STORE_SCHEMA = 1

#: The docs a recommendation cites. They are the hardware record, not a number
#: this module reads at run time: the live card sizes come from nvidia-smi.
EVIDENCE_DOCS = ("docs/MEASURED-2026-10-05-owner-pc.md",
                 "docs/MODEL-TOPOLOGY.md")

MAX_REF_CHARS = 200
MAX_OPINION_CHARS = 2000
MAX_OPINIONS = 20
MAX_REASONS = 6

#: A model reference Ollama accepts: a name, optionally `owner/name`, optionally
#: `:tag`, and the Hugging Face spellings `hf.co/owner/name:QUANT`. No URL, no
#: query, no whitespace - the same shape `jarvis_models.safe_ref` allows.
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@:+-]{0,199}$")

_LOCK = threading.RLock()


# --------------------------------------------------------------------------
#   The config folder and the one store
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    """The folder the rest of the backend keeps its settings in.

    Same rule as `jarvis_speed._config_dir` and `jarvis_presets._config_dir`:
    the framework's CONFIG_DIR, else OPENJARVIS_CONFIG_DIR, else
    `~/.openjarvis`. Read per call so a test can point it at a scratch folder
    without re-importing this module.
    """
    try:
        import jarvis_framework as fw  # type: ignore
        if getattr(fw, "CONFIG_DIR", None):
            return Path(fw.CONFIG_DIR)
    except Exception:
        pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def store_path() -> Path:
    return _config_dir() / STORE_FILE


def _empty_store() -> dict:
    return {"schema": STORE_SCHEMA, "checked_at": None, "candidates": [],
            "skipped_no_size": 0, "benchmarked": {}, "opinions": [],
            "last_opinion": None}


def _clean_benchmark(value) -> Optional[dict]:
    """One benchmark row, only in the shape the contract states. A row missing
    its measured rate is not a benchmark and is dropped, not filled in."""
    if not isinstance(value, dict):
        return None
    rate = _number(value.get("tokens_per_s"))
    if rate is None:
        return None
    out = {"tokens_per_s": round(rate, 2),
           "vram_gb": _optional_round(value.get("vram_gb"), 2),
           "context_tokens": _optional_int(value.get("context_tokens")),
           "measured_at": _optional_int(value.get("measured_at"))}
    return out


def _licence(tags) -> Optional[str]:
    """The repository's declared licence, when the catalogue carries one.

    Hugging Face publishes it as a `license:<id>` tag on the model record, which
    `jarvis_models.fetch_huggingface` already keeps in `Model.tags`. Nothing is
    inferred from a model's name or size, and no tag means no licence - the
    desktop says "not reported by the catalogue" there. There is no SHA-256 to
    read at all: `Model` has no hash field, so none is invented.
    """
    for tag in tags if isinstance(tags, (list, tuple)) else []:
        if not isinstance(tag, str):
            continue
        low = tag.strip().lower()
        if low.startswith("license:") or low.startswith("licence:"):
            value = tag.split(":", 1)[1].strip()
            if value:
                return value[:40]
    return None


def _real_size_gb(d: dict) -> Optional[float]:
    """The download size the public listing really reported, or None.

    `jarvis_models.Model.as_dict()` writes `size_gb = 0.0` when the catalogue
    gave no `bytes_` (see `jarvis-backend/jarvis_models.py`), and `discover()`
    enriches only its first few repos, so most rows arrive that way. **Zero is
    not a small model: it is no report at all.** Treating it as a size is what
    let the 2026-10-28 field test show 27B models at "size 0.00 GB from the
    public file listing" and "estimated to need about 1.5 GB" - the
    estimator's runtime floor with no weights in it.

    Only a positive number counts. `bytes_` is read too, because a caller that
    passes a `Model` through `_model_fields` as a dict may carry the raw field
    rather than `as_dict`'s derived `size_gb`.
    """
    for raw in (d.get("size_gb"),
                _gib(_number(d.get("bytes_")) or _number(d.get("bytes")))):
        gb = _number(raw)
        if gb is not None and gb > 0:
            return gb
    return None


def _provider_words(url: str) -> str:
    """The public library a row's link goes to, named the way the row says it.

    `_source_url` builds one of two hosts, and the 2026-10-28 field test found
    every row labelled "On Hugging Face" while most linked to ollama.com.
    Deriving the words from the URL makes that sentence true for either
    library, and for any host a later catalogue adds.
    """
    host = (urllib.parse.urlsplit(url or "").hostname or "").lower()
    if host == "ollama.com" or host.endswith(".ollama.com"):
        return "Ollama's library"
    if host == "huggingface.co" or host.endswith(".huggingface.co"):
        return "Hugging Face"
    return host or "the public listing"


def _clean_candidate(value) -> Optional[dict]:
    if not isinstance(value, dict):
        return None
    ref = str(value.get("ref") or "").strip()
    if not ref:
        return None
    size_gb = _real_size_gb(value)
    if size_gb is None:
        # A stored row with no real public size cannot carry an honest fit.
        # The 2026-10-28 store was full of them ("size 0.00 GB") because an
        # absent `bytes_` was written as zero; drop them on read rather than
        # show a fit that was computed from nothing.
        return None
    fit = str(value.get("fit") or "")
    if fit not in ("fits", "tight", "no"):
        fit = "no"
    source_url = str(value.get("source_url") or "")[:300]
    return {"ref": ref[:MAX_REF_CHARS],
            "name": str(value.get("name") or ref)[:120],
            "family": str(value.get("family") or "")[:80],
            "params_b": _optional_round(value.get("params_b"), 3),
            "quant": (str(value.get("quant"))[:24]
                      if value.get("quant") else None),
            "size_gb": round(size_gb, 2),
            "context_tokens": _optional_int(value.get("context_tokens")),
            "licence": (str(value.get("licence"))[:40]
                        if value.get("licence") else None),
            # A store written before this field existed still names its host
            # from the URL rather than inheriting a Hugging Face claim.
            "provider": str(value.get("provider")
                            or _provider_words(source_url))[:60],
            "fit": fit,
            "source_url": source_url,
            "why": str(value.get("why") or "")[:1000]}


def _clean_opinion(value) -> Optional[dict]:
    if not isinstance(value, dict):
        return None
    text = str(value.get("text") or "").strip()
    if not text:
        return None
    return {"text": text[:MAX_OPINION_CHARS],
            "rule": str(value.get("rule") or "note")[:16],
            "at": _optional_int(value.get("at"))}


def load_store(path: Optional[Path] = None) -> dict:
    """The store, sanitised. Never raises: a damaged file reads as empty, and a
    missing one is not an error (nothing has been checked yet)."""
    p = Path(path) if path else store_path()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return _empty_store()
    if not isinstance(raw, dict):
        return _empty_store()
    out = _empty_store()
    checked = raw.get("checked_at")
    out["checked_at"] = (_int_or_none(checked))
    cands = []
    dropped_no_size = 0
    for c in raw.get("candidates") or []:
        row = _clean_candidate(c)
        if row:
            cands.append(row)
        elif (isinstance(c, dict) and str(c.get("ref") or "").strip()
              and _real_size_gb(c) is None):
            # A row written before the 2026-10-28 fix carried 0.0 for an absent
            # size. It cannot be shown honestly, and it must not vanish without
            # a word either - the count below is what the panel explains.
            dropped_no_size += 1
    out["candidates"] = cands[:64]
    out["skipped_no_size"] = max(
        0, _optional_int(raw.get("skipped_no_size")) or 0) + dropped_no_size
    bench = {}
    for ref, value in (raw.get("benchmarked") or {}).items():
        row = _clean_benchmark(value)
        if row and isinstance(ref, str) and ref.strip():
            bench[ref.strip()[:MAX_REF_CHARS]] = row
    out["benchmarked"] = bench
    ops = []
    for o in raw.get("opinions") or []:
        row = _clean_opinion(o)
        if row:
            ops.append(row)
    out["opinions"] = ops[-MAX_OPINIONS:]
    out["last_opinion"] = _clean_opinion(raw.get("last_opinion"))
    return out


def save_store(doc: dict, path: Optional[Path] = None) -> Optional[str]:
    """Write the store atomically. Returns None on success, a plain sentence on
    failure - the caller decides whether that is fatal."""
    p = Path(path) if path else store_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n",
                       encoding="utf-8")
        tmp.replace(p)
    except OSError as exc:
        return f"could not save the measurements ({type(exc).__name__})"
    return None


# --------------------------------------------------------------------------
#   Small pure helpers
# --------------------------------------------------------------------------

def _number(value) -> Optional[float]:
    """A finite float, or None. A bool is not a number here, and neither is NaN
    or an infinity - they would put "nan tokens/s" in a sentence."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if not math.isfinite(value):
        return None
    return value


def _int_or_none(value) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)):
        return None
    return int(value)


def _optional_int(value) -> Optional[int]:
    return _int_or_none(value)


def _optional_round(value, places: int) -> Optional[float]:
    number = _number(value)
    return round(number, places) if number is not None else None


def _gib(bytes_: Optional[float]) -> Optional[float]:
    if bytes_ is None:
        return None
    return round(bytes_ / float(1 << 30), 2)


def _date(at: Optional[int]) -> str:
    if not at:
        return "an earlier check"
    try:
        return time.strftime("%Y-%m-%d", time.localtime(int(at)))
    except (OSError, ValueError, OverflowError):
        return "an earlier check"


def safe_ref(ref) -> str:
    """A model reference this module will accept, or ValueError.

    Deliberately the same shape `jarvis_models.safe_ref` allows: a name, an
    `owner/name`, a `:tag`, and the `hf.co/owner/name:QUANT` spelling. No URL,
    no query string, no whitespace.
    """
    text = str(ref or "").strip()
    if not text or len(text) > MAX_REF_CHARS or not _REF.match(text):
        raise ValueError("a model ref looks like qwen3.5:9b or "
                         "hf.co/owner/name:Q4_K_M, not %r" % (ref,))
    return text


def _same_ref(a: str, b: str) -> bool:
    """The same model: the same ref, or a bare name against its `:latest`.

    NOT the same base name: `qwen3.5:4b` and `qwen3.5:9b` are two different
    models that both split on ":" to "qwen3.5", and treating them as one would
    hide every sibling comparison this feature exists to make.
    """
    if not a or not b:
        return False
    if a == b:
        return True
    if ":" not in a:
        return f"{a}:latest" == b
    if ":" not in b:
        return f"{b}:latest" == a
    return False


# --------------------------------------------------------------------------
#   Measured hardware
# --------------------------------------------------------------------------

def _presets_module():
    try:
        import jarvis_presets  # type: ignore
        return jarvis_presets
    except Exception:
        return None


def _role_for(name: str) -> str:
    """Which preset lane this card is the named card of, from
    `jarvis_presets.LANES` - main is the long-context card, coding is the fast
    one - and "unassigned" for a card no lane names."""
    low = str(name or "").lower()
    presets = _presets_module()
    lanes = getattr(presets, "LANES", None) if presets else None
    if isinstance(lanes, dict):
        for key, lane in lanes.items():
            card = str((lane or {}).get("card") or "").lower()
            if card and card in low:
                return str(key)
    return "unassigned"


def _default_detect() -> list:
    """The cards this PC reports, from `jarvis_hardware.detect()` - nvidia-smi
    and Ollama's own log, the same measurement the Hardware screen shows. Never
    raises; no cards reads as []."""
    try:
        import jarvis_hardware  # type: ignore
        got = jarvis_hardware.detect() or {}
        rows = got.get("cards") or []
    except Exception:
        return []
    return rows if isinstance(rows, list) else []


def measured_gpus(detect: Optional[Callable[[], list]] = None) -> list:
    """`[{name, vram_gb, role}]` from the PC's own measurement.

    Only a card that is really usable is listed: `used` False means Ollama's
    own log dropped it (an integrated card, say), and a card whose size was not
    read is not a measured card. A test injects `detect`.
    """
    rows = (detect or _default_detect)()
    out = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        if row.get("used") is False:
            continue
        name = str(row.get("name") or row.get("model") or "").strip()
        total = _number(row.get("total_gib"))
        if total is None:
            total = _number(row.get("vram_gb"))
        if total is None:
            total = _number(row.get("vram"))
        if not name or total is None or total <= 0:
            continue
        out.append({"name": name, "vram_gb": round(total, 1),
                    "role": _role_for(name)})
    rank = {"main": 0, "coding": 1}
    out.sort(key=lambda g: (rank.get(g["role"], 2), -g["vram_gb"], g["name"]))
    return out


# --------------------------------------------------------------------------
#   Candidates from the existing public-catalogue pass
# --------------------------------------------------------------------------

class DiscoveryUnavailable(RuntimeError):
    """The owner's backend has no `jarvis_models.py` to read the catalogue
    with. Distinct from a network failure: nothing was attempted."""


def _default_discover() -> list:
    """The existing capability: `jarvis_models.discover()`.

    Fixed public URLs only, no key and no query term (see the module docstring).
    It enriches the first few Hugging Face repos with their GGUF parameter
    count, context length and Q4_K_M file size from the same public listing.
    Bounded here so one click cannot become an unbounded crawl.
    """
    try:
        import jarvis_models  # type: ignore
    except Exception as exc:
        raise DiscoveryUnavailable(
            "the model catalogue is not on this backend, so nothing could be "
            "looked up - and nothing was made up "
            f"({type(exc).__name__})") from exc
    return jarvis_models.discover(limit=CHECK_LIMIT, pages=CHECK_PAGES,
                                  enrich=CHECK_ENRICH) or []


def _default_estimate(model) -> Optional[float]:
    """Estimated video memory in MB for a candidate, from
    `jarvis_models.estimate_vram_mb` - the same estimate the model manager's own
    cards use. None when it cannot answer; a candidate without a size is not
    judged to fit."""
    try:
        import jarvis_models  # type: ignore
        return float(jarvis_models.estimate_vram_mb(model))
    except Exception:
        return None


def _model_fields(model) -> dict:
    """A `jarvis_models.Model` (or a test's dict) as the values the contract
    needs. The dict form is accepted so a suite never needs the owner-only
    module to exist."""
    if isinstance(model, dict):
        d = dict(model)
    else:
        as_dict = getattr(model, "as_dict", None)
        d = as_dict() if callable(as_dict) else {}
        if not d:
            for name in ("ref", "source", "params", "bytes_", "size_gb",
                         "context", "quant", "downloads", "trending", "bench",
                         "tags", "family"):
                value = getattr(model, name, None)
                if value is not None:
                    if name == "family" and callable(value):
                        value = value()
                    d[name] = value
    return d if isinstance(d, dict) else {}


def _fit_label(need_mb: Optional[float], gpus: list) -> tuple:
    """(fit, card, ratio) for an estimated need against the measured cards."""
    need_gb = (need_mb / 1024.0) if need_mb is not None else None
    if need_gb is None or need_gb <= 0 or not gpus:
        return "no", None, None
    best = ("no", None, None)
    for gpu in gpus:
        cap = _number(gpu.get("vram_gb"))
        if cap is None or cap <= 0:
            continue
        ratio = need_gb / cap
        label = ("fits" if ratio <= FIT_ROOM
                 else "tight" if ratio <= FIT_TIGHT else "no")
        order = {"fits": 0, "tight": 1, "no": 2}
        current = best[2] if best[1] is not None else None
        if best[1] is None or order[label] < order[best[0]] or (
                label == best[0] and current is not None and ratio < current):
            best = (label, gpu, ratio)
    return best


def _source_url(ref: str, source: str) -> str:
    if source == "ollama":
        return "https://ollama.com/library/" + urllib.parse.quote(
            ref.split(":", 1)[0], safe="/")
    return "https://huggingface.co/" + urllib.parse.quote(ref, safe="/:")


def _candidate_row(model, gpus: list, estimate: Callable) -> Optional[dict]:
    """One candidate in the shared shape, or None when there is not enough real
    data to place it (no size means no fit claim)."""
    d = _model_fields(model)
    ref = str(d.get("ref") or "").strip()
    if not ref or len(ref) > MAX_REF_CHARS:
        return None
    size_gb = _real_size_gb(d)
    if size_gb is None:
        # No download size from the public listing. A fit judged from nothing is
        # the exact "confident wrong answer" this project keeps paying for: on
        # 2026-10-28 it put 27B models on screen at "size 0.00 GB" and "needs
        # about 1.5 GB", FITS. No size, no row.
        return None
    need_mb = None
    try:
        got = estimate(model)
        need_mb = _number(got)
    except Exception:
        need_mb = None
    if need_mb is not None and need_mb < size_gb * 1024.0:
        # The weights ARE the download, so a need smaller than them contains no
        # weights at all - the 1.5 GB runtime floor the field test saw. Say the
        # need could not be estimated rather than dress that floor up as a fit.
        need_mb = None
    fit, card, ratio = _fit_label(need_mb, gpus)
    context = _optional_int(d.get("context") or d.get("context_tokens"))
    params = _number(d.get("params"))
    params_b = round(params / 1e9, 3) if params else _optional_round(
        d.get("params_b"), 3)
    quant = d.get("quant") or None
    name = ref.rsplit("/", 1)[-1]
    family = d.get("family")
    if callable(family):
        family = family()
    family = str(family or _family_of(ref))
    source = str(d.get("source") or "")
    source_url = _source_url(ref, source)
    why = []
    bench = d.get("bench") if isinstance(d.get("bench"), dict) else {}
    code = _number(bench.get("humaneval+"))
    if code is not None:
        why.append("scores %.0f%% on HumanEval+ (EvalPlus, a public benchmark - "
                   "not measured on this PC)" % (code * 100))
    if context:
        why.append("the listing says %s tokens of context" % f"{context:,}")
    if quant:
        why.append("quantisation %s" % quant)
    if need_mb is None:
        why.append("its video memory need could not be estimated, so no fit is "
                   "claimed")
    elif card is None:
        why.append("no graphics card was measured, so no fit is claimed")
    elif fit == "fits":
        why.append("estimated to need about %.1f GB, which the measured %s "
                   "(%.1f GB) holds with room" % (need_mb / 1024.0,
                                                   card["name"], card["vram_gb"]))
    elif fit == "tight":
        why.append("estimated to need about %.1f GB - only just inside the "
                   "measured %s (%.1f GB)" % (need_mb / 1024.0, card["name"],
                                              card["vram_gb"]))
    else:
        why.append("estimated to need about %.1f GB; the largest measured card "
                   "(%s, %.1f GB) cannot hold it"
                   % (need_mb / 1024.0, card["name"], card["vram_gb"]))
    why.append("size %.2f GB from the public file listing" % size_gb)
    return {"ref": ref, "name": name[:120], "family": family[:80],
            "params_b": params_b, "quant": (str(quant)[:24] if quant else None),
            "size_gb": round(size_gb, 2), "context_tokens": context,
            "licence": _licence(d.get("tags")),
            "provider": _provider_words(source_url),
            "fit": fit, "source_url": source_url,
            "why": "; ".join(why[:MAX_REASONS])}


def _family_of(ref: str) -> str:
    base = ref.rsplit("/", 1)[-1].split(":", 1)[0]
    return re.sub(r"[-_.]?(gguf|instruct|chat|it)$", "", base, flags=re.I).lower()


def build_candidates(models, gpus: list,
                     estimate: Optional[Callable] = None,
                     skipped: Optional[dict] = None) -> list:
    """The candidate list, pure: no network, no store, no clock.

    Sorted fits-first, then by the catalogue's own trending/downloads figures as
    a weak tie-break (never as evidence of quality), then by ref so the answer
    is stable.

    `skipped` is filled with `no_size`: how many catalogue rows were left out
    because the listing reported no download size for them. The caller puts
    that number on the answer so a missing model is explained, not silently
    dropped.
    """
    estimate = estimate or _default_estimate
    rows = []
    for model in models if isinstance(models, list) else []:
        row = _candidate_row(model, gpus, estimate)
        if row is None:
            if (skipped is not None
                    and _real_size_gb(_model_fields(model)) is None):
                skipped["no_size"] = int(skipped.get("no_size") or 0) + 1
            continue
        d = _model_fields(model)
        rows.append((row, _number(d.get("trending")) or 0.0,
                     _number(d.get("downloads")) or 0.0))
    order = {"fits": 0, "tight": 1, "no": 2}
    rows.sort(key=lambda item: (order.get(item[0]["fit"], 3),
                                -item[1], -item[2], item[0]["ref"]))
    return [row for row, _t, _d in rows]


# --------------------------------------------------------------------------
#   Benchmarking an INSTALLED model on this PC
# --------------------------------------------------------------------------

def _default_installed() -> list:
    try:
        import jarvis_models  # type: ignore
        return list(jarvis_models.installed() or [])
    except Exception as exc:
        raise DiscoveryUnavailable(
            "the model manager is not on this backend, so "
            f"the installed list cannot be read ({type(exc).__name__})") from exc


def _default_measure(ref: str) -> dict:
    """`jarvis_speed.measure()`, the repo's existing bounded benchmark: one
    fixed prompt through Ollama's native /api/generate, a 64-token cap,
    temperature 0, a fixed seed, loopback only - and it writes its own `bench`
    row to `speed.jsonl`."""
    import jarvis_speed  # type: ignore
    return jarvis_speed.measure(ref, prompts=(BENCH_PROMPT,))


def _default_ps() -> dict:
    try:
        import jarvis_models  # type: ignore
        return jarvis_models.offload_status(timeout=4.0) or {}
    except Exception:
        return {}


def _default_geometry(ref: str) -> Optional[dict]:
    try:
        import jarvis_models  # type: ignore
        return jarvis_models.local_geometry(ref) or None
    except Exception:
        return None


def _loaded_vram_gb(ref: str, ps: dict) -> Optional[float]:
    """The model's own `size_vram` from /api/ps, in GB. None when it is not
    listed or Ollama did not report it - never inferred from the download."""
    for row in (ps or {}).get("models") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("model") or "")
        if not _same_ref(name, ref):
            continue
        vram_mb = _number(row.get("vram_mb"))
        if vram_mb is None:
            return None
        return round(vram_mb / 1024.0, 2)
    return None


def run_benchmark(ref, *, store_path_: Optional[Path] = None,
                  installed: Optional[Callable[[], list]] = None,
                  measure: Optional[Callable[[str], dict]] = None,
                  ps: Optional[Callable[[], dict]] = None,
                  geometry: Optional[Callable[[str], Optional[dict]]] = None,
                  clock: Optional[Callable[[], float]] = None) -> tuple:
    """Measure ONE installed model on this PC, keep it, return it.

    Refusals, in plain words and with nothing written:
      * 400 for a ref that is not a model name;
      * 409 when it is not installed (`/api/tags` does not list it);
      * 503 when Ollama cannot be read or will not give timings.

    The measurement is bounded: `jarvis_speed.measure` sends ONE fixed prompt
    and caps the answer at 64 tokens. It LOADS the model - that is what asking
    it anything does - and the answer says so.
    """
    try:
        wanted = safe_ref(ref)
    except ValueError as exc:
        return 400, {"ok": False, "error": str(exc)}
    # `installed()` answers [] for "Ollama is down" AND "you do not have it".
    # /api/ps can tell the two apart, so an empty list is asked one more
    # question before this module calls a model "not installed".
    installed = installed or _default_installed
    measure = measure or _default_measure
    ps = ps or _default_ps
    geometry = geometry or _default_geometry
    clock = clock or time.time
    try:
        names = list(installed() or [])
    except DiscoveryUnavailable as exc:
        return 503, {"ok": False, "error": str(exc)}
    except Exception as exc:
        return 503, {"ok": False,
                     "error": ("this PC's Ollama did not answer its installed "
                               f"list ({type(exc).__name__}); nothing was measured")}
    if not names:
        try:
            reachable = (ps() or {}).get("available")
        except Exception:
            reachable = None
        if reachable is False:
            return 503, {"ok": False, "ref": wanted,
                         "error": ("this PC's Ollama did not answer its model "
                                   "list, so whether the model is installed cannot "
                                   "be known and nothing was measured")}
    if not any(_same_ref(str(n), wanted) for n in names):
        return 409, {"ok": False, "ref": wanted,
                     "error": (f"{wanted} is not installed on this PC, so there "
                               "is nothing to measure. Installing it is the "
                               "existing /api/models/install card.")}
    try:
        result = measure(wanted) or {}
    except Exception as exc:
        return 503, {"ok": False, "ref": wanted,
                     "error": (f"the measurement stopped ({type(exc).__name__}); "
                               "nothing was stored")}
    if not isinstance(result, dict) or not result.get("ok"):
        note = (result or {}).get("note") if isinstance(result, dict) else ""
        return 503, {"ok": False, "ref": wanted,
                     "error": str(note or "the model did not give a timed answer, "
                                          "so there is nothing to store")}
    rate = _number(result.get("tokens_per_s"))
    if rate is None or rate <= 0:
        return 503, {"ok": False, "ref": wanted,
                     "error": "Ollama answered, but without a usable timing number"}
    try:
        ps_report = ps() or {}
    except Exception:
        ps_report = {}
    vram_gb = _loaded_vram_gb(wanted, ps_report)
    context = None
    try:
        geom = geometry(wanted) or {}
        context = _optional_int(geom.get("train_context"))
    except Exception:
        context = None
    at = int(clock())
    entry = {"tokens_per_s": round(rate, 2), "vram_gb": vram_gb,
             "context_tokens": context, "measured_at": at}
    doc = load_store(store_path_)
    doc["benchmarked"][wanted] = entry
    save_error = save_store(doc, store_path_)
    out = {"ok": True, "ref": wanted, **entry,
           "probes": _optional_int(result.get("probes")),
           "note": ("Measured on this PC with one fixed prompt (the model was "
                    "loaded to answer it). The raw row is in speed.jsonl; this "
                    "index keeps the video memory and context too.")}
    if save_error:
        out["ok"] = True
        out["stored"] = False
        out["note"] += " " + save_error + "."
    else:
        out["stored"] = True
    if vram_gb is None:
        out["note"] += (" Ollama did not report how much of the card it held, "
                        "so no video-memory figure is claimed.")
    if context is None:
        out["note"] += (" The model's own context length could not be read, so "
                        "no context figure is claimed.")
    return 200, out


# --------------------------------------------------------------------------
#   The preset table, measured only
# --------------------------------------------------------------------------

def preset_rows() -> list:
    """The rows of `backend/jarvis_presets.py`: `Preset` objects, unchanged.
    [] when the module is not on this backend."""
    presets = _presets_module()
    rows = getattr(presets, "PRESETS", ()) if presets else ()
    return list(rows) if rows else []


def _lane_card(lane: str, gpus: list) -> Optional[dict]:
    for gpu in gpus or []:
        if gpu.get("role") == lane:
            return gpu
    return None


def _bench_rows(benchmarked: Optional[dict]) -> dict:
    """Only rows with a usable measured rate survive. A row without one cannot
    justify anything."""
    out = {}
    for ref, value in (benchmarked or {}).items():
        row = _clean_benchmark(value)
        if row and isinstance(ref, str) and ref.strip():
            out[ref.strip()] = row
    return out


def _why_model(preset, current: dict, cand_ref: str, cand: dict,
               card: dict) -> str:
    return ("measured %.1f tokens/s here against %.1f for %s (saved %s), using "
            "%.1f GB of the %s's measured %.1f GB; its %s-token context covers "
            "the preset's %s"
            % (cand["tokens_per_s"], current["tokens_per_s"], preset.model,
               _date(current.get("measured_at")), cand["vram_gb"], card["name"],
               card["vram_gb"], f"{cand['context_tokens']:,}",
               f"{preset.context:,}"))


def _model_change(preset, current: dict, card: dict, bench: dict,
                  mode: str) -> Optional[dict]:
    """The one model change for one preset, or None.

    `mode` is the owner's opinion rule: "raise" wants any measured gain,
    "lower" wants a smaller measured footprint at no real speed cost,
    "quality" wants a bigger gain and the longest measured context, and the
    default wants GAIN_BAR.
    """
    pool = []
    for ref, row in bench.items():
        if _same_ref(ref, preset.model):
            continue
        if card is None or row.get("vram_gb") is None:
            continue
        if row["vram_gb"] > card["vram_gb"] * FIT_ROOM:
            continue
        # Both sides of the window question must be measured: the preset's own
        # context is what it asks for, and the candidate's must be READ from the
        # model (a benchmark row without one cannot show it would not shrink the
        # window the owner chose).
        if row.get("context_tokens") is None or row["context_tokens"] < preset.context:
            continue
        rate = row["tokens_per_s"]
        if mode == "lower":
            if row["vram_gb"] >= (current.get("vram_gb") or math.inf):
                continue
            if rate < current["tokens_per_s"] * LOWER_SPEED_FLOOR:
                continue
        elif mode == "raise":
            if rate <= current["tokens_per_s"]:
                continue
        elif mode == "quality":
            if rate < current["tokens_per_s"] * (1 + QUALITY_GAIN_BAR):
                continue
        else:
            if rate < current["tokens_per_s"] * (1 + GAIN_BAR):
                continue
        pool.append((ref, row))
    if not pool:
        return None
    if mode == "lower":
        best_ref, best = min(pool, key=lambda item: (item[1]["vram_gb"],
                                                     -item[1]["tokens_per_s"]))
    elif mode == "quality":
        best_ref, best = max(pool, key=lambda item: (item[1].get("context_tokens") or 0,
                                                     item[1]["tokens_per_s"]))
    else:
        best_ref, best = max(pool, key=lambda item: (item[1]["tokens_per_s"],
                                                     -item[1]["vram_gb"]))
    return {"row": "model", "from": preset.model, "to": best_ref,
            "why": _why_model(preset, current, best_ref, best, card)}


def _lane_change(preset, current: dict, home: Optional[dict], gpus: list) -> Optional[dict]:
    """Move the preset's model to another measured card when it demonstrably
    does not fit the card the preset names - and fits one this PC measured."""
    if home is None or current.get("vram_gb") is None:
        return None
    if current["vram_gb"] <= home["vram_gb"] * FIT_ROOM:
        return None
    others = [g for g in gpus or []
              if g.get("role") in ("main", "coding")
              and g.get("role") != preset.lane
              and g.get("vram_gb")
              and current["vram_gb"] <= g["vram_gb"] * FIT_ROOM]
    if not others:
        return None
    target = max(others, key=lambda g: g["vram_gb"])
    return {"row": "lane", "from": preset.lane, "to": target["role"],
            "why": ("its measured %.1f GB does not fit the %s's measured %.1f GB "
                    "with room, but fits the %s's measured %.1f GB"
                    % (current["vram_gb"], home["name"], home["vram_gb"],
                       target["name"], target["vram_gb"]))}


def _context_change(preset, current: dict) -> Optional[dict]:
    """A preset that asks for more tokens than the model on this PC says it has
    is a claim this PC's own measurement contradicts."""
    have = current.get("context_tokens")
    if have is None or have <= 0 or have >= preset.context:
        return None
    return {"row": "context", "from": preset.context, "to": have,
            "why": ("the model on this PC reports a maximum of %s tokens, less "
                    "than the %s this preset asks for"
                    % (f"{have:,}", f"{preset.context:,}"))}


def _evidence(opinion: Optional[dict]) -> str:
    text = ("measured on this PC only: token rates and video memory from the "
            "benchmark store (model-recommendations.json, raw rows in "
            "speed.jsonl), card sizes from nvidia-smi through "
            "jarvis_hardware.detect(); hardware record " + " and ".join(EVIDENCE_DOCS)
            + ". No estimate, popularity figure or external score justifies a "
              "preset change. Video memory is what Ollama reported WHILE the "
              "model was loaded for the benchmark, so a preset's larger "
              "conversation window can need more than that figure.")
    if opinion and opinion.get("rule") and opinion.get("rule") != "note":
        text += (" The owner's opinion was applied: the %s rule." % opinion["rule"])
    return text


def preset_recommendations(*, presets: Optional[list] = None,
                           gpus: Optional[list] = None,
                           benchmarked: Optional[dict] = None,
                           opinion: Optional[dict] = None) -> list:
    """The changes this PC's own measurements justify, and nothing else.

    Pure: no network, no store read, no clock. Called by the GET answer, by the
    check answer, by POST /api/presets/recommend and after an opinion - so all
    four always agree.

    A preset with no benchmark for its CURRENT model gets no model or lane
    change: there is nothing to compare against. Its context can still be
    corrected, because that compares the preset's claim with the model's own
    reported maximum, which is not a comparison between two models.
    """
    rows = presets if presets is not None else preset_rows()
    gpus = gpus if gpus is not None else []
    bench = _bench_rows(benchmarked)
    mode = str((opinion or {}).get("rule") or "note")
    out = []
    for preset in rows:
        if getattr(preset, "pending", False) or getattr(preset, "heavy_mode", False):
            # A pending preset has no model yet; heavy mode needs the both-card
            # lane that does not exist. Recommending either would be advice that
            # cannot be applied.
            continue
        current = bench.get(getattr(preset, "model", ""))
        if current is None:
            continue
        home = _lane_card(getattr(preset, "lane", ""), gpus)
        changes = []
        if mode != "keep":
            change = _model_change(preset, current, home, bench, mode)
            if change is None and mode == "note":
                change = _lane_change(preset, current, home, gpus)
            if change:
                changes.append(change)
        context_change = _context_change(preset, current)
        if context_change:
            changes.append(context_change)
        if changes:
            out.append({"preset": getattr(preset, "id", ""),
                        "changes": changes,
                        "evidence": _evidence(opinion)})
    return out


# --------------------------------------------------------------------------
#   The owner's opinion, applied deterministically
# --------------------------------------------------------------------------

#: The owner's words are matched, never guessed at by a model. Order is the
#: precedence, so "keep it, but faster" keeps. Each rule is a plain noun in the
#: answer so the owner can see what Jarvis thought they meant.
_OPINION_RULES = (
    ("keep", re.compile(
        r"\b(keep|leave (?:it|them|this)|no change|don'?t change|unchanged|"
        r"as (?:it )?is|stay)\b", re.I)),
    ("lower", re.compile(
        r"\b(lower|smaller|cheaper|less (?:vram|video memory|memory)|"
        r"lighter|lightweight)\b", re.I)),
    ("raise", re.compile(
        r"\b(raise|more|bigger|faster|speed|quicker|push|max(?:imum)?)\b", re.I)),
    ("quality", re.compile(
        r"\b(quality|better|smarter|best)\b", re.I)),
)


def classify_opinion(text: str) -> str:
    """Which rule the owner's note asks for: "keep", "lower", "raise",
    "quality", or "note" when nothing is recognised (recorded, ranking
    unchanged). Deterministic and pure - the same words always give the same
    rule, and no model is asked what the owner meant."""
    say = str(text or "").strip()
    for rule, pattern in _OPINION_RULES:
        if pattern.search(say):
            return rule
    return "note"


def record_opinion(text, *, store_path_: Optional[Path] = None,
                   gpus: Optional[list] = None,
                   presets: Optional[list] = None,
                   clock: Optional[Callable[[], float]] = None) -> tuple:
    """Record the owner's note and return the recommendations it produces.

    The note is kept in the local store (never sent anywhere) and the LAST one
    is re-applied on later reads, so the screen does not forget the opinion the
    owner just gave. A new note replaces the rule, not the history: the previous
    twenty are kept.
    """
    say = str(text or "").strip()
    if not say:
        return 400, {"ok": False, "error": "write what you think in \"text\" - "
                                           "for example \"keep these\" or "
                                           "\"prefer less video memory\""}
    say = say[:MAX_OPINION_CHARS]
    rule = classify_opinion(say)
    at = int((clock or time.time)())
    opinion = {"text": say, "rule": rule, "at": at}
    doc = load_store(store_path_)
    doc["opinions"] = (doc.get("opinions") or [])[-(MAX_OPINIONS - 1):] + [opinion]
    doc["last_opinion"] = opinion
    save_error = save_store(doc, store_path_)
    out = {"recommendations": preset_recommendations(
        presets=presets, gpus=gpus if gpus is not None else measured_gpus(),
        benchmarked=doc.get("benchmarked"), opinion=opinion),
        "opinion": opinion}
    if save_error:
        out["stored"] = False
        out["note"] = save_error + "; the answer below still used your note."
    else:
        out["stored"] = True
    return 200, out


# --------------------------------------------------------------------------
#   The three read answers
# --------------------------------------------------------------------------

def recommendations_view(*, path: Optional[Path] = None,
                         gpus: Optional[list] = None,
                         presets: Optional[list] = None) -> dict:
    """GET /api/models/recommendations: the cached check, the measured hardware,
    the measured benchmarks, and the changes they justify.

    READ-ONLY and NETWORK-FREE: it reads one JSON file and the PC's own card
    list. A cached check that does not exist yet is `checked_at: null` and no
    candidates, not an error.
    """
    doc = load_store(path)
    gpus = gpus if gpus is not None else measured_gpus()
    return {"checked_at": doc.get("checked_at"),
            "gpus": gpus,
            "candidates": doc.get("candidates") or [],
            "skipped_no_size": doc.get("skipped_no_size") or 0,
            "recommendations": preset_recommendations(
                presets=presets, gpus=gpus,
                benchmarked=doc.get("benchmarked"),
                opinion=doc.get("last_opinion")),
            "benchmarked": doc.get("benchmarked") or {}}


def check_models(*, path: Optional[Path] = None,
                 gpus: Optional[list] = None,
                 discover: Optional[Callable[[], list]] = None,
                 estimate: Optional[Callable] = None,
                 presets: Optional[list] = None,
                 clock: Optional[Callable[[], float]] = None) -> tuple:
    """POST /api/models/check: one look at the public catalogue, cached.

    NO DOWNLOAD. The only work is the existing catalogue pass (fixed public
    URLs, no key) and the JSON write. The candidates are the models the pass
    has a REAL size for - a row the listing gave no size for is left out and
    counted in `skipped_no_size`, because a fit judged from nothing is a
    guess. The fit is an ESTIMATE against the measured cards and says so. If
    the PC's cards were not measured, nothing is looked up at all - a
    candidate list for unknown hardware would be a guess dressed as an answer.
    """
    gpus = gpus if gpus is not None else measured_gpus()
    if not gpus:
        return 503, {"checked_at": None, "gpus": [], "candidates": [],
                     "skipped_no_size": 0,
                     "recommendations": [],
                     "benchmarked": (load_store(path).get("benchmarked") or {}),
                     "ok": False,
                     "error": ("this PC did not report a graphics card, so there "
                               "is no measured hardware to judge a model against; "
                               "nothing was looked up")}
    try:
        found = (discover or _default_discover)()
    except DiscoveryUnavailable as exc:
        return 503, {"checked_at": None, "gpus": gpus, "candidates": [],
                     "skipped_no_size": 0,
                     "recommendations": [],
                     "benchmarked": (load_store(path).get("benchmarked") or {}),
                     "ok": False, "error": str(exc)}
    except Exception as exc:
        return 503, {"checked_at": None, "gpus": gpus, "candidates": [],
                     "skipped_no_size": 0,
                     "recommendations": [],
                     "benchmarked": (load_store(path).get("benchmarked") or {}),
                     "ok": False,
                     "error": ("the public model catalogue could not be read "
                               f"({type(exc).__name__}); nothing was downloaded "
                               "and nothing was saved")}
    if not found:
        return 503, {"checked_at": None, "gpus": gpus, "candidates": [],
                     "skipped_no_size": 0,
                     "recommendations": [],
                     "benchmarked": (load_store(path).get("benchmarked") or {}),
                     "ok": False,
                     "error": ("the public catalogue pass returned no models at "
                               "all (the PC may be offline); nothing was saved, "
                               "and the last cached check is untouched")}
    skipped = {}
    candidates = build_candidates(found, gpus, estimate=estimate,
                                  skipped=skipped)
    no_size = int(skipped.get("no_size") or 0)
    at = int((clock or time.time)())
    doc = load_store(path)
    doc["checked_at"] = at
    doc["candidates"] = candidates
    doc["skipped_no_size"] = no_size
    save_error = save_store(doc, path)
    out = {"checked_at": at, "gpus": gpus, "candidates": candidates,
           "skipped_no_size": no_size,
           "recommendations": preset_recommendations(
               presets=presets, gpus=gpus, benchmarked=doc.get("benchmarked"),
               opinion=doc.get("last_opinion")),
           "benchmarked": doc.get("benchmarked") or {}}
    if save_error:
        out["ok"] = False
        out["error"] = save_error + "; the answer above was not cached"
    else:
        out["ok"] = True
    return 200, out


def presets_only(*, path: Optional[Path] = None,
                 gpus: Optional[list] = None,
                 presets: Optional[list] = None) -> tuple:
    """POST /api/presets/recommend: only the preset changes, from the cache."""
    rows = presets if presets is not None else preset_rows()
    if not rows:
        return 503, {"recommendations": [], "ok": False,
                     "error": ("the preset table is not on this backend, so "
                               "there are no rows to recommend against")}
    doc = load_store(path)
    gpus = gpus if gpus is not None else measured_gpus()
    if not gpus:
        return 503, {"recommendations": [], "ok": False,
                     "error": ("this PC did not report a graphics card, so no "
                               "preset change can be justified by measured hardware")}
    return 200, {"recommendations": preset_recommendations(
        presets=rows, gpus=gpus, benchmarked=doc.get("benchmarked"),
        opinion=doc.get("last_opinion")), "ok": True}


# --------------------------------------------------------------------------
#   Wiring: five routes, PC only, and nothing else touched
# --------------------------------------------------------------------------

def _peer_local(handler) -> tuple:
    """(the peer address, the address it arrived at), the pair
    `jarvis_owner_check.from_this_pc` rules on - the same extraction
    `jarvis_media_index` and `jarvis_brain_reads` use."""
    peer = (getattr(handler, "client_address", None) or ("",))[0]
    try:
        local = handler.connection.getsockname()[0]
    except Exception:
        local = None
    return peer, local


def install(handler_cls, *, origin_ok, token_ok, read_body,
            from_this_pc=None) -> str:
    """Wrap `handler_cls` with the five routes above, after the server's own
    origin and token checks. Every other request goes to the original handler
    untouched. Returns the banner line.

    PC ONLY, on every method: a phone bearer token must never reach a model
    catalogue (`CLAUDE.md`'s standing rule), so `from_this_pc` is checked before
    a body is read. It is injectable so a suite can drive both sides with no
    network; the shipped default is `jarvis_owner_check.from_this_pc` - the
    project's one rule, not a second one of this module's.

    NO CARD and no change: nothing here downloads, switches or applies. The one
    thing a call can do is write this module's own measurement/cache JSON.
    """
    get0 = getattr(handler_cls, "do_GET", None)
    post0 = getattr(handler_cls, "do_POST", None)
    if getattr(post0, "_jarvis_model_recommendations", False):
        return "  models     recommendations already on (five PC-only routes)"

    def _pc(handler) -> bool:
        check = from_this_pc
        if check is None:
            try:
                import jarvis_owner_check  # type: ignore
                check = jarvis_owner_check.from_this_pc
            except Exception:
                return False
        try:
            return bool(check(*_peer_local(handler)))
        except Exception:
            return False

    def _allowed(handler) -> bool:
        try:
            if not origin_ok(handler):
                handler._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(handler):
                handler._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            handler._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        if not _pc(handler):
            handler._send(403, {"ok": False, "error": DESKTOP_ONLY_REFUSAL})
            return False
        return True

    def do_GET(self):
        route = urllib.parse.urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in GET_PATHS:
            if get0 is None:
                return self._send(404, {"error": "that address is not a Jarvis route"})
            return get0(self)
        if not _allowed(self):
            return None
        try:
            return self._send(200, recommendations_view())
        except Exception as exc:
            return self._send(503, {"ok": False, "error": type(exc).__name__})

    def _body(self) -> dict:
        """The request body, or a 400 already sent. Returns a dict always; an
        invalid body is {} with `_bad` set so the caller can answer 400."""
        try:
            raw = read_body(self) or b"{}"
            body = json.loads(raw)
        except Exception:
            return {"_bad": "the body was not JSON"}
        return body if isinstance(body, dict) else {"_bad": "expected a JSON object"}

    def do_POST(self):
        route = urllib.parse.urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in POST_PATHS:
            if post0 is None:
                return self._send(404, {"error": "that address is not a Jarvis route"})
            return post0(self)
        if not _allowed(self):
            return None
        body = _body(self)
        if body.get("_bad"):
            return self._send(400, {"ok": False, "error": body["_bad"]})
        try:
            if route == PATH_CHECK:
                code, out = check_models()
            elif route == PATH_BENCHMARK:
                code, out = run_benchmark(body.get("ref"))
            elif route == PATH_OPINION:
                code, out = record_opinion(body.get("text"))
            else:
                code, out = presets_only()
        except Exception as exc:
            return self._send(503, {"ok": False, "error": type(exc).__name__})
        return self._send(code, out)

    do_GET._jarvis_model_recommendations = True
    do_POST._jarvis_model_recommendations = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return "  models     recommendations ready at /api/models/recommendations (PC only)"
