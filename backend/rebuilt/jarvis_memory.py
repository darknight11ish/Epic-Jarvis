"""jarvis_memory.py - what Jarvis knows about you, and when it was true.

PART RECOVERED, PART REBUILT. READ THIS FIRST.

The original is gone. More of this file survived than of any other, though,
because five patches in `backend/` quote it: memory-safety, memory-pane,
bitemporal, embedding-guard and memory-noise. 178 lines of the text below are
VERBATIM original source lifted from their context and removed lines - the
whole table schema, add(), retire(), _embed_rows(), the search fusion loop,
current_facts() and status() among them. Where something had to be written
rather than recovered, the comment says INFERRED.

WHAT THIS STORE IS

Two ideas, both of which the patches explain in the original's own words:

  1. Hybrid search. Words (FTS5/bm25) and meaning (vector) are searched
     separately and the two result lists fused with reciprocal rank fusion, so
     a fact that does well on either is found.

  2. Bi-temporal facts: know WHEN a fact was true, AND when we found out.
     Two different questions, two different axes, and conflating them loses
     the one case this store exists for.

     VALID TIME - valid_from, valid_to - is when the fact was true in the
     world. "Mario lives at X" with no dates means that when he moves, both
     addresses sit there as equals.

     TRANSACTION TIME - created, retired_at - is when this machine believed
     it. created is stamped on insert; retired_at is stamped when the fact
     stops being recalled.

     Retiring sets BOTH: retired_at is always now, because that is when we
     learned, and valid_to defaults to now but can be set earlier. That is
     what makes "I moved in January, I am telling you in March" storable. One
     axis cannot hold it: with valid_to alone you either lie about when the
     move happened or lie about when you were told, and a fact accepted late
     out of the review queue has the same problem.

     Since memory idea 4 (2026-09-26) add() also reads that date from the
     words themselves: "I moved to Leeds in January", told in March, is
     true from 1 January (true_from(), fixed rules, never a future date),
     and a correction that is OLDER news than the fact it names keeps that
     fact and is stored as history (Graphiti's rule; add()).

     A fact is never deleted, so "where do I live" returns the current answer,
     "where did I live last year" works, and "what did you think you knew in
     June" is answerable from the same rows.

     THE ONE EXCEPTION IS erase() ("Erase the words", the owner's decision of
     2026-09-24). It wipes a fact's WORDS for good - the text, its search
     entry, its meaning vector, and every copy of the text elsewhere in this
     file - and keeps the row, its id and its dates, so the history still
     shows that something was here and when. The row is never removed.

     "ALWAYS KEEP IN MIND" (the owner's decision of 2026-09-24) is a short
     list of pinned fact IDS - the `profile` table, pin() and profile()
     below - read with every local chat question (with_profile()). It
     holds no words: the facts' own text is read, word for word, and a
     pinned fact that stops being current leaves the list by itself.

     "USED IN THIS ANSWER" (2026-09-25) reads facts BY ID for the apps -
     used_view(), GET /api/memory/used - because the chat reply's header
     and the memory_saved event carry ids only, never words.

     This is the Graphiti idea done natively in the one SQLite file the
     project already uses, because Graphiti requires a graph database server -
     neo4j>=5.26 is not optional there - and the whole point here is one file,
     no daemons. See docs/PEERS.md.

DEGRADES, NEVER FAILS. If the embedding model is not installed or cannot
download, search falls back to words alone and says so in status(); it does
not raise and it does not return nothing.

THE FIVE WAYS THIS FILE USED TO DESTROY DATA, all fixed, none to be undone:

  1. A correction retired a RANDOM unrelated fact. `_accept` took the model's
     free-text `replaces`, ran search(k=1), and retired whatever came back -
     and search has no relevance floor, so it always came back with
     something. Measured: accepting "Mario drives a 1998 Volvo" retired "Mario
     prefers tabs over spaces in Go". find_one() below is the fix: two
     overlapping content words AND 50% containment, or None. **None means
     store the new fact and retire nothing.** Two facts that disagree can be
     sorted out later; a deleted allergy cannot.
  2. FTS5 has no stoplist, so an OR-query built from every word in a question
     matched almost the whole store on "the" and "is". _STOP below.
  3. A NaN or all-zero embedding was stored without complaint, and the row was
     then UNREACHABLE FOREVER - every distance comparison against NaN is
     false, so the fact could never be returned by any query.
     _usable_vector() below.
  4. A different embedding model silently made old vectors incomparable.
     The `meta` table records which model wrote them and rebuilds on change.
  5. retire() with no row matched returned nothing distinguishable from
     success. It returns cur.rowcount > 0.
"""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import struct
import sys
import threading
import zlib
import time
from contextlib import closing
from pathlib import Path
from typing import Iterable, Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - the store must work standalone
    fw = None  # type: ignore


# --------------------------------------------------------------------------
#   Where
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


#: backend/README.md: "DOCS_DB is ~/.openjarvis/memory.db. The memory store
#: creates that file for you." JARVIS_MEMORY_DB overrides it, which is how the
#: surviving test suites give each test its own database.
DOCS_DB = Path(os.environ.get("JARVIS_MEMORY_DB") or (_config_dir() / "memory.db"))

_LOCK = threading.RLock()


# --------------------------------------------------------------------------
#   Vectors
# --------------------------------------------------------------------------

def _pack(v: Iterable[float]) -> bytes:
    v = list(v)
    return struct.pack(f"{len(v)}f", *v)


def _usable_vector(v, dim: int) -> bool:
    """Is this embedding safe to store or query with?

    THE BUG THIS EXISTS FOR, from embedding-guard.patch. `_pack` will happily
    serialise NaN - struct does not care - and a NaN row is then unreachable
    FOREVER, because every distance comparison against NaN is false. The fact
    is in the database, counts in status(), and can never be returned by any
    query. An all-zero vector is the same class of problem from the other
    direction: cosine divides by the norm, so it makes every score NaN rather
    than merely inaccurate. Jan documents that case for the same reason
    (evaluateEmbeddingVector, janhq/jan, Apache-2.0).

    Silent, permanent, and invisible in every count. Checked before the write.

    The WIDTH check is here for a different failure. facts_vec is declared
    float[dim] at creation and sqlite-vec raises on a mismatch; the store
    already handles the model CHANGING width by dropping the table, but a
    single short row from a partial read would raise per-insert for ever.

    Cheap: one pass over 384 floats, on a path that has just run a transformer.
    """
    if not isinstance(v, (list, tuple)) or len(v) != dim:
        return False
    total = 0.0
    for x in v:
        # bool is a subclass of int, and [True]*dim is not an embedding.
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            return False
        if not math.isfinite(x):
            return False
        # _pack writes float32. struct.pack('f', 1e39) does NOT raise - it
        # silently produces +inf, so a value this check called finite became
        # a non-finite vector on disk, counted as embedded, with meaningless
        # distances. The float32 ceiling is ~3.4e38.
        if abs(float(x)) > 3.4e38:
            return False
        total += float(x) * float(x)
    # Not `total == 0`: an all-but-zero vector normalises to garbage just as
    # badly, and float error means an exact zero is not the only way to get
    # there. This threshold is far below any real unit vector, whose norm is 1.
    return total > 1e-12


# Words that match nearly every fact and so tell you nothing about which one.
# FTS5 has no stoplist of its own, so an OR-query built from every word in the
# question matched almost the whole store on "the" and "is", and bm25 then
# ranked that noise. Only content words get a vote.
_STOP = {
    "a", "an", "and", "any", "are", "as", "at", "be", "been", "but", "by",
    "can", "could", "did", "do", "does", "for", "from", "had", "has", "have",
    "how", "i", "if", "in", "is", "it", "its", "just", "me", "my", "no",
    "not", "of", "on", "or", "our", "out", "should", "so", "that", "the",
    "their", "them", "then", "there", "these", "they", "this", "to", "up",
    "am", "he", "her", "hers", "him", "his", "she", "us",
    "was", "we", "were", "what", "when", "where", "which", "who", "why",
    "will", "with", "would", "you", "your",
}


#: How far a vector hit may be before it stops counting. Without this a k-NN
#: scan returns its nearest rows for ANY query, so a full k facts came back for
#: "why is the sky blue" - and put the owner's medication in that prompt.
_MAX_VEC_DISTANCE = float(os.environ.get("JARVIS_MEMORY_MAX_DISTANCE", "1.0"))


def _share_env(name: str, default: float) -> float:
    """A number from 0 to 1 out of the environment, never an exception.

    Not float(os.environ.get(...)) like the line above: that raises at
    import on "" or "half", and an import error here is "memory layer failed
    to start". `$env:X = ""` in PowerShell sets the variable to empty, not
    unset, so empty is the realistic mistake. Anything unreadable is the
    default; anything outside 0..1 is clamped to it.
    """
    raw = os.environ.get(name, "")
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(v):
        return default
    return min(1.0, max(0.0, v))


#: The floor for WORD search (finding F3 of the 2026-09-24 memory research).
#:
#: The distance floor above only ever applied to the meaning (vector) list.
#: Every word-search hit was fused in with no cut-off at all, so a question
#: that shared ONE ordinary word with a fact got that fact: "what is my dog
#: called?" came back with "Owner's cat is called Biscuit", on nothing but
#: "called". On day one - before fastembed has downloaded - words are the
#: only list there is, so this was the whole of recall.
#:
#: The rule: a fact must match at least this SHARE of the question's content
#: words, each word weighted by how rare it is in the store (the same idf
#: weighting bm25 uses). A rare word the question asks about ("dog") that no
#: fact contains carries most of the weight, so a fact that matches only the
#: common word next to it ("called") falls below the line. A fact matching
#: the one specific word ("Where do I live?" -> "Owner lives in Leeds") keeps
#: its full share. 0 turns the floor off (the old behaviour); 1 would demand
#: every word. The default was chosen by backend/eval_memory.py on half of
#: the golden questions and reported on the other half - backend/README.md,
#: "The memory self-test", has the table. Set JARVIS_MEMORY_MIN_WORD_SHARE to
#: change it.
_MIN_WORD_SHARE = _share_env("JARVIS_MEMORY_MIN_WORD_SHARE", 0.1)

#: Words that frame a question rather than say what it is about. They still
#: search (FTS ranks with them, exactly as before); they only do not count
#: towards the floor's share. Without this, "Where did I live BEFORE?" asked
#: the floor to find "before" in the fact about Harrogate, and "What is my
#: dog CALLED?" let the cat fact through on "called" alone. Time words are
#: here because jarvis_past.py reads them as dates; they are never in a fact
#: about the thing asked.
_FRAME = {
    "name", "names", "named", "called", "call", "kind", "sort", "type", "about",
    "ever", "now", "still", "currently", "usually", "often", "always",
    "much", "many", "long", "time", "times", "again", "also", "really",
    "actually", "exactly", "please", "jarvis", "remember", "tell", "told",
    "say", "said", "know", "knew", "think", "thought", "believe", "believed",
    "before", "previously", "formerly", "earlier", "ago", "back", "last",
    "year", "years", "month", "months", "week", "weeks", "use", "used",
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
}


def _floor_terms(terms) -> list:
    """The question's words that the floor weighs: not frame words, not a
    bare year."""
    return [t for t in terms
            if t not in _FRAME and not re.fullmatch(r"(?:19|20)\d\d", t)]


def _words(text: str) -> set:
    """Content words, lowercased, possessives folded. For overlap tests.

    VERBATIM from memory-safety.patch, and the two details that look cosmetic
    are the whole point. Folding "'?s$" and dropping single characters is what
    stops "Mario's" splitting into {"mario", "s"} - because a bare "s" is then
    a free overlap token shared by every fact containing an apostrophe, and
    find_one's "at least two overlapping words" bar is cleared by one real
    word plus "s".

    Measured with the naive split: find_one("Mario's allergy") returned
    "Mario's editor is Vim" - the exact pair memory-safety.patch was written
    about, reproduced by a reconstruction that had dropped two lines.
    """
    out = set()
    for w in re.findall(r"[\w\-]+", str(text).lower()):
        w = re.sub(r"'?s$", "", w) or w
        if len(w) > 1 and w not in _STOP:
            out.add(w)
    return out


def _fts_terms(text: str) -> set:
    """Content words for the FTS5 MATCH query. NOT possessive-folded.

    Separate from `_words` above, and the difference is a real bug that was
    shipped. `facts_fts` is `tokenize='porter unicode61'`, so the index
    already holds Porter stems, and Porter deliberately keeps a double `s`
    ("class" stems to "class", "address" to "address"). `_words` strips one
    trailing `s` from everything - which turns "address" into "addres", a
    string Porter then stems to something the index does not contain. The
    result:

        search("email address")  ->  ['My email address is bob@exam...']
        search("address")        ->  []

    Every word ending in `ss` was unfindable on its own: class, pass,
    address, business, access, press, boss, glass. And `search` swallows
    `sqlite3.OperationalError`, so it would have stayed silent even if it
    had raised.

    Feeding the RAW token and letting Porter do the stemming is both the fix
    and the simpler rule: one stemmer, on both sides of the index. `_words`
    keeps its folding because it is used for the OVERLAP test in
    `find_one`, where both sides are folded the same way and the folding is
    what stops "Mario's" contributing a bare "s".
    """
    out = set()
    for w in re.findall(r"[\w\-]+", str(text).lower()):
        if len(w) > 1 and w not in _STOP:
            out.add(w)
    return out


def _content_words(text: str) -> list[str]:
    return sorted(_words(text))


# --------------------------------------------------------------------------
#   Embedders
# --------------------------------------------------------------------------

class Embedder:
    """The base every embedder subclasses, and the shape the store relies on.

    Four things, and the store touches nothing else:

        name       str   identifies the MODEL. Written into the meta table; a
                         change to it is what triggers the facts_vec rebuild,
                         so two different models must never share one.
        dim        int   how many floats embed() returns per text. facts_vec is
                         declared float[dim] at creation and sqlite-vec raises
                         on a mismatch.
        semantic   bool  whether these vectors mean anything. False for the
                         hash fallback, and search() checks it before
                         consulting vectors at all.
        embed(ts)  ->    one vector per text, in order. A LIST in, a list of
                         lists out - never a single text.

    It exists as a real class rather than as a convention because the suites
    subclass it: `class Broken(M.Embedder)` in test_memory_safety.py and
    `class Bad(M.Embedder)` in test_embedding_guard.py are how a store gets an
    embedder that returns NaN, or the wrong width, or raises. Without the base
    class those files fail at import with AttributeError and none of their
    assertions run - which is exactly what happened.

    The defaults below are deliberately useless: a subclass that forgets to
    set `dim` should be obviously wrong, not quietly one-dimensional.
    """

    name = "base"
    dim = 0
    semantic = False

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class HashEmbedder(Embedder):
    """A deterministic non-semantic embedder. The fallback, not the plan.

    INFERRED. The original's fallback did not survive, but the module docstring
    that did says "DEGRADES, NEVER FAILS: if the embedding model is not
    installed or cannot download, search falls back to words alone". So there
    has to be something here that never raises.

    `semantic = False` is the important field: search() checks it before
    consulting vectors at all, so this contributes nothing to ranking and
    cannot pollute it with hash noise dressed up as meaning. status() reports
    it, so "why are my results worse" has an answer on the screen.
    """

    name = "hash-v1"
    dim = 64
    semantic = False

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * self.dim
            for w in _content_words(t):
                # zlib.crc32, not hash(). Python's hash() is seed-randomised
                # PER PROCESS, so "deterministic" was false across restarts:
                # the same text embedded to different vectors each run, and
                # because the embedder NAME stayed "hash-v1" the meta-table
                # rebuild never fired - facts_vec quietly accumulated vectors
                # from many different seeds, all marked embedded=1.
                v[zlib.crc32(w.encode()) % self.dim] += 1.0
            n = math.sqrt(sum(x * x for x in v))
            out.append([x / n for x in v] if n else v)
        return out


class FastEmbedder(Embedder):
    """The real one, if fastembed is installed.

    THE GUARD IS THE POINT. embedding-guard.patch found that this class had no
    finite/zero check at all, so a model that returned NaN - which they do, on
    an empty string or a pathological input - wrote a row nothing could ever
    find again. Checked here, at the only place vectors are produced.
    """

    semantic = True

    def __init__(self, model: str = "BAAI/bge-small-en-v1.5") -> None:
        from fastembed import TextEmbedding  # imported lazily and on purpose
        self._m = TextEmbedding(model_name=model)
        self.name = model
        self.dim = len(next(iter(self._m.embed(["probe"]))))

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for v in self._m.embed(list(texts)):
            vec = [float(x) for x in v]
            # Zero rather than NaN. The caller (_embed_rows) drops non-finite
            # vectors; returning the wrong LENGTH here would corrupt the vec0
            # table instead, which is worse.
            out.append(vec if _usable_vector(vec, self.dim) else [0.0] * self.dim)
        return out


def _make_embedder():
    """The best available, never an exception."""
    if os.environ.get("JARVIS_NO_EMBED"):
        return HashEmbedder()
    try:
        return FastEmbedder()
    except Exception:
        return HashEmbedder()


# --------------------------------------------------------------------------
#   The re-ranker (memory idea 1, docs/MEMORY-RESEARCH-2026-09-26.md)
# --------------------------------------------------------------------------
#
# Search makes three lists - words, meaning, people - and merges them by
# rank (RRF, in search()). A re-ranker reads the question and each
# candidate fact TOGETHER and scores how well the fact answers it, which a
# rank formula cannot do. Chat recall (jarvis_past.recall) asks for it: the
# top RERANK_POOL facts search found are re-ordered, and the first k go to
# the model as before. It never adds a fact, never drops one that would
# have been in the pool, never changes k or either floor, and never touches
# find_one(), corrections or anything that writes.
#
# The model is fastembed's cross-encoder `Xenova/ms-marco-MiniLM-L-6-v2`
# (Apache-2.0, about 80 MB, English only - like the meaning model), the
# default of Hindsight (MIT). Jarvis already uses fastembed for meaning
# search. It runs on the processor, on this PC; fastembed downloads it once,
# the way it downloads the meaning model.
#
# FAILS SOFT, NEVER BLOCKS A CHAT. The model is loaded on a background
# thread the first time recall asks - never on the chat's own thread - and
# until it is ready, recall is exactly what it was. If it cannot load (no
# fastembed, a fastembed too old to have re-rankers, no download), recall
# stays as it was for good, and that is said ONCE (the audit log and the
# backend's window, and status()). A re-rank that takes longer than
# RERANK_BUDGET_S seconds is not waited for: that question gets the merged
# order. JARVIS_MEMORY_RERANK=0 turns it off.

RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"


def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(os.environ.get(name) or default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float, lo: float, hi: float) -> float:
    try:
        v = float(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v)) if math.isfinite(v) else default


#: How many of search's facts the re-ranker re-orders ("the top ~20").
RERANK_POOL = _env_int("JARVIS_MEMORY_RERANK_POOL", 20, 1, 100)
#: The longest a question waits for the re-ranker, in seconds.
RERANK_BUDGET_S = _env_float("JARVIS_MEMORY_RERANK_BUDGET", 1.5, 0.05, 10.0)
_RERANK_ON = os.environ.get("JARVIS_MEMORY_RERANK", "1").strip().lower() not in (
    "0", "off", "false", "no")


class Reranker:
    """The shape the store relies on: `name`, and score(query, texts) - one
    number per text, in order, higher = answers the question better."""

    name = "base"

    def score(self, query: str, texts: list) -> list:
        raise NotImplementedError


class FastReranker(Reranker):
    """fastembed's cross-encoder. Imported lazily and on purpose."""

    def __init__(self, model: str = RERANK_MODEL) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        self._m = TextCrossEncoder(model_name=model)
        self.name = model
        list(self._m.rerank("probe", ["probe"]))      # load it now, not on a question

    def score(self, query: str, texts: list) -> list:
        return [float(x) for x in self._m.rerank(query, list(texts))]


_rr_lock = threading.Lock()
_rr_busy = threading.Lock()
_rr: dict = {"state": "not started", "model": None, "why": "", "said": False,
             "slow": 0, "used": 0}


def _rr_say_once(why: str) -> None:
    """Said once per process: in the audit log and the backend's window.
    Recall carries on as it was."""
    if _rr["said"]:
        return
    _rr["said"] = True
    try:
        if fw is not None:
            fw.audit_log("memory.rerank_off", {"why": why[:200]})
    except Exception:
        pass
    try:
        print(f"  memory     the re-ranker is off ({why}); recall works as before",
              file=sys.stderr)
    except Exception:
        pass


def _rr_load(factory) -> None:
    """Load it; only a load still wanted ("loading") changes the state, so a
    set_reranker() made meanwhile is never overwritten."""
    try:
        m = factory()
        with _rr_lock:
            if _rr["state"] == "loading":
                _rr.update(state="ready", model=m, why="")
    except Exception as exc:
        why = (f"{type(exc).__name__}: fastembed is not installed or has no re-ranker"
               if isinstance(exc, ImportError) else
               f"{type(exc).__name__}: the re-ranking model could not be loaded")
        with _rr_lock:
            if _rr["state"] != "loading":
                return
            _rr.update(state="off", model=None, why=why)
        _rr_say_once(why)


def reranker(*, wait: bool = False):
    """The loaded re-ranker, or None. The first call starts loading it on a
    background thread and returns None at once (`wait=True`, for the
    self-test, loads it on this thread instead)."""
    if not _RERANK_ON:
        return None
    with _rr_lock:
        st = _rr["state"]
        if st == "ready":
            return _rr["model"]
        if st != "not started":
            return None
        _rr["state"] = "loading"
    if wait:
        _rr_load(FastReranker)
        return _rr["model"]
    threading.Thread(target=_rr_load, args=(FastReranker,), daemon=True,
                     name="jarvis-memory-reranker").start()
    return None


def set_reranker(model) -> None:
    """Use this re-ranker (a Reranker, or None for none at all). For the
    self-test's stand-in and the tests; the backend never calls it."""
    with _rr_lock:
        if model is None:
            _rr.update(state="off", model=None, why="switched off here")
        else:
            _rr.update(state="ready", model=model, why="")


def reranker_status() -> dict:
    """{"state": "on" | "loading" | "off" | "not started", "model", "why",
    "used", "slow"} - for status(). Never the words of anything."""
    if not _RERANK_ON:
        return {"state": "off", "model": None, "why": "JARVIS_MEMORY_RERANK=0", "used": 0}
    with _rr_lock:
        st = _rr["state"]
        out = {"state": "on" if st == "ready" else st,
               "model": getattr(_rr["model"], "name", None), "why": _rr["why"],
               "used": _rr["used"]}
        if _rr["slow"]:
            out["slow"] = _rr["slow"]
        return out


def _rerank(query: str, facts: list) -> Optional[list]:
    """`facts` re-ordered by the re-ranker, best first - or None, meaning
    "keep the merged order": no re-ranker (yet), one still busy with an
    earlier question, a failure, or no answer within RERANK_BUDGET_S."""
    rr = reranker()
    if rr is None or len(facts) < 2:
        return None
    if not _rr_busy.acquire(blocking=False):
        return None
    box: dict = {}

    def work():
        try:
            box["scores"] = rr.score(query, [f["text"] for f in facts])
        except Exception as exc:
            box["error"] = exc
        finally:
            _rr_busy.release()
    t = threading.Thread(target=work, daemon=True, name="jarvis-memory-rerank")
    t.start()
    t.join(RERANK_BUDGET_S)
    if t.is_alive():
        with _rr_lock:
            _rr["slow"] += 1
        return None
    scores = box.get("scores")
    if not isinstance(scores, list) or len(scores) != len(facts) or not all(
            isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
            for x in scores):
        return None
    with _rr_lock:
        _rr["used"] += 1
    # Stable: equal scores keep the merged order.
    order = sorted(range(len(facts)), key=lambda i: (-scores[i], i))
    return [facts[i] for i in order]


# --------------------------------------------------------------------------
#   "True from" dates from the owner's words (memory idea 4)
# --------------------------------------------------------------------------
#
# A fact's valid_from - when it became TRUE - used to be the moment it was
# saved, always. But the owner's words often say when: "I moved to Leeds in
# January", told in March. true_from() reads that date, with fixed rules and
# no model, and add() stores it as valid_from. So "where did I live in
# February?" is answered from when things really changed, not from when
# Jarvis was told.
#
# THE RULES, ALL STRICT ON PURPOSE - a date that is not clearly "when this
# became true" is left alone, and the fact keeps the day it was saved, as
# before:
#   * the words must say something CHANGED or began, in the past: "moved",
#     "started", "joined", "switched", "got", "bought", "left", "since"...
#     A fact that only mentions a date ("visited Iceland in 2023",
#     "passport expires in January 2028") keeps the day it was saved;
#   * nothing may point at the future: "will", "going to", "next", "plan",
#     "is moving" ... - "I'm moving to Leeds in March" is a plan, true NOW
#     as a plan, and a true-from date in March would hide it until March;
#   * exactly ONE date: two ("married in 2019 and moved in 2021") is
#     ambiguous, so none;
#   * the date must already have begun. NEVER a future date: a fact "true
#     from" a day that has not come yet would be hidden until then;
#   * the date is the START of what was said: "in January" is 1 January,
#     "in 2025" is 1 January 2025, "(week of 2026-09-14)" is that Monday. A
#     month or year with no year is the most recent one that has begun
#     ("in January", said in March, is this January; "last June", said in
#     June, is last year's), like jarvis_past.when();
#   * the dates jarvis_intake adds in brackets ("yesterday (2026-09-25)",
#     "last month (2026-08)", "(around 2026-06-24)") are read as dates; its
#     "(as of 2023-05-01)" on an old imported fact is NOT a true-from date -
#     it is the day the words were said, and a bare month is read from it.
#   * English only, like the relation words of the entity layer. Anything
#     it cannot read is the old behaviour, never an error.

_MONTH_NUM = {m: i for i, m in enumerate(
    ("january february march april may june july august september october november "
     "december").split(), 1)}
_MONTH_NUM.update({m[:3]: i for m, i in list(_MONTH_NUM.items())})
_MONTH_NUM["sept"] = 9
_MONTH_WORD = r"(?:january|february|march|april|may|june|july|august|september|october" \
              r"|november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)"

#: Words that say something changed or began, in the past.
_BEGAN = re.compile(
    r"\b(?:moved|relocated|started|began|begun|joined|switched|changed|became|got|bought"
    r"|adopted|took\s+up|left|quit|retired|graduated|married|engaged|divorced|sold"
    r"|finished|hired|promoted|opened|launched|signed|enrolled|arrived|founded|since"
    r"|has\s+been|have\s+been|has\s+had|have\s+had|has\s+lived|has\s+worked)\b", re.I)
#: Anything that points at the future, or is only a wish or a maybe.
_NOT_YET = re.compile(
    r"\b(?:will|shall|going\s+to|gonna|plans?|planning|planned|next|soon|upcoming"
    r"|hopes?|hoping|wants?\s+to|wanted\s+to|would|might|could|intends?"
    r"|is\s+(?:moving|starting|joining|switching|leaving|getting|buying)"
    r"|are\s+(?:moving|starting|joining|switching|leaving|getting|buying))\b"
    r"|'ll\b|\btomorrow\b", re.I)
#: "may" the maybe, in lower case - "May" the month is capitalised.
_MAYBE = re.compile(r"\bmay\b(?!\s+\d)")
_AS_OF = re.compile(r"\(as of (\d{4})-(\d{2})-(\d{2})\)")

_DATE_FORMS = [
    # jarvis_intake's brackets, and plain ISO dates
    ("day", re.compile(r"\((?:(?:week|weekend) of |around )?(\d{4})-(\d{2})-(\d{2})\)")),
    ("month", re.compile(r"\((?:around )?(\d{4})-(\d{2})\)")),
    ("year", re.compile(r"\((\d{4})\)")),
    ("day", re.compile(r"(?<![\d(-])(\d{4})-(\d{2})-(\d{2})(?![\d-])")),
    # "14 March 2026", "14th of March 2026", "March 14, 2026"
    ("dmy", re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH_WORD})\s+"
                       r"((?:19|20)\d\d)\b", re.I)),
    ("mdy", re.compile(rf"\b({_MONTH_WORD})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+"
                       r"((?:19|20)\d\d)\b", re.I)),
    # "March 2026"
    ("my", re.compile(rf"\b({_MONTH_WORD})\s+((?:19|20)\d\d)\b", re.I)),
    # "in / since / from / last / back in March" - no year
    ("m", re.compile(rf"\b(in|since|from|during|last|back\s+in)\s+({_MONTH_WORD})\b(?!\s+\d)",
                     re.I)),
    # "in / since 2025"
    ("y", re.compile(r"\b(?:in|since|from|during)\s+((?:19|20)\d\d)\b(?![-/]\d)", re.I)),
]


def _midnight(y: int, m: int, d: int = 1) -> Optional[float]:
    try:
        return time.mktime((y, m, d, 0, 0, 0, 0, 0, -1))
    except (OverflowError, ValueError):
        return None


#: meta["true_from"] on a fact whose valid_from came from its words.
TRUE_FROM_SAID = "said"


def said_from(meta) -> bool:
    """Did this fact's valid_from come from its own words (true_from)?
    `meta` is the row's meta, as stored (JSON text) or a dict."""
    if isinstance(meta, str):
        try:
            meta = json.loads(meta or "{}")
        except Exception:
            return False
    return isinstance(meta, dict) and meta.get("true_from") == TRUE_FROM_SAID


def true_from(text: str, now: Optional[float] = None) -> Optional[float]:
    """When the fact's own words say it became true, as epoch seconds (the
    start of that day, month or year, this PC's time zone) - or None: no
    clear date, a date in the future, or a plan. See the rules above."""
    if not isinstance(text, str) or not text.strip():
        return None
    now = time.time() if now is None else float(now)
    ref = now
    m = _AS_OF.search(text)
    if m:
        ref = _midnight(int(m.group(1)), int(m.group(2)), int(m.group(3))) or now
        ref = min(ref + 86399, now)
    body = _AS_OF.sub(" ", text)
    if not _BEGAN.search(body) or _NOT_YET.search(body) or _MAYBE.search(body):
        return None
    found = []
    taken = []
    for kind, rx in _DATE_FORMS:
        for mm in rx.finditer(body):
            if any(a < mm.end() and mm.start() < b for a, b in taken):
                continue            # inside a date already read
            taken.append((mm.start(), mm.end()))
            g = mm.groups()
            lt = time.localtime(ref)
            when = None
            if kind == "day":
                when = _midnight(int(g[0]), int(g[1]), int(g[2]))
            elif kind == "month":
                when = _midnight(int(g[0]), int(g[1]))
            elif kind == "year":
                when = _midnight(int(g[0]), 1)
            elif kind == "dmy":
                when = _midnight(int(g[2]), _MONTH_NUM[g[1].lower()], int(g[0]))
            elif kind == "mdy":
                when = _midnight(int(g[2]), _MONTH_NUM[g[0].lower()], int(g[1]))
            elif kind == "my":
                when = _midnight(int(g[1]), _MONTH_NUM[g[0].lower()])
            elif kind == "m":
                n = _MONTH_NUM[g[1].lower()]
                if g[0].lower() == "last":
                    y = lt.tm_year if n < lt.tm_mon else lt.tm_year - 1
                else:
                    y = lt.tm_year if n <= lt.tm_mon else lt.tm_year - 1
                when = _midnight(y, n)
            elif kind == "y":
                when = _midnight(int(g[0]), 1)
            if when is None:
                return None
            found.append(when)
    if len(set(found)) != 1:
        return None
    when = found[0]
    # Never a date that has not begun, and never before 1900.
    if when > now or when < -2208988800:
        return None
    return when


# --------------------------------------------------------------------------
#   The store
# --------------------------------------------------------------------------

class MemoryStore:

    #: Did the last add(supersedes=...) actually retire what it was aiming at?
    #: A CLASS default, because add() only assigns it when a supersede is
    #: attempted - so anything reading it on a fresh store (the memory pane
    #: rendering a correction card) got AttributeError instead of "no".
    last_supersede_failed = False
    #: Did the last add(supersedes=...) find the correction was OLDER news
    #: than the fact it named, and so keep that fact (memory idea 4)?
    last_older_news = False

    def __init__(self, path: Optional[Path] = None, embedder=None) -> None:
        self.path = Path(path or DOCS_DB)
        self.embedder = embedder or _make_embedder()
        self._vec_ok = False
        # The entity layer's "is this a likely typo of a name we have?"
        # index: {entity id: (fuzzy form, 3-letter chunks)}. Built on first
        # use; only ever a hint for a card, so a copy that another process
        # has moved on from costs at most one card not raised.
        self._fuzzy_index: Optional[dict] = None
        self._entity_errors = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    # ---- plumbing ---------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        # isolation_level=None - AUTOCOMMIT, and this is not a preference.
        #
        # jarvis_extract owns the review queue but not its own database: it
        # writes through this store's connection, `with closing(store._connect())
        # as c`, and never calls commit(). Under the sqlite3 default that opens
        # an implicit transaction and close() discards it, so propose() returned
        # the rows it had just inserted while pending() found an empty queue -
        # the extraction queue silently did nothing, for every proposal, for
        # ever. Measured: `proposed [{...}], pending []`.
        #
        # The store's own writes do call commit(); under autocommit those are
        # harmless no-ops. Making the caller commit instead would mean editing
        # a module that is not in this repository, on the owner's machine, to
        # match a rebuild - which is backwards.
        c = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        c.row_factory = sqlite3.Row
        # WAL so a read during a write does not raise "database is locked" -
        # the HUD reads this on the request thread while the extractor writes
        # on another.
        try:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.Error:
            pass
        # EVERY connection, not just the one that built the table.
        #
        # A sqlite3 extension is loaded per CONNECTION, not per database file.
        # An earlier version of this method loaded sqlite-vec once during
        # _init() and nowhere else, so `CREATE VIRTUAL TABLE ... USING vec0`
        # succeeded, the table existed on disk, _vec_ok said True - and every
        # subsequent connection raised "no such module: vec0" on touching it.
        # Because _embed_rows and search() both wrap their vector work in
        # `except: continue`, that failed SILENTLY: facts were stored, never
        # embedded, never found by meaning, and status() reported
        # "vector_search": true the whole time.
        #
        # A capability that reports itself available and does nothing is the
        # exact failure JARVIS-FRAMEWORK.md calls out ("that's how you end up
        # trusting a control that doesn't do anything"). Caught by a test
        # asserting unembedded == 0, not by reading the code.
        self._load_vec(c)
        return c

    @staticmethod
    def _load_vec(c: sqlite3.Connection) -> bool:
        try:
            import sqlite_vec  # type: ignore
            c.enable_load_extension(True)
            sqlite_vec.load(c)
            c.enable_load_extension(False)
            return True
        except Exception:
            return False

    def _try_vec(self, c: sqlite3.Connection) -> bool:
        """Does vector search actually WORK on this connection?

        Not "is sqlite_vec importable" - that was the old test and it was true
        on a machine where nothing worked. This creates a throwaway vec0 table
        and writes one row to it. Only a probe that exercises the thing can
        answer whether the thing is available.
        """
        if not self._load_vec(c):
            return False
        try:
            c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp._vec_probe "
                      "USING vec0(id INTEGER PRIMARY KEY, embedding float[2])")
            c.execute("INSERT OR REPLACE INTO temp._vec_probe (id, embedding) "
                      "VALUES (1, ?)", (_pack([0.0, 1.0]),))
            c.execute("DROP TABLE temp._vec_probe")
            # Belt and braces. _connect() is autocommit now, so this INSERT
            # opens no transaction and this commit() is a no-op. It is kept
            # because of what happened when it was not: under the sqlite3
            # default the INSERT opened an implicit deferred transaction, the
            # rest of _init() ran inside it, and "INSERT OR REPLACE INTO meta"
            # became a read->write upgrade - which SQLite refuses with
            # SQLITE_BUSY WITHOUT invoking the busy handler, so the 30-second
            # timeout was skipped and __init__ raised "database is locked"
            # instantly. Measured: 5 of 6 concurrent processes failed to
            # construct a store, reported by jarvis_hud as "memory layer failed
            # to start". If the isolation level is ever changed back, this line
            # is what stops that returning.
            c.commit()
            return True
        except Exception:
            try:
                c.rollback()
            except Exception:
                pass
            return False

    def _init(self) -> None:
        with _LOCK, closing(self._connect()) as c:
            self._vec_ok = self._try_vec(c)
            c.execute("""
                CREATE TABLE IF NOT EXISTS facts (
                    id         INTEGER PRIMARY KEY,
                    text       TEXT NOT NULL,
                    source     TEXT,
                    created    REAL NOT NULL,
                    valid_from REAL NOT NULL,
                    valid_to   REAL,            -- NULL = still true
                    retired_at REAL,            -- when WE stopped believing it
                    retired_by INTEGER,         -- the fact that replaced this one
                    embedded   INTEGER NOT NULL DEFAULT 0,
                    meta       TEXT
                )""")
            # Stores written before retired_at existed. ALTER TABLE ADD COLUMN
            # is the one schema change SQLite does cheaply and without
            # rewriting the file, and it cannot be made conditional in SQL, so
            # the column list is read first. Doing it inside a try/except
            # instead would swallow a real failure as "already there".
            have = {r["name"] for r in c.execute("PRAGMA table_info(facts)")}
            if "retired_at" not in have:
                try:
                    c.execute("ALTER TABLE facts ADD COLUMN retired_at REAL")
                except sqlite3.OperationalError as e:
                    # NOTHING HOLDS A LOCK between the PRAGMA above and this
                    # ALTER, so two processes opening the same pre-retired_at
                    # store can both read "no retired_at" and both try to add
                    # it. The loser gets "duplicate column name", which
                    # escapes _init() -> __init__ -> store() and surfaces as
                    # "memory layer failed to start". Measured with eight
                    # processes released at the same instant: a failure in 2
                    # trials of 8, only on the ONE run that migrates an old
                    # database - which is the owner's upgrade path.
                    #
                    # Narrow: only this error, and only here. Anything else
                    # from an ALTER is a real problem and still raises. This
                    # is the one case where "already there" is the truth
                    # rather than a swallowed failure, because the PRAGMA
                    # said otherwise a moment ago.
                    if "duplicate column name" not in str(e).lower():
                        raise
                # The best available guess for rows retired before the column
                # existed, and it is only a guess: back then the two axes were
                # the same number, so every historical retirement reads as
                # "we learned the moment it stopped being true". That is often
                # false and there is no way to recover the truth. New
                # retirements record both separately.
                c.execute("UPDATE facts SET retired_at=valid_to "
                          "WHERE valid_to IS NOT NULL AND retired_at IS NULL")
            if "erased_at" not in have:
                # "Erase the words" (erase() below): when a fact's words were
                # wiped. NULL for every fact that still has them. Added the
                # same way, and with the same race handled the same way, as
                # retired_at above.
                try:
                    c.execute("ALTER TABLE facts ADD COLUMN erased_at REAL")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise
            c.execute("CREATE INDEX IF NOT EXISTS ix_facts_valid ON facts(valid_to, valid_from)")
            c.execute("CREATE INDEX IF NOT EXISTS ix_facts_known ON facts(created, retired_at)")
            c.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
                    text, content='facts', content_rowid='id', tokenize='porter unicode61')""")
            c.execute("""
                CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
                  INSERT INTO facts_fts(rowid, text) VALUES (new.id, new.text);
                END;""")
            c.execute("""
                CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
                  INSERT INTO facts_fts(facts_fts, rowid, text) VALUES('delete', old.id, old.text);
                END;""")
            c.execute("""
                CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE OF text ON facts BEGIN
                  INSERT INTO facts_fts(facts_fts, rowid, text) VALUES('delete', old.id, old.text);
                  INSERT INTO facts_fts(rowid, text) VALUES (new.id, new.text);
                END;""")
            if self._vec_ok:
                c.execute(f"""
                    CREATE VIRTUAL TABLE IF NOT EXISTS facts_vec USING vec0(
                        fact_id INTEGER PRIMARY KEY,
                        embedding float[{self.embedder.dim}])""")
            c.execute("""
                CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)""")
            # "Always keep in mind" (the owner's decision, 2026-09-24): the
            # facts the owner pinned, BY ID ONLY. The words stay in `facts`,
            # word for word - nothing here holds, summarises or rewrites
            # them - and profile() joins back to the facts that are still
            # current, so a pinned fact that is forgotten, corrected, runs
            # out or is erased simply stops being read. See pin().
            c.execute("""
                CREATE TABLE IF NOT EXISTS profile (
                    fact_id INTEGER PRIMARY KEY,
                    added   REAL NOT NULL,
                    how     TEXT NOT NULL DEFAULT 'tap')""")
            # "Who is my sister?" - the entity layer (memory wave 3,
            # 2026-09-25; the section "The entity layer" below). Three plain
            # tables, the research sketch's own, plus the bookkeeping for
            # the "are these the same?" cards. They never touch the three
            # tables welded to one fact id. Links are made from SAVED facts
            # only, and a link can only ADD a fact to what recall considers
            # - nothing here retires, edits or hides a fact.
            c.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id          INTEGER PRIMARY KEY,
                    name        TEXT NOT NULL,
                    kind        TEXT,
                    created     REAL NOT NULL,
                    merged_into INTEGER)""")      # a merge is a pointer, never a delete
            c.execute("""
                CREATE TABLE IF NOT EXISTS entity_aliases (
                    alias     TEXT NOT NULL,
                    entity_id INTEGER NOT NULL,
                    fact_id   INTEGER,               -- the fact that taught it; NULL = the name itself
                    PRIMARY KEY (alias, entity_id))""")
            c.execute("""
                CREATE TABLE IF NOT EXISTS fact_entities (
                    fact_id   INTEGER NOT NULL,
                    entity_id INTEGER NOT NULL,
                    PRIMARY KEY (fact_id, entity_id))""")
            # "Said again" (memory idea 3, 2026-09-26): each time the owner
            # says something Jarvis already knows, one row - the fact's ID,
            # when this PC saw the owner's turn arrive, and whether it was
            # typed or said aloud. NO WORDS, and nothing a guess can be
            # checked against: see said_again().
            c.execute("""
                CREATE TABLE IF NOT EXISTS fact_repeats (
                    fact_id INTEGER NOT NULL,
                    said_at REAL NOT NULL,
                    how     TEXT NOT NULL,
                    PRIMARY KEY (fact_id, said_at))""")
            c.execute("CREATE INDEX IF NOT EXISTS ix_fe_entity ON fact_entities(entity_id)")
            c.execute("CREATE INDEX IF NOT EXISTS ix_ea_fact ON entity_aliases(fact_id)")
            c.execute("""
                CREATE TABLE IF NOT EXISTS entity_merge_asks (
                    a           INTEGER NOT NULL,    -- the older entity (kept)
                    b           INTEGER NOT NULL,    -- the newer one
                    proposal_id INTEGER,             -- the card, once raised
                    state       TEXT NOT NULL DEFAULT 'waiting',
                    created     REAL NOT NULL,
                    PRIMARY KEY (a, b))""")
            if not c.execute("SELECT 1 FROM meta WHERE k='entities'").fetchone():
                # A store written before the entity layer: link the facts it
                # already has, once. The same rules as a new fact.
                self._backfill_entities(c)
                c.execute("INSERT OR REPLACE INTO meta VALUES ('entities', ?)",
                          (ENTITY_LAYER_VERSION,))
            row = c.execute("SELECT v FROM meta WHERE k='embedder'").fetchone()
            if row and row["v"] != self.embedder.name:
                # A different model: the vectors are not comparable. Rebuild.
                #
                # DROP, not DELETE. `CREATE VIRTUAL TABLE IF NOT EXISTS` above
                # has already run, so a DELETE leaves the table DECLARED AT THE
                # OLD WIDTH - and every later insert of a differently-sized
                # vector fails silently inside _embed_rows. Measured with a
                # 256-dim stand-in replaced by a 384-dim model: unembedded only
                # ever climbed, backfill returned 0 for ever, and
                # "vector_search": true throughout.
                if self._vec_ok:
                    c.execute("DROP TABLE IF EXISTS facts_vec")
                    c.execute(f"""
                        CREATE VIRTUAL TABLE IF NOT EXISTS facts_vec USING vec0(
                            fact_id INTEGER PRIMARY KEY,
                            embedding float[{self.embedder.dim}])""")
                c.execute("UPDATE facts SET embedded=0")
            c.execute("INSERT OR REPLACE INTO meta VALUES ('embedder', ?)", (self.embedder.name,))
            c.commit()

    # ---- writing ----------------------------------------------------------

    def add(self, text: str, source: str = "", meta: Optional[dict] = None,
            valid_from: Optional[float] = None,
            supersedes: Optional[int] = None) -> int:
        """Store one fact. Returns its id.

        valid_from   when it became TRUE. Left out, it is the date the
                     fact's own words give (true_from(), memory idea 4:
                     "moved to Leeds in January" is true from 1 January),
                     marked meta["true_from"] = "said" - and otherwise now,
                     as it always was.
        supersedes   the id of the fact this one corrects. It is retired on
                     both axes: retired_at now (when Jarvis learned), and
                     valid_to the new fact's true-from date when the words
                     give one after the old fact began, else now. UNLESS the
                     correction is older news (Graphiti's rule): both facts'
                     dates come from the owner's words and this one's is
                     EARLIER - then the old fact stays in use, and this one
                     is kept as history, true until the old one began
                     (last_older_news says so).
        """
        text = " ".join(str(text).split())
        if not text:
            raise ValueError("refusing to store an empty fact")
        now = time.time()
        meta = dict(meta or {})
        said = None
        if valid_from is None:
            try:
                said = true_from(text, now)
            except Exception:
                said = None          # an unreadable date is the old behaviour
            if said is not None:
                meta["true_from"] = TRUE_FROM_SAID
        with _LOCK, closing(self._connect()) as c:
            old = None
            if supersedes:
                old = c.execute("SELECT valid_from, valid_to, meta FROM facts WHERE id=?",
                                (supersedes,)).fetchone()
            # Older news never replaces newer news: only when BOTH dates are
            # the owner's own words. A date that is only when Jarvis was told
            # says nothing about when the old fact became true.
            older_than = None
            if (old is not None and said is not None and said_from(old["meta"])
                    and (old["valid_to"] is None or old["valid_to"] > now)
                    and said < float(old["valid_from"])):
                older_than = float(old["valid_from"])
            if older_than is None:
                cur = c.execute(
                    "INSERT INTO facts (text, source, created, valid_from, meta)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (text, source, now, valid_from or said or now, json.dumps(meta)))
            else:
                # History from the start: true from its own date until the
                # newer fact began, and never in use - retired_at now, and
                # retired_by the fact that is newer, so timeline() shows the
                # two in order and erasing that fact erases this one too
                # (its earlier wordings, erase()).
                cur = c.execute(
                    "INSERT INTO facts (text, source, created, valid_from, valid_to,"
                    " retired_at, retired_by, meta) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (text, source, now, said, older_than, now, int(supersedes),
                     json.dumps(meta)))
            fid = cur.lastrowid
            self.last_older_news = older_than is not None
            if older_than is not None:
                self.last_supersede_failed = False
                try:
                    if fw is not None:
                        fw.audit_log("memory.older_news", {"new": fid, "kept": supersedes})
                except Exception:
                    pass
            elif supersedes:
                # Both axes. A correction arriving now means we learned now
                # (retired_at). The old fact stopped being true when the new
                # one's own words say it began - if they say, and it is after
                # the old one began - and otherwise now. Callers that know
                # the real date call retire() with it before adding.
                end = now
                if old is not None and said is not None and said > float(old["valid_from"]):
                    end = said
                # "Still in use" is valid_to NULL OR in the future - the rule
                # every reader uses. This matched `valid_to IS NULL` only, so
                # a fact that ends later (a lease to December) could never be
                # corrected (the bug fixed with memory idea 4, 2026-09-26).
                done = c.execute(
                    "UPDATE facts SET valid_to=?, retired_at=?, retired_by=?"
                    " WHERE id=? AND (valid_to IS NULL OR valid_to > ?)",
                    (end, now, fid, supersedes, now))
                if done.rowcount:
                    # The old wording is history now: its names and the
                    # "sister" it taught stop being looked up (the entity
                    # layer). The new wording links its own below.
                    self._unlink_safely(c, int(supersedes))
                if done.rowcount == 0:
                    # Already retired - and that is the DOCUMENTED workflow,
                    # not a failure. retire()'s own docstring tells a caller
                    # who knows the real date to "call retire() with it before
                    # adding", which sets valid_to and makes the UPDATE above
                    # match nothing. So "I moved in January, I am telling you
                    # in March" left retired_by NULL, broke the chain
                    # timeline() walks, and logged memory.supersede_missed on
                    # a correction that was filed exactly as instructed.
                    #
                    # Link it without touching either date: the valid_to the
                    # caller set is the one they meant, and retire() is still
                    # one-way. retired_by IS NULL so this cannot re-point a
                    # fact that some other version already superseded.
                    done = c.execute(
                        "UPDATE facts SET retired_by=?"
                        " WHERE id=? AND retired_by IS NULL", (fid, supersedes))
                if done.rowcount == 0:
                    # The caller believes it filed a correction that retired
                    # the old fact. It did not - the id does not exist, or was
                    # already retired - and add() returning the new id either
                    # way said nothing. retire() reports this; so does this.
                    self.last_supersede_failed = True
                    try:
                        if fw is not None:
                            fw.audit_log("memory.supersede_missed",
                                         {"new": fid, "wanted": supersedes})
                    except Exception:
                        pass
                else:
                    self.last_supersede_failed = False
            self._embed_rows(c, [(fid, text)])
            # The entity layer: who and what this SAVED fact names, found
            # without a model, in the same breath as the save. Never raises -
            # like _embed_rows, the fact is already stored by now. Not for
            # older news: it is history from the start, like a retired fact.
            if older_than is None:
                self._link_safely(c, fid, text)
            c.commit()
            try:
                waiting = c.execute("SELECT 1 FROM entity_merge_asks"
                                    " WHERE state='waiting' LIMIT 1").fetchone()
            except sqlite3.Error:
                waiting = None
        if waiting:
            self.raise_merge_cards()
        return fid

    #: The name jarvis_hud reaches for in one place. Same call, kept so a
    #: caller written against either name works.
    add_fact = add

    def retire(self, fact_id: int, replaced_by: Optional[int] = None,
               valid_to: Optional[float] = None) -> bool:
        """Stop recalling a fact. Never deletes it.

        retired_at is always now - that is when this machine learned. valid_to
        is when the fact stopped being TRUE, which defaults to now but is the
        parameter to pass when you know better: "I moved in January" told in
        March is retire(id, valid_to=<january>), and the row then says both
        things at once.

        A valid_to in the future is allowed and means exactly what it says -
        a lease that ends in December is not retired today - so nothing that
        reads these rows may treat "valid_to is not NULL" as "not current".
        """
        with _LOCK, closing(self._connect()) as c:
            now = time.time()
            vt = now if valid_to is None else float(valid_to)
            # retired_at only once the fact has actually STOPPED being
            # recalled. A valid_to in the future has not happened yet - the
            # docstring above says so, current_facts(), status() and search()
            # all agree, and known_at() did not: it reads retired_at, so a
            # lease recorded in October as ending in December vanished from
            # the memory pane's as-of view the moment it was entered, while
            # recall went on injecting it into prompts. Two screens, opposite
            # answers, no error anywhere. Nothing was retracted, so nothing is
            # stamped; when December arrives the fact leaves current_facts on
            # the valid-time axis, which is the axis that ended it.
            #
            # This diverges from bitemporal.patch, which stamps now
            # unconditionally. The patch predates retire() taking a date.
            ra = now if vt <= now else None
            # "Still in use" is valid_to NULL OR in the future, the rule
            # every reader uses. `valid_to IS NULL` alone meant a fact that
            # ends later (a lease to December) could never be forgotten, and
            # a "stop using this fact?" card on it did nothing (the bug fixed
            # with memory idea 4, 2026-09-26).
            cur = c.execute("UPDATE facts SET valid_to=?, retired_at=?, retired_by=?"
                            " WHERE id=? AND (valid_to IS NULL OR valid_to > ?)",
                            (vt, ra, replaced_by, fact_id, now))
            if cur.rowcount and ra is not None:
                # Forget (or a correction) takes the fact's links and the
                # aliases it taught with it: "sister" stops meaning Priya the
                # moment "My sister is called Priya" is forgotten. A lease
                # that ends later is still current, so it keeps them until
                # then - and every lookup checks the fact is current anyway.
                self._unlink_safely(c, int(fact_id))
            c.commit()
            # rowcount, not None. "Retired a fact that was already retired" and
            # "retired the fact" have to be distinguishable, or the caller
            # cannot tell a no-op from a change.
            return cur.rowcount > 0

    def edit(self, fact_id: int, text: str) -> bool:
        """Correct a fact's wording in place. Used by the memory pane.

        Re-embeds, because the trigger updates FTS but nothing updates the
        vector - leaving the old meaning indexed against the new words.
        """
        text = " ".join(str(text).split())
        if not text:
            return False
        with _LOCK, closing(self._connect()) as c:
            # A retired fact is history. bitemporal's whole premise is that a
            # superseded version stays readable as it was; rewriting one makes
            # "where did I live last year" answer with today's words.
            row = c.execute("SELECT valid_to FROM facts WHERE id=?", (fact_id,)).fetchone()
            # Still in use = valid_to NULL or in the future (a lease that ends
            # in December is still current, and can be reworded).
            if row is None or (row["valid_to"] is not None and row["valid_to"] <= time.time()):
                return False
            cur = c.execute("UPDATE facts SET text=?, embedded=0 WHERE id=?", (text, fact_id))
            if cur.rowcount:
                # DELETE THE OLD VECTOR FIRST. The FTS trigger has already
                # reindexed the new words, but if the new text fails to embed
                # - NaN, model down, width mismatch - _embed_rows skips its
                # INSERT OR REPLACE and the PREVIOUS text's vector stays in
                # facts_vec. Words and meaning then point at different facts:
                # measured, a row edited from "allergic to penicillin" to
                # "enjoys long walks" was still returned for "allergic to
                # penicillin" with zero word overlap.
                if self._vec_ok:
                    try:
                        c.execute("DELETE FROM facts_vec WHERE fact_id=?", (fact_id,))
                    except Exception:
                        pass
                self._embed_rows(c, [(int(fact_id), text)])
                # New words, new links: the old wording's names and aliases
                # go, and whatever the new wording names is linked instead
                # (first, so a name both wordings say keeps its entry).
                try:
                    self._unlink_fact(c, int(fact_id), new_text=text)
                except Exception:
                    self._entity_errors += 1
            c.commit()
            return cur.rowcount > 0

    def erase(self, fact_id: int, *, earlier: bool = True) -> Optional[dict]:
        """"Erase the words": wipe one fact's text for good. Keep its dates.

        The owner's decision of 2026-09-24 (CLAUDE.md). Forget (retire())
        hides a fact and keeps its words as history; this is the second
        action, for words that must really be gone. It is the one place in
        this store that destroys anything, so it destroys exactly one thing -
        the words - and keeps the row:

          * `text` becomes ERASED_TEXT, a fixed marker with no words in it.
          * `meta` keeps only ERASE_KEEPS_META - dates, ids, where it came
            from - and drops everything else, above all `message_hash` (a
            hash of the words, which a guess can be checked against) and
            `conversation_id` (which points at where the words were said).
          * the word-search row (facts_fts) and the meaning vector
            (facts_vec) for this id are deleted - they are the words too.
          * if the fact is still current, it is retired exactly as retire()
            stamps it (valid_to and retired_at = now); a fact already retired
            keeps the dates it has.
          * `erased_at` records when. id, created, valid_from, valid_to,
            retired_at, retired_by and source are left as they were, so the
            history, the supersede chain and "what did you know in June"
            still show that a fact was here - and never what it said.
          * every COPY of the words elsewhere in this file goes too: the
            review-queue rows that became this fact or named it as the fact
            they would replace, and any queue row holding exactly these
            words (a card still waiting with them is turned down - keeping
            it would keep the words). See _erase_copies().
          * then the file itself: word search is compacted ('optimize'),
            with secure_delete on, so the freed pages are zeroed rather than
            left holding the old text, and the write-ahead log (the -wal
            file) is checkpointed and truncated to nothing.

        Works on a current fact AND on one already forgotten (retired), so
        the owner can erase something forgotten earlier. Erasing an erased
        fact again changes nothing but re-runs the clean-up.

        THE EARLIER WORDINGS GO TOO (security audit L3, 2026-09-25). A fact
        that was reworded (/api/memory/edit) or corrected is a NEW row that
        supersedes the old one, and the old row keeps the old words as
        history ("Owner's bank PIN is 4821" under "... 4822"). Erasing only
        the newest row left the earlier words in memory.db - and the phone,
        which lists only current facts, could never reach them. So `earlier`
        (the default) erases, the same way, every row this fact replaced,
        and every row THOSE replaced: the whole chain of this fact's earlier
        wordings, found by `retired_by`. Never a LATER one - erasing an old
        wording does not erase the fact that replaced it, which may be what
        the owner still wants remembered.

        Returns None if there is no such fact, else
        {"id", "erased_at", "already_erased", "retired_now", "file_clean",
        "copies", "earlier"} - `earlier` the ids of the earlier wordings
        erased with it. Never the words.
        """
        fid = int(fact_id)
        if earlier:
            out = self.erase(fid, earlier=False)
            if out is None:
                return None
            chain = self._earlier_wordings(fid)
            for old in chain:
                done = self.erase(old, earlier=False)
                if done is not None and not done["file_clean"]:
                    out["file_clean"] = False
            out["earlier"] = chain
            return out
        with _LOCK, closing(self._connect()) as c:
            row = c.execute("SELECT * FROM facts WHERE id=?", (fid,)).fetchone()
            if row is None:
                return None
            row = dict(row)
            old_text = str(row.get("text") or "")
            already = row.get("erased_at") is not None
            now = time.time()
            # Before any write on this connection: freed space is zeroed.
            try:
                c.execute("PRAGMA secure_delete=ON")
            except sqlite3.Error:
                pass
            c.execute("BEGIN IMMEDIATE")
            try:
                vt, ra = row.get("valid_to"), row.get("retired_at")
                retired_now = False
                # The same rule every reader uses for "current": valid_to
                # NULL or still in the future. A lease that ends in December
                # is current today, and an erased fact must never be recalled
                # again, so it is retired now too (retire() uses the same rule
                # since 2026-09-26; it used to match valid_to IS NULL only).
                if vt is None or float(vt) > now:
                    vt, retired_now = now, True
                if ra is None and float(vt) <= now:
                    ra = now
                erased_at = row.get("erased_at") if already else now
                c.execute("UPDATE facts SET meta=?, valid_to=?, retired_at=?, erased_at=?,"
                          " embedded=0 WHERE id=?",
                          (json.dumps(_erased_meta(row.get("meta"))), vt, ra, erased_at, fid))
                if not already:
                    # The UPDATE OF text trigger takes the OLD words out of
                    # facts_fts and puts the marker in; the marker then comes
                    # out too, so an erased fact is found by no word at all.
                    # Only when the words are still there: run on a row that
                    # is already the marker, the trigger would ask FTS5 to
                    # delete an entry it no longer has, which corrupts it.
                    c.execute("UPDATE facts SET text=? WHERE id=?", (ERASED_TEXT, fid))
                    c.execute("INSERT INTO facts_fts(facts_fts, rowid, text)"
                              " VALUES('delete', ?, ?)", (fid, ERASED_TEXT))
                if self._vec_ok:
                    try:
                        c.execute("DELETE FROM facts_vec WHERE fact_id=?", (fid,))
                    except sqlite3.Error:
                        pass
                copies = _erase_copies(c, fid, old_text if not already else "", now)
                # The entity layer: this fact's links and the aliases it
                # taught go, and so does every name that no other fact still
                # says - with any "are these the same?" card that showed it.
                # Inside this transaction, on this secure_delete connection,
                # so the scrub below zeroes those bytes too. Not "safely":
                # an erase that could not take the names out must fail.
                copies += self._unlink_fact(c, fid, now=now)
                c.execute("COMMIT")
            except Exception:
                try:
                    c.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
            file_clean = _scrub_file(c)
        try:
            if fw is not None:
                fw.audit_log("memory.erased", {"id": fid})   # the id only, never the words
        except Exception:
            pass
        return {"id": fid, "erased_at": erased_at, "already_erased": already,
                "retired_now": retired_now, "file_clean": file_clean, "copies": copies,
                "earlier": []}

    def _earlier_wordings(self, fact_id: int) -> list:
        """The ids of every fact `fact_id` replaced, directly or through
        another: the rows whose `retired_by` leads, step by step, to it.
        Oldest last. A loop in the links (which add() cannot make, but a
        hand-edited file could) is walked once."""
        seen, chain, todo = {int(fact_id)}, [], [int(fact_id)]
        with _LOCK, closing(self._connect()) as c:
            while todo:
                cur = todo.pop(0)
                for (i,) in c.execute("SELECT id FROM facts WHERE retired_by=? ORDER BY id DESC",
                                      (cur,)).fetchall():
                    if i not in seen:
                        seen.add(i)
                        chain.append(i)
                        todo.append(i)
        return chain

    # Counted rather than logged: this module has no logger, and a print on a
    # background thread in a windowed app goes to a closed handle. status() is
    # where it becomes visible.
    _bad_vectors = 0

    def _embed_rows(self, c, rows: list[tuple[int, str]]) -> int:
        """Embed and index. Returns how many rows were actually written.

        A count, not None: backfill_embeddings loops until this stops making
        progress, and a version that returned nothing would either loop for
        ever or stop after one batch depending on how the caller guessed.

        AND IT NEVER RAISES. Restored from memory-safety.patch, whose copy of
        this docstring is the original's: "add_fact's INSERT has already
        committed by the time this runs (isolation_level=None), so an
        exception escaping here reported failure for a fact that was in fact
        stored - and each retry of the 'failed' accept wrote another copy of
        it." Measured with an embedder whose embed() returns None: add()
        raised TypeError, one row was in facts, the retry raised again, and
        two identical facts were stored.

        The shipped embedders cannot do that. A test double, a half-installed
        fastembed, or a future embedder can, and the caller cannot tell the
        difference - so the whole body is guarded, not only the parts that
        looked risky.
        """
        if not rows or not self._vec_ok:
            return 0
        try:
            vecs = list(self.embedder.embed([t for _, t in rows]))
        except Exception:
            return 0
        try:
            dim = int(self.embedder.dim)
        except Exception:
            # An embedder with no usable dim cannot be width-checked, so
            # nothing it produces may be stored.
            return 0
        done = 0
        for (fid, _), v in zip(rows, vecs):
            try:
                v = list(v)
            except TypeError:
                # An embedder that returned a scalar, or a flat list of floats
                # for one text (the single-vector API mistake). Outside the
                # try this raised out of add() and the fact was never stored -
                # "DEGRADES, NEVER FAILS" says it must be stored and merely
                # unembedded.
                continue
            if not _usable_vector(v, dim):
                # Leave embedded=0, exactly as a failed INSERT does. The row
                # stays findable by WORDS, and backfill will try it again when
                # a better model is installed. Storing it would make the fact
                # permanently unreachable and say nothing about it anywhere.
                self._bad_vectors += 1
                continue
            try:
                c.execute("INSERT OR REPLACE INTO facts_vec (fact_id, embedding) VALUES (?, ?)",
                          (fid, _pack(v)))
                c.execute("UPDATE facts SET embedded=1 WHERE id=?", (fid,))
                done += 1
            except Exception:
                continue
        return done

    def backfill_embeddings(self, batch: int = 64) -> int:
        """Embed anything that was stored while no model was available."""
        done = 0
        while True:
            with _LOCK, closing(self._connect()) as c:
                # Never an erased fact: its text is only the marker, and a
                # vector of "[erased]" would be a search hit for nothing.
                rows = c.execute("SELECT id, text FROM facts WHERE embedded=0"
                                 " AND erased_at IS NULL LIMIT ?",
                                 (batch,)).fetchall()
                if not rows:
                    break
                wrote = self._embed_rows(c, [(r["id"], r["text"]) for r in rows])
                c.commit()
                if not wrote:
                    # No vector table, no embedder, or every row was refused.
                    # The next SELECT would return these same rows, so
                    # continuing spins on them forever.
                    break
                done += wrote
        return done

    def import_legacy(self, path: Optional[Path] = None) -> int:
        """Pull facts out of an older store. Best-effort, never destructive."""
        src = Path(path) if path else (_config_dir() / "facts.json")
        if not src.is_file():
            return 0
        try:
            rows = json.loads(src.read_text(encoding="utf-8-sig"))
        except Exception:
            return 0
        if isinstance(rows, dict):
            rows = rows.get("facts") or []
        n = 0
        for r in rows:
            text = r.get("text") if isinstance(r, dict) else str(r)
            if not text:
                continue
            try:
                self.add(text, source=(r.get("source") if isinstance(r, dict) else "") or "legacy")
                n += 1
            except Exception:
                continue
        return n

    # ---- reading ----------------------------------------------------------

    def _word_floor(self, c, terms: list, rows: list, floor: float) -> list:
        """The word-search hits that match at least `floor` of the question.

        Each content word of the question is weighted by how rare it is in
        the store, ln(1 + (N + 1) / (df + 0.5)), and a hit's share is the
        weight of the words it contains over the weight of all of them.

        Not bm25's own idf, ln(1 + (N - df + 0.5) / (df + 0.5)), which was
        tried first: it gives a word that is in EVERY fact a weight of almost
        nothing, so in a small store where every fact mentions the laptop,
        "what did I say about my laptop" weighed "laptop" at 0.18 against
        1.79 for "about" and floored the right fact away. This one still
        ranks rare words above common ones, and never weighs a word at zero. Which words a hit contains is asked of FTS5 itself,
        one word at a time, so the Porter stemming is the index's own and
        "lives" still matches "live".

        Two small queries per content word (a question has one to six), and
        only over the hits already found. If anything here fails the hits
        come back unfiltered: this decides relevance, not safety, and the
        old behaviour is the right thing to degrade to.
        """
        terms = _floor_terms(terms)
        if floor <= 0 or not rows or not terms:
            # Nothing left to judge by ("what's my name?" is all frame):
            # the hits stand, as they always did.
            return rows
        try:
            n = c.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            ids = [row["rowid"] for row in rows]
            marks = ",".join("?" * len(ids))
            weight, has = {}, {}
            for t in terms:
                q = f'"{t}"'
                df = c.execute("SELECT COUNT(*) FROM facts_fts WHERE facts_fts MATCH ?",
                               (q,)).fetchone()[0]
                weight[t] = math.log(1.0 + (n + 1.0) / (df + 0.5))
                has[t] = {r[0] for r in c.execute(
                    "SELECT rowid FROM facts_fts WHERE facts_fts MATCH ?"
                    f" AND rowid IN ({marks})", (q, *ids))}
            total = sum(weight.values())
            if total <= 0:
                return rows
            return [row for row in rows
                    if sum(w for t, w in weight.items() if row["rowid"] in has[t]) / total
                    >= floor - 1e-9]
        except Exception:
            return rows

    def search(self, query: str, k: int = 8, candidates: int = 50,
               at: Optional[float] = None, include_retired: bool = False,
               known_at: Optional[float] = None,
               word_floor: Optional[float] = None,
               entities: bool = False, rerank: bool = False) -> list[dict]:
        """Words and meaning, fused with reciprocal rank fusion.

        at          VALID time: only facts true at that moment (default now).
        known_at    TRANSACTION time: only facts this machine BELIEVED at that
                    moment - the same condition known_at() uses, created <= t
                    and not yet retired at t. On its own it answers "what did
                    Jarvis think in June", right or wrong, so the valid-time
                    filter is then applied only when `at` is given as well.
        include_retired  skip the valid-time filter (timeline()).
        word_floor  the share of the question a word-search hit must match;
                    None is _MIN_WORD_SHARE, 0 turns it off (find_one does).
        entities    the entity layer (chat recall asks for it, through
                    jarvis_past.recall; nothing else does). The question's
                    words are looked up in the alias table - "my sister's"
                    finds Priya - the full names are added to the question
                    for word and meaning search, and the facts linked to
                    those people and things are a THIRD list in the fusion.
                    No model is asked. k and both floors are unchanged, and
                    a link can only add a candidate. JARVIS_MEMORY_ENTITIES=0
                    turns it off.
        rerank      the re-ranker (memory idea 1, above; chat recall asks for
                    it, through jarvis_past.recall): the first RERANK_POOL
                    facts that pass every filter are re-ordered by it before
                    the first k are kept. Without a loaded re-ranker, or on
                    any failure, the merged order - exactly as without it.
        """
        at_given = at is not None
        query = " ".join(str(query).split())
        if not query:
            return []
        if k <= 0:
            # The truncation below appends and THEN checks `len(out) >= k`, so
            # k=0 returned exactly one fact. That reads as an off-by-one and is
            # worse than one, because this is the function that decides what
            # private text goes into a prompt: someone setting the recall width
            # to zero to turn recall OFF still got a fact in every request.
            return []
        at = time.time() if at is None else at
        with _LOCK, closing(self._connect()) as c:
            ranks: dict[int, float] = {}
            roots: list = []
            if entities and _ENTITY_RECALL:
                try:
                    roots, names = self._entity_hits(c, query, at)
                except Exception:
                    roots, names = [], []
                # The rewrite: "where is my sister getting married?" is also
                # searched as "... Priya", so word and meaning search can
                # find "Priya's wedding is in Lisbon". Only names the
                # question does not already say.
                have = " " + _name_key(query) + " "
                extra = [n for n in names if f" {_name_key(n)} " not in have]
                if extra:
                    query = query + " " + " ".join(extra)
            # words. Content terms only, and RAW - see _fts_terms. An
            # OR-query over every word in the question matched most of the
            # store on "the" and "is", so a fact that shared nothing but
            # function words still got a rank.
            terms = sorted(_fts_terms(query))
            try:
                if not terms:
                    raise sqlite3.OperationalError("no content terms")
                q = " OR ".join(f'"{w}"' for w in terms)
                rows = c.execute(
                    "SELECT rowid, bm25(facts_fts) AS s FROM facts_fts WHERE facts_fts MATCH ?"
                    " ORDER BY s LIMIT ?", (q, candidates)).fetchall()
                # The floor (F3): a hit that matches too little of the
                # question does not get a rank at all. See _MIN_WORD_SHARE.
                rows = self._word_floor(
                    c, terms, rows, _MIN_WORD_SHARE if word_floor is None else word_floor)
                for r, row in enumerate(rows, 1):
                    ranks[row["rowid"]] = ranks.get(row["rowid"], 0) + 1.0 / (60 + r)
            except sqlite3.OperationalError:
                pass
            # meaning
            if self._vec_ok and self.embedder.semantic:
                try:
                    qv = self.embedder.embed([query])[0]
                    # A bad QUERY vector is worse than a bad stored one: it
                    # does not fail, it silently ranks the whole table by
                    # distance-from-nonsense, and those rows then outrank the
                    # keyword hits through RRF. Drop the vector vote and let
                    # FTS5 answer alone - the same thing that happens on a
                    # machine with no embedding model at all.
                    if _usable_vector(list(qv), self.embedder.dim):
                        rows = c.execute(
                            "SELECT fact_id, distance FROM facts_vec WHERE embedding MATCH ?"
                            " ORDER BY distance LIMIT ?", (_pack(qv), candidates)).fetchall()
                        for r, row in enumerate(rows, 1):
                            # Sorted by distance, so the first one that is too
                            # far ends it. Without this floor a k-NN scan
                            # returns its nearest rows for ANY query and a full
                            # k facts come back for "why is the sky blue".
                            if (row["distance"] is not None
                                    and row["distance"] > _MAX_VEC_DISTANCE):
                                break
                            ranks[row["fact_id"]] = ranks.get(row["fact_id"], 0) + 1.0 / (60 + r)
                except Exception:
                    pass
            # people and things: the facts linked to whoever the question
            # named, most names shared first, newest first. The same RRF
            # constant as the other two lists, so a linked fact that neither
            # words nor meaning found ranks like a word hit would.
            if roots:
                try:
                    linked = self._linked_facts(
                        c, roots, candidates, at=at,
                        include_retired=include_retired or (known_at is not None
                                                            and not at_given),
                        known_at=known_at)
                    for r, fid in enumerate(linked, 1):
                        ranks[fid] = ranks.get(fid, 0) + 1.0 / (60 + r)
                except Exception:
                    pass

            if not ranks:
                return []
            ids = sorted(ranks, key=lambda i: -ranks[i])
            marks = ",".join("?" * len(ids))
            rows = {r["id"]: dict(r) for r in c.execute(
                f"SELECT * FROM facts WHERE id IN ({marks})", ids)}

        out: list[dict] = []
        for fid in ids:
            f = rows.get(fid)
            if f is None:
                continue
            score = ranks[fid]
            if known_at is not None:
                # What this machine believed at known_at: the exact condition
                # known_at() uses, so the memory pane's as-of list and a
                # search as of the same moment cannot disagree.
                if f["created"] > known_at:
                    continue
                if f["retired_at"] is not None and f["retired_at"] <= known_at:
                    continue
            valid = f["valid_from"] <= at and (f["valid_to"] is None or f["valid_to"] > at)
            if (not valid and not include_retired
                    and (known_at is None or at_given)):
                continue
            f["score"] = round(score, 5)
            # Was `f["valid_to"] is None`, which disagreed with the validity
            # line above it for a valid_to in the FUTURE: the fact counted as
            # valid and was returned, then arrived flagged not-current.
            # Unreachable while retire() could only stamp now; reachable the
            # moment it takes a date. Same rule in both places.
            f["current"] = f["valid_to"] is None or f["valid_to"] > at
            out.append(f)
            if len(out) >= (max(k, RERANK_POOL) if rerank else k):
                break
        if rerank:
            ranked = _rerank(query, out)
            if ranked is not None:
                out = ranked
        return out[:k]

    # ---- "said again" (memory idea 3, 2026-09-26) -------------------------

    def said_again(self, fact_id: int, said_at: float, how: str = "typed") -> bool:
        """Record that the owner said this fact again. True if a row was
        written.

        `said_at` is when this PC saw the owner's turn arrive (the live-turn
        registry's time, jarvis_chat_log) - so the same turn, read again by
        the learner on its next pass over the conversation, is the same row
        and is not counted twice. `how` is "typed" or "voice"; the caller
        (jarvis_intake.note_said_again) has already checked the turn with
        the same rules automatic learning uses.

        Only for a fact that is still in use and whose words are not erased,
        only for a turn AFTER the fact was saved (a turn from before is the
        one it was learned from, not a repeat), and never a time in the
        future. The row holds no words: erasing the fact's words leaves it,
        like the fact's own dates. Nothing reads it to decide anything - it
        can never make a fact harder to forget, correct or erase."""
        if how not in ("typed", "voice"):
            return False
        try:
            t = float(said_at)
        except (TypeError, ValueError):
            return False
        now = time.time()
        if not math.isfinite(t) or t > now + 60:
            return False
        with _LOCK, closing(self._connect()) as c:
            row = c.execute("SELECT created, valid_to, erased_at FROM facts WHERE id=?",
                            (int(fact_id),)).fetchone()
            if row is None or row["erased_at"] is not None:
                return False
            if row["valid_to"] is not None and row["valid_to"] <= now:
                return False
            if t <= float(row["created"]):
                return False
            cur = c.execute("INSERT OR IGNORE INTO fact_repeats (fact_id, said_at, how)"
                            " VALUES (?, ?, ?)", (int(fact_id), t, how))
            c.commit()
            return cur.rowcount > 0

    def said_again_counts(self, ids) -> dict:
        """{fact id: {"count": times said again, "last": when, epoch
        seconds}} for those of `ids` said again at least once."""
        ids = [int(i) for i in ids or [] if isinstance(i, int) and not isinstance(i, bool)]
        if not ids:
            return {}
        out = {}
        with _LOCK, closing(self._connect()) as c:
            for i in range(0, len(ids), 500):
                part = ids[i:i + 500]
                for r in c.execute(
                        "SELECT fact_id, COUNT(*) AS n, MAX(said_at) AS last FROM fact_repeats"
                        f" WHERE fact_id IN ({','.join('?' * len(part))}) GROUP BY fact_id",
                        part):
                    out[int(r["fact_id"])] = {"count": int(r["n"]), "last": float(r["last"])}
        return out

    def get(self, fact_id: int) -> Optional[dict]:
        """One fact by id, retired or not. None if it is not there."""
        with _LOCK, closing(self._connect()) as c:
            row = c.execute("SELECT * FROM facts WHERE id=?", (int(fact_id),)).fetchone()
        return dict(row) if row else None

    def find_one(self, text: str, *, min_overlap: float = 0.5) -> Optional[dict]:
        """The one current fact a correction is about, or None.

        VERBATIM contract from memory-safety.patch, including the DICT return
        type - a first reconstruction returned an int, and the patched
        `jarvis_extract._accept` does `target["id"]`, so it raised TypeError
        on the one path that matters.

        search() is the wrong tool for this and using it cost data: it is a
        ranker, it returns its top-k whatever the query, and the top-1 for a
        string that matches nothing is an arbitrary fact - which then got
        retired. Accepting "Mario drives a 1998 Volvo" retired "Mario prefers
        tabs over spaces"; a replaces string reading "Mario's allergy" retired
        the note about Vim.

        Containment, not Jaccard: a correction names the old fact in fewer
        words than the fact itself, so the shorter side is the denominator.
        Two content words minimum, whatever the ratio - "where Mario is"
        reduces to the single word "mario", which is in half the store, and
        one common word is not an identification. When it is ambiguous the
        answer is None: two facts that disagree can be sorted out later, a
        fact retired in error cannot be got back.
        """
        want = _words(text)
        if not want:
            return None
        best, best_score = None, 0.0
        # word_floor=0: this has its own, stricter rule below (two shared
        # words and 50% containment), and a correction names facts in its
        # own words - "Mario drives a 2005 Honda" shares only two of four
        # with the fact it replaces, and the recall floor would hide it.
        for cand in self.search(text, k=5, word_floor=0.0):
            have = _words(cand["text"])
            shared = want & have
            if len(shared) < 2:
                continue
            score = len(shared) / min(len(want), len(have))
            if score > best_score:
                best, best_score = cand, score
        return best if best_score >= min_overlap else None

    def timeline(self, query: str, k: int = 20) -> list[dict]:
        """Every version of the matching facts, retired ones included, oldest
        first - the 'where did I live last year' view."""
        hits = self.search(query, k=k, include_retired=True)
        if not hits:
            return []
        ids = [h["id"] for h in hits]
        seen = set(ids)
        with _LOCK, closing(self._connect()) as c:
            # Walk the retired_by chain both ways so a fact's whole history
            # comes back, not only the versions that matched the words.
            frontier = list(ids)
            while frontier:
                marks = ",".join("?" * len(frontier))
                rows = c.execute(
                    f"SELECT id, retired_by FROM facts WHERE retired_by IN ({marks})"
                    f" OR id IN (SELECT retired_by FROM facts WHERE id IN ({marks}))",
                    frontier + frontier).fetchall()
                frontier = [r["id"] for r in rows if r["id"] not in seen]
                seen.update(frontier)
            marks = ",".join("?" * len(seen))
            hist = [dict(r) for r in c.execute(
                f"SELECT * FROM facts WHERE id IN ({marks}) ORDER BY valid_from, id",
                list(seen))]
        now = time.time()
        for h in hist:
            # Same rule as search() and current_facts(). This line said
            # `h["valid_to"] is None`, so the same row came back current from
            # search and not-current from timeline - the exact disagreement
            # retire()'s docstring forbids: "nothing that reads these rows may
            # treat valid_to is not NULL as not current".
            h["current"] = h["valid_to"] is None or h["valid_to"] > now
        return hist

    def current_facts(self, limit: int = 400) -> list[dict]:
        """What is true NOW. A valid_to in the future has not happened yet."""
        with _LOCK, closing(self._connect()) as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM facts WHERE valid_to IS NULL OR valid_to > ?"
                " ORDER BY id DESC LIMIT ?", (time.time(), limit))]

    def known_at(self, when: float, limit: int = 400) -> list[dict]:
        """What this machine BELIEVED at a past moment, right or wrong.

        The transaction-time query, and the reason retired_at exists. A fact
        entered on Tuesday and retired on Friday is in Wednesday's answer even
        though it is not in today's, and a fact learned yesterday about last
        year is not in last year's answer at all.
        """
        with _LOCK, closing(self._connect()) as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM facts WHERE created <= ?"
                " AND (retired_at IS NULL OR retired_at > ?)"
                " ORDER BY id DESC LIMIT ?", (when, when, limit))]

    def status(self) -> dict:
        with _LOCK, closing(self._connect()) as c:
            total = c.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            current = c.execute(
                "SELECT COUNT(*) FROM facts WHERE valid_to IS NULL OR valid_to > ?",
                (time.time(),)).fetchone()[0]
            pending = c.execute("SELECT COUNT(*) FROM facts WHERE embedded=0"
                                " AND erased_at IS NULL").fetchone()[0]
            erased = c.execute("SELECT COUNT(*) FROM facts"
                               " WHERE erased_at IS NOT NULL").fetchone()[0]
            ents = c.execute("SELECT COUNT(*) FROM entities WHERE merged_into IS NULL"
                             ).fetchone()[0]
            repeats = c.execute("SELECT COUNT(*) FROM fact_repeats").fetchone()[0]
        out = {"db": str(self.path), "facts": total, "current": current,
               "retired": total - current,
               "embedder": self.embedder.name, "semantic": self.embedder.semantic,
               "vector_search": self._vec_ok, "unembedded": pending,
               "erased": erased, "entities": ents, "reranker": reranker_status(),
               "said_again": repeats}
        if self._entity_errors:
            out["entity_errors"] = self._entity_errors
        if self._bad_vectors:
            # Only when it has happened. A permanent "bad_vectors: 0" line is
            # noise on every screen that renders status().
            out["bad_vectors"] = self._bad_vectors
            out["bad_vectors_note"] = (
                f"{self._bad_vectors} embedding(s) came back unusable - not a "
                "number, or all zeros - and were not stored. Those facts are "
                "still found by keyword. If this keeps climbing the embedding "
                "model is broken, not the store.")
        return out

    # ---- "Always keep in mind" (the owner's decision, 2026-09-24) ---------

    #: The one rule for "a pinned fact Jarvis still reads": pinned, current
    #: (the same `valid_to IS NULL OR valid_to > now` every reader uses),
    #: and its words not erased. Oldest pin first, so the list reads the
    #: same on every turn until the owner changes it.
    _PROFILE_SQL = (
        "SELECT f.id, f.text, f.created, f.valid_from, f.source, p.added, p.how"
        " FROM profile p JOIN facts f ON f.id = p.fact_id"
        " WHERE (f.valid_to IS NULL OR f.valid_to > ?) AND f.erased_at IS NULL"
        " ORDER BY p.added, p.fact_id")

    def profile(self) -> list[dict]:
        """The pinned facts Jarvis reads with every question, oldest pin
        first: each fact's own row (id, text, created, valid_from, source)
        plus when it was pinned (`added`) and how (`how`).

        A JOIN to the facts that are current NOW, never a copy: a pinned
        fact that is forgotten, corrected (which retires it), reaches its
        end date or has its words erased drops out here at once, with
        nothing to clean up. Its pin row stays, holding an id and nothing
        else; no fact comes back to life, so it is never read again."""
        with _LOCK, closing(self._connect()) as c:
            return [dict(r) for r in c.execute(self._PROFILE_SQL, (time.time(),))]

    def is_pinned(self, fact_id: int) -> bool:
        """Is this fact on the "Always keep in mind" list now?"""
        return any(p["id"] == int(fact_id) for p in self.profile())

    def pin(self, fact_id: int, how: str = "tap") -> dict:
        """Put ONE current fact on the "Always keep in mind" list.

        Only its id is stored. Refused, with `reason`, when there is no such
        fact ("no_such_fact"), when it is no longer current or its words
        were erased ("not_current"), when it is longer than the whole list
        allows ("fact_too_long"), or when the pinned facts' words would then
        pass PROFILE_LIMIT characters ("too_long"). The check and the write
        are one transaction, so two pins at once cannot both squeeze under
        the limit. Pinning a fact that is already pinned changes nothing.

        `how` is who put it there. "tap" - the owner's own tap on a fact they
        can see - is the only one today; a later suggestion card would say
        so here. Returns {"ok", "id", "pinned", "changed", "chars", "limit"}
        (+ "reason" when refused). Never the words."""
        fid = int(fact_id)
        how = how if isinstance(how, str) and _META_LABEL.match(how) else "tap"
        now = time.time()
        with _LOCK, closing(self._connect()) as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                row = c.execute("SELECT text, valid_to, erased_at FROM facts WHERE id=?",
                                (fid,)).fetchone()
                pins = [dict(r) for r in c.execute(self._PROFILE_SQL, (now,))]
                used = sum(len(str(p["text"] or "")) for p in pins)
                out = {"ok": False, "id": fid, "pinned": False, "changed": False,
                       "chars": used, "limit": PROFILE_LIMIT}
                if row is None:
                    out["reason"] = "no_such_fact"
                elif (row["erased_at"] is not None
                      or (row["valid_to"] is not None and float(row["valid_to"]) <= now)):
                    out["reason"] = "not_current"
                elif any(p["id"] == fid for p in pins):
                    out.update(ok=True, pinned=True)
                else:
                    n = len(str(row["text"] or ""))
                    if n > PROFILE_LIMIT:
                        out["reason"] = "fact_too_long"
                    elif used + n > PROFILE_LIMIT:
                        out["reason"] = "too_long"
                    else:
                        # INSERT OR REPLACE: a pin row left behind by a fact
                        # that stopped being current cannot be this id (a
                        # fact never becomes current again), but a stale
                        # row must never block a pin either.
                        c.execute("INSERT OR REPLACE INTO profile (fact_id, added, how)"
                                  " VALUES (?, ?, ?)", (fid, now, how))
                        out.update(ok=True, pinned=True, changed=True, chars=used + n)
                c.execute("COMMIT")
            except Exception:
                try:
                    c.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
        if out["changed"]:
            _audit("memory.pinned", {"id": fid, "how": how})   # the id only, never the words
        return out

    def unpin(self, fact_id: int) -> dict:
        """Take ONE fact off the list. The fact itself is not touched - only
        the pin goes. Unpinning a fact that is not pinned changes nothing.
        Returns {"ok": True, "id", "pinned": False, "changed", "chars",
        "limit"}."""
        fid = int(fact_id)
        with _LOCK, closing(self._connect()) as c:
            cur = c.execute("DELETE FROM profile WHERE fact_id=?", (fid,))
            changed = cur.rowcount > 0
            used = sum(len(str(r["text"] or ""))
                       for r in c.execute(self._PROFILE_SQL, (time.time(),)))
        if changed:
            _audit("memory.unpinned", {"id": fid})
        return {"ok": True, "id": fid, "pinned": False, "changed": changed,
                "chars": used, "limit": PROFILE_LIMIT}

    # ---- the entity layer (memory wave 3, 2026-09-25) --------------------
    #
    # See the module-level section "The entity layer" for the rules. These
    # methods are the store's half: linking a saved fact, unlinking one that
    # was forgotten, corrected or erased, the lookup chat recall uses, the
    # list the desktop shows, and merging two entries - one pair, by card.

    def _link_safely(self, c, fid: int, text: str) -> None:
        """_link_fact, never raising (a counted failure instead): the fact is
        already saved, and a save must never fail because of its links."""
        try:
            self._link_fact(c, fid, text)
        except Exception:
            self._entity_errors += 1

    def _unlink_safely(self, c, fid: int) -> None:
        try:
            self._unlink_fact(c, fid)
        except Exception:
            self._entity_errors += 1

    def _link_fact(self, c, fid: int, text: str, found: Optional[dict] = None) -> dict:
        """Link ONE saved fact to the people and things it names.

        `found` is {"names": [(name, kind)], "aliases": [(alias, name)]} -
        find_entities(text) when not given (the no-model linker), or what
        the optional local-model pass read (jarvis_entities.py). Either way
        the same rules hold here, where the rows are written:

          * GROUNDED OR DROPPED: a name or alias that is not in this fact's
            own text word for word is not linked.
          * An alias ("sister") is kept only with a name from the SAME fact
            ("My sister is called Priya"), and it records this fact's id -
            forget the fact and the alias goes.
          * The same name, once normalised, is the same entry (the only
            automatic merge). A name that is only LIKE one already there
            ("Priya Sharma" / "Priya Sharmaa") gets its own entry and a
            waiting "are these the same?" question - see raise_merge_cards.

        Returns {"entities": [ids linked], "aliases": n}."""
        found = found if found is not None else find_entities(text)
        c.execute("SAVEPOINT entity_link")
        try:
            out = self._link_rows(c, int(fid), text, found)
        except Exception:
            c.execute("ROLLBACK TO entity_link")
            c.execute("RELEASE entity_link")
            raise
        c.execute("RELEASE entity_link")
        return out

    def _link_rows(self, c, fid: int, text: str, found: dict) -> dict:
        out = {"entities": [], "aliases": 0}
        now = time.time()
        by_key: dict = {}
        fresh: list = []
        for name, kind in found.get("names") or []:
            name = " ".join(str(name).split())
            key = _name_key(name)
            if not _entity_name_ok(name, key) or not _grounded(text, name):
                continue
            kind = kind if kind in ENTITY_KINDS else None
            row = c.execute("SELECT entity_id FROM entity_aliases WHERE alias=? AND"
                            " fact_id IS NULL ORDER BY entity_id LIMIT 1", (key,)).fetchone()
            if row is None:
                eid = c.execute("INSERT INTO entities (name, kind, created) VALUES (?, ?, ?)",
                                (name, kind, now)).lastrowid
                c.execute("INSERT OR IGNORE INTO entity_aliases (alias, entity_id, fact_id)"
                          " VALUES (?, ?, NULL)", (key, eid))
                fresh.append((eid, name))
            else:
                eid = int(row[0])
                if kind:
                    c.execute("UPDATE entities SET kind=? WHERE id=? AND kind IS NULL",
                              (kind, eid))
            c.execute("INSERT OR IGNORE INTO fact_entities (fact_id, entity_id) VALUES (?, ?)",
                      (int(fid), eid))
            by_key[key] = eid
            if eid not in out["entities"]:
                out["entities"].append(eid)
        for alias, name in found.get("aliases") or []:
            alias = " ".join(str(alias).split())
            akey = _name_key(alias)
            eid = by_key.get(_name_key(name))
            if (eid is None or not _alias_ok(akey) or akey == _name_key(name)
                    or not _grounded(text, alias) or not _grounded(text, name)):
                continue
            cur = c.execute("INSERT OR IGNORE INTO entity_aliases (alias, entity_id, fact_id)"
                            " VALUES (?, ?, ?)", (akey, eid, int(fid)))
            out["aliases"] += max(cur.rowcount, 0)
        for eid, name in fresh:
            self._note_likely_same(c, eid, name, now)
        return out

    def _unlink_fact(self, c, fid: int, now: Optional[float] = None,
                     new_text: Optional[str] = None) -> int:
        """Take ONE fact out of the entity layer: its links, the aliases it
        taught, and every entry no fact links to any more - with the
        "are these the same?" cards that named one (their words wiped, a
        waiting one turned down). An alias another current fact ALSO
        teaches is put back from that fact. `new_text`: the fact's new
        wording (an edit in place), linked BEFORE the clean-up, so a name
        both wordings say keeps its entry (and its merges and cards).
        Returns how many cards' words were wiped."""
        c.execute("SAVEPOINT entity_unlink")
        try:
            wiped = self._unlink_rows(c, int(fid), time.time() if now is None else now,
                                      new_text)
        except Exception:
            c.execute("ROLLBACK TO entity_unlink")
            c.execute("RELEASE entity_unlink")
            raise
        c.execute("RELEASE entity_unlink")
        return wiped

    def _unlink_rows(self, c, fid: int, now: float, new_text: Optional[str] = None) -> int:
        linked = {r[0] for r in c.execute(
            "SELECT entity_id FROM fact_entities WHERE fact_id=?", (fid,))}
        taught = {r[0] for r in c.execute(
            "SELECT entity_id FROM entity_aliases WHERE fact_id=?", (fid,))}
        affected = linked | taught
        c.execute("DELETE FROM fact_entities WHERE fact_id=?", (fid,))
        c.execute("DELETE FROM entity_aliases WHERE fact_id=?", (fid,))
        if new_text is not None:
            self._link_fact(c, fid, new_text)
        if not affected:
            return 0
        if taught:
            # Only aliases can need putting back - another fact's LINKS were
            # never touched - so only the facts about the entries this one
            # taught an alias for are read again. Idempotent: the same names
            # map to the same entries, and only the aliases a fact itself
            # teaches come back.
            marks = ",".join("?" * len(taught))
            others = c.execute(
                "SELECT DISTINCT f.id, f.text FROM fact_entities fe"
                " JOIN facts f ON f.id = fe.fact_id"
                f" WHERE fe.entity_id IN ({marks}) AND f.id != ? AND f.erased_at IS NULL"
                " AND (f.valid_to IS NULL OR f.valid_to > ?)",
                (*taught, fid, now)).fetchall()
            for ofid, otext in others:
                self._link_fact(c, int(ofid), str(otext or ""))
        wiped = 0
        for eid in sorted(affected):
            if not c.execute("SELECT 1 FROM fact_entities WHERE entity_id=? LIMIT 1",
                             (eid,)).fetchone():
                wiped += self._drop_entity(c, eid, now)
        return wiped

    def _drop_entity(self, c, eid: int, now: float) -> int:
        """Delete one entry nothing links to any more, and keep the merges
        around it: entries merged INTO it now point where it pointed (or
        the oldest of them becomes the entry the rest point at). Its cards
        go with it. The only deletes in the entity layer, and only of
        derived rows - a fact is never touched."""
        row = c.execute("SELECT merged_into FROM entities WHERE id=?", (eid,)).fetchone()
        parent = row[0] if row else None
        kids = [r[0] for r in c.execute("SELECT id FROM entities WHERE merged_into=?"
                                        " ORDER BY id", (eid,))]
        if kids:
            if parent is None:
                parent = kids[0]
                c.execute("UPDATE entities SET merged_into=NULL WHERE id=?", (parent,))
            c.execute("UPDATE entities SET merged_into=? WHERE merged_into=? AND id != ?",
                      (parent, eid, parent))
        c.execute("DELETE FROM entity_aliases WHERE entity_id=?", (eid,))
        c.execute("DELETE FROM entities WHERE id=?", (eid,))
        if self._fuzzy_index is not None:
            self._fuzzy_index.pop(eid, None)
        wiped = 0
        for pid, state in c.execute("SELECT proposal_id, state FROM entity_merge_asks"
                                    " WHERE a=? OR b=?", (eid, eid)).fetchall():
            if pid is not None:
                wiped += _wipe_merge_card(c, int(pid), now)
        c.execute("DELETE FROM entity_merge_asks WHERE a=? OR b=?", (eid, eid))
        return wiped

    def _backfill_entities(self, c) -> int:
        """Link every current fact of a store that predates the entity
        layer. Once (the meta row 'entities'), in one transaction."""
        rows = c.execute("SELECT id, text FROM facts WHERE erased_at IS NULL"
                         " AND (valid_to IS NULL OR valid_to > ?)", (time.time(),)).fetchall()
        n = 0
        c.execute("BEGIN IMMEDIATE")
        try:
            for fid, text in rows:
                try:
                    # _link_fact undoes its own half-written rows on failure.
                    self._link_fact(c, int(fid), str(text or ""))
                    n += 1
                except Exception:
                    self._entity_errors += 1
            c.execute("COMMIT")
        except Exception:
            try:
                c.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        return n

    def _root(self, c, eid: int) -> int:
        """Follow `merged_into` to the entry a group is known by. A loop (a
        hand-edited file) is walked at most a few steps."""
        seen = set()
        cur = int(eid)
        while cur not in seen and len(seen) < 32:
            seen.add(cur)
            row = c.execute("SELECT merged_into FROM entities WHERE id=?", (cur,)).fetchone()
            if row is None or row[0] is None:
                return cur
            cur = int(row[0])
        return cur

    def _group(self, c, root: int) -> list:
        """The root and every entry merged into it, however deep."""
        return [r[0] for r in c.execute(
            "WITH RECURSIVE g(id) AS (SELECT ? UNION"
            " SELECT e.id FROM entities e JOIN g ON e.merged_into = g.id)"
            " SELECT id FROM g LIMIT 200", (int(root),))]

    def _entity_hits(self, c, query: str, at: float) -> tuple:
        """([root ids], [their names]) that the question names, by the alias
        table. Aliases count only while the fact that taught them is
        current; an alias that points at more than ALIAS_MAX_ENTITIES
        different people or things ("friend", with thirty friends) says
        nothing about which, so it is left out."""
        grams = _query_grams(query)
        if not grams:
            return [], []
        marks = ",".join("?" * len(grams))
        rows = c.execute(
            "SELECT a.alias, a.entity_id FROM entity_aliases a"
            " LEFT JOIN facts f ON f.id = a.fact_id"
            f" WHERE a.alias IN ({marks}) AND (a.fact_id IS NULL OR (f.id IS NOT NULL"
            " AND f.erased_at IS NULL AND (f.valid_to IS NULL OR f.valid_to > ?)))",
            (*grams, at)).fetchall()
        by_alias: dict = {}
        for alias, eid in rows:
            by_alias.setdefault(alias, set()).add(self._root(c, eid))
        order = {g: i for i, g in enumerate(grams)}
        roots: list = []
        for alias in sorted(by_alias, key=lambda a: order.get(a, 0)):
            group = by_alias[alias]
            if len(group) > ALIAS_MAX_ENTITIES:
                continue
            for r in sorted(group):
                if r not in roots:
                    roots.append(r)
        roots = roots[:ENTITY_HITS_MAX]
        names = []
        for r in roots:
            row = c.execute("SELECT name FROM entities WHERE id=?", (r,)).fetchone()
            if row and row[0]:
                names.append(str(row[0]))
        return roots, names

    def _linked_facts(self, c, roots, limit: int, *, at: float,
                      include_retired: bool = False,
                      known_at: Optional[float] = None) -> list:
        """The third list: facts linked to these entries (and whatever was
        merged into them), most of them named first, then newest first.
        Never an erased fact; by default only facts true at `at`."""
        ids = []
        for r in roots:
            for e in self._group(c, r):
                if e not in ids:
                    ids.append(e)
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        where, args = "", []
        if known_at is not None:
            where = " AND f.created <= ? AND (f.retired_at IS NULL OR f.retired_at > ?)"
            args = [known_at, known_at]
        if not include_retired:
            where += " AND f.valid_from <= ? AND (f.valid_to IS NULL OR f.valid_to > ?)"
            args += [at, at]
        return [r[0] for r in c.execute(
            "SELECT fe.fact_id, COUNT(*) AS n FROM fact_entities fe"
            " JOIN facts f ON f.id = fe.fact_id"
            f" WHERE fe.entity_id IN ({marks}) AND f.erased_at IS NULL{where}"
            " GROUP BY fe.fact_id ORDER BY n DESC, fe.fact_id DESC LIMIT ?",
            (*ids, *args, int(limit)))]

    def _note_likely_same(self, c, eid: int, name: str, now: float) -> None:
        """A NEW entry whose name is a likely typo of one already there
        ("Priya Sharmaa" beside "Priya Sharma") gets ONE waiting question,
        per pair, ever: entity_merge_asks. Graphiti's own test
        (dedup_helpers.py): both names specific enough - at least 6
        characters or two words, and entropy of at least 1.5 - and at least
        90% of their three-letter chunks shared. Anything less stays apart."""
        fz = _fuzzy_form(name)
        if not _has_high_entropy(fz):
            if self._fuzzy_index is not None:
                self._fuzzy_index[eid] = (fz, None)
            return
        mine = _shingles(fz)
        if self._fuzzy_index is None:
            self._fuzzy_index = {}
            for oid, oname in c.execute("SELECT id, name FROM entities"):
                ofz = _fuzzy_form(oname)
                self._fuzzy_index[int(oid)] = (
                    ofz, _shingles(ofz) if _has_high_entropy(ofz) else None)
        self._fuzzy_index[eid] = (fz, mine)
        n = len(mine)
        for oid, (ofz, theirs) in list(self._fuzzy_index.items()):
            if oid == eid or not theirs or ofz == fz:
                continue
            m = len(theirs)
            if min(n, m) < MERGE_JACCARD * max(n, m):
                continue          # too different in length to reach 0.9
            if _jaccard(mine, theirs) < MERGE_JACCARD:
                continue
            if not c.execute("SELECT 1 FROM entities WHERE id=?", (oid,)).fetchone():
                self._fuzzy_index.pop(oid, None)
                continue
            if self._root(c, oid) == self._root(c, eid):
                continue
            a, b = min(oid, eid), max(oid, eid)
            c.execute("INSERT OR IGNORE INTO entity_merge_asks (a, b, state, created)"
                      " VALUES (?, ?, 'waiting', ?)", (a, b, now))

    def raise_merge_cards(self) -> int:
        """Turn each waiting "are these the same?" question into ONE card in
        the ordinary review queue - jarvis_extract.propose_merge, which
        memory-entities.patch adds. Never a list form, never an
        approve-all: one pair, one card, one decision, the owner's.

        Also notes the answers that came back: a card turned down means
        "different", and the pair is never asked about again. Without the
        patch in this process, the questions wait (nothing is guessed).
        Returns how many cards were raised."""
        import sys
        x = sys.modules.get("jarvis_extract")
        propose = getattr(x, "propose_merge", None) if x is not None else None
        raised = 0
        try:
            with _LOCK, closing(self._connect()) as c:
                if _has_table(c, "proposals"):
                    c.execute(
                        "UPDATE entity_merge_asks SET state='different' WHERE state='asked'"
                        " AND proposal_id IN (SELECT id FROM proposals WHERE state='rejected')")
                if propose is None:
                    return 0
                waiting = c.execute("SELECT a, b FROM entity_merge_asks WHERE state='waiting'"
                                    " ORDER BY created, a, b LIMIT 20").fetchall()
                for a, b in waiting:
                    ra = c.execute("SELECT name, kind FROM entities WHERE id=?", (a,)).fetchone()
                    rb = c.execute("SELECT name, kind FROM entities WHERE id=?", (b,)).fetchone()
                    if ra is None or rb is None:
                        c.execute("DELETE FROM entity_merge_asks WHERE a=? AND b=?", (a, b))
                        continue
                    if self._root(c, a) == self._root(c, b):
                        c.execute("UPDATE entity_merge_asks SET state='same' WHERE a=? AND b=?",
                                  (a, b))
                        continue
                    pid = propose(merge_card_text(ra[0], rb[0], ra[1] or rb[1]))
                    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
                        break          # the queue is full: try again after the next save
                    c.execute("UPDATE entity_merge_asks SET state='asked', proposal_id=?"
                              " WHERE a=? AND b=?", (pid, a, b))
                    raised += 1
        except Exception:
            self._entity_errors += 1
        return raised

    def merge_from_card(self, proposal_id: int) -> Optional[dict]:
        """The owner said yes on ONE "are these the same?" card: join that
        pair. Called by jarvis_extract when that card is accepted - never
        by anything else, and never for more than the one pair the card
        named. None when the card names no pair (or it is gone)."""
        with _LOCK, closing(self._connect()) as c:
            row = c.execute("SELECT a, b FROM entity_merge_asks WHERE proposal_id=?",
                            (int(proposal_id),)).fetchone()
        if row is None:
            return None
        out = self.merge(int(row[0]), int(row[1]))
        if out is not None:
            with _LOCK, closing(self._connect()) as c:
                c.execute("UPDATE entity_merge_asks SET state='same' WHERE proposal_id=?",
                          (int(proposal_id),))
        return out

    def merge(self, keep: int, other: int) -> Optional[dict]:
        """Join two entries: `other`'s group now points at `keep`'s. A
        pointer, never a delete - every link and alias stays where it is,
        and lookups follow the pointer. Exactly two ids; there is no list
        form. None when either is gone."""
        with _LOCK, closing(self._connect()) as c:
            if not (c.execute("SELECT 1 FROM entities WHERE id=?", (int(keep),)).fetchone()
                    and c.execute("SELECT 1 FROM entities WHERE id=?", (int(other),)).fetchone()):
                return None
            rk, ro = self._root(c, keep), self._root(c, other)
            if rk != ro:
                c.execute("UPDATE entities SET merged_into=? WHERE id=?", (rk, ro))
        _audit("memory.entities_merged", {"keep": rk, "other": ro})   # ids only
        return {"keep": rk, "merged": ro, "changed": rk != ro}

    def link_entities(self, fact_id: int, found: dict) -> Optional[dict]:
        """Link one CURRENT fact to names a local model read in it (the
        optional pass, jarvis_entities.py). Every rule of _link_fact holds -
        above all, a name or alias not in the fact word for word is
        dropped. None for a fact that is gone, forgotten or erased."""
        with _LOCK, closing(self._connect()) as c:
            row = c.execute("SELECT text, valid_to, erased_at FROM facts WHERE id=?",
                            (int(fact_id),)).fetchone()
            if (row is None or row["erased_at"] is not None
                    or (row["valid_to"] is not None and float(row["valid_to"]) <= time.time())):
                return None
            out = self._link_fact(c, int(fact_id), str(row["text"] or ""), found=found)
        self.raise_merge_cards()
        return out

    def entities_view(self, limit: int = 500, now: Optional[float] = None) -> dict:
        """GET /api/memory/entities: the people and things Jarvis has linked
        facts to, for the desktop's "About <name>".

            {"entities": [{"id", "name", "kind", "also": [other names joined
              to it], "aliases": ["sister"], "fact_ids": [newest first],
              "facts": n}], "count": n, "limit": limit}

        One entry per group (merges followed), only groups with at least
        one current, unerased fact, most facts first. Words only as they
        are in the facts; nothing is summarised. The facts' own words are
        read by id (GET /api/memory/used)."""
        now = time.time() if now is None else float(now)
        with _LOCK, closing(self._connect()) as c:
            ents = {int(r[0]): {"name": r[1], "kind": r[2], "into": r[3]}
                    for r in c.execute("SELECT id, name, kind, merged_into FROM entities")}
            root = {eid: self._root(c, eid) for eid in ents}
            links = c.execute(
                "SELECT fe.entity_id, fe.fact_id FROM fact_entities fe"
                " JOIN facts f ON f.id = fe.fact_id WHERE f.erased_at IS NULL"
                " AND (f.valid_to IS NULL OR f.valid_to > ?)", (now,)).fetchall()
            aliases = c.execute(
                "SELECT a.alias, a.entity_id FROM entity_aliases a JOIN facts f ON f.id = a.fact_id"
                " WHERE f.erased_at IS NULL AND (f.valid_to IS NULL OR f.valid_to > ?)",
                (now,)).fetchall()
        groups: dict = {}
        for eid, fid in links:
            r = root.get(int(eid))
            if r is None or r not in ents:
                continue
            g = groups.setdefault(r, {"facts": set(), "aliases": set()})
            g["facts"].add(int(fid))
        for alias, eid in aliases:
            r = root.get(int(eid))
            if r in groups:
                groups[r]["aliases"].add(str(alias))
        members: dict = {}
        for e, r in root.items():
            members.setdefault(r, []).append(e)
        out = []
        for r, g in groups.items():
            group = members.get(r, [r])
            also = sorted({ents[e]["name"] for e in group
                           if e != r and ents[e]["name"] != ents[r]["name"]})
            out.append({"id": r, "name": ents[r]["name"],
                        "kind": ents[r]["kind"] or next(
                            (ents[e]["kind"] for e in group if ents[e]["kind"]), None),
                        "also": also, "aliases": sorted(g["aliases"]),
                        "fact_ids": sorted(g["facts"], reverse=True),
                        "facts": len(g["facts"])})
        out.sort(key=lambda e: (-e["facts"], str(e["name"]).lower(), e["id"]))
        return {"entities": out[:max(0, int(limit))], "count": len(out), "limit": int(limit)}


# --------------------------------------------------------------------------
#   "Erase the words" (the owner's decision, 2026-09-24)
# --------------------------------------------------------------------------

#: What an erased fact's text becomes. Fixed, and no words of the fact in it.
#: The apps never show it: they read `erased_at` and say "Erased on <date>".
ERASED_TEXT = "[erased]"

#: The meta keys an erased fact keeps: dates, ids and where it came from -
#: never words, and never a hash of them. Anything else in meta is dropped,
#: including keys this list has never heard of: an allowlist, because meta
#: is free-form and a new key holding words must not survive by default.
ERASE_KEEPS_META = ("auto", "saved_at", "proposal_id", "proposal_source", "provenance",
                    "device", "tainted", "confidence", "true_from")

#: A kept string value must look like a label ("typed", "phone",
#: "import:claude"), never like a sentence.
_META_LABEL = re.compile(r"^[a-z][a-z0-9_:.-]{0,31}$")

#: The review-queue source of a "retire this?" card (feedback.patch). Its
#: `fact_id` names the fact it RETIRED, and its `text` is only the reason.
_RETIRE_SOURCE = "feedback_retire"


def _erased_meta(raw) -> dict:
    """An erased fact's meta: ERASE_KEEPS_META only, and only plain values."""
    try:
        meta = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
    except (TypeError, ValueError):
        meta = {}
    if not isinstance(meta, dict):
        return {}
    out = {}
    for k in ERASE_KEEPS_META:
        v = meta.get(k)
        if isinstance(v, bool) or (isinstance(v, (int, float)) and math.isfinite(v)):
            out[k] = v
        elif isinstance(v, str) and _META_LABEL.match(v):
            out[k] = v
    return out


def _same_words(a, b: str) -> bool:
    return isinstance(a, str) and " ".join(a.split()).lower() == b


def _erase_copies(c, fid: int, old_text: str, now: float) -> int:
    """Every copy of an erased fact's words elsewhere in memory.db. Returns
    how many rows it changed.

    What is in this file (checked 2026-09-24): `facts`, `facts_fts`,
    `facts_vec` (erase() handles those three), `meta` (the embedder's name
    only), `profile` ("Always keep in mind": fact ids and dates, never
    words - an erased fact is no longer current, so it leaves that list by
    itself), `auto_learn_notes` (why a card stayed a card - a fixed sentence,
    never the fact), a `documents` table that is not Jarvis's, and the
    review queue, `proposals`, which jarvis_extract keeps here:

      * the card that BECAME this fact (`fact_id`): its text is the words.
        Not a "retire this?" card, whose `fact_id` names the fact it retired
        and whose text is only the reason.
      * cards that named this fact as the one they would replace
        (`replaces_id`): their `replaces` / `replaces_text` are its words.
        A "retire this?" card still waiting about it is turned down - the
        fact is retired already, and the card showed nothing but its words.
      * any card holding exactly these words (a card discarded earlier, or
        one proposed again and still waiting). A waiting one is turned down:
        keeping it would keep the words, and keeping it by mistake later
        would save them again.

    A table the owner's jarvis_extract has not created yet, or an older one
    without some column, is simply skipped.
    """
    if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='proposals'"
                     ).fetchone():
        return 0
    cols = {r[1] for r in c.execute("PRAGMA table_info(proposals)")}
    if "text" not in cols:
        return 0
    has = cols.__contains__
    n = 0

    def turn_down(pid: int) -> None:
        if has("state"):
            sets = "state='rejected'" + (", decided=?" if has("decided") else "")
            c.execute(f"UPDATE proposals SET {sets} WHERE id=? AND state='pending'",
                      ((now, pid) if has("decided") else (pid,)))

    if has("fact_id"):
        if has("source"):
            cur = c.execute("UPDATE proposals SET text=? WHERE fact_id=? AND text IS NOT ?"
                            " AND COALESCE(source, '') != ?",
                            (ERASED_TEXT, fid, ERASED_TEXT, _RETIRE_SOURCE))
        else:
            cur = c.execute("UPDATE proposals SET text=? WHERE fact_id=? AND text IS NOT ?",
                            (ERASED_TEXT, fid, ERASED_TEXT))
        n += max(cur.rowcount, 0)
    if has("replaces_id"):
        for col in ("replaces", "replaces_text"):
            if has(col):
                cur = c.execute(f"UPDATE proposals SET {col}=? WHERE replaces_id=?"
                                f" AND {col} IS NOT NULL AND {col} IS NOT ?",
                                (ERASED_TEXT, fid, ERASED_TEXT))
                n += max(cur.rowcount, 0)
        if has("source") and has("state"):
            for (pid,) in c.execute("SELECT id FROM proposals WHERE replaces_id=? AND source=?"
                                    " AND state='pending'", (fid, _RETIRE_SOURCE)).fetchall():
                turn_down(pid)
    want = " ".join(str(old_text or "").split()).lower()
    if want:
        pick = ["id", "text"] + [k for k in ("replaces", "state") if has(k)]
        for r in c.execute(f"SELECT {', '.join(pick)} FROM proposals").fetchall():
            r = dict(zip(pick, r))
            if r.get("state") == "accepting":
                continue            # mid-decision elsewhere; not this call's to touch
            if _same_words(r["text"], want):
                c.execute("UPDATE proposals SET text=? WHERE id=?", (ERASED_TEXT, r["id"]))
                n += 1
                if r.get("state") == "pending":
                    turn_down(r["id"])
            if _same_words(r.get("replaces"), want):
                c.execute("UPDATE proposals SET replaces=? WHERE id=?", (ERASED_TEXT, r["id"]))
                n += 1
    return n


def _scrub_file(c) -> bool:
    """Make the erased words really gone from the file, not only unreachable.

    SQLite does not overwrite what it frees, and FTS5 does not even free a
    deleted entry at once - it adds a "deleted" marker and keeps the old
    words in its index until the index is merged. So, on the connection
    that erased (which has secure_delete on, so freed pages are zeroed):
    merge the word index ('optimize'), then copy the write-ahead log into
    the file and truncate the log to nothing. Measured in
    backend/test_memory_erase.py by reading memory.db and memory.db-wal as
    raw bytes.

    Returns whether the log was emptied. False when another connection was
    in the middle of reading and the log could not be truncated after a few
    tries - the old words may then stay in memory.db-wal until the next
    checkpoint. The caller says so.
    """
    try:
        c.execute("INSERT INTO facts_fts(facts_fts) VALUES('optimize')")
    except sqlite3.Error:
        pass
    # A TRUNCATE checkpoint waits on a reader through the busy handler, which
    # _connect() sets to 30 seconds - five tries would hold the erase (and
    # _LOCK, and the owner's button) for two and a half minutes. Short waits
    # here, about two seconds in all; the caller says when it did not work.
    try:
        c.execute("PRAGMA busy_timeout=200")
    except sqlite3.Error:
        pass
    for attempt in range(5):
        try:
            busy = c.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]
        except sqlite3.Error:
            busy = 1
        if not busy:
            return True
        time.sleep(0.1 * (attempt + 1))
    return False


def handle_erase(body) -> tuple:
    """POST /api/memory/erase {"id": <fact id>} -> (http status, reply).

    memory-erase.patch hands the route here after the same origin and token
    checks as /api/memory/forget. One fact per request, and nothing else in
    the body: there is no list form, the same as forget and decide. The
    reply never carries the words - not even the "was" forget sends back.
    """
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "need an object"}
    fid = body.get("id")
    if not isinstance(fid, int) or isinstance(fid, bool):
        return 400, {"ok": False, "error": "need an integer id"}
    if set(body) - {"id"}:
        return 400, {"ok": False, "error": 'erase takes one fact: {"id": <int>} and nothing else'}
    try:
        out = store().erase(fid)
    except Exception as exc:
        return 500, {"ok": False, "error": type(exc).__name__}
    if out is None:
        return 404, {"ok": False, "reason": "no_such_fact", "error": "no fact with that id"}
    note = ("Erased. The words are gone from Jarvis's memory on this PC; only the "
            "dates are kept, so the history shows something was erased here. "
            "There is no undo.")
    if not out["file_clean"]:
        note += (" Another part of Jarvis was reading the memory file at that "
                 "moment, so an older copy may stay in memory.db-wal until the "
                 "file is next tidied.")
    return 200, {"ok": True, **out, "note": note}


# --------------------------------------------------------------------------
#   "Always keep in mind" (the owner's decision, 2026-09-24)
# --------------------------------------------------------------------------
#
# A short list of facts the owner pins, read with EVERY local chat question,
# word for word. Search brings back the five facts that share words or
# meaning with the question; "the owner is vegetarian" shares neither with
# "what should I cook tonight?", so it was never there when it mattered.
# (The idea is Letta's, MIRIX's and MemoryOS's "core memory" - with none of
# their rewriting: nothing here lets a model add to, merge or summarise the
# list. docs/RESEARCH-2026-09-24.md section 3 item 2.)
#
# The words are never copied, shortened or rewritten. Summarising drops
# words, and the word most often dropped is "not" - this store is
# bi-temporal precisely because negation matters (docs/ARCHITECTURE.md
# section 5: "never compress facts").

#: How many characters the pinned facts' words may add up to. About 300
#: tokens, around 7% of the 4,096-token context the primary model runs with
#: today (jarvis-primary.Modelfile) - re-read on every local question, so it
#: is kept small. Counted as the facts' own text, without the date or the
#: "- " each line gets in the prompt.
PROFILE_LIMIT = 1200

#: The refusals, in the words both apps show.
PIN_TOO_LONG = "That would make the list too long - unpin something first"
PIN_FACT_TOO_LONG = ("That fact is too long for the list on its own - the list holds "
                     f"{PROFILE_LIMIT:,} characters in all")
PIN_NOT_CURRENT = "That fact is no longer in use, so it cannot be kept in mind"
PIN_NO_SUCH_FACT = "no fact with that id"


def _audit(event: str, data: dict) -> None:
    try:
        if fw is not None:
            fw.audit_log(event, data)
    except Exception:
        pass


def profile_view(st: Optional["MemoryStore"] = None) -> dict:
    """GET /api/memory/profile's answer: {"facts": [{"id", "text",
    "added"}], "chars", "limit"}. `chars` counts the words of the facts
    listed - the pinned facts that are still current - which is what the
    limit is about."""
    st = st or store()
    facts = [{"id": int(p["id"]), "text": str(p["text"] or ""), "added": p["added"]}
             for p in st.profile()]
    return {"facts": facts, "chars": sum(len(f["text"]) for f in facts),
            "limit": PROFILE_LIMIT}


def handle_profile_get() -> tuple:
    """GET /api/memory/profile -> (http status, reply). memory-profile.patch
    hands the route here after the token and origin checks."""
    try:
        return 200, profile_view()
    except Exception as exc:
        return 500, {"error": type(exc).__name__}


def handle_profile(body) -> tuple:
    """POST /api/memory/profile {"id": <fact id>, "pinned": true|false} ->
    (http status, reply).

    ONE fact per request, and nothing else in the body - no list form, the
    same as forget, erase and decide. No approval card: this is the owner's
    own tap on a fact they can see (like Forget), and both apps hold it on a
    stale link. The reply never carries the words; an app reads the list
    again (GET) to draw it.

      200  {"ok": true, "id", "pinned", "changed", "chars", "limit", "note"}
      404  {"ok": false, "reason": "no_such_fact", "error"}
      409  {"ok": false, "reason": "too_long" | "fact_too_long" | "not_current",
            "error": <the sentence to show>, "chars", "limit"}
      400  anything but one integer id and one true/false
    """
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "need an object"}
    fid, want = body.get("id"), body.get("pinned")
    if not isinstance(fid, int) or isinstance(fid, bool):
        return 400, {"ok": False, "error": "need an integer id"}
    if not isinstance(want, bool):
        return 400, {"ok": False, "error": 'need "pinned": true or false'}
    if set(body) - {"id", "pinned"}:
        return 400, {"ok": False,
                     "error": 'pin one fact: {"id": <int>, "pinned": true|false} and nothing else'}
    try:
        st = store()
        out = st.pin(fid) if want else st.unpin(fid)
    except Exception as exc:
        return 500, {"ok": False, "error": type(exc).__name__}
    reason = out.get("reason")
    if reason == "no_such_fact":
        return 404, {"ok": False, "reason": reason, "error": PIN_NO_SUCH_FACT}
    if reason:
        return 409, {**out, "error": {"too_long": PIN_TOO_LONG,
                                      "fact_too_long": PIN_FACT_TOO_LONG,
                                      "not_current": PIN_NOT_CURRENT}[reason]}
    note = ("Jarvis will read this with every question, word for word." if want
            else "Jarvis will only use this when a question calls for it.")
    return 200, {**out, "note": note}


def with_profile(st, hits, k: int) -> list:
    """What a local chat turn recalls, the pinned facts first.

    `hits` is what the search found (jarvis_past.recall's answer: current
    facts, and on a question about the past some retired ones, labelled).
    The pinned facts go in front, each marked `pinned: True`, and a pinned
    fact the search also found is left out of the rest, so nothing is said
    twice. k <= 0 - JARVIS_MEMORY_K=0, the switch for no memory at all - is
    NOTHING, pinned facts included. If the list cannot be read, the search's
    facts alone: the old behaviour."""
    if k <= 0:
        return []
    hits = list(hits or [])
    try:
        pins = st.profile()
    except Exception:
        return hits
    if not pins:
        return hits
    ids = {p["id"] for p in pins}
    return ([dict(p, pinned=True, current=True) for p in pins]
            + [h for h in hits if h.get("id") not in ids])


# --------------------------------------------------------------------------
#   "Used in this answer" (the owner's decision, 2026-09-25)
# --------------------------------------------------------------------------
#
# The chat reply's X-Jarvis-Route header lists the facts an answer used by
# id only (`injected_ids`, "mem:<id>"), and the `memory_saved` event lists
# the facts automatic learning just saved by id only - both reach places a
# fact's words must not (a phone's lock screen, a log). An app that wants to
# SHOW those facts asks for their words here, behind the pairing token, the
# same as every other memory read: GET /api/memory/used?ids=12,15.
#
# Read-only. One call reads a handful of facts the owner is looking at -
# there is nothing here to act on, so no list form of any write follows
# from it: Forget and Erase stay one fact per request.

#: The most ids one read takes. An answer uses at most JARVIS_MEMORY_K
#: searched facts, three past ones and the pinned list (1,200 characters -
#: a few dozen short facts at the very most); one learning pass saves a few.
USED_MAX = 100


def parse_used_ids(raw) -> Optional[list]:
    """The fact ids in `?ids=`, in the order given, each once - or None when
    the value is not a comma-separated list of 1..USED_MAX whole numbers
    above 0. "mem:12" (the header's own spelling) is read as 12; anything
    else - "fact:3" (the old word list, which has no id), a name, a
    negative, a fraction - makes the whole request a 400, rather than a
    silently shorter list."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    out = []
    for part in raw.split(","):
        part = part.strip()
        if part.startswith("mem:"):
            part = part[4:]
        # ASCII digits only: str.isdigit() would also take "١٢" and "²".
        if not re.fullmatch(r"[0-9]{1,12}", part):
            return None
        n = int(part)
        if n <= 0:
            return None
        if n not in out:
            out.append(n)
    if not out or len(out) > USED_MAX:
        return None
    return out


def used_view(ids, st: Optional["MemoryStore"] = None,
              now: Optional[float] = None) -> dict:
    """GET /api/memory/used's answer for these fact ids:

        {"facts": [{"id", "text", "current", "pinned", "created",
                    "valid_to", "erased_at"}], "missing": [id, ...]}

    In the order asked. `current` is the rule every reader uses (valid_to
    empty or still ahead) and false for an erased fact; `pinned` is whether
    it is on "Always keep in mind" now. A fact that is no longer current
    still comes with its words - an answer may have used it (a question
    about the past recalls retired facts, labelled), and Forget kept them -
    so an app can say "no longer in use" beside them. An ERASED fact never
    comes with words: `text` is "" (never the "[erased]" marker) and
    `erased_at` says when. An id with no fact at all is in `missing`."""
    st = st or store()
    now = time.time() if now is None else float(now)
    try:
        pinned = {int(p["id"]) for p in st.profile()}
    except Exception:
        pinned = set()
    facts, missing = [], []
    for fid in ids:
        row = st.get(fid)
        if row is None:
            missing.append(int(fid))
            continue
        erased = row.get("erased_at")
        vt = row.get("valid_to")
        current = erased is None and (vt is None or float(vt) > now)
        facts.append({
            "id": int(row["id"]),
            "text": "" if erased is not None else str(row.get("text") or ""),
            "current": bool(current),
            "pinned": bool(current and int(row["id"]) in pinned),
            "created": row.get("created"),
            "valid_to": vt,
            "erased_at": erased,
        })
    return {"facts": facts, "missing": missing}


def handle_used_get(query: str) -> tuple:
    """GET /api/memory/used?ids=<id>,<id>... -> (http status, reply).

    temporary-chat.patch hands the route here after the same token and
    origin checks as every other memory read. 400 for anything but 1 to
    USED_MAX whole-number ids (see parse_used_ids)."""
    try:
        from urllib.parse import parse_qs
        raw = (parse_qs(query or "", keep_blank_values=True).get("ids") or [""])[0]
    except Exception:
        raw = ""
    ids = parse_used_ids(raw)
    if ids is None:
        return 400, {"error": f"need ?ids= with 1 to {USED_MAX} fact ids, "
                              "separated by commas (for example ?ids=12,15)"}
    try:
        return 200, used_view(ids)
    except Exception as exc:
        return 500, {"error": type(exc).__name__}


# --------------------------------------------------------------------------
#   The entity layer - "who is my sister?" (memory wave 3, 2026-09-25)
# --------------------------------------------------------------------------
#
# Word search and meaning search cannot connect "my sister's wedding" to
# "Priya's wedding is in Lisbon": nothing in the question says Priya. A fact
# the owner saved can - "Owner's sister is called Priya" - so each saved fact
# is linked to the people, pets, places and things it names, and the word
# the owner uses for them ("sister") becomes an ALIAS of that name. Recall
# then looks the question's words up in the alias table, adds the full names
# to the search, and fuses the facts linked to them in as a third list.
#
# The research sketch's seven rules (memresearch/graph/REPORT.md, "Design
# sketch: the entity layer"), and where each one is kept:
#
#   1. Links come from SAVED facts only, never from the conversation - they
#      are made in MemoryStore.add() (and edit()), after every check the fact
#      already passed. Nothing else writes them.
#   2. A link can only ADD a candidate to recall. Nothing here retires,
#      edits, hides or re-orders a stored fact; search() keeps its k and both
#      floors, and the third list goes through the same current-only filter.
#   3. Grounded or dropped: every name and alias must be in the fact's own
#      text word for word (_grounded), whoever found it - these fixed rules
#      or the optional local model. An alias is kept only with a name from
#      the SAME fact, and records that fact's id; forgetting, correcting or
#      erasing the fact takes the alias and the links with it, and erasing
#      takes every name no other fact still says (_unlink_fact).
#   4. Merging is the owner's call, one pair at a time: only an EXACT match
#      after normalising joins by itself (the same entry is reused). A likely
#      typo raises ONE "are these the same?" card per pair, ever, in the
#      ordinary review queue; anything less stays apart.
#   5. The model is optional (jarvis_entities.py, OFF by default, unmeasured):
#      one local call per learner pass, on the learner's background thread.
#      The no-model rules below run on every save.
#   6. Recall: possessives folded, aliases looked up, names added to the
#      question, linked facts as a third RRF list. No model call on the chat
#      path - there is no import of anything that could make one.
#   7. Both apps: recall improves in both because it happens on the PC. The
#      desktop lists an entry's facts ("About Priya", no summary); the phone
#      shows no graph, by rule (ARCHITECTURE.md section 8).
#
# LANGUAGES. The relation pattern ("my sister is called Priya", "my brother
# Arjun", "Mario is my manager") is ENGLISH only. Finding capitalised names
# works for any language written in Latin letters that capitalises names,
# but the list of capitalised words that are not names (sentence starters,
# days, months) is English, so another language gets more noise entries -
# which can only add candidates, never remove one. Names in other scripts
# are not found by these rules at all.

#: Stored in meta once a store's existing facts have been linked.
ENTITY_LAYER_VERSION = "1"

#: The kinds an entry may have. The no-model rules only ever say person or
#: pet (from the relation word); the optional model may say the rest.
ENTITY_KINDS = ("person", "pet", "place", "organisation", "project", "thing")

#: Chat recall uses the entity layer unless JARVIS_MEMORY_ENTITIES=0.
_ENTITY_RECALL = os.environ.get("JARVIS_MEMORY_ENTITIES", "1").strip().lower() not in (
    "0", "false", "off", "no")

#: An alias that names more than this many different entries ("friend",
#: with thirty friends in memory) does not say which one - it is ignored.
ALIAS_MAX_ENTITIES = 2

#: At most this many entries from one question.
ENTITY_HITS_MAX = 5

#: Graphiti's thresholds (graphiti_core/utils/maintenance/dedup_helpers.py,
#: Apache-2.0, checked 2026-09-25): names must be at least 6 characters or
#: two words, with character entropy of at least 1.5, and share at least 90%
#: of their three-letter chunks. What that catches, measured in
#: backend/test_memory_entities.py: a letter doubled or dropped at the END of
#: a long name ("Priya Sharma" / "Priya Sharmaa"). What it does not: a typo
#: inside a short name ("Priya" / "Priyaa" share 3 of 4 chunks, 0.75) - those
#: stay two entries, which is the safe side.
MERGE_JACCARD = 0.9
_MIN_NAME_LENGTH = 6
_MIN_TOKEN_COUNT = 2
_NAME_ENTROPY_THRESHOLD = 1.5

#: The review-queue `source` of an "are these the same?" card
#: (jarvis_extract.MERGE_SOURCE, memory-entities.patch).
MERGE_SOURCE = "entity_merge"

#: Relation words, English. Each maps to the kind of entry it names.
_PEOPLE = """
sister brother sis bro mum mom mother mam mummy mommy dad father daddy parent
wife husband partner spouse girlfriend boyfriend fiance fiancé fiancee fiancée
son daughter child kid baby stepson stepdaughter
aunt auntie aunty uncle cousin niece nephew godmother godfather goddaughter godson
grandma grandmother gran granny nan nana nanna grandad granddad grandfather grandpa
grandson granddaughter grandchild stepmum stepmom stepmother stepdad stepfather
stepsister stepbrother sister-in-law brother-in-law mother-in-law father-in-law
friend mate pal buddy colleague coworker co-worker boss manager supervisor
flatmate roommate housemate neighbour neighbor landlord landlady lodger tenant
doctor gp dentist therapist counsellor counselor physio optician vet
teacher tutor coach trainer mentor babysitter nanny cleaner accountant lawyer solicitor
""".split()
_PETS = "cat dog puppy kitten rabbit bunny hamster guinea-pig parrot budgie horse pony tortoise turtle pet".split()
_RELATIONS = {w: "person" for w in _PEOPLE}
_RELATIONS.update({w: "pet" for w in _PETS})

#: A modifier before a relation that means the name is NOT who that word
#: means now ("my former manager Marta"): then only "former manager" is an
#: alias, never "manager".
_PAST_MODIFIERS = {"former", "old", "previous", "ex", "late", "last", "first"}

#: Capitalised words that are not names on their own: pronouns and
#: determiners, titles, the owner, days and months, common sentence starters.
_NOT_NAMES = set("""
i i'm i've i'd i'll im ive owner owners the a an my our your his her their its this that these
those he she they we you it me him them us there here mr mrs ms miss mx dr prof sir madam
monday tuesday wednesday thursday friday saturday sunday mondays tuesdays wednesdays thursdays
fridays saturdays sundays weekend weekends today tomorrow yesterday tonight morning evening
january february march april may june july august september october november december
jan feb mar apr jun jul aug sep sept oct nov dec
yes no ok okay please thanks thank hi hello hey also maybe sometimes usually every each all
some most both when if after before since because remember note always never not once
""".split())

#: Titles stay on the front of a name: "Mrs Okafor" is one name, not "Okafor".
_TITLES = {"mr", "mrs", "ms", "miss", "mx", "dr", "prof", "sir"}

_UPPER = "A-ZÀ-ÖØ-Þ"
_WORD_CAP = rf"[{_UPPER}][\w'’\-]*"
#: A name: capitalised words, a title allowed first ("Dr Singh", "Mrs Okafor").
_NAME_RX = rf"(?:(?:Dr|Mr|Mrs|Ms|Miss|Mx|Prof)\.?\s+)?{_WORD_CAP}(?:\s+{_WORD_CAP})*"
_POSS_RX = r"(?i:my|our|the\s+owner['’]s|owner['’]s|owners['’])"
_REL_RX = "|".join(re.escape(w) for w in sorted(_RELATIONS, key=len, reverse=True))
_MOD_RX = r"(?:(?P<mod>(?i:[a-z][a-z\-]*))\s+)?"
#: "my sister is called Priya", "Owner's best friend Kofi", "my dentist, Dr Singh".
_REL_FORWARD = re.compile(
    rf"(?<![\w']){_POSS_RX}\s+{_MOD_RX}(?P<rel>(?i:{_REL_RX}))(?![\w\-])\s*,?\s*"
    r"(?:(?i:is\s+called|is\s+named|was\s+called|is|['’]s\s+name\s+is|called|named)\s+)?"
    rf"(?P<name>{_NAME_RX})")
#: "Mario is my manager".
_REL_BACKWARD = re.compile(
    rf"(?P<name>{_NAME_RX})\s+(?i:is)\s+{_POSS_RX}\s+{_MOD_RX}"
    rf"(?P<rel>(?i:{_REL_RX}))(?![\w\-])")
_TOKEN_RX = re.compile(r"[\w][\w'’\-]*|[.!?;:]")
_CONNECT = {"of", "de", "da", "del", "della", "van", "von", "der", "den", "la", "le", "du",
            "di", "dos", "das", "bin", "al"}


def _fold(text: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKC", str(text or "")).replace("’", "'").replace("‘", "'")


def _key_tokens(text: str) -> list:
    """Lowercased words with "'s" (and a bare trailing apostrophe) taken
    off - "Priya's" and "Priya" are one name, "sister's" is "sister". Not
    _words(): that strips ANY trailing s, so "Jonas" and "Jonas's" came out
    different. Single letters go; numbers stay ("RTX 2080")."""
    out = []
    for w in re.findall(r"[\w][\w'\-]*", _fold(text).lower()):
        w = re.sub(r"'s$", "", w).rstrip("'")
        if len(w) > 1 or w.isdigit():
            out.append(w)
    return out


def _name_key(text: str) -> str:
    """The normalised form two names must share EXACTLY to be one entry
    (the only merge that happens by itself), and the form every alias is
    stored and looked up in. A leading "the" does not count."""
    toks = _key_tokens(text)
    if len(toks) > 1 and toks[0] == "the":
        toks = toks[1:]
    return " ".join(toks)


def _grounded(text: str, phrase: str) -> bool:
    """Is `phrase` in `text` word for word (case and spacing aside)? The
    rule every name and alias must pass, whoever found it."""
    t = " ".join(_fold(text).lower().split())
    p = " ".join(_fold(phrase).lower().split())
    if not p:
        return False
    return re.search(r"(?<![\w])" + re.escape(p) + r"(?![\w])", t) is not None


def _entity_name_ok(name: str, key: str) -> bool:
    if not key or len(key) > 80 or len(key.split()) > 6:
        return False
    toks = key.split()
    if all(t in _NOT_NAMES or t in _STOP or t in _FRAME or t.isdigit() for t in toks):
        return False
    return any(ch.isalpha() for ch in name)


def _alias_ok(akey: str) -> bool:
    """An alias must say something: not a stop or framing word, not a
    name-shaped nothing, at most four words."""
    toks = akey.split()
    if not toks or len(toks) > 4:
        return False
    return not all(t in _STOP or t in _FRAME or t in _NOT_NAMES for t in toks)


def _query_grams(query: str) -> list:
    """The question's word runs of one to four words, in the order they
    appear, in the alias table's own form - only those with at least one
    word that is not a stop or framing word ("my" alone never matches)."""
    # A long message is looked at in full up to QUERY_TOKENS_MAX words, and
    # the list stays under SQLite's oldest limit on "?" marks (999).
    toks = _key_tokens(query)[:QUERY_TOKENS_MAX]
    out, seen = [], set()
    for n in (1, 2, 3, 4):
        for i in range(len(toks) - n + 1):
            g = toks[i:i + n]
            if all(t in _STOP or t in _FRAME for t in g):
                continue
            s = " ".join(g)
            if s not in seen:
                seen.add(s)
                out.append(s)
            if len(out) >= 800:
                return out
    return out


#: How many of a question's words the alias lookup reads.
QUERY_TOKENS_MAX = 200


def _clean_name(raw: str) -> str:
    """A name as found: spacing tidied, a trailing "'s" off, a leading
    "The" off."""
    name = " ".join(str(raw).split())
    name = re.sub(r"['’]s$", "", name).rstrip("'’")
    name = re.sub(r"^The\s+", "", name)
    return name.strip()


def _capitalised_names(text: str) -> list:
    """Runs of capitalised words that read as names: "Priya", "Hull City",
    "Priory Medical Centre", "The Left Hand of Darkness" (kept as "Left Hand
    of Darkness"). A single capitalised word that opens a sentence counts
    only when it is not a common English word there ("Priya's wedding"
    yes, "Tomorrow" no)."""
    toks = [(m.group(0), m.start()) for m in _TOKEN_RX.finditer(_fold(text))]
    out, i, start = [], 0, True
    while i < len(toks):
        tok, _ = toks[i]
        if tok in ".!?;:":
            start = True
            i += 1
            continue
        if not (tok[:1].isupper() and tok[:1].isalpha()):
            start = False
            i += 1
            continue
        run, j = [tok], i + 1
        while j < len(toks):
            t = toks[j][0]
            if t[:1].isupper() and t[:1].isalpha():
                run.append(t)
                j += 1
            elif t.isdigit() and len(run) >= 1:
                run.append(t)
                j += 1
            elif (t in _CONNECT and j + 1 < len(toks)
                  and toks[j + 1][0][:1].isupper() and toks[j + 1][0][:1].isalpha()):
                run += [t, toks[j + 1][0]]
                j += 2
            else:
                break
        at_start = start
        start = False
        i = j
        # Words at the front that are not part of a name: "Owner's", "The".
        while len(run) > 1 and _name_key(run[0]) in _NOT_NAMES and _name_key(run[0]) not in _TITLES:
            run = run[1:]
            at_start = False
        name = _clean_name(" ".join(run))
        key = _name_key(name)
        if not _entity_name_ok(name, key):
            continue
        if len(key.split()) == 1 and at_start and (key in _STOP or key in _FRAME
                                                    or key in _NOT_NAMES):
            continue
        out.append(name)
    return out


def find_entities(text: str) -> dict:
    """The no-model linker: {"names": [(name, kind)], "aliases": [(alias,
    name)]} for one fact's text. Fixed rules, no model, English relation
    words (see LANGUAGES above). Everything returned is in the text word
    for word; _link_fact checks that again anyway."""
    text = str(text or "")
    names: dict = {}
    aliases: list = []

    def add(name, kind=None):
        name = _clean_name(name)
        key = _name_key(name)
        if not _entity_name_ok(name, key):
            return None
        old = names.get(key)
        if old is None:
            names[key] = (name, kind)
        elif kind and not old[1]:
            names[key] = (old[0], kind)
        return names[key][0]

    for rx in (_REL_FORWARD, _REL_BACKWARD):
        for m in rx.finditer(_fold(text)):
            rel = m.group("rel").lower()
            mod = (m.group("mod") or "").lower()
            if mod in _RELATIONS or mod in ("is", "was", "called", "named"):
                mod = ""          # "my sister is ..." - no modifier there
            name = add(m.group("name"), _RELATIONS.get(rel))
            if name is None:
                continue
            if mod and mod not in _STOP:
                aliases.append((f"{mod} {rel}", name))
            if not mod or mod not in _PAST_MODIFIERS:
                aliases.append((rel, name))
    for name in _capitalised_names(text):
        add(name)
    return {"names": [v for v in names.values()], "aliases": aliases}


# Graphiti's matching, word for word in behaviour (dedup_helpers.py
# _normalize_name_for_fuzzy, _name_entropy, _has_high_entropy, _shingles,
# _jaccard_similarity). Apache-2.0; see THIRD-PARTY-NOTICES.txt.

def _fuzzy_form(name: str) -> str:
    s = re.sub(r"[\s]+", " ", str(name or "").lower()).strip()
    s = re.sub(r"[^a-z0-9' ]", " ", s).strip()
    return re.sub(r"[\s]+", " ", s)


def _name_entropy(fz: str) -> float:
    chars = fz.replace(" ", "")
    if not chars:
        return 0.0
    counts: dict = {}
    for ch in chars:
        counts[ch] = counts.get(ch, 0) + 1
    total = len(chars)
    return -sum((n / total) * math.log2(n / total) for n in counts.values())


def _has_high_entropy(fz: str) -> bool:
    if len(fz) < _MIN_NAME_LENGTH and len(fz.split()) < _MIN_TOKEN_COUNT:
        return False
    return _name_entropy(fz) >= _NAME_ENTROPY_THRESHOLD


def _shingles(fz: str) -> set:
    cleaned = fz.replace(" ", "")
    if len(cleaned) < 2:
        return {cleaned} if cleaned else set()
    return {cleaned[i:i + 3] for i in range(len(cleaned) - 2)}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def likely_same(a: str, b: str) -> bool:
    """Would these two names raise an "are these the same?" card? Not the
    same after normalising (that joins by itself), both specific enough,
    and at least MERGE_JACCARD of their three-letter chunks shared."""
    fa, fb = _fuzzy_form(a), _fuzzy_form(b)
    if _name_key(a) == _name_key(b) or fa == fb:
        return False
    if not (_has_high_entropy(fa) and _has_high_entropy(fb)):
        return False
    return _jaccard(_shingles(fa), _shingles(fb)) >= MERGE_JACCARD


def merge_card_text(a: str, b: str, kind: Optional[str] = None) -> str:
    """The card's words. Both names, as the facts wrote them - and nothing
    else from any fact."""
    who = "the same person" if kind in ("person", "pet") else "the same"
    return (f"Are these {who}? “{a}” and “{b}”. Saying yes joins them, so "
            f"a question about one also finds what Jarvis knows about the other. No fact is "
            f"changed or forgotten. Saying no keeps them apart, and Jarvis will not ask again.")


def _has_table(c, name: str) -> bool:
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                     (name,)).fetchone() is not None


def _wipe_merge_card(c, pid: int, now: float) -> int:
    """An "are these the same?" card that names an entry being deleted: its
    words (the two names) go, and if it is still waiting it is turned down
    - keeping it would keep the names. 1 if a card was changed."""
    if not _has_table(c, "proposals"):
        return 0
    cols = {r[1] for r in c.execute("PRAGMA table_info(proposals)")}
    if "text" not in cols:
        return 0
    cur = c.execute("UPDATE proposals SET text=? WHERE id=? AND text IS NOT ?",
                    (ERASED_TEXT, pid, ERASED_TEXT))
    if "state" in cols:
        if "decided" in cols:
            c.execute("UPDATE proposals SET state='rejected', decided=? WHERE id=?"
                      " AND state='pending'", (now, pid))
        else:
            c.execute("UPDATE proposals SET state='rejected' WHERE id=? AND state='pending'",
                      (pid,))
    return 1 if cur.rowcount else 0


def accept_merge_card(proposal_id: int) -> Optional[dict]:
    """jarvis_extract calls this when the owner accepts ONE "are these the
    same?" card (memory-entities.patch). Joins that pair, nothing else."""
    return store().merge_from_card(int(proposal_id))


def handle_entities_get() -> tuple:
    """GET /api/memory/entities -> (http status, reply). memory-entities.patch
    hands the route here after the token and origin checks. A read."""
    try:
        return 200, store().entities_view()
    except Exception as exc:
        return 500, {"error": type(exc).__name__}


# --------------------------------------------------------------------------
#   The singleton
# --------------------------------------------------------------------------

_store: Optional[MemoryStore] = None


def store(path: Optional[Path] = None) -> MemoryStore:
    """The one store. Eight call sites, all `jarvis_memory.store()`.

    Opening a second MemoryStore on the same file is not an error - SQLite
    handles it - but each one re-probes sqlite-vec and re-checks the embedder
    name, which is slow enough to notice on a per-request path.
    """
    global _store
    with _LOCK:
        if _store is None or (path is not None and Path(path) != _store.path):
            _store = MemoryStore(path)
        return _store


def reset() -> None:
    """Drop the singleton. For tests, which give each one its own database."""
    global _store
    with _LOCK:
        _store = None


if __name__ == "__main__":
    for k, v in store().status().items():
        print(f"  {k:<16} {v}")
