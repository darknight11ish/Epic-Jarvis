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

     A fact is never deleted, so "where do I live" returns the current answer,
     "where did I live last year" works, and "what did you think you knew in
     June" is answerable from the same rows.

     THE ONE EXCEPTION IS erase() ("Erase the words", the owner's decision of
     2026-09-24). It wipes a fact's WORDS for good - the text, its search
     entry, its meaning vector, and every copy of the text elsewhere in this
     file - and keeps the row, its id and its dates, so the history still
     shows that something was here and when. The row is never removed.

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
#   The store
# --------------------------------------------------------------------------

class MemoryStore:

    #: Did the last add(supersedes=...) actually retire what it was aiming at?
    #: A CLASS default, because add() only assigns it when a supersede is
    #: attempted - so anything reading it on a fresh store (the memory pane
    #: rendering a correction card) got AttributeError instead of "no".
    last_supersede_failed = False

    def __init__(self, path: Optional[Path] = None, embedder=None) -> None:
        self.path = Path(path or DOCS_DB)
        self.embedder = embedder or _make_embedder()
        self._vec_ok = False
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
        text = " ".join(str(text).split())
        if not text:
            raise ValueError("refusing to store an empty fact")
        now = time.time()
        with _LOCK, closing(self._connect()) as c:
            cur = c.execute(
                "INSERT INTO facts (text, source, created, valid_from, meta)"
                " VALUES (?, ?, ?, ?, ?)",
                (text, source, now, valid_from or now, json.dumps(meta or {})))
            fid = cur.lastrowid
            if supersedes:
                # Both axes. A correction arriving now means we learned now
                # (retired_at), and - absent anything better - that the old
                # fact stopped being true now too (valid_to). Callers that
                # know the real date call retire() with it before adding.
                done = c.execute(
                    "UPDATE facts SET valid_to=?, retired_at=?, retired_by=?"
                    " WHERE id=? AND valid_to IS NULL",
                    (now, now, fid, supersedes))
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
            c.commit()
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
            cur = c.execute("UPDATE facts SET valid_to=?, retired_at=?, retired_by=?"
                            " WHERE id=? AND valid_to IS NULL",
                            (vt, ra, replaced_by, fact_id))
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
            if row is None or row["valid_to"] is not None:
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
            c.commit()
            return cur.rowcount > 0

    def erase(self, fact_id: int) -> Optional[dict]:
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

        Returns None if there is no such fact, else
        {"id", "erased_at", "already_erased", "retired_now", "file_clean",
        "copies"}. Never the words.
        """
        fid = int(fact_id)
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
                # again, so it is retired now too - which retire() alone
                # would not do (it matches valid_to IS NULL only).
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
                "retired_now": retired_now, "file_clean": file_clean, "copies": copies}

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

    def search(self, query: str, k: int = 8, candidates: int = 50,
               at: Optional[float] = None, include_retired: bool = False) -> list[dict]:
        """Words and meaning, fused with reciprocal rank fusion."""
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
            valid = f["valid_from"] <= at and (f["valid_to"] is None or f["valid_to"] > at)
            if not valid and not include_retired:
                continue
            f["score"] = round(score, 5)
            # Was `f["valid_to"] is None`, which disagreed with the validity
            # line above it for a valid_to in the FUTURE: the fact counted as
            # valid and was returned, then arrived flagged not-current.
            # Unreachable while retire() could only stamp now; reachable the
            # moment it takes a date. Same rule in both places.
            f["current"] = f["valid_to"] is None or f["valid_to"] > at
            out.append(f)
            if len(out) >= k:
                break
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
        for cand in self.search(text, k=5):
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
        out = {"db": str(self.path), "facts": total, "current": current,
               "retired": total - current,
               "embedder": self.embedder.name, "semantic": self.embedder.semantic,
               "vector_search": self._vec_ok, "unembedded": pending,
               "erased": erased}
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
                    "device", "tainted", "confidence")

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
    only), `auto_learn_notes` (why a card stayed a card - a fixed sentence,
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
