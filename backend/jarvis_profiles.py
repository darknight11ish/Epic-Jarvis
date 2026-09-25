"""jarvis_profiles.py - the three setups Jarvis offers for your graphics cards.

NEW MODULE, shipped whole (apply-patches.ps1 copies it beside jarvis_hud.py).
Pure functions: no files, no network, no processes. jarvis_hardware.py finds
the cards and does everything that touches the PC; this module only does
the arithmetic, the choices and the words.

WHAT IT IS FOR. docs/HARDWARE-PROFILES.md is the design. For any single card
of 6-24 GB, or any pair of cards, this works out three setups ("presets")
and says in plain words what each one switches off and why:

    fast       "Fastest answers"   a smaller, quicker everyday model
    smart      "Smartest answers"  the biggest everyday model the cards hold
    features   "Most features"     a balanced model, plus pictures and long
                                   conversations wherever there is room

Nothing here changes anything. A preset is only ever applied through the
existing approval cards, one step at a time (jarvis_hardware.py).

THE ARITHMETIC (design section 4.2). Every figure is CALCULATED, NOT
MEASURED, until the speed recorder has a row for it (section 4.7):

    room for models = total - desktop share - 0.33 x processes - gap
    model need      = weights (+ picture reader) + context x cache per token
                      + working space (+ 0.25 for a picture model)

and, for a second model beside chat in the same Ollama, Ollama's own rough
guess must pass its 80% check too (section 2.4). The gap is 0.75 GB - the
owner's decision 1 (2026-09-24); llama.cpp's own default is 1 GB.

Every constant is in CONSTANTS below with the place it came from, so the
Details view can show it and nothing is a bare number.

Standard library only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Optional

GIB = 1024 ** 3

# --------------------------------------------------------------------------
#   Constants, each with where it came from
# --------------------------------------------------------------------------

#: The empty gap llama.cpp keeps on every card. The owner's decision 1
#: (docs/HARDWARE-PROFILES.md section 5, 2026-09-24): 0.75 GB.
GAP_GIB = 0.75
#: llama.cpp's own default (common/common.h:481, 1024 MiB per device). The
#: design's section 4.4 tables were written with it; the tests replay them.
LLAMA_DEFAULT_GAP_GIB = 1.00
CUDA_START_GIB = 0.33
CUSHION_GIB = 0.10
SHARE_MONITOR_GIB = 1.10
SHARE_NO_MONITOR_GIB = 0.60
PICTURE_GIB = 0.25
Q4_BITS = 4.90
KV_BYTES = {"q8_0": 1.0625, "f16": 2.0}
OLLAMA_GATE = 0.80
#: The context sizes a preset picks from (tokens). The design's tables use
#: exactly these; the Qwen 3 models were trained to 32,768.
CONTEXTS = (4096, 6144, 8192, 12288, 16384, 32768)
#: Chat below this is not offered: 6K is the smallest the design gives an
#: 8B or 14B (8 GB, "Smartest answers").
CHAT_MIN_CTX = 6144
#: The small model's floor: "room for qwen3:4b at >= 8,192" (section 4.1).
#: Below it, a card is not used for chat at all.
SMALL_MIN_CTX = 8192
#: "Long conversations" means at least this much. Below it, chat is not
#: counted as the long-conversation feature (the design's "-").
LONG_MIN_CTX = 12288
#: Every picture costs at least 1,024 tokens (section 2.5), so pictures get
#: 8K; 4K only as the last try on a small card.
PICTURE_CTX = 8192
#: "Smartest answers" with two cards keeps chat on the faster card when the
#: biggest model gets at least this much there; below it, chat moves to the
#: card where it gets the most room (the design's 8 + 10 GB rows).
FAST_CARD_MIN_CTX = 8192

CONSTANTS = {
    "gap": (GAP_GIB, "the empty gap on each card: the owner's decision 1, 2026-09-24 "
                     "(llama.cpp's own default is 1 GB, common/common.h:481)"),
    "cuda_start": (CUDA_START_GIB, "graphics start-up per model process "
                                   "(docs/MODEL-TOPOLOGY.md; not re-measured)"),
    "cushion": (CUSHION_GIB, "a rounding allowance of this design (section 4.2)"),
    "share_monitor": (SHARE_MONITOR_GIB, "the desktop's share of a card with a monitor: "
                                         "a placeholder until measured (section 4.1)"),
    "share_no_monitor": (SHARE_NO_MONITOR_GIB, "the share of a card with no monitor: a "
                                               "placeholder until measured (section 4.1)"),
    "picture": (PICTURE_GIB, "reading one picture: a placeholder (section 4.2)"),
    "q4_bits": (Q4_BITS, "bits per weight for Q4_K_M (docs/MODEL-TOPOLOGY.md)"),
    "q8_0_bytes": (KV_BYTES["q8_0"], "bytes per value in the compact q8_0 conversation "
                                     "format (section 2.8)"),
    "ollama_gate": (OLLAMA_GATE, "Ollama loads a second model beside another only if its "
                                 "own guess is under 80% of what is free (server/sched.go, "
                                 "section 2.4)"),
}

# --------------------------------------------------------------------------
#   The models (design section 2.8 and appendix 8.2)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Model:
    """One model's shape, from its config.json (section 2.8). Sizes are
    COMPUTED from the parameter count, never read from ollama.com (which
    was blocked where this was written)."""
    ref: str
    size: str               # "8B" - the words the apps show
    params: int             # the text part, counted from the shape
    reader_params: int      # the picture reader, 0 for a text model
    layers: int
    kv_heads: int
    head_dim: int
    embedding: int
    heads: int
    compute_gib: float      # working space at num_batch 512 (placeholder)
    max_ctx: int
    source: str

    @property
    def pictures(self) -> bool:
        return self.reader_params > 0

    @property
    def weights_gib(self) -> float:
        return self.params * Q4_BITS / 8 / GIB

    @property
    def reader_gib(self) -> float:
        """The picture reader, assumed f16 (2 bytes a parameter)."""
        return self.reader_params * 2 / GIB

    @property
    def file_gib(self) -> float:
        return self.weights_gib + self.reader_gib

    @property
    def download_gb(self) -> float:
        """What `ollama pull` fetches, in the GB a download dialog shows.
        Computed, not read from ollama.com."""
        return (self.params * Q4_BITS / 8 + self.reader_params * 2) / 1e9

    def kv_bytes(self, kv: str = "q8_0") -> float:
        """Cache per token: 2 (K and V) x layers x KV heads x head size x bytes."""
        return 2 * self.layers * self.kv_heads * self.head_dim * KV_BYTES[kv]

    def cache_gib(self, ctx: int, kv: str = "q8_0") -> float:
        return ctx * self.kv_bytes(kv) / GIB

    def need(self, ctx: int, kv: str = "q8_0") -> float:
        """What llama.cpp's fit measures (section 4.2)."""
        return (self.file_gib + self.cache_gib(ctx, kv) + self.compute_gib
                + (PICTURE_GIB if self.pictures else 0.0))

    def ollama_guess(self, ctx: int) -> float:
        """Ollama's own rough guess (llm/llama_server.go PredictServerVRAM,
        section 2.5): the file plus an f16 cache with head size embedding /
        heads. It decides whether a second model may load beside another."""
        per = 2 * self.layers * self.kv_heads * (self.embedding // self.heads) * 2
        return self.file_gib + ctx * per / GIB


def _text_params(h, inter, layers, heads, kv, hd, vocab, tied, qkv_bias=False, qk_norm=False):
    """Parameters of a Qwen/Llama-shaped decoder, from config.json fields."""
    per = (h * heads * hd + 2 * h * kv * hd + heads * hd * h
           + ((heads * hd + 2 * kv * hd) if qkv_bias else 0)
           + 3 * h * inter + 2 * h + (2 * hd if qk_norm else 0))
    return per * layers + vocab * h * (1 if tied else 2) + h


def _vit_params(out, depth=32, h=1280, inter=3420):
    """Qwen2.5-VL's picture reader: 32 blocks, width 1280 (section 2.8)."""
    patch = 3 * 2 * 14 * 14 * h
    block = (h + h * 3 * h + 3 * h + h * h + h + h
             + 2 * (h * inter + inter) + inter * h + h)
    merger = h + 4 * h * 4 * h + 4 * h + 4 * h * out + out
    return patch + block * depth + merger


_SRC = "config.json copy named in docs/HARDWARE-PROFILES.md section 2.8"
MODELS = {
    "qwen3:4b": Model("qwen3:4b", "4B",
                      _text_params(2560, 9728, 36, 32, 8, 128, 151936, True, qk_norm=True), 0,
                      36, 8, 128, 2560, 32, 0.25, 40960, _SRC),
    "qwen3:8b": Model("qwen3:8b", "8B",
                      _text_params(4096, 12288, 36, 32, 8, 128, 151936, False, qk_norm=True), 0,
                      36, 8, 128, 4096, 32, 0.30, 40960, _SRC),
    "qwen3:14b": Model("qwen3:14b", "14B",
                       _text_params(5120, 17408, 40, 40, 8, 128, 151936, False, qk_norm=True), 0,
                       40, 8, 128, 5120, 40, 0.35, 40960, _SRC),
    "qwen2.5vl:3b": Model("qwen2.5vl:3b", "3B",
                          _text_params(2048, 11008, 36, 16, 2, 128, 151936, True, qkv_bias=True),
                          _vit_params(2048), 36, 2, 128, 2048, 16, 0.25, 128000, _SRC),
    "qwen2.5vl:7b": Model("qwen2.5vl:7b", "7B",
                          _text_params(3584, 18944, 28, 28, 4, 128, 152064, False, qkv_bias=True),
                          _vit_params(3584), 28, 4, 128, 3584, 28, 0.30, 128000, _SRC),
}

#: Chat, biggest first.
CHAT_MODELS = ("qwen3:14b", "qwen3:8b", "qwen3:4b")
#: The long-conversation lane on another card, in order of preference - the
#: design's section 4.4 tables, which never give a 14B lane more than 16K.
LANE_CANDIDATES = (("qwen3:14b", 16384), ("qwen3:14b", 12288), ("qwen3:14b", 8192),
                   ("qwen3:8b", 32768), ("qwen3:4b", 32768))
#: Pictures, biggest first; swapping on one card always uses the small one.
PICTURE_MODELS = ("qwen2.5vl:7b", "qwen2.5vl:3b")
SWAP_PICTURES = (("qwen2.5vl:3b", PICTURE_CTX), ("qwen2.5vl:3b", 4096))

#: Models to test later - NOT in any preset (decision 4, and the research of
#: 2026-09-24). Shown in the Details view, so nobody mistakes the gap for
#: an oversight.
TEST_LATER = (
    ("Spark-X2.5-4B", "the owner's decision 4: tested once the second card is installed and "
                      "measured, against the Qwen choice; not in any preset until then"),
    ("qwen3.5:4b / qwen3.5:9b", "Qwen 3.5 keeps conversation in far less memory (research "
                                "2026-09-24, second-hand model-card numbers); its tool use "
                                "has not been measured, so it is a test for later, not a "
                                "preset"),
)

#: The names a preset creates. jarvis-primary is never overwritten
#: (section 4.8): going back is a model switch.
TUNED = {"chat": "jarvis-chat", "long": "jarvis-long", "pictures": "jarvis-vision"}

PRESETS = (
    {"id": "fast", "name": "Fastest answers",
     "summary": "A smaller, quicker everyday model."},
    {"id": "smart", "name": "Smartest answers",
     "summary": "The biggest everyday model your cards can hold, even if that makes "
                "answers slower."},
    {"id": "features", "name": "Most features",
     "summary": "A balanced everyday model, plus pictures and long conversations wherever "
                "there is room left over."},
)
PRESET_IDS = tuple(p["id"] for p in PRESETS)
_PRESET = {p["id"]: p for p in PRESETS}

#: Published memory speeds (GB/s), the only ones this design has a source
#: for (docs/MODEL-TOPOLOGY.md). A card not listed is "not known", never
#: guessed; the planner then falls back to its other rules.
SPEEDS_GBS = (
    ("2080 TI", 616.0),
    ("2080 SUPER", 496.0),
    ("2060", 336.0),     # the 12 GB model; the 6 GB one has the same bus speed
)


def published_speed(name: str) -> Optional[float]:
    up = " ".join(str(name or "").upper().split())
    for key, gbs in SPEEDS_GBS:
        if key in up:
            if key == "2060" and ("SUPER" in up):
                return None      # the 2060 Super is faster; not in the table
            return gbs
    return None


# --------------------------------------------------------------------------
#   The cards, as the planner sees them
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Card:
    """One graphics card. jarvis_hardware.py builds these from Ollama's log,
    nvidia-smi and the registry; the tests build them by hand."""
    key: str
    name: str
    total_gib: float
    monitor: Optional[bool] = None
    #: The desktop's share, measured (free memory with nothing loaded), or
    #: None for the placeholder.
    share_gib: Optional[float] = None
    share_source: str = ""
    route: str = "CUDA"              # CUDA, ROCm, Vulkan
    compute: str = ""                # "7.5", or a gfx name for AMD
    vendor: str = "nvidia"           # nvidia, amd, intel, other
    uuid: str = ""
    speed_gbs: Optional[float] = None

    @property
    def cc(self) -> Optional[float]:
        try:
            return float(self.compute)
        except (TypeError, ValueError):
            return None


def desktop_share(card: Card) -> tuple:
    """(GB, "measured" | "placeholder")."""
    if card.share_gib is not None and card.share_gib >= 0:
        return float(card.share_gib), "measured"
    return (SHARE_NO_MONITOR_GIB if card.monitor is False else SHARE_MONITOR_GIB), "placeholder"


def room(card: Card, processes: int = 1, gap: float = GAP_GIB) -> float:
    """Room for models on the card (section 4.2), before the cushion."""
    return card.total_gib - desktop_share(card)[0] - CUDA_START_GIB * processes - gap


def kv_type(card: Card) -> tuple:
    """("q8_0" | "f16", why) - the conversation format this card gets
    (section 2.2 and 4.2)."""
    if card.route == "CUDA":
        cc = card.cc
        if cc is None:
            return "f16", (f"Jarvis could not tell the {card.name}'s generation, so it gets the "
                           f"larger conversation format (f16), which always works")
        if cc < 6.0 or abs(cc - 7.2) < 1e-9:
            return "f16", (f"the {card.name} cannot use the compact conversation format (q8_0) "
                           f"- it would stop models loading - so it gets the larger one (f16)")
        return "q8_0", ""
    if card.route == "ROCm":
        return "q8_0", ""
    return "f16", (f"the {card.name} is reached through Vulkan, where the compact conversation "
                   f"format (q8_0) is only safe on some drivers, so it gets the larger one "
                   f"(f16) until a measured test says otherwise")


def best_effort(card: Card) -> Optional[str]:
    """Why presets on this card are "best effort, not tested", or None."""
    if card.vendor in ("amd", "intel") or card.route in ("ROCm", "Vulkan"):
        maker = {"amd": "an AMD", "intel": "an Intel"}.get(card.vendor, "a non-NVIDIA")
        return (f"the {card.name} is {maker} card: Jarvis gives it safe settings, but it has "
                f"not been tested")
    cc = card.cc
    if card.route == "CUDA" and cc is not None and cc < 7.5:
        return (f"the {card.name} is older than the RTX 20 series: it runs the same models on "
                f"slower routines, and it has not been tested")
    return None


def rank(cards: list, primary: str = "") -> tuple:
    """(cards, fastest first; the sentence saying why the first is first).

    Section 4.1: `[compute] primary_gpu` overrides everything; otherwise
    published memory speed when both are known; otherwise the card Jarvis's
    settings are made for (NVIDIA, RTX 20 or newer) over a best-effort one;
    otherwise the newer generation; otherwise the card with more room. "The
    card with the monitor" is not a rule any more."""
    cards = list(cards)
    if not cards:
        return [], "no card"
    if len(cards) == 1:
        return cards, "it is the only card"
    want = str(primary or "").strip().lower()
    if want:
        for i, c in enumerate(cards):
            if (c.uuid and c.uuid.lower() == want) or c.key.lower() == want:
                rest = cards[:i] + cards[i + 1:]
                return [c] + rest, "[compute] primary_gpu names it"
    a, b = cards[0], cards[1]
    rest = cards[2:]
    sa = a.speed_gbs if a.speed_gbs is not None else published_speed(a.name)
    sb = b.speed_gbs if b.speed_gbs is not None else published_speed(b.name)
    if sa and sb and abs(sa - sb) > 1e-9:
        first, second = (a, b) if sa > sb else (b, a)
        return [first, second] + rest, (f"its memory is faster ({max(sa, sb):.0f} against "
                                        f"{min(sa, sb):.0f} GB/s, the published figures)")
    ea, eb = best_effort(a) is None, best_effort(b) is None
    if ea != eb:
        first, second = (a, b) if ea else (b, a)
        return [first, second] + rest, ("it is the card Jarvis's settings are made for; the "
                                        "other is best effort")
    ca, cb = a.cc, b.cc
    if a.route == b.route == "CUDA" and ca and cb and abs(ca - cb) > 1e-9:
        first, second = (a, b) if ca > cb else (b, a)
        return [first, second] + rest, "it is the newer generation"
    ra, rb = room(a), room(b)
    if abs(ra - rb) > 1e-9:
        first, second = (a, b) if ra > rb else (b, a)
        return [first, second] + rest, ("the two look equally fast, and it has more room "
                                        "(no monitor on it)")
    return [a, b] + rest, "the two look equally fast, and it is listed first"


# --------------------------------------------------------------------------
#   A layout: where each model goes
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Role:
    role: str               # chat, long, pictures
    model: Model
    ctx: int
    kv: str
    card: Card
    #: own (alone in its Ollama), beside (with chat in one Ollama), swap
    #: (unloads chat while it runs), turns (shares the other card with
    #: another lane, one at a time)
    mode: str

    @property
    def need(self) -> float:
        return self.model.need(self.ctx, self.kv)

    @property
    def tuned(self) -> str:
        return TUNED[self.role]


@dataclass
class Bar:
    card: Card
    models_gib: float
    processes: int
    gap: float

    @property
    def fixed_gib(self) -> float:
        return desktop_share(self.card)[0] + CUDA_START_GIB * self.processes + self.gap

    @property
    def used_gib(self) -> float:
        return self.models_gib + self.fixed_gib

    @property
    def blocks(self) -> str:
        full = max(0, min(16, round(self.used_gib / self.card.total_gib * 16)))
        return "█" * full + "░" * (16 - full)


@dataclass
class Layout:
    preset: str
    gap: float
    cards: list
    chat: Optional[Role] = None
    long: Optional[Role] = None
    long_is_chat: bool = False
    pictures: Optional[Role] = None
    off: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    best_effort: list = field(default_factory=list)
    bars: list = field(default_factory=list)

    @property
    def roles(self) -> list:
        return [r for r in (self.chat, self.long, self.pictures) if r is not None]

    @property
    def two_ollamas(self) -> bool:
        return any(r.card is not self.chat.card for r in self.roles) if self.chat else False

    @property
    def lane_card(self) -> Optional[Card]:
        for r in (self.long, self.pictures):
            if r is not None:
                return r.card
        return None


def _fits(model: Model, ctx: int, kv: str, card: Card, processes: int, gap: float,
          already: float = 0.0) -> bool:
    return already + model.need(ctx, kv) <= room(card, processes, gap) - CUSHION_GIB + 1e-9


def best_ctx(model: Model, card: Card, *, gap: float, min_ctx: int, processes: int = 1,
             already: float = 0.0, cap: Optional[int] = None) -> Optional[int]:
    """The largest context from CONTEXTS that fits, at least `min_ctx`."""
    kv = kv_type(card)[0]
    top = min(model.max_ctx, cap or model.max_ctx)
    for ctx in sorted(CONTEXTS, reverse=True):
        if ctx < min_ctx or ctx > top:
            continue
        if _fits(model, ctx, kv, card, processes, gap, already):
            return ctx
    return None


def _gate_ok(first: Role, second: Model, ctx: int, card: Card) -> bool:
    """Ollama's own check before loading `second` beside `first` (4.2):
    its guess <= 0.8 x (total - desktop share - 0.33 - first model's need)."""
    free = card.total_gib - desktop_share(card)[0] - CUDA_START_GIB - first.need
    return second.ollama_guess(ctx) <= OLLAMA_GATE * free + 1e-9


def _min_ctx(ref: str) -> int:
    return SMALL_MIN_CTX if ref == "qwen3:4b" else CHAT_MIN_CTX


def pages(tokens: int) -> int:
    """About how many pages of conversation (an estimate: about 750 words
    per 1,000 tokens, and 1,000 words a page)."""
    return max(1, int(tokens * 0.75 // 1000))


def ctx_words(tokens: int) -> str:
    return f"{tokens // 1024}K"


def _gb(x: float) -> str:
    return f"{x:.2f}"


def plan(cards: list, preset: str, *, gap: float = GAP_GIB, primary: str = "",
         limits: Optional[dict] = None) -> Layout:
    """Where each model goes for `preset` on these cards. Never raises for
    a known preset. `limits` caps a role's context ({"chat": 8192}) - the
    measuring step's "it did not fit, drop to the next size" (4.7)."""
    if preset not in _PRESET:
        raise ValueError(f"no preset called {preset!r}")
    limits = dict(limits or {})
    ranked, why_first = rank(cards, primary)
    lay = Layout(preset=preset, gap=gap, cards=ranked)
    if not ranked:
        lay.off.append("No graphics card Ollama can use was found, so everything runs on the "
                       "processor, slowly. Pictures and extra features are off.")
        return lay
    if len(ranked) > 2:
        extra = ", ".join(c.name for c in ranked[2:])
        lay.notes.append(f"Jarvis plans for up to two cards; the {extra} is left out.")
        ranked = ranked[:2]
        lay.cards = ranked
    for c in ranked:
        be = best_effort(c)
        if be and be not in lay.best_effort:
            lay.best_effort.append(be)
        kv, why = kv_type(c)
        if why:
            lay.notes.append(why[0].upper() + why[1:] + ".")
    if len(ranked) == 1:
        _plan_one(lay, ranked[0], preset, gap, limits)
    else:
        _plan_two(lay, ranked[0], ranked[1], preset, gap, limits, why_first)
    _bars(lay)
    return lay


def _chat_on(card: Card, ref: str, gap: float, limits: dict, min_ctx: Optional[int] = None) \
        -> Optional[Role]:
    m = MODELS[ref]
    ctx = best_ctx(m, card, gap=gap, min_ctx=min_ctx or _min_ctx(ref), cap=limits.get("chat"))
    if ctx is None:
        return None
    return Role("chat", m, ctx, kv_type(card)[0], card, "own")


def _plan_one(lay: Layout, card: Card, preset: str, gap: float, limits: dict) -> None:
    kv = kv_type(card)[0]
    chat = None
    if preset == "fast":
        chat = _chat_on(card, "qwen3:4b", gap, limits)
    elif preset == "smart":
        for ref in CHAT_MODELS:
            chat = _chat_on(card, ref, gap, limits)
            if chat:
                break
    else:
        chat = _chat_on(card, "qwen3:8b", gap, limits)
        if chat is not None and chat.ctx < LONG_MIN_CTX:
            small = _chat_on(card, "qwen3:4b", gap, limits)
            if small is not None:
                lay.notes.append(
                    f"Chat is the 4B: the 8B would get only {chat.ctx:,} tokens of conversation "
                    f"here, too little for long conversations, and nothing would fit beside it.")
                chat = small
        if chat is None:
            chat = _chat_on(card, "qwen3:4b", gap, limits)
    if chat is None:
        m = MODELS["qwen3:4b"]
        lay.off.append(
            f"The {card.name} does not have room for even the small model "
            f"({_gb(m.need(SMALL_MIN_CTX, kv))} GB needed with {SMALL_MIN_CTX:,} tokens, "
            f"{_gb(room(card, 1, gap) - CUSHION_GIB)} GB of room), so chat runs on the "
            f"processor, slowly. Pictures and extra features are off.")
        return
    lay.chat = chat
    lay.long_is_chat = chat.ctx >= LONG_MIN_CTX
    if not lay.long_is_chat:
        lay.off.append(
            f"Long conversations: no. Chat gets only {chat.ctx:,} tokens (about "
            f"{pages(chat.ctx)} pages): the {chat.model.size} model's weights and the empty gap "
            f"leave little room on a {card.total_gib:.0f} GB card.")
    # Pictures, one card.
    beside = None
    for ref in PICTURE_MODELS:
        pm = MODELS[ref]
        if _fits(pm, PICTURE_CTX, kv, card, 2, gap, already=chat.need) and \
                _gate_ok(chat, pm, PICTURE_CTX, card):
            beside = Role("pictures", pm, PICTURE_CTX, kv, card, "beside")
            break
    if preset in ("fast", "smart"):
        if preset == "fast":
            lay.off.append("Pictures: off. They would share the card with chat, and this choice "
                           "keeps the card for chat alone.")
        elif beside is not None:
            lay.off.append("Pictures: off by choice. A picture model would fit beside chat, but "
                           "this choice keeps the card for chat alone, so nothing competes "
                           "with it.")
        else:
            lay.off.append(f"Pictures: off. The picture model does not fit beside the "
                           f"{chat.model.size} chat model on this card.")
        return
    if beside is not None:
        lay.pictures = beside
        return
    for ref, ctx in SWAP_PICTURES:
        pm = MODELS[ref]
        if _fits(pm, ctx, kv, card, 1, gap):
            lay.pictures = Role("pictures", pm, ctx, kv, card, "swap")
            lay.off.append(
                f"Pictures take turns with chat: a message with a picture unloads chat for a "
                f"moment ({pm.ref} needs {_gb(pm.need(ctx, kv))} GB on its own), and chat loads "
                f"again on your next message. That costs a few seconds each way (not measured).")
            return
    pm = MODELS["qwen2.5vl:3b"]
    lay.off.append(
        f"Pictures: off. Even the small picture model does not fit on this card on its own "
        f"({_gb(pm.need(4096, kv))} GB needed, {_gb(room(card, 1, gap) - CUSHION_GIB)} GB of room).")


def _lanes_possible(card: Card) -> Optional[str]:
    """Why Jarvis cannot start its second Ollama on this card, or None."""
    if card.vendor != "nvidia" or card.route != "CUDA":
        return (f"Extra features on the {card.name}: not possible yet. Jarvis starts its second "
                f"copy of Ollama only on an NVIDIA card, pinned by the card's id.")
    if not card.uuid:
        return (f"Extra features on the {card.name}: not possible, because its id (GPU-...) "
                f"could not be read, and Jarvis only points work at a card by its id.")
    return None


def _plan_two(lay: Layout, a: Card, b: Card, preset: str, gap: float, limits: dict,
              why_first: str) -> None:
    chat = None
    if preset == "fast":
        chat = _chat_on(a, "qwen3:4b", gap, limits) or _chat_on(b, "qwen3:4b", gap, limits)
    elif preset == "smart":
        for ref in CHAT_MODELS:
            on_a = _chat_on(a, ref, gap, limits)
            on_b = _chat_on(b, ref, gap, limits)
            if on_a and on_a.ctx >= FAST_CARD_MIN_CTX:
                chat = on_a
            elif on_a or on_b:
                chat = max((x for x in (on_a, on_b) if x), key=lambda r: (r.ctx, r.card is a))
            if chat:
                break
    else:
        chat = _chat_on(a, "qwen3:8b", gap, limits) or _chat_on(a, "qwen3:4b", gap, limits) \
            or _chat_on(b, "qwen3:8b", gap, limits) or _chat_on(b, "qwen3:4b", gap, limits)
    if chat is None:
        lay.off.append("Neither card has room for even the small model, so chat runs on the "
                       "processor, slowly.")
        return
    lay.chat = chat
    other = b if chat.card is a else a
    lay.notes.append(f"Chat runs on the {chat.card.name}"
                     + (f" ({why_first})." if chat.card is a else
                        f", the slower card: the {chat.model.size} gets more room there, and "
                        f"answers come out more slowly."))
    lay.long_is_chat = chat.ctx >= LONG_MIN_CTX
    blocked = _lanes_possible(other)
    if blocked:
        lay.off.append(blocked)
        if not lay.long_is_chat:
            lay.off.append(f"Long conversations: no. Chat gets only {chat.ctx:,} tokens.")
        return
    okv = kv_type(other)[0]
    long = None
    for ref, ctx in LANE_CANDIDATES:
        if ctx <= chat.ctx or (limits.get("long") and ctx > limits["long"]):
            continue
        if _fits(MODELS[ref], ctx, okv, other, 1, gap):
            long = Role("long", MODELS[ref], ctx, okv, other, "own")
            break
    pics = None
    for ref in PICTURE_MODELS:
        if _fits(MODELS[ref], PICTURE_CTX, okv, other, 1, gap):
            pics = Role("pictures", MODELS[ref], PICTURE_CTX, okv, other, "own")
            break
    if long is not None:
        lay.long = long
    elif lay.long_is_chat:
        lay.off.append(f"A separate long-conversation model: off. The {other.name} cannot hold "
                       f"more conversation than chat already does ({chat.ctx:,} tokens).")
    else:
        lay.off.append(f"Long conversations: no. Chat gets only {chat.ctx:,} tokens, and the "
                       f"{other.name} has no room for more.")
    if pics is not None:
        lay.pictures = pics
    else:
        lay.off.append(f"Pictures: off. No picture model fits on the {other.name}.")
    if long is not None and pics is not None:
        lay.long = replace(long, mode="turns")
        lay.pictures = replace(pics, mode="turns")
        lay.notes.append(f"Long conversations and pictures take turns on the {other.name}: "
                         f"one model is loaded there at a time.")


def _bars(lay: Layout) -> None:
    lay.bars = []
    for c in lay.cards:
        on = [r for r in lay.roles if r.card is c]
        if not on:
            lay.bars.append(Bar(c, 0.0, 0, lay.gap))
            continue
        beside = [r for r in on if r.mode == "beside"]
        if beside:
            models = sum(r.need for r in on)
            procs = len(on)
        else:
            models = max(r.need for r in on)
            procs = 1
        lay.bars.append(Bar(c, models, procs, lay.gap))


# --------------------------------------------------------------------------
#   Words
# --------------------------------------------------------------------------

def role_words(r: Role) -> str:
    """"qwen3:8b, 8K of conversation, compact format, on the RTX 2080 SUPER"."""
    fmt = "compact format" if r.kv == "q8_0" else "larger format (f16)"
    return f"{r.model.ref}, {ctx_words(r.ctx)}, {fmt}, on the {r.card.name}"


def recommended(layouts: dict) -> tuple:
    """(preset id, one sentence why). "Most features" when its everyday
    model is the 8B or bigger - the size Jarvis has been tuned with - and it
    adds what fits; otherwise "Smartest answers", which then keeps the
    bigger model."""
    feat = layouts.get("features")
    if feat is not None and feat.chat is not None and feat.chat.model.ref != "qwen3:4b":
        return "features", ("It keeps an 8B everyday model on the "
                            f"{feat.chat.card.name} and adds what fits beside it.")
    smart = layouts.get("smart")
    if smart is not None and smart.chat is not None:
        return "smart", (f"It keeps the {smart.chat.model.size} everyday model; the other "
                         f"choices would swap it for the smaller 4B to make room.")
    return "fast", "Only the small model fits on this PC."


def describe(lay: Layout) -> dict:
    """A layout as display text and numbers - what GET /api/hardware sends.
    No structured model list beyond this one preset's roles (the phone must
    never get a catalogue: section 4.6)."""
    p = _PRESET[lay.preset]

    def role(r: Optional[Role]) -> Optional[dict]:
        if r is None:
            return None
        return {"model": r.model.ref, "size": r.model.size, "context": r.ctx,
                "context_words": f"remembers about {pages(r.ctx)} pages of conversation "
                                 f"(an estimate)",
                "format": r.kv, "card": r.card.name, "card_key": r.card.key,
                "mode": r.mode, "need_gib": round(r.need, 2), "creates": r.tuned,
                "words": role_words(r)}

    long = role(lay.long)
    if long is None and lay.long_is_chat and lay.chat is not None:
        long = {"same_as_chat": True, "context": lay.chat.ctx,
                "words": f"chat itself ({ctx_words(lay.chat.ctx)})"}
    return {
        "id": lay.preset, "name": p["name"], "summary": p["summary"],
        "chat": role(lay.chat), "long": long, "pictures": role(lay.pictures),
        "off": list(lay.off), "notes": list(lay.notes),
        "best_effort": bool(lay.best_effort), "best_effort_why": list(lay.best_effort),
        "ollamas": 2 if lay.two_ollamas else 1,
        "bars": [{"card": b.card.name, "card_key": b.card.key,
                  "models_gib": round(b.models_gib, 2), "fixed_gib": round(b.fixed_gib, 2),
                  "used_gib": round(b.used_gib, 2), "total_gib": round(b.card.total_gib, 2),
                  "blocks": b.blocks,
                  "words": (f"{b.models_gib:.2f} + {b.fixed_gib:.2f} = {b.used_gib:.2f} of "
                            f"{b.card.total_gib:.0f} GB")}
                 for b in lay.bars],
        "details": details(lay),
    }


def details(lay: Layout) -> list:
    """Every number with its arithmetic (section 8), one line each."""
    out = []
    for c in lay.cards:
        share, how = desktop_share(c)
        procs = next((b.processes for b in lay.bars if b.card is c), 1) or 1
        r = room(c, procs, lay.gap)
        out.append(
            f"Room on the {c.name}: {c.total_gib:.2f} - {share:.2f} (desktop, {how}) - "
            f"{CUDA_START_GIB * procs:.2f} (start-up, {procs} model{'s' if procs > 1 else ''}) - "
            f"{lay.gap:.2f} (empty gap) = {r:.2f} GB; {r - CUSHION_GIB:.2f} after the "
            f"{CUSHION_GIB:.2f} rounding allowance.")
    for r in lay.roles:
        m = r.model
        parts = [f"{m.weights_gib:.2f} (weights)"]
        if m.pictures:
            parts.append(f"{m.reader_gib:.2f} (picture reader)")
        parts.append(f"{m.cache_gib(r.ctx, r.kv):.2f} (conversation, {r.ctx:,} tokens, {r.kv})")
        parts.append(f"{m.compute_gib:.2f} (working space)")
        if m.pictures:
            parts.append(f"{PICTURE_GIB:.2f} (one picture)")
        out.append(f"{r.role.capitalize()}: {m.ref} = " + " + ".join(parts) +
                   f" = {r.need:.2f} GB. Ollama's own guess: {m.ollama_guess(r.ctx):.2f} GB.")
    out.append("Everything above is calculated, not measured.")
    return out


# --------------------------------------------------------------------------
#   The one PowerShell line (section 4.5, step 6)
# --------------------------------------------------------------------------

#: The only names the line may set, and what each value must look like.
ALLOWED = {
    "OLLAMA_KV_CACHE_TYPE": re.compile(r"q8_0|f16"),
    "OLLAMA_KEEP_ALIVE": re.compile(r"-1"),
    "CUDA_VISIBLE_DEVICES": re.compile(r"GPU-[0-9A-Fa-f-]{8,64}"),
    "OLLAMA_VULKAN": re.compile(r"0"),
    "LLAMA_ARG_FIT_TARGET": re.compile(r"\d{1,5}"),
}
ORDER = tuple(ALLOWED)
#: Prints what is set now. Reads only.
CHECK_LINE = ("foreach ($n in 'OLLAMA_KV_CACHE_TYPE','OLLAMA_KEEP_ALIVE','CUDA_VISIBLE_DEVICES',"
              "'OLLAMA_VULKAN','LLAMA_ARG_FIT_TARGET') { '{0} = {1}' -f $n, "
              "[Environment]::GetEnvironmentVariable($n, 'User') }")
_RESTART = ("Now quit Ollama (right-click its icon by the clock, then Quit Ollama) and start it "
            "again from the Start menu.")


def settings_for(lay: Layout) -> list:
    """[(name, value)] Ollama must read at start-up for this layout, in a
    fixed order. Only the everyday Ollama's; Jarvis sets the second one's
    itself (jarvis_second_card.lane_env)."""
    if lay.chat is None:
        return []
    out = [("OLLAMA_KV_CACHE_TYPE", lay.chat.kv), ("OLLAMA_KEEP_ALIVE", "-1")]
    cards = lay.cards
    if len(cards) >= 2 and lay.chat.card.uuid and lay.chat.card.route == "CUDA":
        out.append(("CUDA_VISIBLE_DEVICES", lay.chat.card.uuid))
    if cards and all(c.vendor == "nvidia" and c.route == "CUDA" for c in cards):
        out.append(("OLLAMA_VULKAN", "0"))
    if abs(lay.gap - LLAMA_DEFAULT_GAP_GIB) > 1e-9:
        out.append(("LLAMA_ARG_FIT_TARGET", str(int(round(lay.gap * 1024)))))
    return out


def _check(name: str, value: str) -> str:
    pat = ALLOWED.get(name)
    if pat is None:
        raise ValueError(f"{name} is not a setting this line may change")
    if not isinstance(value, str) or not pat.fullmatch(value):
        raise ValueError(f"{name} would be set to something unexpected; refused")
    return value


def one_line(settings: list) -> Optional[str]:
    """One line, Windows PowerShell 5.1-safe: only SetEnvironmentVariable
    for the user and one Write-Host. None when there is nothing to set."""
    if not settings:
        return None
    parts = [f"[Environment]::SetEnvironmentVariable('{n}', '{_check(n, v)}', 'User')"
             for n, v in settings]
    n = len(settings)
    parts.append(f"Write-Host 'Saved {n} setting{'s' if n != 1 else ''} for your Windows user "
                 f"(nothing was written to a file). {_RESTART}'")
    return "; ".join(parts)


def undo_line(settings: list, before: Optional[dict] = None) -> Optional[str]:
    """The matching undo: each name back to what it was before (`before`,
    read from the user settings) when that looks right, else removed."""
    if not settings:
        return None
    before = before or {}
    parts = []
    for n, _ in settings:
        old = before.get(n)
        pat = ALLOWED[n]
        if isinstance(old, str) and pat.fullmatch(old):
            parts.append(f"[Environment]::SetEnvironmentVariable('{n}', '{old}', 'User')")
        else:
            parts.append(f"[Environment]::SetEnvironmentVariable('{n}', $null, 'User')")
    parts.append(f"Write-Host 'Put {len(settings)} setting{'s' if len(settings) != 1 else ''} "
                 f"back the way they were (nothing was written to a file). {_RESTART}'")
    return "; ".join(parts)


# --------------------------------------------------------------------------
#   The tuned models (section 4.5, step 3)
# --------------------------------------------------------------------------

#: Kept word for word the same as backend/jarvis-primary.Modelfile's SYSTEM
#: block (test_profiles.py checks), so a preset's chat model keeps Jarvis's
#: rules.
JARVIS_SYSTEM = (
    "You are Jarvis, a private assistant running entirely on this machine.\n\n"
    "Say what is a guess and what is verified. If you are not sure, say you are not sure - "
    "a confident wrong answer costs more here than a hedged one.\n\n"
    "Never claim an action was taken that was not. You do not send email, edit files, or run "
    "commands yourself; you propose them and a person approves each one. If you have proposed "
    "something, say that you have proposed it, not that it is done.\n\n"
    "Anything recalled about the owner is private and stays on this machine. Do not repeat it "
    "back unless it is relevant to what was asked.\n")

#: jarvis-primary.Modelfile's settings, kept for every tuned model.
_QWEN3_SAMPLING = (("temperature", 0.7), ("top_p", 0.8), ("top_k", 20), ("min_p", 0.0),
                   ("repeat_penalty", 1.05))
_STOPS = ("<|im_end|>", "<|im_start|>")


def tuned_parameters(r: Role) -> dict:
    p = {"num_ctx": int(r.ctx), "num_batch": 512, "num_predict": 1024}
    if r.model.ref.startswith("qwen3:"):
        p.update(dict(_QWEN3_SAMPLING))
    p["stop"] = list(_STOPS)
    return p


def modelfile(r: Role) -> str:
    """The Modelfile the approval card shows, word for word what is made."""
    lines = [f"FROM {r.model.ref}"]
    for k, v in tuned_parameters(r).items():
        if k == "stop":
            lines += [f'PARAMETER stop "{s}"' for s in v]
        else:
            lines.append(f"PARAMETER {k} {v}")
    lines.append(f'SYSTEM """{JARVIS_SYSTEM}"""')
    return "\n".join(lines) + "\n"


def create_request(r: Role) -> dict:
    """Ollama's POST /api/create body for this model (the structured form:
    `from`, `parameters`, `system`). Not run against a real Ollama here."""
    return {"model": r.tuned, "from": r.model.ref, "parameters": tuned_parameters(r),
            "system": JARVIS_SYSTEM, "stream": False}
