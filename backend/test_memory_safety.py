"""Executable reproductions of the five destructive memory defects.

Each test is written as the audit found it: the inputs that produced data
loss, and the behaviour that is required instead. Several are CONTROLS - they
fail if the corresponding fix is removed, which is the only way a patch like
this stays applied.

    python3 test_memory_safety.py

No pytest, no network, no model. It builds real sqlite stores in a temp dir.
"""
import os, sys, json, shutil, sqlite3, tempfile, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# BACKEND is where the modules under test actually live - this folder
# in the dev container, $JARVIS_BACKEND on a real install. REPO is this
# repository. They used to be the same path and are not on the machine
# that runs Jarvis.
from _where import BACKEND, REPO, explain
import _base  # noqa: E402

#: WHICH copy of the files this suite reads. The owner's install when
#: `JARVIS_BACKEND` names one, `backend/` when the file is here, and
#: otherwise the PUBLISHED BASE (`jarvis-backend/`, the state the whole
#: patch stack left at its last re-take) - so the required backend job runs
#: these checks for real instead of skipping the suite. backend/_base.py
#: holds the rule; the line printed below says which folder answered.
BASE = _base.folder("jarvis_extract.py")
if BASE is not None:
    BACKEND = BASE
    _base.put_on_path(BASE)
    _base.say(BACKEND, "jarvis_extract.py")


def missing(*names):
    """`_where.missing`, asked of the folder this run really reads."""
    return _base.missing(BACKEND, *names)

import jarvis_memory as M
import jarvis_extract as X

FAILED = []
PASSED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def fresh(embedder=None):
    d = Path(tempfile.mkdtemp(prefix="jarvis-mem-"))
    s = M.MemoryStore(path=d / "memory.db", embedder=embedder)
    M._store = s
    return s, d


class Fake384(M.Embedder):
    """Stands in for bge-small: a different name and a different width."""
    name = "BAAI/bge-small-en-v1.5"
    dim = 384
    semantic = True

    def embed(self, texts):
        out = []
        for t in texts:
            v = [0.0] * self.dim
            for i, ch in enumerate(str(t).lower()):
                v[(ord(ch) * (i + 7)) % self.dim] += 1.0
            n = sum(x * x for x in v) ** 0.5 or 1.0
            out.append([x / n for x in v])
        return out


class Broken(M.Embedder):
    name = "broken"
    dim = 256
    semantic = True

    def embed(self, texts):
        raise RuntimeError("model went away mid-write")


# ---------------------------------------------------------------- 1. replaces
def t_replaces_never_guesses():
    s, d = fresh()
    s.add_fact("Mario prefers tabs over spaces in Go")
    s.add_fact("Mario is allergic to penicillin and carries an EpiPen")
    s.add_fact("Mario's main editor is Vim")

    # The three strings the audit drove through _accept. Each retired a real,
    # correct, unrelated fact because search() always returns its top-1.
    for probe in ("the user has a pet iguana named Steve who lives in Peru",
                  # One shared common word is not an identification: this
                  # reduces to {"mario"}, which is in most of the store.
                  "where Mario is",
                  "the old GPU note",
                  "zzzzzz qqqqqq"):
        hit = s.find_one(probe)
        check(f"find_one refuses to guess: {probe!r}", hit is None,
              f"returned {hit['text']!r}" if hit else "")

    # CONTROL: a real correction must still resolve, or supersession is dead.
    hit = s.find_one("Mario's main editor is Vim")
    check("CONTROL find_one resolves a real correction",
          hit is not None and "Vim" in hit["text"],
          f"got {hit!r}")
    hit = s.find_one("Mario uses Vim as his editor")
    check("CONTROL find_one resolves a paraphrased correction",
          hit is not None and "Vim" in hit["text"], f"got {hit!r}")
    # Two content words that genuinely name the fact are enough; a single one
    # is not, even when it is the right fact.
    check("a one-word overlap is refused even when plausible",
          s.find_one("Mario's allergy") is None,
          "matched on 'mario' alone")
    shutil.rmtree(d, ignore_errors=True)


def t_accept_retires_only_what_was_shown():
    s, d = fresh()
    keep = s.add_fact("Mario prefers tabs over spaces in Go")
    old = s.add_fact("Mario's main editor is Vim")

    reply = json.dumps({"facts": [
        {"text": "Mario drives a 1998 Volvo",
         "replaces": "the user has a pet iguana named Steve", "confidence": 0.9},
        {"text": "Mario's main editor is VS Code",
         "replaces": "Mario's main editor is Vim", "confidence": 0.9},
    ]})
    rows = X.propose([{"role": "user", "content": "hi"}], llm=lambda _p: reply)
    check("both proposals queued", len(rows) == 2, f"got {len(rows)}")

    volvo = [r for r in rows if "Volvo" in r["text"]][0]
    editor = [r for r in rows if "VS Code" in r["text"]][0]
    check("an unresolvable `replaces` retires nothing",
          volvo["replaces_id"] is None, f"targets fact {volvo['replaces_id']}")
    check("a real correction names its target on the card",
          editor["replaces_id"] == old and editor["replaces_text"] == "Mario's main editor is Vim",
          f"{editor['replaces_id']} / {editor['replaces_text']!r}")

    for r in rows:
        X.decide(r["id"], True)
    check("the unrelated fact survived the car", s.get(keep)["valid_to"] is None,
          "the tabs preference was retired by a fact about a Volvo")
    check("CONTROL the corrected fact was retired", s.get(old)["valid_to"] is not None)
    shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------- 2. the embedder swap
def _can_do_vectors(where):
    """Can a vec0 table be created HERE at all? Asked of sqlite, not the store.

    THE BRANCH MUST NOT BE CHOSEN BY THE THING UNDER TEST (2026-10-28).
    `status()["vector_search"]` is itself one of the claims this suite checks, so
    a store that answered True where nothing works - the exact failure
    `_connect`'s docstring describes - would otherwise pick its own branch and be
    judged by checks written for the other one. This probe asks sqlite directly,
    on a throwaway database, and the test then compares the store's claim
    against the answer. Measured, not assumed, on both sides.
    """
    c = sqlite3.connect(str(Path(where) / "vec-probe.db"))
    try:
        if not M.MemoryStore._load_vec(c):
            return False
        c.execute("CREATE VIRTUAL TABLE probe USING vec0("
                  "id INTEGER PRIMARY KEY, embedding float[2])")
        return True
    except Exception:
        return False
    finally:
        c.close()


def t_embedder_swap_does_not_brick_writes():
    """The model arrives after facts were already stored: writes keep working.

    THE DEFECT THIS PINS (memory-safety.patch). A 256-dim stand-in was replaced
    by a 384-dim model and `facts_vec` stayed DECLARED AT THE OLD WIDTH, because
    the rebuild used DELETE where it needed DROP. Every later insert of a
    differently sized vector then failed silently inside `_embed_rows`:
    unembedded only ever climbed, `backfill_embeddings` returned 0 for ever, and
    `status()` said "vector_search": true throughout. The fix is the
    DROP-and-recreate in `_init`; this test is the control that keeps it.

    WHICH HALF OF IT RUNS IS MEASURED, NOT ASSUMED (2026-10-28). The required
    `backend` job installs no sqlite-vec - `ci.yml` says so twice, at :273 and
    :803: "the memory ones (onnxruntime and the meaning model, sqlite-vec) are
    left out on purpose - the suites use a hash embedder and must pass without
    them". There `_load_vec` raises on `import sqlite_vec`, `_vec_ok` is False,
    `facts_vec` is never created, and a check demanding `float[384]` in its DDL
    cannot pass on ANY machine without the extension. Measured on 2026-10-28,
    one tree, both ways: with sqlite-vec every check passes; without it the
    three vector ones fail with exactly CI's detail - DDL "", "backfilled 0",
    "4 unembedded" - which is the red this suite went and got when the base
    fallback let it run in CI for the first time.

    SO EACH CHECK ASKS THE BRANCH THIS MACHINE IS REALLY IN - MEASURED FROM
    SQLITE IN `_can_do_vectors`, NEVER FROM THE STORE'S OWN CLAIM - AND SAYS
    WHICH IN ITS OWN NAME. Without vectors the width invariant is still tested:
    through the width the store now ENFORCES (`_usable_vector` against the new
    dim), the claim `status()` makes about it, and the table it must not pretend
    to have. That is the "a capability that reports itself available and does
    nothing" rule `_connect`'s docstring was written for. No check is skipped
    either way, the count is the same either way, and the line printed below
    says out loud which half this machine ran, so a green line is never read as
    a proof it did not earn.
    """
    d = Path(tempfile.mkdtemp(prefix="jarvis-mem-"))
    db = d / "memory.db"
    s1 = M.MemoryStore(path=db, embedder=M.HashEmbedder())
    old_ids = [s1.add_fact(t) for t in ("Mario runs Linux Mint",
                                        "Mario uses vim keybindings",
                                        "Mario drinks oat milk")]
    before = s1.status()

    s2 = M.MemoryStore(path=db, embedder=Fake384())          # the model arrived
    st = s2.status()
    # MEASURED, NOT ASSUMED - and never from `st["vector_search"]`, which is a
    # claim under test below (see _can_do_vectors).
    vec = _can_do_vectors(d)
    print("      vectors in use here: "
          + ("yes - the rebuild and the backfill below are the vector ones"
             if vec else
             "NO (no sqlite-vec, as in the required backend job) - the checks below "
             "prove the store says so and still works, NOT that facts_vec was rebuilt"))

    c = sqlite3.connect(db)
    try:
        row = c.execute("SELECT sql FROM sqlite_master WHERE name='facts_vec'").fetchone()
        ddl = row[0] if row else ""
        # Every vector of the old model is stale whichever half runs: this
        # UPDATE is outside `if self._vec_ok` in _init, and it is what makes
        # the rebuild mean something rather than what the rebuild does.
        stale = [c.execute("SELECT embedded FROM facts WHERE id=?",
                           (i,)).fetchone()[0] for i in old_ids]
        name_now = c.execute("SELECT v FROM meta WHERE k='embedder'").fetchone()[0]
    finally:
        c.close()

    # THE CLAIM, AGAINST THE MEASURED ANSWER, WHICHEVER BRANCH IS TAKEN. This is
    # the check that catches a store saying True where nothing works - the
    # failure _connect()'s docstring records ("a capability that reports itself
    # available and does nothing"), and the one a branch chosen from that same
    # claim could never see.
    check("status reports vector search only where a vec0 table can be made",
          st["vector_search"] == vec,
          f"status says {st['vector_search']!r}, and vec0 "
          f"{'can' if vec else 'cannot'} be made here")

    if vec:
        check("facts_vec is rebuilt at the new width", "float[384]" in ddl,
              f"DDL still says: {ddl}")
    else:
        # No sqlite-vec: there must be no table at all (the claim is checked
        # above). The WIDTH is still checked: the store must now expect 384
        # floats and refuse the old 64, which is the half of the defect a
        # machine without the extension can measure.
        check("the store expects the new width with no table to hold it",
              not ddl
              and M._usable_vector([0.1] * 384, int(s2.embedder.dim))
              and not M._usable_vector([0.1] * 64, int(s2.embedder.dim)),
              f"DDL {ddl!r}, dim {s2.embedder.dim}")

    check("the model change is recorded and every old vector is marked stale",
          name_now == Fake384.name and stale == [0, 0, 0],
          f"meta says {name_now!r}, embedded flags {stale}")

    ok, err = True, ""
    try:
        s2.add_fact("Mario moved to Berlin in March")
    except Exception as exc:
        ok, err = False, f"{type(exc).__name__}: {exc}"
    check("a write after the model arrives succeeds", ok, err)

    n = s2.backfill_embeddings()
    if vec:
        check("backfill re-embeds the rows stored before the model", n >= 3,
              f"backfilled {n}")
        check("nothing is left unembedded", s2.status()["unembedded"] == 0,
              f"{s2.status()['unembedded']} unembedded")
    else:
        # Nothing CAN be embedded without the extension. The honest answers are
        # "no progress claimed" and a count that says every fact is waiting -
        # never a 0 that would read as "all embedded".
        check("backfill claims no progress it did not make, with no vector store",
              n == 0, f"backfilled {n}")
        check("every fact is reported unembedded rather than claimed embedded",
              s2.status()["unembedded"] == s2.status()["facts"] == before["facts"] + 1,
              f"{s2.status()['unembedded']} unembedded of {s2.status()['facts']} facts")
    check("CONTROL no facts were lost in the swap",
          s2.status()["facts"] == before["facts"] + 1)
    shutil.rmtree(d, ignore_errors=True)


def t_write_never_reports_failure_for_a_stored_fact():
    d = Path(tempfile.mkdtemp(prefix="jarvis-mem-"))
    s = M.MemoryStore(path=d / "memory.db", embedder=Broken())
    ok, err = True, ""
    try:
        s.add_fact("Mario uses vim keybindings in every editor")
    except Exception as exc:
        ok, err = False, f"{type(exc).__name__}: {exc}"
    check("a failing embedder does not raise out of add_fact", ok, err)
    check("CONTROL the fact is stored exactly once", s.status()["facts"] == 1,
          f"{s.status()['facts']} rows")
    shutil.rmtree(d, ignore_errors=True)


def t_backfill_terminates():
    d = Path(tempfile.mkdtemp(prefix="jarvis-mem-"))
    s = M.MemoryStore(path=d / "memory.db", embedder=Broken())
    s.add_fact("one fact that cannot be embedded")
    import threading
    done = threading.Event()
    def run():
        try:
            s.backfill_embeddings()
        finally:
            done.set()
    threading.Thread(target=run, daemon=True).start()
    check("backfill terminates when the embedder is broken", done.wait(10),
          "still spinning after 10s - the while True never breaks")
    shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------- 3. the relevance floor
CORPUS = [
    "Mario is allergic to peanuts and carries an EpiPen",
    "Mario takes 20mg of citalopram each morning",
    "Mario's bank is Monzo, account ending 4417",
    "The home NAS is a Synology DS920+ with four 8TB drives",
    "Rapier2D is the physics engine picked for the Isoforge prototype",
    "The car is a 2014 Honda Jazz, MOT due in November",
    "Mario's wife Anna has a birthday on the 3rd of March",
    "Mario is vegetarian but eats fish on holiday",
]


def t_off_topic_queries_inject_nothing():
    # The floor's own logic, measured with the deterministic embedder, the same
    # way the rest of this file pins it. Left on the default, this test chose
    # the REAL embedding model wherever one is installed, and bge-small scores
    # unrelated short texts around 0.87-0.99 cosine distance against a floor of
    # 1.0 - so the outcome depended on whether a model happened to be on the
    # machine (CI has none) rather than on the floor. That real-model separation
    # is a tuning question for backend/eval_memory.py, not something this test
    # can settle (2026-10-03).
    s, d = fresh(M.HashEmbedder())
    for t in CORPUS:
        s.add_fact(t)
    for q in ("explain how a python decorator works",
              "why is the sky blue",
              "what causes thunder",
              "what is the capital of France",
              "write me a haiku about rain",
              "zzzz qqqq"):
        hits = s.search(q, k=5)
        check(f"off-topic returns nothing: {q!r}", hits == [],
              "injected: " + "; ".join(h["text"][:40] for h in hits))

    # CONTROLS: the floor must not have simply turned retrieval off.
    for q, want in (("am I allergic to anything", "peanuts"),
                    ("which physics engine did I pick", "Rapier2D"),
                    ("when is the MOT due", "MOT")):
        hits = s.search(q, k=5)
        check(f"CONTROL on-topic still retrieves: {q!r}",
              any(want in h["text"] for h in hits),
              "got: " + ("; ".join(h["text"][:40] for h in hits) or "nothing"))
    shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------ 4. no auto-accept
def t_no_auto_accept_even_when_configured():
    s, d = fresh()
    real = X._cfg
    X._cfg = lambda k, dflt: True if k in ("auto_accept", "setup_complete", "enabled") else real(k, dflt)
    try:
        reply = json.dumps({"facts": [
            {"text": "Mario only drinks oat milk", "replaces": None, "confidence": 0.99}]})
        rows = X.propose([{"role": "user", "content": "hi"}], llm=lambda _p: reply)
        check("auto_accept writes no fact", s.status()["facts"] == 0,
              f"{s.status()['facts']} facts written with no human decision")
        check("the proposal is still waiting for a human",
              rows and rows[0]["state"] == "pending")
        check("setup_status reports auto_accept off, because it is",
              X.setup_status()["auto_accept"] is False)
        # CONTROL: an explicit decision still works.
        X.decide(rows[0]["id"], True)
        check("CONTROL an accepted proposal is written", s.status()["facts"] == 1)
    finally:
        X._cfg = real
    shutil.rmtree(d, ignore_errors=True)


# ----------------------------------------------------- 5. the pre-queue filter
def t_filter_keeps_statements_and_drops_questions():
    s, d = fresh()
    keep = ["Allergic to penicillin", "Wife: Dana", "Uses vim", "Is vegetarian",
            "Can't eat gluten", "Does not drink alcohol", "Hates phone calls",
            "Should always use metric units", "Do not suggest Docker, ever",
            "Is on call every third weekend", "Wants replies in British English"]
    drop = ["Are you sure", "What is the plan", "Whose birthday is 3 March",
            "Do you want coffee?", "How does this work"]
    reply = json.dumps({"facts": [{"text": t, "replaces": None, "confidence": 0.9}
                                  for t in keep + drop]})
    rows = X.propose([{"role": "user", "content": "hi"}], llm=lambda _p: reply)
    got = {r["text"] for r in rows}
    for t in keep:
        check(f"kept: {t!r}", t in got, "silently discarded before the queue")
    for t in drop:
        check(f"dropped: {t!r}", t not in got, "a question reached the queue")
    shutil.rmtree(d, ignore_errors=True)


def t_bad_confidence_does_not_truncate_the_batch():
    s, d = fresh()
    reply = json.dumps({"facts": [
        {"text": "good fact number one here", "confidence": 0.9},
        {"text": "good fact number two here", "confidence": "high"},
        {"text": "good fact number three here", "confidence": 0.9},
    ]})
    rows = X.propose([{"role": "user", "content": "hi"}], llm=lambda _p: reply)
    check("a non-numeric confidence loses nothing", len(rows) == 3,
          f"{len(rows)} of 3 queued - the batch was truncated at the bad value")
    shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    for fn in (t_replaces_never_guesses, t_accept_retires_only_what_was_shown,
               t_embedder_swap_does_not_brick_writes,
               t_write_never_reports_failure_for_a_stored_fact,
               t_backfill_terminates, t_off_topic_queries_inject_nothing,
               t_no_auto_accept_even_when_configured,
               t_filter_keeps_statements_and_drops_questions,
               t_bad_confidence_does_not_truncate_the_batch):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
