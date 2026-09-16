"""jarvis_recall.py - which stored facts are worth attaching to a question.

REBUILT. Two call sites, both exact:

    jarvis_hud.py:1014   jarvis_recall.rank(query, [c["text"] for c in corpus],
                                            top_k=len(corpus), near_k=0,
                                            min_score=0.0)[0]
    jarvis_hud.py:1761   jarvis_recall.select_facts(query, facts,
                                                    text_of=lambda f: str(f.get("text","")))

`rank(...)[0]` is subscripted, so it returns a sequence whose first element is
what the caller wants - a (scores, order) pair. With top_k=len(corpus) and
min_score=0.0 nothing is filtered out, so that call is asking for SCORES FOR
EVERYTHING, in corpus order, to feed its own graph walk.

WHY A SEPARATE MODULE FROM jarvis_memory

memory decides what is TRUE. This decides what is RELEVANT to one question.
They fail differently: a memory bug destroys a fact permanently, a recall bug
attaches the wrong fact to one answer. Keeping them apart is what lets recall
be tuned freely - and it is the reason the owner could park "reworking
Jarvis's own recall" without touching the store.

THE COST OF GETTING THIS WRONG is not just a poor answer. Facts chosen here
are injected into the prompt, and memory-prefix.patch records what that cost:
recalled facts were the first thing in every request, which "dropped the
persona invariants and threw away the KV cache for the whole conversation,
every turn". Selecting fewer, better facts is a performance decision as much
as a quality one.
"""
from __future__ import annotations

import math
import re
from typing import Callable, Optional, Sequence

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore

try:
    from jarvis_memory import _content_words          # one stoplist, not two
except Exception:                                      # pragma: no cover
    _STOP = {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
             "how", "i", "in", "is", "it", "of", "on", "or", "that", "the",
             "to", "was", "what", "when", "where", "which", "who", "why",
             "with", "you", "your", "my", "me"}

    def _content_words(text: str) -> list:             # type: ignore
        return [w for w in re.findall(r"[\w\-]+", str(text).lower())
                if w not in _STOP]


def _cfg(key: str, default=None):
    if fw is None:
        return default
    try:
        return fw.load_framework().get("memory", {}).get(key, default)
    except Exception:
        return default


def score_one(query_words: set, text: str) -> float:
    """How relevant is this text to that question? 0 to 1.

    Overlap of content words, weighted so that a rare word counts for more
    than a common one, normalised by the question's length. Deliberately
    simple and explainable: a fact appearing in a prompt without the owner
    having asked for it needs a reason that can be stated in one line, and
    "it shares three uncommon words with your question" is such a reason.
    """
    have = _content_words(text)
    if not have or not query_words:
        return 0.0
    hits = [w for w in have if w in query_words]
    if not hits:
        return 0.0
    # Longer words are more discriminating than short ones. Cheap proxy for
    # inverse document frequency without keeping corpus statistics.
    weight = sum(1.0 + math.log(1 + len(w)) for w in set(hits))
    ideal = sum(1.0 + math.log(1 + len(w)) for w in query_words) or 1.0
    return round(min(weight / ideal, 1.0), 5)


def rank(query: str, texts: Sequence[str], top_k: int = 8, near_k: int = 0,
         min_score: float = 0.0, **_extra):
    """Score every text against the query.

    Returns (scores, order):
      scores  a list parallel to `texts`, in the SAME order as the input
      order   the indices of the kept texts, best first

    The caller at jarvis_hud:1014 takes `[0]`, so element zero has to be the
    parallel score list - it is zipped back against its own corpus. Returning
    them sorted would silently mis-associate every score with the wrong fact.

    `near_k` is accepted and, at 0, does nothing. It is the number of
    graph-adjacent facts to pull in alongside a hit; the caller passes 0 and
    then does its own neighbour walk with kg_neighbours(), so implementing it
    here would double-count. Honoured only when asked for.
    """
    qw = set(_content_words(query))
    scores = [score_one(qw, t) for t in texts]

    order = [i for i, s in enumerate(scores) if s > min_score or
             (min_score <= 0.0 and s >= 0.0)]
    # min_score=0.0 means "keep everything" - that is how the hud calls it,
    # together with top_k=len(corpus). A strict `s > 0.0` there would drop
    # every fact that shares no word, and the caller wants their zeros.
    if min_score > 0.0:
        order = [i for i, s in enumerate(scores) if s >= min_score]

    order.sort(key=lambda i: (-scores[i], i))
    if top_k is not None and top_k >= 0:
        order = order[:top_k]

    if near_k:
        order = order[:max(0, top_k - near_k)] if top_k else order
    return scores, order


def select_facts(query: str, facts: Sequence, text_of: Optional[Callable] = None,
                 k: Optional[int] = None, min_score: Optional[float] = None,
                 **_extra) -> list:
    """The facts worth putting in the prompt. Possibly none.

    `text_of` is passed by the caller as a lambda pulling "text" off a dict,
    so facts are opaque here - they may be rows, dicts or strings.

    RETURNS AN EMPTY LIST RATHER THAN A BEST GUESS. The caller writes
    `if chosen_facts:` and injects nothing when empty, which is the right
    behaviour for a question that has nothing to do with anything stored.
    Padding the prompt with the least-irrelevant facts would be worse than
    silence: it spends context, evicts the persona block, and invites the
    model to use something that does not apply.
    """
    if not facts:
        return []
    get = text_of or (lambda f: f.get("text", "") if isinstance(f, dict) else str(f))
    texts = [str(get(f) or "") for f in facts]

    top = k if k is not None else int(_cfg("recall_k", 5) or 5)
    floor = min_score if min_score is not None else float(_cfg("recall_min_score", 0.12) or 0.12)

    scores, order = rank(query, texts, top_k=top, min_score=floor)
    return [facts[i] for i in order]


def explain(query: str, facts: Sequence, text_of: Optional[Callable] = None) -> list:
    """Why each fact was or was not chosen. For the memory pane.

    INFERRED. It exists because "why did Jarvis bring that up" is the question
    the memory pane is for, and a relevance score with no explanation is not
    an answer.
    """
    get = text_of or (lambda f: f.get("text", "") if isinstance(f, dict) else str(f))
    qw = set(_content_words(query))
    out = []
    for f in facts:
        t = str(get(f) or "")
        shared = sorted(qw & set(_content_words(t)))
        out.append({"text": t[:120], "score": score_one(qw, t), "shared": shared})
    return sorted(out, key=lambda r: -r["score"])
