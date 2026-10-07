"""
jarvis_content_risk.py - one pipeline for text that arrived from outside.

Three things the 2026 attacks taught, built as one module so the scanner, the
gate and the MCP loader all treat outside text the same way:

  1. NORMALISE BEFORE YOU LOOK.  Instructions hidden in Unicode Tag characters
     (U+E0000-E007F) render as nothing to a person and as text to a model.
     Zero-width joiners split a keyword so a regex misses it. Bidi overrides
     make "txt.exe" display as "exe.txt". NFKC folds the look-alike letters
     that pass a diff as "no change". So every outside text is normalised
     first, the stripped characters are counted and reported, and anything a
     Tag sequence spelled out is decoded and scanned as hidden text.

  2. PIN WHAT YOU APPROVED.  A skill body or an MCP server's tool description
     that was benign when approved and hostile later (the ClawHub rug-pull,
     the Trail of Bits "line jumping" attack) is caught by hashing the
     NORMALISED text at approval and comparing on every load or tools/list.
     A diff is shown for the eye, but the scanner's verdict on the FULL
     current text is what decides - diffs are stateless, so twenty benign
     deltas can sum to a hostile whole. Cumulative drift past a threshold
     forces a full re-read.

  3. URGENCY IS A RED FLAG.  Text that rushes or minimises ("just approve
     these", "no need to check each one", "quick, before it expires") RAISES
     the effective tier of anything that follows. Applied only to outside
     content - tool results, skill bodies, tool descriptions, connector text -
     never to the owner's own words, or it fires on your own "quick, before
     it expires". The card shows the matched words, and repeat hits from one
     source collapse to a count, which is also the denial-of-service signal.

Nothing here asks a model anything. The text being judged is precisely the
text you must not put in a model's context and then ask for an opinion about.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    import jarvis_framework as fw
    _CFG_DIR = Path(fw.CONFIG_DIR)
except Exception:                                    # pragma: no cover
    fw = None
    _CFG_DIR = Path(os.path.expanduser("~/.openjarvis"))

STATE_PATH = Path(os.environ.get("JARVIS_CONTENT_RISK_STATE",
                                 _CFG_DIR / "content-risk.json"))
_LOCK = threading.RLock()


def _cfg(key: str, default):
    try:
        return fw.load_framework().get("content_risk", {}).get(key, default)
    except Exception:
        return default


# --------------------------------------------------------------------------
#   1. Normalisation
# --------------------------------------------------------------------------

# Unicode Tag block: U+E0000 (language tag) .. U+E007F (cancel tag). U+E0020-
# E007E map one-to-one onto printable ASCII, which is exactly how the hidden
# instructions were spelled.
_TAG_LO, _TAG_HI = 0xE0000, 0xE007F

# Characters with no width and no honest reason to be inside instructions.
_ZERO_WIDTH = frozenset([
    0x200B,  # zero width space
    0x200C,  # zero width non-joiner
    0x200D,  # zero width joiner
    0x2060,  # word joiner
    0x2061, 0x2062, 0x2063, 0x2064,   # invisible operators
    0xFEFF,  # byte order mark / zero width no-break space
    0x00AD,  # soft hyphen
    0x180E,  # mongolian vowel separator
])

# Bidirectional controls: the ones that reverse or embed display order.
_BIDI = frozenset([
    0x202A, 0x202B, 0x202C, 0x202D, 0x202E,   # LRE RLE PDF LRO RLO
    0x2066, 0x2067, 0x2068, 0x2069,           # LRI RLI FSI PDI
    0x200E, 0x200F, 0x061C,                   # LRM RLM ALM
])

# Variation selectors (U+FE00-FE0F, U+E0100-E01EF) are legitimate in emoji
# text, so they are counted but only reported when they appear in bulk.
def _is_variation_selector(cp: int) -> bool:
    return 0xFE00 <= cp <= 0xFE0F or 0xE0100 <= cp <= 0xE01EF


@dataclass
class Normalised:
    text: str                         # what the scanner and the model should see
    hidden: str = ""                  # text spelled out in Tag characters, decoded
    tags: int = 0                     # Tag characters removed
    zero_width: int = 0
    bidi: int = 0
    variation_selectors: int = 0
    controls: int = 0                 # other C0/C1 controls (not \t \n \r)
    nfkc_changed: bool = False        # NFKC altered at least one character
    changed: bool = False             # anything at all differed from the input

    @property
    def stripped(self) -> int:
        return self.tags + self.zero_width + self.bidi + self.controls

    def as_dict(self) -> dict:
        d = asdict(self)
        d.pop("text", None)
        d["stripped"] = self.stripped
        return d


def normalise(text: str) -> Normalised:
    """Fold and strip. Returns the text a person would have seen, plus a
    count of everything a person would NOT have seen."""
    if not isinstance(text, str):
        text = str(text)
    out: list[str] = []
    hidden: list[str] = []
    n = Normalised(text="")
    for ch in text:
        cp = ord(ch)
        if _TAG_LO <= cp <= _TAG_HI:
            n.tags += 1
            if 0xE0020 <= cp <= 0xE007E:
                hidden.append(chr(cp - 0xE0000))
            elif cp == _TAG_HI and hidden:
                hidden.append(" ")
            continue
        if cp in _ZERO_WIDTH:
            n.zero_width += 1
            continue
        if cp in _BIDI:
            n.bidi += 1
            continue
        if _is_variation_selector(cp):
            n.variation_selectors += 1
            continue
        if cp < 0x20 and ch not in "\t\n\r" or 0x7F <= cp <= 0x9F:
            n.controls += 1
            continue
        out.append(ch)
    joined = "".join(out)
    folded = unicodedata.normalize("NFKC", joined)
    n.nfkc_changed = folded != joined
    n.text = folded
    n.hidden = "".join(hidden).strip()
    n.changed = folded != text
    return n


# --------------------------------------------------------------------------
#   2. The urgency rule
# --------------------------------------------------------------------------
# Every phrase here is a way of asking the reader to decide faster than they
# would have. None of them is something a tool result or a skill body has an
# honest reason to say. The owner's own utterances never pass through here.

_RUSH = re.compile(
    r"\b(?:"
    r"just\s+(?:approve|accept|allow|confirm|run|click)\b"
    r"|approve\s+(?:all|them\s+all|these|everything|the\s+rest|it\s+all)\b"
    r"|(?:no\s+need|don'?t\s+(?:need|bother|have|worry\s+about))\s+to\s+"
    r"(?:check|review|read|verify|confirm|ask|look|inspect)\b"
    r"|(?:without|skip|bypass|instead\s+of)\s+(?:the\s+)?"
    r"(?:review(?:ing)?|check(?:ing)?|confirmation|approval|verif(?:ying|ication))\b"
    # Carry up to two more words so the quoted phrase on the card reads as a
    # sentence ("quick, before it expires") rather than stopping at "before it".
    r"|(?:quick(?:ly)?|hurry|fast|now)\s*[,!-]?\s*before\s+"
    r"(?:it|this|the|they|your)(?:\s+\w+){0,2}"
    r"|before\s+(?:it|this|the\s+\w+|your\s+\w+)\s+(?:expires?|closes?|is\s+gone|runs?\s+out|locks?)\b"
    r"|(?:act|respond|reply|do\s+(?:this|it))\s+(?:now|immediately|right\s+away|at\s+once)\b"
    r"|(?:within|in)\s+(?:the\s+next\s+)?\d+\s+(?:seconds?|minutes?|mins?|hours?)\s+or\b"
    r"|time[-\s]sensitive|last\s+chance|final\s+(?:warning|notice|reminder)"
    r"|(?:this\s+is|it'?s)\s+(?:completely\s+|totally\s+|perfectly\s+)?safe\b"
    r"|(?:already\s+(?:been\s+)?|has\s+(?:already\s+)?been\s+|was\s+)"
    r"(?:pre-?)?(?:approved|verified|reviewed|vetted|checked)\s+(?:by|for|so)\b"
    r"|trust\s+(?:me|us|this)\b"
    r"|(?:you\s+)?(?:do\s+not|don'?t)\s+(?:need\s+to\s+)?(?:ask|tell|inform|notify)\s+"
    r"(?:the\s+)?(?:user|owner|human|anyone)\b"
    r"|urgent(?:ly)?[:!]|\burgent\s+(?:action|request|update|security)\b"
    r")",
    re.I)


@dataclass
class RushHit:
    phrase: str          # the 3-6 words that matched, quoted on the card
    context: str         # one short sentence around it, for the expand
    offset: int

    def as_dict(self) -> dict:
        return asdict(self)


def find_rush(text: str) -> list[RushHit]:
    """Every rushing phrase in already-normalised text."""
    hits = []
    for m in _RUSH.finditer(text or ""):
        a, b = m.start(), m.end()
        # widen to sentence-ish bounds for the context line
        s = max(0, text.rfind(".", 0, a), text.rfind("\n", 0, a))
        e_candidates = [i for i in (text.find(".", b), text.find("\n", b)) if i != -1]
        e = min(e_candidates) if e_candidates else len(text)
        ctx = text[s:e].strip(" .\n")[:200]
        phrase = " ".join(m.group(0).split())
        hits.append(RushHit(phrase=phrase[:80], context=ctx, offset=a))
    return hits


# --------------------------------------------------------------------------
#   Persistent state: pins and rush counters (one small JSON, atomic writes)
# --------------------------------------------------------------------------

def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text("utf-8"))
    except Exception:
        return {"pins": {}, "rush": {"latch": None, "hits": []}}


def _save_state(st: dict) -> bool:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(st, indent=1), "utf-8")
        os.replace(tmp, STATE_PATH)
        return True
    except Exception:
        return False


def _audit(event: str, detail: dict) -> None:
    try:
        fw.audit_log(event, detail)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   3. Rush latch - what the gate consults
# --------------------------------------------------------------------------

def _day(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def latch_rush(source: str, hits: list[RushHit], minutes: Optional[float] = None) -> dict:
    """Record that outside text tried to rush the reader. The gate raises the
    effective tier of everything that follows while the latch holds. Returns
    the reason chip a card should show.

    Repeat hits from one source are counted per day: "4th time today" is both
    the honest thing to show and the denial-of-service signal - a source that
    trips this every few minutes is trying to make approvals cost more.
    """
    if not hits:
        return {}
    if minutes is None:
        # `_cfg(...) or 10` would make 0 mean 10, so a config that sets the
        # latch to zero - the owner's way of turning the rule off - would
        # silently switch it back on.
        raw = _cfg("rush_latch_minutes", 10)
        try:
            minutes = 10.0 if raw is None else float(raw)
        except (TypeError, ValueError):
            minutes = 10.0
    if minutes <= 0:
        _audit("content_risk.rush_ignored", {"source": source[:120],
                                             "why": "rush_latch_minutes is 0"})
        return {}
    now = time.time()
    with _LOCK:
        st = _load_state()
        rush = st.setdefault("rush", {"latch": None, "hits": []})
        today = _day(now)
        rush["hits"] = [h for h in rush.get("hits", []) if _day(h.get("ts", 0)) == today]
        rush["hits"].append({"source": source[:120], "ts": now,
                             "phrase": hits[0].phrase})
        count = sum(1 for h in rush["hits"] if h["source"] == source[:120])
        until = now + max(0.0, float(minutes)) * 60.0
        prev = rush.get("latch") or {}
        if not prev or prev.get("until", 0) < until:
            rush["latch"] = {"until": until, "source": source[:120],
                             "phrase": hits[0].phrase, "context": hits[0].context,
                             "count_today": count, "set": now}
        else:
            prev["count_today"] = max(prev.get("count_today", 0), count)
        _save_state(st)
    # Log the phrase, never the surrounding content: the phrase is the
    # attacker's words, the surrounding content may be the owner's mail.
    _audit("content_risk.rushed", {"source": source[:120], "phrase": hits[0].phrase,
                                   "count_today": count, "minutes": minutes})
    return reason_chip(source, hits[0], count)


CHIP_TEXT = "Tier raised — this text tried to rush you"


def reason_chip(source: str, hit: RushHit, count_today: int) -> dict:
    """The card's reason, shaped for a phone: a one-line text, the quoted
    words, and a count. The source is named, never quoted."""
    return chip_from({"source": source, "phrase": hit.phrase,
                      "context": hit.context, "count_today": count_today})


def chip_from(latch: dict) -> dict:
    """The same chip, built from a stored latch rather than a fresh hit, so
    the gate and the scanner cannot drift into saying it differently."""
    count = int(latch.get("count_today", 1) or 1)
    text = CHIP_TEXT
    if count > 1:
        text += f" ({_ordinal(count)} time today)"
    return {"code": "rushed", "text": text,
            "quote": latch.get("phrase", ""),
            "context": latch.get("context", ""),
            "source": str(latch.get("source", ""))[:120],
            "count_today": count}


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def rush_active() -> Optional[dict]:
    """The current latch, or None. A state file that cannot be read is
    treated as no latch: this rule can only ever RAISE a tier, so failing
    open here means falling back to the ordinary tier table, never below it."""
    try:
        st = _load_state()
        latch = (st.get("rush") or {}).get("latch")
        if latch and float(latch.get("until", 0)) > time.time():
            return dict(latch)
    except Exception:
        pass
    return None


def clear_rush() -> bool:
    with _LOCK:
        st = _load_state()
        st.setdefault("rush", {})["latch"] = None
        return _save_state(st)


_RANK = {"auto": 0, "notify": 1, "ask": 2, "never": 3}


def raise_tier(tier: str) -> tuple[str, Optional[dict]]:
    """Apply the latch to a tier. Content can only ever raise. `never` stays
    `never`; `ask` stays `ask`; `auto` and `notify` become `ask` (or whatever
    [content_risk].rush_raises_to says, floored at the original)."""
    latch = rush_active()
    if not latch:
        return tier, None
    target = str(_cfg("rush_raises_to", "ask") or "ask")
    if target not in _RANK:
        target = "ask"
    if _RANK.get(tier, 2) >= _RANK[target]:
        return tier, latch                  # already at or above; still show why
    return target, latch


# --------------------------------------------------------------------------
#   4. Pins - hash what was approved, on normalised text
# --------------------------------------------------------------------------

def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _key(kind: str, key: str) -> str:
    return f"{kind}:{key}"


@dataclass
class PinCheck:
    status: str                       # "new" | "pinned" | "drifted"
    sha: str
    pinned_sha: Optional[str] = None
    drift: float = 0.0                # 0..1, this change vs the pinned text
    cumulative_drift: float = 0.0     # summed over re-approvals since first pin
    needs_full_reread: bool = False
    diff: str = ""                    # unified diff, normalised text, for the eye
    first_approved: Optional[float] = None
    last_approved: Optional[float] = None

    def as_dict(self) -> dict:
        return asdict(self)


def check_pin(kind: str, key: str, normalised_text: str) -> PinCheck:
    """Compare normalised text against what was approved. Never mutates."""
    st = _load_state()
    row = (st.get("pins") or {}).get(_key(kind, key))
    sha = _sha(normalised_text)
    if not row:
        return PinCheck("new", sha)
    if row.get("sha") == sha:
        return PinCheck("pinned", sha, row["sha"], 0.0,
                        float(row.get("cumulative_drift", 0.0)), False, "",
                        row.get("first"), row.get("last"))
    old = row.get("text", "")
    ratio = difflib.SequenceMatcher(None, old, normalised_text, autojunk=False).ratio() \
        if old else 0.0
    drift = round(1.0 - ratio, 4)
    cumulative = round(float(row.get("cumulative_drift", 0.0)) + drift, 4)
    threshold = float(_cfg("full_reread_drift", 0.35) or 0.35)
    diff = "\n".join(difflib.unified_diff(
        old.splitlines(), normalised_text.splitlines(),
        fromfile=f"{key} (approved)", tofile=f"{key} (now)", lineterm="", n=1))
    return PinCheck("drifted", sha, row.get("sha"), drift, cumulative,
                    cumulative >= threshold or not old, diff[:8000],
                    row.get("first"), row.get("last"))


def pin(kind: str, key: str, normalised_text: str, by: str = "owner") -> dict:
    """Record an approval of this exact normalised text. Keeps the text so the
    next drift can be diffed and measured; text is the approved instructions,
    not the owner's data, so keeping it is not a second copy of anything
    private."""
    now = time.time()
    with _LOCK:
        st = _load_state()
        pins = st.setdefault("pins", {})
        k = _key(kind, key)
        prev = pins.get(k)
        chk = check_pin(kind, key, normalised_text)
        cumulative = chk.cumulative_drift if chk.status == "drifted" else \
            float((prev or {}).get("cumulative_drift", 0.0))
        if chk.needs_full_reread:
            cumulative = 0.0            # a full re-read resets the drift budget
        pins[k] = {"sha": chk.sha, "text": normalised_text[:200_000],
                   "first": (prev or {}).get("first", now), "last": now,
                   "by": by[:64], "cumulative_drift": cumulative,
                   "approvals": int((prev or {}).get("approvals", 0)) + 1}
        _save_state(st)
    _audit("content_risk.pinned", {"kind": kind, "key": key, "sha": chk.sha[:16],
                                   "status": chk.status, "drift": chk.drift})
    return {"kind": kind, "key": key, "sha": chk.sha, "was": chk.status}


def unpin(kind: str, key: str) -> bool:
    with _LOCK:
        st = _load_state()
        removed = (st.get("pins") or {}).pop(_key(kind, key), None) is not None
        _save_state(st)
    return removed


def pinned(kind: Optional[str] = None) -> list[dict]:
    st = _load_state()
    out = []
    for k, row in sorted((st.get("pins") or {}).items()):
        kk, _, key = k.partition(":")
        if kind and kk != kind:
            continue
        out.append({"kind": kk, "key": key, "sha": row.get("sha"),
                    "first": row.get("first"), "last": row.get("last"),
                    "approvals": row.get("approvals", 0),
                    "cumulative_drift": row.get("cumulative_drift", 0.0)})
    return out


# --------------------------------------------------------------------------
#   5. The pipeline itself
# --------------------------------------------------------------------------

def _scanner():
    """The skill scanner is the rule table for outside text. Imported lazily
    so this module has no import-time dependency on it (and vice versa)."""
    import jarvis_skills
    return jarvis_skills


@dataclass
class Assessment:
    source: str
    normalised: dict
    findings: list[dict] = field(default_factory=list)   # scanner findings on the full text
    hidden_findings: list[dict] = field(default_factory=list)  # findings inside Tag-hidden text
    rush: list[dict] = field(default_factory=list)
    reason: dict = field(default_factory=dict)            # the card chip, if rushed
    pin: Optional[dict] = None
    verdict: str = "clean"                                # clean | review | refuse
    text: str = ""                                        # normalised text, for the caller

    def as_dict(self) -> dict:
        d = asdict(self)
        d.pop("text", None)
        return d


def assess(text: str, source: str, *, kind: Optional[str] = None,
           key: Optional[str] = None, where: str = "text",
           latch: bool = True) -> Assessment:
    """Run outside text through the whole pipeline.

    - normalise, count what was stripped, decode Tag-hidden text
    - scan the FULL normalised text with the skill scanner's rule table
    - scan any hidden text separately (a hit there is always a block)
    - find rushing phrases; latch the gate if any (when `latch`)
    - compare against the pin for (kind, key) if given
    """
    n = normalise(text)
    sk = _scanner()
    # scan_text normalises on its own way in, so handing it the RAW text gives
    # one set of findings: the rule table over the folded text, plus the
    # invisible-character findings (hidden_tags, hidden_<rule>, bidi_override,
    # zero_width) it raises itself. Hidden-text hits are split out so a card
    # can say "this was invisible" rather than burying it in the list.
    all_findings = [f.as_dict() for f in sk.scan_text(text, where)]
    findings = [f for f in all_findings if not f["code"].startswith("hidden_")]
    hidden_findings = [f for f in all_findings if f["code"].startswith("hidden_")]

    rush = find_rush(n.text) + (find_rush(n.hidden) if n.hidden else [])
    reason = {}
    if rush and latch:
        reason = latch_rush(source, rush)

    pinchk = None
    if kind and key:
        pinchk = check_pin(kind, key, n.text).as_dict()

    sev = [f["severity"] for f in findings + hidden_findings]
    verdict = "refuse" if "block" in sev else ("review" if "warn" in sev or rush else "clean")
    return Assessment(source=source, normalised=n.as_dict(), findings=findings,
                      hidden_findings=hidden_findings, rush=[h.as_dict() for h in rush],
                      reason=reason, pin=pinchk, verdict=verdict, text=n.text)


# --------------------------------------------------------------------------
#   6. MCP tool catalogues and tool results
# --------------------------------------------------------------------------

def _tool_text(tool: dict) -> str:
    """Everything a model reads about a tool: name, description, and every
    description string inside its input schema. The Cursor exfiltration hid
    in a parameter description, which the approval dialog never showed."""
    parts = [str(tool.get("name", "")), str(tool.get("description", ""))]

    def walk(node: Any):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("description", "title") and isinstance(v, str):
                    parts.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(tool.get("inputSchema") or tool.get("input_schema") or {})
    return "\n".join(parts)


def vet_tool_catalog(server: str, tools: Iterable[dict], *, latch: bool = True) -> dict:
    """Run at EVERY tools/list, not once at approval. Returns which tools may
    be offered to the model now and which need a person first.

    - refused: scanner block on the full text -> never offered
    - new: no pin yet on a server that HAS other pins -> needs approval
      (a newly added tool on an approved server is a new approval, not an
      inheritance)
    - drifted: text differs from the pin -> needs re-approval; carries the
      diff for the eye, the full-text verdict for the decision, and
      needs_full_reread when cumulative drift passed the threshold
    - allowed: pinned and unchanged, or first sight of an entirely new server
      (returned under `unpinned` so the caller can decide to pin the set)
    """
    tools = list(tools)
    server_has_pins = any(p["key"].startswith(server + "/") for p in pinned("mcp_tool"))
    out = {"server": server, "allowed": [], "refused": [], "new": [], "drifted": [],
           "unpinned": [], "assessments": {}}
    for t in tools:
        name = str(t.get("name", "?"))
        key = f"{server}/{name}"
        a = assess(_tool_text(t), f"mcp:{key}", kind="mcp_tool", key=key,
                   where=f"tool {name}", latch=latch)
        out["assessments"][name] = a.as_dict()
        if a.verdict == "refuse":
            out["refused"].append(name)
            continue
        status = (a.pin or {}).get("status")
        if status == "pinned":
            out["allowed"].append(name)
        elif status == "drifted":
            out["drifted"].append(name)
        elif server_has_pins:
            out["new"].append(name)
        else:
            out["allowed"].append(name)
            out["unpinned"].append(name)
    _audit("content_risk.tools_list", {"server": server, "n": len(tools),
                                       "refused": len(out["refused"]),
                                       "new": len(out["new"]),
                                       "drifted": len(out["drifted"])})
    return out


def approve_tool(server: str, tool: dict, by: str = "owner") -> dict:
    """A person read the FULL current text and said yes. Pin it."""
    n = normalise(_tool_text(tool))
    return pin("mcp_tool", f"{server}/{tool.get('name', '?')}", n.text, by=by)


def vet_tool_result(tool: str, content: Any, *, server: str = "") -> dict:
    """Tool RESULTS are the other half of the line-jumping vector: a web page,
    a file, a mail body that the model reads as if it were the owner. They
    cannot be refused - they are data - but they are normalised, scanned, and
    any rushing phrase latches the gate. Returns the normalised content plus
    the assessment; callers replace the content with `text` so invisible
    characters never reach the model at all."""
    if not isinstance(content, str):
        return {"text": content, "changed": False, "assessment": None}
    src = f"tool:{server + '/' if server else ''}{tool}"
    a = assess(content, src, where=f"result of {tool}", latch=True)
    return {"text": a.text, "changed": bool(a.normalised.get("changed")),
            "assessment": a.as_dict(), "rushed": bool(a.rush),
            "reason": a.reason}


def status() -> dict:
    """For the HUD and the desktop: is a latch active, what is pinned."""
    return {"rush": rush_active(), "pins": pinned(),
            "config": {"rush_latch_minutes": _cfg("rush_latch_minutes", 10),
                       "rush_raises_to": _cfg("rush_raises_to", "ask"),
                       "full_reread_drift": _cfg("full_reread_drift", 0.35)}}
