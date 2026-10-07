"""
jarvis_style.py - sound like the owner, without touching any weights.

The full version of this proposal was fine-tuning: a LoRA adapter trained on
the owner's writing, plus a preference vector learned from thumbs and edits.
Both halves were cut, for different reasons.

The adapter does not fit. Training one for an 8B model needs 7.5-9 GB and this
card has 8 GB with a desktop compositor already holding some of it, so it
spills to system memory and runs 10-50x slower; merging at fp16 needs 16 GB
outright. And the part that matters more than the arithmetic: rolling back a
retrieval index is free, and rolling back weights is not. An adapter also
memorises the corpus in a way nobody can extract or audit, which makes it
personal data wearing a filename.

The preference vector does not have the data. It wants hundreds of labelled
pairs; one person produces five to ten signals a day, so it says nothing
useful for three to six months - and the thumbs-up button that would collect
them is the feature nobody presses after the second week.

What survives is the part that was always doing the work: show the model how
the owner actually writes, at generation time, by retrieving it.

Two rules make that safe, and both came out of the review.

  1. IT IS A MEMORY READ. Not a side table, not a cache, not a text file of
     samples. It goes through the memory store, so it trips the same taint
     latch every other memory read trips, and the conversation stays local.
     A style lookup that quietly bypassed that would put the owner's own
     prose into a cloud lane - which is the one rule this whole project is
     built around.

  2. ENTITIES ARE STRIPPED. Exemplars are chosen by how similar they are, not
     by how sensitive they are, so the phrasing of a private message will
     sometimes be the closest match for a note to a colleague. The names,
     addresses, numbers and companies come out before the text reaches a
     prompt. What is wanted is the shape of the sentences, and the shape
     survives the stripping.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional

try:
    import jarvis_framework as fw
except Exception:                                    # pragma: no cover
    fw = None


def _cfg(key: str, default):
    try:
        return fw.load_framework().get("style", {}).get(key, default)
    except Exception:
        return default


def _audit(event: str, detail: dict) -> None:
    try:
        fw.audit_log(event, detail)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   Stripping
# --------------------------------------------------------------------------
# Deliberately blunt. A clever entity recogniser would miss a different set of
# things and would be a dependency and a model; these patterns are the ones
# whose presence in a colleague-facing note would actually matter, and a
# false positive costs a placeholder in a sample nobody reads directly.

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_URL = re.compile(r"\bhttps?://\S+", re.I)
_PHONE = re.compile(r"(?<!\w)(?:\+\d{1,3}[\s-]?)?(?:\(\d{2,4}\)[\s-]?)?"
                    r"\d{3,4}[\s-]?\d{3,4}(?:[\s-]?\d{2,4})?(?!\w)")
_MONEY = re.compile(r"[$£€]\s?\d[\d,]*(?:\.\d+)?(?:\s?[kKmMbB])?")
_LONGNUM = re.compile(r"(?<!\w)\d[\d\s-]{5,}\d(?!\w)")
_PATH = re.compile(r"(?:[A-Za-z]:\\[^\s\"']+|(?:/[\w.-]+){2,})")
_DATE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")
_HANDLE = re.compile(r"(?<![\w/])@[A-Za-z][\w.-]{2,}")

# A capitalised word that is not at the start of a sentence and is not one of
# the ordinary ones. Crude, and that is the point: it over-strips rather than
# leaving a surname in.
_COMMON = frozenset("""
i a an the and or but if then so because while when where what who why how
monday tuesday wednesday thursday friday saturday sunday january february
march april may june july august september october november december
i'm i'll i've it's that's there's here's we're they're you're don't can't
ok okay yes no thanks hi hello dear regards best cheers
""".split())


@dataclass
class Exemplar:
    text: str
    source: str
    when: Optional[float] = None
    stripped: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def strip_entities(text: str) -> tuple:
    """Return (text, count). Everything replaced keeps its shape as a label,
    so a sentence reads as a sentence rather than collapsing."""
    n = 0

    def sub(rx, label, s):
        nonlocal n
        out, k = rx.subn(label, s)
        n += k
        return out

    s = text or ""
    s = sub(_URL, "[link]", s)
    s = sub(_EMAIL, "[email]", s)
    s = sub(_PATH, "[path]", s)
    s = sub(_HANDLE, "[handle]", s)
    s = sub(_MONEY, "[amount]", s)
    s = sub(_DATE, "[date]", s)
    s = sub(_PHONE, "[number]", s)
    s = sub(_LONGNUM, "[number]", s)

    # Proper nouns last, so the patterns above have already taken their pieces.
    out, start = [], True
    for token in re.split(r"(\s+)", s):
        if not token.strip():
            out.append(token)
            continue
        bare = token.strip(".,;:!?()[]\"'")
        if (not start and bare and bare[0].isupper() and bare.lower() not in _COMMON
                and not bare.isupper() and "[" not in token):
            out.append(token.replace(bare, "[name]"))
            n += 1
        else:
            out.append(token)
        start = token.rstrip().endswith((".", "!", "?", ":"))
    return "".join(out), n


# --------------------------------------------------------------------------
#   Retrieval
# --------------------------------------------------------------------------

def exemplars(about: str, k: Optional[int] = None,
              store: Any = None, latch: bool = True) -> list:
    """Find how the owner has written about something like this before.

    Goes through the memory store's own search, which is what makes this a
    memory read rather than a private index. `latch` trips the taint latch, so
    the turn that asked for a style sample stays on the local model - the
    same rule that applies to reading their mail, for the same reason.
    """
    if not _cfg("enabled", True):
        return []
    k = int(k if k is not None else _cfg("exemplars", 3) or 3)
    if k <= 0:
        return []
    try:
        if store is None:
            import jarvis_memory
            store = jarvis_memory.store()
        rows = store.search(about or "", k=max(1, k * 3))
    except Exception:
        return []

    if latch:
        # Before returning anything, not after. A latch set after the text has
        # been handed back is a latch that did not apply to the turn that used
        # it.
        try:
            import jarvis_gate
            jarvis_gate.latch_taint(why="style_exemplars")
        except Exception:
            pass

    min_words = int(_cfg("min_words", 6) or 6)
    out = []
    for r in rows:
        text = str(r.get("text") or "")
        if len(text.split()) < min_words:
            continue                       # too short to carry a style
        clean, n = strip_entities(text)
        out.append(Exemplar(clean, str(r.get("source") or "memory"),
                            r.get("at") or r.get("ts"), n))
        if len(out) >= k:
            break
    _audit("style.exemplars", {"asked": k, "returned": len(out),
                               "stripped": sum(e.stripped for e in out)})
    return out


def prompt_block(about: str, k: Optional[int] = None, store: Any = None) -> str:
    """The exemplars as a block to put in front of a draft.

    Empty when there is nothing to show, and that is on purpose: a heading
    with no examples under it teaches the model that this section is
    sometimes noise, and it discounts the section when there IS something in
    it.
    """
    found = exemplars(about, k=k, store=store)
    if not found:
        return ""
    lines = ["Here is how the owner has written about similar things before.",
             "Match the rhythm, the sentence length and the level of formality.",
             "Names and numbers have been removed; do not copy the placeholders.",
             ""]
    lines += [f"- {e.text}" for e in found]
    return "\n".join(lines)


def status() -> dict:
    return {"available": True, "exemplars": int(_cfg("exemplars", 3) or 3),
            "note": ("Retrieved at generation time through the memory store, "
                     "so it taints the turn local. No weights are changed and "
                     "nothing is learned in the background.")}
