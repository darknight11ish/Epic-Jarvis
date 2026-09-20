"""A broken embedder must not write rows that can never be read.

    python3 test_embedding_guard.py

No pytest, no network, no model. Fake embedders that return exactly the bad
shapes, against real sqlite stores in a temp dir.

Why this exists: `_pack` is `struct.pack(f"{n}f", *v)`, which accepts NaN and
infinity silently. A NaN in facts_vec is not "a row that ranks badly", it is a
row no distance comparison can ever be true about - unreachable, with nothing
anywhere saying so. Jan documents the all-zero case for the same reason:
cosine divides by the norm, so a zero vector makes every score NaN rather than
merely inaccurate. Borrowed from evaluateEmbeddingVector in
janhq/jan extensions/llamacpp-extension/src/readiness.ts (Apache-2.0).
"""
import sys, tempfile, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# BACKEND is where the modules under test actually live - this folder
# in the dev container, $JARVIS_BACKEND on a real install. REPO is this
# repository. They used to be the same path and are not on the machine
# that runs Jarvis.
from _where import BACKEND, REPO, missing, explain

import jarvis_memory as M

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class Bad(M.Embedder):
    """Semantic, so the vector path is actually taken, and broken."""
    name = "broken-test-embedder"
    dim = 8
    semantic = True

    def __init__(self, maker):
        self.maker = maker

    def embed(self, texts):
        return [self.maker(t) for t in texts]


class Good(M.Embedder):
    name = "good-test-embedder"
    dim = 8
    semantic = True

    def embed(self, texts):
        out = []
        for t in texts:
            v = [0.0] * self.dim
            v[abs(hash(t)) % self.dim] = 1.0
            out.append(v)
        return out


def fresh(embedder):
    d = Path(tempfile.mkdtemp(prefix="jarvis-emb-"))
    s = M.MemoryStore(path=d / "memory.db", embedder=embedder)
    M._store = s
    return s


def vec_rows(store):
    if not store._vec_ok:
        return None
    c = store._connect()
    try:
        return c.execute("SELECT COUNT(*) FROM facts_vec").fetchone()[0]
    finally:
        c.close()


def embedded_flags(store):
    c = store._connect()
    try:
        return [r["embedded"] for r in c.execute("SELECT embedded FROM facts ORDER BY id")]
    finally:
        c.close()


def t_the_validator():
    """The predicate itself, before any database is involved."""
    u = M._usable_vector
    ok = [0.0] * 7 + [1.0]
    check("a unit vector is usable", u(ok, 8) is True)
    check("NaN is refused", u([float("nan")] + [0.0] * 7, 8) is False)
    check("+inf is refused", u([float("inf")] + [0.0] * 7, 8) is False)
    check("-inf is refused", u([float("-inf")] + [0.0] * 7, 8) is False)
    check("all zeros is refused", u([0.0] * 8, 8) is False)
    check("a near-zero vector is refused too",
          u([1e-30] * 8, 8) is False,
          "float error means exact zero is not the only way to get garbage")
    check("the wrong width is refused", u([1.0, 0.0], 8) is False)
    check("a non-list is refused", u("not a vector", 8) is False)
    check("a string inside is refused", u(["1.0"] + [0.0] * 7, 8) is False)
    check("a bool inside is refused", u([True] + [0.0] * 7, 8) is False,
          "bool is an int subclass and would pack as 1.0 silently")
    check("None is refused", u(None, 8) is False)


def t_a_nan_is_not_stored():
    s = fresh(Bad(lambda t: [float("nan")] + [0.0] * 7))
    if not s._vec_ok:
        check("a NaN row is not written", True, "sqlite-vec absent; skipped")
        return
    s.add_fact("Mario is allergic to penicillin")
    check("a NaN row is not written to facts_vec", vec_rows(s) == 0,
          f"facts_vec holds {vec_rows(s)} rows")
    check("and the fact is still stored", len(s.current_facts()) == 1)
    check("and it is left unembedded, so a backfill retries it",
          embedded_flags(s) == [0], f"got {embedded_flags(s)}")


def t_all_zeros_is_not_stored():
    s = fresh(Bad(lambda t: [0.0] * 8))
    if not s._vec_ok:
        check("an all-zero row is not written", True, "sqlite-vec absent; skipped")
        return
    s.add_fact("Mario prefers tabs over spaces")
    check("an all-zero row is not written to facts_vec", vec_rows(s) == 0)
    check("and the fact is still stored", len(s.current_facts()) == 1)


def t_a_good_vector_still_lands():
    """CONTROL. A guard that rejects everything would pass the tests above."""
    s = fresh(Good())
    if not s._vec_ok:
        check("a good vector is stored", True, "sqlite-vec absent; skipped")
        return
    s.add_fact("Mario's main editor is Vim")
    check("a good vector IS written", vec_rows(s) == 1,
          f"facts_vec holds {vec_rows(s)} rows")
    check("and the row is flagged embedded", embedded_flags(s) == [1])


def t_it_is_counted_and_said_out_loud():
    s = fresh(Bad(lambda t: [float("nan")] + [0.0] * 7))
    if not s._vec_ok:
        check("status reports the count", True, "sqlite-vec absent; skipped")
        return
    s.add_fact("one")
    s.add_fact("two")
    st = s.status()
    check("status counts them", st.get("bad_vectors") == 2, f"status={st}")
    check("and explains what it means in words",
          "not a number" in str(st.get("bad_vectors_note", "")))
    check("and says the facts are still findable",
          "keyword" in str(st.get("bad_vectors_note", "")))


def t_status_stays_quiet_when_nothing_is_wrong():
    s = fresh(Good())
    s.add_fact("Mario drives a 1998 Volvo")
    st = s.status()
    check("no bad_vectors key when there are none", "bad_vectors" not in st,
          f"status={st}")


def t_a_broken_query_falls_back_to_keywords():
    """The query side. Silence here is worse than an error.

    A garbage query vector does not fail - it ranks the whole table by
    distance-from-nonsense, and RRF then lets those rows outrank the real
    keyword hits.
    """
    s = fresh(Good())
    if not s._vec_ok:
        check("a broken query still answers from FTS5", True, "sqlite-vec absent; skipped")
        return
    s.add_fact("Mario is allergic to penicillin and carries an EpiPen")
    s.add_fact("Mario prefers tabs over spaces in Go")
    # Now break only the query: same store, an embedder that returns NaN.
    s.embedder = Bad(lambda t: [float("nan")] + [0.0] * 7)
    hits = s.search("penicillin", k=3)
    check("a broken query still answers, from FTS5", len(hits) >= 1,
          f"got {hits}")
    if hits:
        check("and answers correctly", "penicillin" in hits[0]["text"],
              f"top hit was {hits[0]['text']!r}")


def main():
    for fn in (t_the_validator, t_a_nan_is_not_stored, t_all_zeros_is_not_stored,
               t_a_good_vector_still_lands, t_it_is_counted_and_said_out_loud,
               t_status_stays_quiet_when_nothing_is_wrong,
               t_a_broken_query_falls_back_to_keywords):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
