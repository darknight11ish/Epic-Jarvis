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
from _where import BACKEND, REPO, missing, explain

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
def t_embedder_swap_does_not_brick_writes():
    d = Path(tempfile.mkdtemp(prefix="jarvis-mem-"))
    db = d / "memory.db"
    s1 = M.MemoryStore(path=db, embedder=M.HashEmbedder())
    for t in ("Mario runs Linux Mint", "Mario uses vim keybindings", "Mario drinks oat milk"):
        s1.add_fact(t)
    before = s1.status()

    s2 = M.MemoryStore(path=db, embedder=Fake384())          # the model arrived
    ddl = ""
    with sqlite3.connect(db) as c:
        row = c.execute("SELECT sql FROM sqlite_master WHERE name='facts_vec'").fetchone()
        ddl = row[0] if row else ""
    check("facts_vec is rebuilt at the new width", "float[384]" in ddl,
          f"DDL still says: {ddl}")

    ok, err = True, ""
    try:
        s2.add_fact("Mario moved to Berlin in March")
    except Exception as exc:
        ok, err = False, f"{type(exc).__name__}: {exc}"
    check("a write after the model arrives succeeds", ok, err)

    n = s2.backfill_embeddings()
    check("backfill re-embeds the rows stored before the model", n >= 3, f"backfilled {n}")
    check("nothing is left unembedded", s2.status()["unembedded"] == 0,
          f"{s2.status()['unembedded']} unembedded")
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
    s, d = fresh()
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
