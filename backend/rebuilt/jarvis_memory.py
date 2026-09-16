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

  2. Bi-temporal facts. "Mario lives at X" with no dates means that when he
     moves, both addresses sit there as equals. Every fact carries valid_from
     and valid_to. A fact that is contradicted is RETIRED - its valid_to is
     set and it records what replaced it - not deleted, so "where do I live"
     returns the current answer and "where did I live last year" also works.
     This is the Graphiti idea done natively in the one SQLite file the
     project already uses, because Graphiti wants a graph database server and
     the whole point here is one file, no daemons.

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
     false, so the fact could never be returned by any query. _finite() below.
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


def _finite(v: list[float]) -> bool:
    """Is this vector safe to store?

    THE BUG THIS EXISTS FOR, from embedding-guard.patch. `_pack` will happily
    serialise NaN - struct does not care - and a NaN row is then unreachable
    FOREVER, because every distance comparison against NaN is false. The fact
    is in the database, counts in status(), and can never be returned by any
    query. An all-zero vector is the same class of problem from the other
    direction: it is equidistant from everything, so it either never ranks or
    always does.

    Silent, permanent, and invisible in every count. Checked before the write.
    """
    if not v:
        return False
    total = 0.0
    for x in v:
        if not isinstance(x, (int, float)) or not math.isfinite(x):
            return False
        total += float(x) * float(x)
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


def _content_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[\w\-]+", str(text).lower()) if w not in _STOP]


# --------------------------------------------------------------------------
#   Embedders
# --------------------------------------------------------------------------

class HashEmbedder:
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
                v[hash(w) % self.dim] += 1.0
            n = math.sqrt(sum(x * x for x in v))
            out.append([x / n for x in v] if n else v)
        return out


class FastEmbedder:
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
            out.append(vec if _finite(vec) else [0.0] * self.dim)
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

    def __init__(self, path: Optional[Path] = None, embedder=None) -> None:
        self.path = Path(path or DOCS_DB)
        self.embedder = embedder or _make_embedder()
        self._vec_ok = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    # ---- plumbing ---------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=30)
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
            return True
        except Exception:
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
                    retired_by INTEGER,         -- the fact that replaced this one
                    embedded   INTEGER NOT NULL DEFAULT 0,
                    meta       TEXT
                )""")
            c.execute("CREATE INDEX IF NOT EXISTS ix_facts_valid ON facts(valid_to, valid_from)")
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
                if self._vec_ok:
                    c.execute("DELETE FROM facts_vec")
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
                c.execute("UPDATE facts SET valid_to=?, retired_by=? WHERE id=? AND valid_to IS NULL",
                          (now, fid, supersedes))
            self._embed_rows(c, [(fid, text)])
            c.commit()
        return fid

    #: The name jarvis_hud reaches for in one place. Same call, kept so a
    #: caller written against either name works.
    add_fact = add

    def retire(self, fact_id: int, replaced_by: Optional[int] = None) -> bool:
        with _LOCK, closing(self._connect()) as c:
            cur = c.execute("UPDATE facts SET valid_to=?, retired_by=? WHERE id=? AND valid_to IS NULL",
                            (time.time(), replaced_by, fact_id))
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
            cur = c.execute("UPDATE facts SET text=?, embedded=0 WHERE id=?", (text, fact_id))
            if cur.rowcount:
                self._embed_rows(c, [(int(fact_id), text)])
            c.commit()
            return cur.rowcount > 0

    def _embed_rows(self, c, rows: list[tuple[int, str]]) -> int:
        """Embed and index. Returns how many rows were actually written.

        A count, not None: backfill_embeddings loops until this stops making
        progress, and a version that returned nothing would either loop for
        ever or stop after one batch depending on how the caller guessed.
        """
        if not rows or not self._vec_ok:
            return 0
        try:
            vecs = self.embedder.embed([t for _, t in rows])
        except Exception:
            return 0
        done = 0
        for (fid, _), v in zip(rows, vecs):
            v = list(v)
            if not _finite(v):
                # Leave embedded=0. The row stays findable by WORDS, and
                # backfill will try it again when a better model is installed.
                # Storing it would make the fact permanently unreachable.
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
                rows = c.execute("SELECT id, text FROM facts WHERE embedded=0 LIMIT ?",
                                 (batch,)).fetchall()
                if not rows:
                    break
                wrote = self._embed_rows(c, [(r["id"], r["text"]) for r in rows])
                c.commit()
                if not self._vec_ok or not wrote:
                    # No progress. Without this the loop is infinite whenever a
                    # row cannot be embedded at all - which is exactly what a
                    # NaN-producing model causes.
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
        at = time.time() if at is None else at
        with _LOCK, closing(self._connect()) as c:
            ranks: dict[int, float] = {}
            # words
            try:
                words = _content_words(query)
                if words:
                    q = " OR ".join(f'"{w}"' for w in words)
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
                    if _finite(list(qv)):
                        rows = c.execute(
                            "SELECT fact_id, distance FROM facts_vec WHERE embedding MATCH ?"
                            " ORDER BY distance LIMIT ?", (_pack(qv), candidates)).fetchall()
                        for r, row in enumerate(rows, 1):
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
            f["score"] = round(score, 5); f["current"] = f["valid_to"] is None
            out.append(f)
            if len(out) >= k:
                break
        return out

    def find_one(self, description: str, at: Optional[float] = None) -> Optional[int]:
        """Which single existing fact does this describe? None if unsure.

        THE MOST IMPORTANT FUNCTION IN THIS FILE, and the reason
        memory-safety.patch exists. `_accept` used to resolve a correction's
        free-text `replaces` with search(k=1) and retire whatever came back.
        search has no relevance floor, so it ALWAYS came back with something:
        accepting "Mario drives a 1998 Volvo" retired "Mario prefers tabs over
        spaces in Go", and the reply was {"ok": true} either way.

        Two bars, both must clear:
          * at least two overlapping CONTENT words (stopwords do not count), and
          * 50% containment - half the description's content words appear in
            the candidate.

        RETURNS None RATHER THAN A GUESS, and None means "store the new fact,
        retire nothing". Two facts that disagree can be sorted out later by a
        human looking at the memory pane. A deleted allergy cannot: retire()
        has no way back.
        """
        want = set(_content_words(description))
        if len(want) < 2:
            # One word cannot identify a fact. "address", "allergy", "car" -
            # each matches a dozen rows and picking one is the original bug.
            return None
        best_id, best_score = None, 0.0
        for row in self.search(description, k=5, at=at):
            have = set(_content_words(row["text"]))
            overlap = want & have
            if len(overlap) < 2:
                continue
            containment = len(overlap) / len(want)
            if containment < 0.5:
                continue
            if containment > best_score:
                best_id, best_score = row["id"], containment
        return best_id

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
        for h in hist:
            h["current"] = h["valid_to"] is None
        return hist

    def current_facts(self, limit: int = 400) -> list[dict]:
        with _LOCK, closing(self._connect()) as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM facts WHERE valid_to IS NULL ORDER BY id DESC LIMIT ?", (limit,))]

    def status(self) -> dict:
        with _LOCK, closing(self._connect()) as c:
            total = c.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            current = c.execute(
                "SELECT COUNT(*) FROM facts WHERE valid_to IS NULL OR valid_to > ?",
                (time.time(),)).fetchone()[0]
            pending = c.execute("SELECT COUNT(*) FROM facts WHERE embedded=0").fetchone()[0]
        return {"db": str(self.path), "facts": total, "current": current, "retired": total - current,
                "embedder": self.embedder.name, "semantic": self.embedder.semantic,
                "vector_search": self._vec_ok, "unembedded": pending}


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
