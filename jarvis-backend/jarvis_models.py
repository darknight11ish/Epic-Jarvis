"""jarvis_models.py - the model steward: find, judge, install, switch.

Four jobs, in the order they happen:

  DISCOVER   Fetch public catalogues of local models - Hugging Face's GGUF
             listing, Ollama's library, and the one benchmark that is both
             current and machine-readable (EvalPlus).
  JUDGE      Score each candidate against what YOU actually work on and
             what your GPUs can actually hold.
  INSTALL    Download an approved model, streaming progress.
  SWITCH     Make it the default - separately approved, with the previous
             model pinned so a bad switch is one tap back.

THE PRIVACY PROPERTY, WHICH IS THE WHOLE DESIGN
The obvious way to build this is to send "the user writes game engines and
poker apps, recommend a model" to some API. That would take the single
thing this project exists to protect and post it to a third party.

So discovery and personalisation are SEPARATE, and only discovery touches
the network. Every outbound request here is a fixed, public query - "list
trending GGUF text-generation models" - identical no matter who is asking.
The work profile is built from your memory store on this machine, and the
scoring happens here, against a catalogue already in hand. Nothing about
you is ever a search term. `outbound_requests()` returns every URL this
module will fetch so that claim is checkable, and the test suite asserts
no profile token appears in any of them.

WHAT THE RESEARCH ACTUALLY FOUND (so the code is not built on hope)
  - Ollama has NO public listing API. /v2/.../tags/list is a 404. The
    library page must be scraped, and it uses HTMX lazy pagination: without
    an `HX-Request: true` header every page after the first silently
    redirects back to page 1. That is the non-obvious part.
  - Ollama's registry manifests DO work, unauthenticated, and give exact
    download bytes per layer. That is where real sizes come from.
  - Hugging Face's API is fine anonymously (500 calls / 5 min / IP) and
    `?expand[]=gguf` returns parsed GGUF metadata - parameter count and
    context length - which is the closest thing to a machine-readable
    model spec that exists.
  - There is NO source anywhere that publishes "model X needs N GB of
    VRAM". It has to be computed, and a naive "file size + KV cache"
    under-predicts by about 1.5 GB of runtime overhead.
  - For task fit, coding is well served (EvalPlus, live JSON). Reasoning
    has only a leaderboard frozen in March 2025. Multilingual and general
    chat quality have no fetchable current source at all. The code says so
    rather than inventing a number.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

try:
    import jarvis_framework as fw
    _CFG_DIR = Path(fw.CONFIG_DIR)
except Exception:                                    # pragma: no cover
    fw = None
    _CFG_DIR = Path(os.path.expanduser("~/.openjarvis"))

CACHE = Path(os.environ.get("JARVIS_MODEL_CACHE", _CFG_DIR / "model-catalog.json"))
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
UA = "jarvis-model-steward/1.0 (personal, non-commercial)"
_LOCK = threading.RLock()


def _cfg(key: str, default):
    try:
        return fw.load_framework().get("models", {}).get(key, default)
    except Exception:
        return default


# --------------------------------------------------------------------------
#   Every URL this module will ever fetch. Fixed, public, impersonal.
# --------------------------------------------------------------------------

HF_TRENDING = ("https://huggingface.co/api/models"
               "?pipeline_tag=text-generation&filter=gguf"
               "&sort=trendingScore&direction=-1&limit={limit}")
HF_MODEL = "https://huggingface.co/api/models/{repo}?expand[]=gguf"
HF_TREE = "https://huggingface.co/api/models/{repo}/tree/main"
OLLAMA_SEARCH = "https://ollama.com/search?page={page}"
OLLAMA_MANIFEST = "https://registry.ollama.ai/v2/library/{model}/manifests/{tag}"
EVALPLUS = "https://raw.githubusercontent.com/evalplus/evalplus.github.io/main/results.json"


def outbound_requests(limit: int = 40) -> list[str]:
    """Every URL discovery can issue. Auditable by eye and by test: none of
    these carries a query term derived from the user."""
    return [HF_TRENDING.format(limit=limit),
            OLLAMA_SEARCH.format(page=1),
            EVALPLUS,
            HF_MODEL.format(repo="<public repo id from the listing above>"),
            HF_TREE.format(repo="<public repo id from the listing above>"),
            OLLAMA_MANIFEST.format(model="<public model name>", tag="<public tag>")]


def _get(url: str, timeout: float = 12.0, headers: Optional[dict] = None) -> Optional[str]:
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimited(f"{url} rate-limited") from e
        return None
    except Exception:
        return None


class RateLimited(RuntimeError):
    pass


# --------------------------------------------------------------------------
#   Catalogue entries
# --------------------------------------------------------------------------

@dataclass
class Model:
    ref: str                       # "qwen3:14b" or "unsloth/Qwen3-8B-GGUF"
    source: str                    # "ollama" | "huggingface"
    params: Optional[int] = None   # parameter count
    bytes_: Optional[int] = None   # download size of the weights
    context: Optional[int] = None
    quant: Optional[str] = None
    tags: list = field(default_factory=list)
    downloads: int = 0
    trending: float = 0.0
    bench: dict = field(default_factory=dict)   # {"humaneval+": 0.71, ...}
    fetched: float = field(default_factory=time.time)

    # filled in by judge()
    vram_mb: Optional[int] = None
    fits: Optional[bool] = None
    score: float = 0.0
    why: list = field(default_factory=list)

    def as_dict(self) -> dict:
        d = asdict(self); d["size_gb"] = round((self.bytes_ or 0) / 2**30, 2); return d

    @property
    def family(self) -> str:
        base = self.ref.split("/")[-1].split(":")[0]
        return re.sub(r"[-_.]?(gguf|instruct|chat|it)$", "", base, flags=re.I).lower()


# --------------------------------------------------------------------------
#   VRAM, computed - because nobody publishes it
# --------------------------------------------------------------------------

RUNTIME_OVERHEAD_MB = int(os.environ.get("JARVIS_RUNTIME_OVERHEAD_MB", "1500"))
# CUDA context + compute buffer; the term naive maths omits. The measured
# parts of it on a Windows/WDDM llama-server are the CUDA context (~330 MiB)
# and the compute buffer (~250-350 MiB at num_batch 512), so ~650 MiB - which
# makes 1500 conservative by roughly 850 MiB. That is not a mistake to
# "correct" blindly: this estimate is deliberately a FLOOR, and the cost of
# being wrong downward is a model that spills into system RAM and runs at a
# fifth of the speed. It is now overridable, and named, so the headroom is a
# decision rather than a constant nobody can see.


def _cache_bits_from_env() -> float:
    """What the KV cache ACTUALLY costs per element, right now, on this box.

    The old default was a bare `cache_bits: int = 8` - a q8_0 cache - while
    nothing in this tree sets OLLAMA_KV_CACHE_TYPE, so Ollama was running f16
    and every estimate was ~47% light on the KV term. Sizing a configuration
    the runtime is not running is worse than sizing none: it is wrong in a
    direction that says "this fits".

    And q8_0 is not 8 bits. llama.cpp stores 32 values in 34 bytes - a fp16
    scale per block - so it is 8.5 bits per element. Ollama's own pre-flight
    estimator rounds this to 8 and therefore under-counts a quantised cache by
    about 6%; on a ~7 GiB ceiling at 16K that is ~70 MiB of optimism this
    function does not need to inherit.

    Note the environment variable is read on every call rather than cached.
    It is set outside the process and the boot banner should report what is
    true when it prints, not what was true when the module first imported.
    """
    kind = os.environ.get("OLLAMA_KV_CACHE_TYPE", "").strip().lower()
    return {"q4_0": 4.5, "q8_0": 8.5, "f16": 16.0, "": 16.0}.get(kind, 16.0)


# server/sched.go generationBatchSurcharge: Ollama adds a FLAT allocation for
# large generation batches, and its auto-batch reaches for these sizes when it
# believes there is headroom.
#
#     case batch >= 2048: return 2 * GibiByte
#     case batch >= 1024: return 768 * MebiByte
#     default:            return 0
#
# Nothing here modelled it, so an estimate could say a model fits and Ollama
# could then add 768 MiB or 2 GiB on top and spill. Pin num_batch 512 (see
# backend/jarvis-primary.Modelfile) and this term is zero, which is the point
# of pinning it.
def batch_surcharge_mb(num_batch: int) -> int:
    if num_batch >= 2048:
        return 2048
    if num_batch >= 1024:
        return 768
    return 0


def kv_cache_mb(ctx: int, layers: int, embed_dim: int, heads: int, kv_heads: int,
                cache_bits: Optional[float] = None) -> float:
    """The standard formula. head_dim x n_kv_heads x 2 (K and V) x ctx x layers.

    The kv_heads/heads ratio is what makes grouped-query models cheap - an
    8B model with 8 KV heads against 32 attention heads pays a quarter of
    what the naive calculation suggests.
    """
    if not all((ctx, layers, embed_dim, heads, kv_heads)):
        return 0.0
    if cache_bits is None:
        cache_bits = _cache_bits_from_env()
    per_token = (embed_dim * kv_heads / heads) * 2 * (cache_bits / 8)
    return ctx * layers * per_token / 2**20


def estimate_vram_mb(m: "Model", ctx: Optional[int] = None,
                     geometry: Optional[dict] = None,
                     cache_bits: Optional[float] = None,
                     num_batch: int = 512) -> int:
    """Weights + KV cache + runtime overhead, in MB.

    Deliberately a FLOOR, not a promise. Model geometry (layers, heads) is
    only available from a local `ollama show` or by parsing GGUF headers, so
    for a model that is not installed yet the KV term is approximated from
    the parameter count. The caller is expected to keep a margin; see
    `fits_with_margin`.
    """
    weights_mb = (m.bytes_ or 0) / 2**20
    if not weights_mb and m.params:
        weights_mb = m.params * 0.6 / 2**20 * 1024      # ~Q4_K_M bytes/param
    if cache_bits is None:
        cache_bits = _cache_bits_from_env()
    # 16384, not 8192. The old ceiling meant a model you intend to deploy at
    # 16K was judged as if it were at 8K - so fits_with_margin waved through a
    # configuration that spills the moment it is actually used. A cap that
    # flatters the answer is worse than no cap.
    ctx = ctx or min(m.context or 16384, int(_cfg("assume_context", 16384)))
    if geometry:
        kv = kv_cache_mb(ctx, geometry.get("layers", 0), geometry.get("embed", 0),
                         geometry.get("heads", 1), geometry.get("kv_heads", 1), cache_bits)
    else:
        # Rough stand-in: ~0.13 MB per 1k tokens per billion params at q8
        # cache. Wrong in the third digit, right enough to rank by.
        b = (m.params or 0) / 1e9
        kv = 0.13 * (ctx / 1000.0) * max(b, 0.5) * (cache_bits / 8) * 8
    return int(weights_mb + kv + RUNTIME_OVERHEAD_MB + batch_surcharge_mb(num_batch))


def fits_with_margin(vram_mb: int, budget_mb: int, margin: float = 0.10) -> bool:
    """Anything within `margin` of the ceiling counts as not fitting. The
    estimate is a floor and the consequence of being wrong is a model that
    spills into system RAM and runs at a fifth of the speed."""
    return vram_mb <= budget_mb * (1 - margin)


# --------------------------------------------------------------------------
#   Discovery - fixed public queries only
# --------------------------------------------------------------------------

def fetch_huggingface(limit: int = 30, fetcher: Callable = _get) -> list[Model]:
    raw = fetcher(HF_TRENDING.format(limit=limit))
    if not raw:
        return []
    try:
        rows = json.loads(raw)
    except Exception:
        return []
    out = []
    for r in rows if isinstance(rows, list) else []:
        rid = r.get("id") or r.get("modelId")
        if not rid:
            continue
        out.append(Model(ref=rid, source="huggingface",
                         tags=[t for t in (r.get("tags") or []) if isinstance(t, str)],
                         downloads=int(r.get("downloads") or 0),
                         trending=float(r.get("trendingScore") or 0)))
    return out


def enrich_huggingface(m: Model, fetcher: Callable = _get) -> Model:
    """Parameter count and context from HF's parsed GGUF header; the size of
    the smallest sensible quant from the file tree."""
    raw = fetcher(HF_MODEL.format(repo=urllib.parse.quote(m.ref, safe="/")))
    if raw:
        try:
            g = (json.loads(raw) or {}).get("gguf") or {}
            if g.get("total"):
                m.params = int(g["total"])
            if g.get("context_length"):
                m.context = int(g["context_length"])
        except Exception:
            pass
    raw = fetcher(HF_TREE.format(repo=urllib.parse.quote(m.ref, safe="/")))
    if raw:
        try:
            files = json.loads(raw)
            best = None
            for f in files if isinstance(files, list) else []:
                name = (f.get("path") or "").lower()
                if not name.endswith(".gguf"):
                    continue
                # Prefer Q4_K_M: the quantisation everyone actually runs.
                rank = 0 if "q4_k_m" in name else (1 if "q4" in name else 2)
                if best is None or rank < best[0]:
                    best = (rank, f)
            if best:
                m.bytes_ = int(best[1].get("size") or 0)
                q = re.search(r"(iq?\d[_a-z0-9]*)", (best[1].get("path") or "").lower())
                m.quant = q.group(1).upper() if q else None
        except Exception:
            pass
    return m


# Two patterns, in order of how likely they are to survive a redesign. The
# /library/ path is part of the site's URL structure and changes rarely; the
# class-based match is the fallback for cards that link to a bare slug.
# Depending on Tailwind class names alone was the earlier version and it
# fails silently - a class rename returns zero models and discovery just
# goes quiet rather than erroring.
_OLLAMA_LINK = re.compile(r'href="/library/([A-Za-z0-9][A-Za-z0-9._-]*)"', re.I)
_OLLAMA_CARD = re.compile(
    r'<a[^>]+href="/([A-Za-z0-9][A-Za-z0-9._-]*)"[^>]*class="[^"]*\bgroup\b', re.I)


def fetch_ollama_library(pages: int = 2, fetcher: Callable = _get) -> list[Model]:
    """Scrape the library listing. There is no JSON API - /v2/.../tags/list
    is a 404 and the documented API only lists models already installed.

    The `HX-Request: true` header is load-bearing: the search page uses HTMX
    lazy pagination and without it every page after the first quietly
    redirects to page 1, so a scraper looks like it is working and returns
    the same twenty models over and over.
    """
    out, seen = [], set()
    for page in range(1, max(1, pages) + 1):
        html = fetcher(OLLAMA_SEARCH.format(page=page),
                       headers={"HX-Request": "true", "Accept": "text/html"})
        if not html:
            break
        slugs = _OLLAMA_LINK.findall(html) + _OLLAMA_CARD.findall(html)
        if not slugs:
            break
        for slug in slugs:
            slug = slug.strip("/")
            if slug.startswith("library/"):
                slug = slug.split("/", 1)[1]
            if not slug or "/" in slug or slug in seen:
                continue
            seen.add(slug)
            out.append(Model(ref=slug, source="ollama"))
    return out


def ollama_size(model: str, tag: str = "latest", fetcher: Callable = _get) -> Optional[int]:
    """Exact download bytes from the registry manifest - the one Ollama
    endpoint that is real JSON and needs no auth."""
    raw = fetcher(OLLAMA_MANIFEST.format(model=urllib.parse.quote(model), tag=urllib.parse.quote(tag)))
    if not raw:
        return None
    try:
        man = json.loads(raw)
        for layer in man.get("layers", []):
            if layer.get("mediaType", "").endswith("image.model"):
                return int(layer.get("size") or 0)
    except Exception:
        pass
    return None


def fetch_benchmarks(fetcher: Callable = _get) -> dict:
    """EvalPlus: the one leaderboard that is current, clean JSON and free.

    Coding only. The Open LLM Leaderboard froze in March 2025, LiveCodeBench
    has no JSON, and LMArena publishes only a 116 MB bulk dataset - so
    reasoning, multilingual and general chat quality have NO fetchable
    current source. Rather than invent numbers for those, the scorer says
    it has no evidence and leans on size and recency instead.
    """
    raw = fetcher(EVALPLUS)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    out = {}
    for name, row in (data or {}).items():
        if not isinstance(row, dict):
            continue
        p = row.get("pass@1") or {}
        if not isinstance(p, dict):
            continue
        out[_norm_name(name)] = {
            "humaneval+": float(p.get("humaneval+") or 0) / 100.0 if (p.get("humaneval+") or 0) > 1 else float(p.get("humaneval+") or 0),
            "mbpp+": float(p.get("mbpp+") or 0) / 100.0 if (p.get("mbpp+") or 0) > 1 else float(p.get("mbpp+") or 0),
            "size_b": row.get("size"),
        }
    return out


def _norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def discover(limit: int = 30, pages: int = 2, fetcher: Callable = _get,
             enrich: int = 8) -> list[Model]:
    """One public pass. Returns whatever came back; an unreachable source is
    simply absent, never an exception."""
    models = fetch_huggingface(limit, fetcher) + fetch_ollama_library(pages, fetcher)
    bench = fetch_benchmarks(fetcher)
    for m in models[:enrich]:
        if m.source == "huggingface":
            enrich_huggingface(m, fetcher)
        else:
            m.bytes_ = m.bytes_ or ollama_size(m.ref.split(":")[0],
                                               m.ref.split(":")[1] if ":" in m.ref else "latest",
                                               fetcher)
    if bench:
        for m in models:
            key = _norm_name(m.family)
            for bname, row in bench.items():
                if key and (key in bname or bname in key):
                    m.bench = {k: v for k, v in row.items() if k != "size_b"}
                    break
    return models


# --------------------------------------------------------------------------
#   The work profile - built HERE, from YOUR machine, never sent anywhere
# --------------------------------------------------------------------------

TASK_SIGNALS = {
    "coding":       r"\b(code|coding|python|javascript|typescript|rust|engine|refactor|debug|"
                    r"api|function|repo|git|compile|unity|webgl|canvas|shader|sql)\b",
    "reasoning":    r"\b(analy[sz]e|audit|plan|architecture|design|strategy|prove|reason|"
                    r"trade[- ]?off|compare|decide|review)\b",
    "writing":      r"\b(write|draft|essay|book|chapter|blog|article|prose|edit|story|novel)\b",
    "vision":       r"\b(screenshot|image|diagram|screen|visual|ocr|photo|ui mock)\b",
    "multilingual": r"\b(translate|translation|spanish|french|german|japanese|chinese|language)\b",
    "long_context": r"\b(whole (?:file|repo|book)|entire|long document|transcript|codebase)\b",
}


@dataclass
class Profile:
    counts: dict = field(default_factory=dict)
    total: int = 0
    top: list = field(default_factory=list)
    sources: list = field(default_factory=list)

    def weight(self, task: str) -> float:
        if not self.total:
            return 0.0
        return self.counts.get(task, 0) / self.total

    def as_dict(self) -> dict:
        return asdict(self)


def build_profile(texts: Optional[Iterable[str]] = None,
                  latch: bool = True) -> Profile:
    """What you actually work on, counted from local sources only.

    Reads the memory store and the Logseq graph. Never the Joplin vault -
    that is the personal-life store and it is excluded from every automatic
    read in this project by design. Never leaves this function.

    Reading stored memory pins the turn to the local model, the same way a
    Joplin read does. The counts are aggregate, not content - but "coding:
    412, writing: 88" is still derived from what you have stored, and the
    rule is that stored memory does not reach a cloud lane. Callers that do
    not pass the profile onward (cards(), which emits refs and reasons only)
    pass latch=False, and a caller that supplies its own `texts` never
    latches because it read nothing.
    """
    p = Profile()
    blob: list[str] = []
    if texts is not None:
        blob = [str(t) for t in texts]
        p.sources.append("supplied")
    else:
        # A source counts as READ only if it actually yielded text. An empty
        # Logseq graph is not a source, and recording it as one would latch
        # the conversation local over a read that returned nothing.
        try:
            import jarvis_memory as M
            got = [f["text"] for f in M.store().current_facts(limit=1000)]
            if got:
                blob += got
                p.sources.append("memory")
        except Exception:
            pass
        try:
            from tools import logseq_tool as L
            root = L.graph_dir()
            got = []
            for f in list((root / "pages").glob("*.md"))[:200]:
                got.append(f.read_text(encoding="utf-8", errors="replace")[:4000])
            for f in L.recent_journals(30)[:30]:
                got.append(f.read_text(encoding="utf-8", errors="replace")[:4000])
            got = [t for t in got if t.strip()]
            if got:
                blob += got
                p.sources.append("logseq")
        except Exception:
            pass
    if latch and blob and p.sources and p.sources != ["supplied"]:
        try:
            import jarvis_gate
            jarvis_gate.latch_taint(why="model_profile_reads_memory")
        except Exception:
            pass
    joined = "\n".join(blob).lower()
    for task, pat in TASK_SIGNALS.items():
        n = len(re.findall(pat, joined, re.I))
        if n:
            p.counts[task] = n
    p.total = sum(p.counts.values())
    p.top = [t for t, _ in sorted(p.counts.items(), key=lambda kv: -kv[1])][:3]
    return p


# --------------------------------------------------------------------------
#   Judging - local, against the profile and the real VRAM budget
# --------------------------------------------------------------------------

def _budget_mb() -> int:
    try:
        import jarvis_compute as C
        pl = C.plan()
        if pl.total_mb:
            return pl.total_mb
    except Exception:
        pass
    return int(os.environ.get("JARVIS_VRAM_MB", "8192"))


def judge(models: list[Model], profile: Optional[Profile] = None,
          budget_mb: Optional[int] = None) -> list[Model]:
    """Score every candidate. Everything here is arithmetic on data already
    in memory - no network, no model, nothing leaves."""
    profile = profile or build_profile()
    budget = budget_mb or _budget_mb()
    for m in models:
        m.vram_mb = estimate_vram_mb(m)
        m.fits = fits_with_margin(m.vram_mb, budget)
        m.why = []
        s = 0.0
        if not m.fits:
            m.score = 0.0
            m.why.append(f"needs about {m.vram_mb/1024:.1f} GB, you have {budget/1024:.1f} GB "
                         f"- it would spill into system RAM and crawl")
            continue
        # Headroom is worth something: a model that leaves room for vision
        # and voice avoids a swap on every request.
        head = 1 - (m.vram_mb / budget)
        s += head * 1.5
        if head > 0.35:
            m.why.append("leaves room for vision and voice to stay loaded")
        # Coding is the one task with real, current evidence.
        if m.bench.get("humaneval+"):
            code = (m.bench["humaneval+"] + m.bench.get("mbpp+", 0)) / 2
            s += code * 3.0 * max(profile.weight("coding"), 0.15)
            m.why.append(f"scores {m.bench['humaneval+']*100:.0f}% on HumanEval+ "
                         f"(measured, not claimed)")
        elif "coding" in profile.top:
            # No benchmark: say so rather than guessing.
            if re.search(r"cod(er|ing)|dev", m.ref, re.I):
                s += 0.6 * profile.weight("coding")
                m.why.append("named as a coding model, but has no EvalPlus score - unverified")
        for task in ("vision", "multilingual", "long_context", "reasoning", "writing"):
            w = profile.weight(task)
            if w < 0.08:
                continue
            if task == "vision" and re.search(r"\bvl\b|vision|llava|moondream", m.ref, re.I):
                s += w * 2.0; m.why.append("handles images, which your work involves")
            if task == "long_context" and (m.context or 0) >= 100_000:
                s += w * 1.5; m.why.append(f"{(m.context or 0)//1000}k context window")
            if task == "reasoning" and (m.params or 0) >= 12e9:
                s += w * 1.0; m.why.append("large enough to reason through multi-step problems")
        # Popularity as a weak tiebreak only - it is evidence that a model
        # works, not evidence that it suits you.
        s += min(math.log10(max(m.downloads, 1)) / 20, 0.3)
        s += min(m.trending / 500, 0.2)
        m.score = round(s, 4)
    return sorted(models, key=lambda x: -x.score)


def recommend(models: Optional[list[Model]] = None, k: int = 3,
              profile: Optional[Profile] = None, fetcher: Callable = _get) -> dict:
    p = profile or build_profile()
    ms = models if models is not None else discover(fetcher=fetcher)
    ranked = judge(ms, p)
    picks = [m for m in ranked if m.fits][:k]
    return {"profile": p.as_dict(), "budget_mb": _budget_mb(),
            "picks": [m.as_dict() for m in picks],
            "rejected_for_size": sum(1 for m in ranked if not m.fits),
            "evidence_note": ("Coding scores are measured (EvalPlus). Reasoning, "
                              "multilingual and chat quality have no current public "
                              "benchmark that can be fetched, so those are judged on "
                              "size and context only - treat them as weaker evidence.")}


# --------------------------------------------------------------------------
#   Task-fit suggestions, with a cost/benefit bar
# --------------------------------------------------------------------------

@dataclass
class Suggestion:
    task: str
    current: str
    candidate: str
    benefit: float                 # 0..1, measured where possible
    cost_gb: float
    cost_notes: list = field(default_factory=list)
    worth_it: bool = False
    reason: str = ""

    def as_dict(self): return asdict(self)


def suggest_for_task(task: str, current_ref: str, models: list[Model],
                     profile: Optional[Profile] = None,
                     budget_mb: Optional[int] = None) -> Optional[Suggestion]:
    """Is a different model worth the trouble for THIS kind of work?

    The bar exists because the answer is usually no. Switching costs a
    download, disk, and - if the new model is bigger than the one resident -
    a swap on every request, which is 5-15 seconds of silence each time.
    A suggestion only surfaces when the measured gain clears that.
    """
    budget = budget_mb or _budget_mb()
    ranked = judge([m for m in models], profile, budget)
    cur = next((m for m in ranked if m.family == Model(ref=current_ref, source="x").family), None)
    cur_score = 0.0
    if task == "coding":
        cur_score = (cur.bench.get("humaneval+", 0) if cur else 0)
    best = None
    for m in ranked:
        if not m.fits or m.family == (cur.family if cur else None):
            continue
        gain = (m.bench.get("humaneval+", 0) - cur_score) if task == "coding" else 0.0
        if gain <= 0:
            continue
        if best is None or gain > best[0]:
            best = (gain, m)
    if not best:
        return None
    gain, m = best
    cost_gb = round((m.bytes_ or 0) / 2**30, 2)
    notes = []
    min_gain = float(_cfg("min_benefit", 0.05))
    max_gb = float(_cfg("max_download_gb", 12))
    worth = gain >= min_gain and cost_gb <= max_gb
    if gain < min_gain:
        notes.append(f"only {gain*100:.0f} points better - under the {min_gain*100:.0f}-point bar")
    if cost_gb > max_gb:
        notes.append(f"{cost_gb} GB download is over the {max_gb} GB limit you set")
    if m.vram_mb and cur and cur.vram_mb and m.vram_mb > cur.vram_mb:
        notes.append(f"bigger than what you run now, so it may swap in and out "
                     f"(about {(m.vram_mb - cur.vram_mb)/1024:.1f} GB more)")
    return Suggestion(task=task, current=current_ref, candidate=m.ref,
                      benefit=round(gain, 4), cost_gb=cost_gb, cost_notes=notes,
                      worth_it=worth,
                      reason=(f"{m.ref} scores {gain*100:.0f} points higher on HumanEval+ "
                              f"than {current_ref} for {cost_gb} GB"
                              if worth else "; ".join(notes) or "not worth the swap"))


# --------------------------------------------------------------------------
#   Which model is current - a file, not the framework TOML
# --------------------------------------------------------------------------
#
# The obvious place to record "the local lane now runs qwen3:14b" is
# jarvis-framework.toml. It is also the one place this module must never
# write: the TOML is in the gate's _PROTECTED list precisely so that no
# approved action can edit the policy that approves actions. Reaching around
# that to write "just the model line" would be the same hole with a nicer
# name.
#
# So the TOML keeps the declared default and this file records the override.
# The router reads current_model() first and falls back to the TOML. A
# corrupt or missing state file therefore degrades to the hand-written
# configuration rather than to nothing.

STATE = Path(os.environ.get("JARVIS_MODEL_STATE", _CFG_DIR / "model-state.json"))

MAX_HISTORY = 20


def _read_state() -> dict:
    try:
        with _LOCK:
            return json.loads(STATE.read_text("utf-8"))
    except Exception:
        return {}


def _write_state(st: dict) -> bool:
    """Temp file plus os.replace. A half-written state file would leave the
    router with no model at all, which is worse than a stale one."""
    try:
        with _LOCK:
            STATE.parent.mkdir(parents=True, exist_ok=True)
            tmp = STATE.with_suffix(".tmp")
            tmp.write_text(json.dumps(st, indent=2), "utf-8")
            os.replace(tmp, STATE)
        return True
    except Exception:
        return False


def current_model() -> Optional[str]:
    """The model the local lane should use, or None to mean 'whatever the
    framework file says'."""
    return _read_state().get("current") or None


def previous_model() -> Optional[str]:
    """The model pinned for one-tap revert."""
    return _read_state().get("previous") or None


# --------------------------------------------------------------------------
#   Reference safety
# --------------------------------------------------------------------------
#
# A model reference can arrive from a catalogue fetch, from the HUD, or -
# the case that matters - from text a model wrote after reading a web page.
# `ollama pull` interprets a leading host component as a registry, so an
# unchecked reference is an arbitrary-registry pull: "evil.example.com/x"
# fetches whatever that host serves and runs it as your assistant.
#
# Two hosts are allowed, both because they are the ones discovery actually
# returns. Everything else is refused rather than sanitised, on the same
# principle as sanitize_title() in the Logseq tool: a reference that needs
# repairing is a reference nobody should be pulling.

_ALLOWED_HOSTS = ("hf.co/", "huggingface.co/")
_REF_BODY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)?"
                       r"(?::[A-Za-z0-9][A-Za-z0-9._-]*)?$")


def safe_ref(ref: Any) -> str:
    """Return `ref` unchanged if it is a model reference we will pull, else
    raise ValueError. Never repairs."""
    if not isinstance(ref, str):
        raise ValueError("model reference must be a string")
    r = ref.strip()
    if not r or len(r) > 200:
        raise ValueError("model reference is empty or absurdly long")
    if any(c.isspace() for c in r) or "\\" in r or ".." in r:
        raise ValueError(f"refusing malformed model reference {ref!r}")
    if "://" in r:
        raise ValueError(f"refusing a URL as a model reference: {ref!r}")
    body, host = r, ""
    for h in _ALLOWED_HOSTS:
        if r.lower().startswith(h):
            host, body = r[:len(h)], r[len(h):]
            break
    if not _REF_BODY.match(body):
        raise ValueError(f"refusing malformed model reference {ref!r}")
    if not host and "/" in body and "." in body.split("/")[0]:
        # A dotted component BEFORE a slash is how Ollama spells "use this
        # registry". A dot with no slash is just a version - llama3.3:70b is
        # an ordinary library model and must not be refused.
        raise ValueError(
            f"refusing {ref!r}: only the Ollama library and hf.co are allowed "
            f"as sources")
    return r


# --------------------------------------------------------------------------
#   Talking to the local Ollama
# --------------------------------------------------------------------------

def _post(path: str, payload: dict, timeout: float = 15.0) -> Optional[dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA}{path}", data=data, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


def installed(timeout: float = 6.0) -> list[str]:
    """Model references present on this machine right now."""
    raw = _get(f"{OLLAMA}/api/tags", timeout=timeout)
    if not raw:
        return []
    try:
        return [m.get("name", "") for m in json.loads(raw).get("models", [])
                if m.get("name")]
    except Exception:
        return []


def is_installed(ref: str, names: Optional[list] = None) -> bool:
    """Match with and without the implicit :latest tag, because /api/tags
    reports "qwen3:14b" while a human types "qwen3" and means the same
    thing."""
    names = installed() if names is None else names
    want = ref if ":" in ref else f"{ref}:latest"
    return any(n == ref or n == want or n.split(":")[0] == ref for n in names)


def offload_status(timeout: float = 4.0) -> dict:
    """Is the model actually on the graphics card, or only pretending to be?

    THE FAILURE THIS CATCHES. llama.cpp fits as many layers as it thinks will
    fit and silently runs the rest on the CPU. Ollama reports the model as
    loaded and healthy either way; nothing warns, nothing errors, and the only
    symptom is that answers take fifteen seconds instead of two. On a 6.9 GB
    budget that is the difference between "Jarvis is slow today" and "Jarvis
    has not touched the GPU since you installed that other model".

    /api/ps gives `size` (total resident) and `size_vram` (the part on the
    card) per loaded model, so the split is a subtraction rather than a guess.
    Jan built the same check by counting devices, which catches only the
    all-CPU case; this catches partial spill too, which is the commoner one.

    Never raises and never blocks for long: a four-second budget, and every
    failure reports "unknown" rather than inventing a number. A diagnostic
    that takes the status page down with it is worse than no diagnostic.
    """
    out = {"available": False, "status": "unknown", "models": [], "note": ""}
    raw = _get(f"{OLLAMA}/api/ps", timeout=timeout)
    if not raw:
        out["note"] = ("Ollama did not answer, so there is nothing to report. "
                       "This is normal when nothing has been asked yet.")
        return out
    try:
        running = json.loads(raw).get("models") or []
    except Exception:
        out["note"] = "Ollama answered with something that was not JSON."
        return out

    out["available"] = True
    if not running:
        out["status"] = "idle"
        out["note"] = ("No model is loaded right now. Ollama unloads after a "
                       "few minutes idle; ask Jarvis something and look again.")
        return out

    worst = 100
    for m in running:
        total = int(m.get("size") or 0)
        vram = int(m.get("size_vram") or 0)
        # A zero total would be a divide-by-zero, and it happens while a model
        # is still being loaded.
        pct = 100 if total <= 0 else max(0, min(100, round(vram * 100 / total)))
        worst = min(worst, pct)
        out["models"].append({
            "name": m.get("name") or m.get("model") or "(unnamed)",
            "size_mb": round(total / (1024 * 1024)),
            "vram_mb": round(vram / (1024 * 1024)),
            "on_gpu_percent": pct,
        })

    out["on_gpu_percent"] = worst
    if worst >= 99:
        out["status"] = "gpu"
        out["note"] = "The model is on the graphics card. This is what you want."
    elif worst <= 1:
        out["status"] = "cpu"
        out["note"] = (
            "The model is running on the CPU, not the graphics card. Answers "
            "will be several times slower and nothing else will tell you. "
            "Usually this means the model is too big for the card, another "
            "program is holding video memory, or the graphics driver needs "
            "restarting.")
    else:
        out["status"] = "partial"
        out["note"] = (
            f"Only {worst}% of the model is on the graphics card; the rest is "
            "on the CPU, which is what makes it slow. A smaller model, or a "
            "shorter context, would fit.")

    # Said only when it adds something. The budget is what the owner told us
    # the card has, not what was probed - so this compares a claim against a
    # measurement rather than pretending to know the hardware.
    if out["status"] in ("cpu", "partial"):
        try:
            budget = _budget_mb()
            biggest = max((x["size_mb"] for x in out["models"]), default=0)
            if biggest and budget:
                out["note"] += (f" The model needs about {biggest} MB and the "
                                f"configured budget is {budget} MB.")
        except Exception:
            pass
    return out


def local_geometry(ref: str, timeout: float = 15.0) -> Optional[dict]:
    """Exact layer/head counts for an INSTALLED model, so estimate_vram_mb
    can use the real KV formula instead of the parameter-count stand-in.

    /api/show returns model_info keyed by architecture - "qwen3.block_count",
    "llama.attention.head_count_kv" and so on - so the architecture prefix
    has to be discovered from the keys rather than assumed.
    """
    info = _post("/api/show", {"model": safe_ref(ref)}, timeout=timeout)
    if not isinstance(info, dict):
        return None
    mi = info.get("model_info") or {}
    arch = mi.get("general.architecture")
    if not arch:
        for k in mi:
            if k.endswith(".block_count"):
                arch = k.rsplit(".", 1)[0]
                break
    if not arch:
        return None

    def g(suffix, default=0):
        return mi.get(f"{arch}.{suffix}", default) or default

    heads = int(g("attention.head_count", 1)) or 1
    geom = {"arch": arch,
            "layers": int(g("block_count")),
            "embed": int(g("embedding_length")),
            "heads": heads,
            "kv_heads": int(g("attention.head_count_kv", heads)) or heads,
            "train_context": int(g("context_length"))}
    return geom if geom["layers"] else None


# --------------------------------------------------------------------------
#   Install - approved once, then streamed
# --------------------------------------------------------------------------

_CANCEL = threading.Event()


def cancel_install() -> None:
    """Ask an in-flight pull to stop at the next progress frame. Ollama
    keeps whatever blobs it already has, so resuming later is cheap."""
    _CANCEL.set()


def _gate(action: str, detail: dict, prompt: str):
    """Ask the gate. If the gate cannot be imported at all, refuse - an
    approval system you can bypass by breaking its import is not one."""
    try:
        import jarvis_gate
    except Exception as exc:                              # pragma: no cover
        class _No:
            allowed, tier, reason = False, "unknown", f"gate unavailable ({exc})"
        return _No()
    return jarvis_gate.check(action, detail=detail, prompt=prompt)


def preflight(ref: str, models: Optional[list] = None,
              budget_mb: Optional[int] = None) -> dict:
    """Everything the human should see BEFORE being asked to approve a
    download: real size, estimated VRAM, whether it fits, what it displaces."""
    ref = safe_ref(ref)
    budget = budget_mb or _budget_mb()
    m = None
    for cand in (models or []):
        if cand.ref == ref:
            m = cand
            break
    if m is None:
        m = Model(ref=ref, source="ollama")
        if "/" not in ref:
            name, _, tag = ref.partition(":")
            m.bytes_ = ollama_size(name, tag or "latest")
    geom = local_geometry(ref) if is_installed(ref) else None
    vram = estimate_vram_mb(m, geometry=geom)
    return {"ref": ref,
            "size_gb": round((m.bytes_ or 0) / 2**30, 2),
            "vram_mb": vram,
            "budget_mb": budget,
            "fits": fits_with_margin(vram, budget),
            "already_installed": is_installed(ref),
            "geometry": geom,
            "current": current_model()}


def _pull_lines(ref: str, timeout: float = 3600.0):
    """Yield the NDJSON progress frames from /api/pull, one dict per line.

    Split out from install() so the frame handling can be tested against the
    shapes Ollama really sends without a network or a 5 GB download.
    """
    body = json.dumps({"model": ref, "stream": True}).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA}/api/pull", data=body, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def install(ref: str, on_progress: Optional[Callable[[dict], None]] = None,
            models: Optional[list] = None, allow_oversize: bool = False,
            timeout: float = 3600.0) -> dict:
    """Download a model. Gated as `download_model` - tier "ask".

    Progress frames from /api/pull carry `total` and `completed`, except that
    early frames omit `completed` entirely and later ones repeat a digest
    that is already finished. A missing `completed` means zero, not "same as
    last time"; treating it as the latter makes the bar jump backwards.
    """
    try:
        ref = safe_ref(ref)
    except ValueError as exc:
        return {"ok": False, "ref": str(ref), "reason": str(exc)}

    pre = preflight(ref, models)
    if pre["already_installed"]:
        return {"ok": True, "ref": ref, "already_installed": True,
                "reason": "already on this machine"}

    if not pre["fits"] and not allow_oversize:
        # Refused before the gate on purpose. Spending a human's attention on
        # approving a download that cannot run afterwards is worse than
        # saying no here, and the override is one named argument away.
        return {"ok": False, "ref": ref, "preflight": pre,
                "override": "allow_oversize",
                "reason": (f"needs about {pre['vram_mb']/1024:.1f} GB of VRAM "
                           f"against a {pre['budget_mb']/1024:.1f} GB budget, so it "
                           f"would spill into system RAM and run several times "
                           f"slower")}

    v = _gate("download_model",
              {"ref": ref, "size_gb": pre["size_gb"], "vram_mb": pre["vram_mb"],
               "budget_mb": pre["budget_mb"], "fits": pre["fits"],
               "oversize_override": bool(allow_oversize and not pre["fits"])},
              prompt=(f"Download {ref} ({pre['size_gb']} GB, needs about "
                      f"{pre['vram_mb']/1024:.1f} GB VRAM)?"))
    if not getattr(v, "allowed", False):
        return {"ok": False, "ref": ref, "reason": getattr(v, "reason", "refused"),
                "tier": getattr(v, "tier", "unknown"), "preflight": pre}

    _CANCEL.clear()
    seen: dict[str, int] = {}
    totals: dict[str, int] = {}
    last_status = ""
    try:
        for msg in _pull_lines(ref, timeout):
            if _CANCEL.is_set():
                return {"ok": False, "ref": ref, "cancelled": True,
                        "reason": "cancelled; partial layers are kept, so "
                                  "resuming later downloads only the rest"}
            if msg.get("error"):
                return {"ok": False, "ref": ref, "reason": str(msg["error"])}
            last_status = msg.get("status", last_status)
            digest = msg.get("digest")
            if digest:
                totals[digest] = int(msg.get("total") or totals.get(digest, 0))
                # A frame that omits `completed` means zero, not "unchanged".
                # Ollama sends the bare {status, digest, total} frame first;
                # carrying the previous value forward instead makes the bar
                # jump backwards when a new layer starts.
                seen[digest] = int(msg.get("completed") or 0)
            done, whole = sum(seen.values()), sum(totals.values())
            if on_progress:
                try:
                    on_progress({"ref": ref, "status": last_status,
                                 "completed": done, "total": whole,
                                 "pct": round(100.0 * done / whole, 1) if whole else 0.0})
                except Exception:
                    # A HUD that went away must not abort a 20 GB download.
                    pass
    except Exception as exc:
        return {"ok": False, "ref": ref, "reason": f"pull failed: {exc}"}

    ok = is_installed(ref)
    st = _read_state()
    hist = [h for h in st.get("installs", []) if h.get("ref") != ref]
    hist.append({"ref": ref, "at": time.time(), "size_gb": pre["size_gb"], "ok": ok})
    st["installs"] = hist[-MAX_HISTORY:]
    _write_state(st)
    return {"ok": ok, "ref": ref, "size_gb": pre["size_gb"],
            "status": last_status,
            "reason": "downloaded" if ok else
                      "the pull finished but the model is not listed locally"}


# --------------------------------------------------------------------------
#   Switch, and the way back
# --------------------------------------------------------------------------

def switch_to(ref: str, why: str = "") -> dict:
    """Make `ref` the local lane's model. Gated as `switch_model`.

    Separate from download on purpose. Approving a download is agreeing to
    spend bandwidth and disk; approving a switch is agreeing to change which
    model reads your email. Bundling them would let the second decision ride
    in on the first.
    """
    try:
        ref = safe_ref(ref)
    except ValueError as exc:
        return {"ok": False, "ref": str(ref), "reason": str(exc)}

    if not is_installed(ref):
        return {"ok": False, "ref": ref,
                "reason": "not installed on this machine; download it first"}

    st = _read_state()
    cur = st.get("current")
    if cur == ref:
        return {"ok": True, "ref": ref, "unchanged": True,
                "reason": "already the current model"}

    v = _gate("switch_model",
              {"from": cur, "to": ref, "why": why},
              prompt=f"Switch the local model from {cur or 'the configured default'} "
                     f"to {ref}?")
    if not getattr(v, "allowed", False):
        return {"ok": False, "ref": ref, "reason": getattr(v, "reason", "refused"),
                "tier": getattr(v, "tier", "unknown")}

    # Record how the OUTGOING model answers the probes, before it stops being
    # the one in use. After the swap there is nothing left to compare against:
    # you cannot ask the model you just replaced how it would have answered.
    try:
        import jarvis_tripwire
        jarvis_tripwire.baseline(_probe_asker(cur), cur or "previous")
    except Exception:
        pass

    st["previous"] = cur
    st["current"] = ref
    st["switched_at"] = time.time()
    st["why"] = why[:300]
    log = st.get("switches", [])
    log.append({"from": cur, "to": ref, "at": st["switched_at"]})
    st["switches"] = log[-MAX_HISTORY:]
    if not _write_state(st):
        return {"ok": False, "ref": ref,
                "reason": "could not write the model state file; nothing changed"}
    out = {"ok": True, "ref": ref, "previous": cur,
           "revert_with": "jarvis_models.rollback()",
           "reason": f"local lane now uses {ref}"}
    # A smoke test, not an evaluation. It catches a model that is broken -
    # answering in another language, looping, unable to emit JSON - which is
    # what a bad swap actually looks like. It cannot tell you the new one is
    # better and does not claim to.
    try:
        import jarvis_tripwire
        out["tripwire"] = jarvis_tripwire.after_swap(_probe_asker(ref), ref)
    except Exception as exc:
        out["tripwire"] = {"available": False, "reason": str(exc)}
    return out


def _probe_asker(ref: Optional[str]):
    """A one-shot caller for the tripwire, pinned to one model.

    Short timeout and a low temperature on purpose: these probes are about
    whether the model works at all, and a model that needs ninety seconds to
    say "Paris" has already told you something.
    """
    def ask(prompt: str) -> str:
        body = {"model": ref or os.environ.get("JARVIS_LOCAL_MODEL", "qwen3:8b"),
                "prompt": prompt, "stream": False,
                "options": {"temperature": 0.0, "num_predict": 200}}
        req = urllib.request.Request(
            f"{OLLAMA}/api/generate", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode()).get("response", "")
    return ask


def rollback() -> dict:
    """Go back to the model pinned by the last switch. Gated as
    `rollback_model` - tier "auto", because undoing a change you approved is
    not a new decision, and a revert that needs permission is a revert that
    happens too late."""
    st = _read_state()
    prev, cur = st.get("previous"), st.get("current")
    if not prev:
        return {"ok": False, "reason": "nothing pinned to go back to"}
    if not is_installed(prev):
        return {"ok": False, "reason": f"{prev} is no longer installed"}

    v = _gate("rollback_model", {"from": cur, "to": prev},
              prompt=f"Revert the local model to {prev}?")
    if not getattr(v, "allowed", False):
        return {"ok": False, "reason": getattr(v, "reason", "refused")}

    st["current"], st["previous"] = prev, cur
    st["switched_at"] = time.time()
    st["why"] = "rollback"
    _write_state(st)
    return {"ok": True, "ref": prev, "previous": cur,
            "reason": f"back on {prev}"}


# --------------------------------------------------------------------------
#   Cards - the recommendation in words a person can act on
# --------------------------------------------------------------------------

def _gb(mb: Optional[float]) -> str:
    return f"{(mb or 0)/1024:.1f} GB"


def explain(m: Model, profile: Optional[Profile] = None,
            names: Optional[list] = None) -> dict:
    """One HUD card. The point of the prose is that a recommendation you
    cannot argue with is a recommendation you cannot refuse intelligently."""
    lines = list(m.why)
    if m.vram_mb:
        lines.append(f"needs about {_gb(m.vram_mb)} of your {_gb(_budget_mb())}"
                     + ("" if m.fits else " - which is why it is marked as not fitting"))
    if m.bench:
        lines.extend(f"{k}: {v:.2f}" for k, v in sorted(m.bench.items()))
    else:
        lines.append("no current public benchmark covers this one, so the "
                     "ranking here is by fit and popularity, not measured quality")
    here = is_installed(m.ref, names)
    return {"ref": m.ref, "source": m.source,
            "size_gb": round((m.bytes_ or 0) / 2**30, 2),
            "fits": m.fits, "score": round(m.score, 3),
            "installed": here,
            "because": lines,
            # One action per card, and never both. The card that offers a
            # download does not also offer the switch, because they are
            # separate approvals and a single tap must not answer two
            # questions.
            "actions": [{"id": "switch_model" if here else "download_model",
                         "ref": m.ref, "tier": "ask"}]}


def cards(k: int = 3, models: Optional[list] = None,
          profile: Optional[Profile] = None,
          fetcher: Callable = _get) -> list[dict]:
    """Top k recommendations as HUD cards. Works on Model objects rather
    than on recommend()'s dicts so nothing has to be round-tripped back
    through the dataclass."""
    # latch=False: a card carries a model ref, a size and a sentence of
    # reasoning. None of the profile goes out with it, so pinning the
    # conversation local here would cost something and protect nothing.
    p = profile or build_profile(latch=False)
    ms = models if models is not None else discover(fetcher=fetcher)
    ranked = [m for m in judge(ms, p) if m.fits][:k]
    names = installed()          # one lookup, not one per card
    return [explain(m, p, names) for m in ranked]


# --------------------------------------------------------------------------
#   The periodic check, for the heartbeat
# --------------------------------------------------------------------------

def periodic_check(force: bool = False) -> dict:
    """Look for something better, on a schedule. Never installs, never
    switches - it produces cards and stops, because a background task that
    can change your model is a background task that eventually will.

    Gated as `browse_model_catalog` (auto): fetching three public URLs that
    say nothing about you does not need permission.
    """
    if not _cfg("enabled", True):
        return {"checked": False, "reason": "the model steward is off in "
                                            "jarvis-framework.toml"}
    every_h = float(_cfg("check_every_hours", 168))       # weekly by default
    st = _read_state()
    last = float(st.get("last_check") or 0)
    if not force and time.time() - last < every_h * 3600:
        return {"checked": False, "reason": "checked recently",
                "next_due": last + every_h * 3600}

    v = _gate("browse_model_catalog", {"urls": len(outbound_requests())},
              prompt="Check the public model catalogues for anything new?")
    if not getattr(v, "allowed", False):
        return {"checked": False, "reason": getattr(v, "reason", "refused")}

    try:
        found = discover()
    except RateLimited as exc:
        return {"checked": False, "reason": str(exc)}
    except Exception as exc:
        return {"checked": False, "reason": f"catalogue fetch failed: {exc}"}

    st["last_check"] = time.time()
    _write_state(st)
    out = cards(k=int(_cfg("suggest_count", 3)), models=found)
    cur = current_model()
    sugg = []
    if cur:
        for task in ("coding",):
            s = suggest_for_task(task, cur, found)
            if s and s.worth_it:
                sugg.append(s.as_dict())
    return {"checked": True, "at": st["last_check"], "cards": out,
            "task_suggestions": sugg, "current": cur}
