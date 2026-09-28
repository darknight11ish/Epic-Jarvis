"""eval_memory.py - Jarvis's memory self-test. Does search find the right fact?

    python eval_memory.py                      # the full run, about 2-10 minutes
    python eval_memory.py --sizes 0,100        # a quick one
    python eval_memory.py --words-only         # as on day one, before fastembed
    python eval_memory.py --out C:\\somewhere   # where the two result files go
    python eval_memory.py --against old.json   # better / worse than an earlier run;
                                               # exit 1 if recall@5, a wrong version
                                               # or a learner case got worse
    python eval_memory.py --locomo             # ONLY LoCoMo's "link two facts"
                                               # questions (milestone 13; see
                                               # "LoCoMo's multi-hop questions")

WHAT IT DOES, IN PLAIN WORDS

It makes up a person - about 60 facts in backend/eval/golden_facts.jsonl,
including people and what the owner calls them, an address that changed,
facts that were replaced, "tea, not coffee", dates and preferences - and
asks about 140 questions from backend/eval/golden_questions.jsonl whose
right answers are known. About 25 of them have NO answer in memory ("what
is my dog called?"): for those, the right number of facts to bring back is
zero. Then it buries the made-up person under 100, 1,000 and 10,000 filler
facts, two ways - about unrelated things, and about the same things but
other people (the hard case) - and asks again.

NEVER YOUR DATA. The store it fills is a new file in a temporary folder,
deleted at the end. JARVIS_MEMORY_DB is pointed at that file before the
memory module is even imported, and the store is opened by that path, so
your real memory.db is never opened. No chat model is asked anything, and
nothing is sent anywhere. (The one download it can cause is fastembed
fetching its embedding model, the same one Jarvis uses, if this PC does not
have it yet.)

WHAT IT MEASURES

  recall@1 / recall@5   how often the right fact is first / in the five
                        facts a chat turn gets (5 is JARVIS_MEMORY_K)
  MRR, nDCG@5           how high up the right fact is, on average
  replaced came back    how often an OLD version (the address before the
                        move) is among the five for a question about now
  "don't know"          how many facts come back for a question memory
                        cannot answer - every one of them is a wrong fact
                        put in front of the model - and how often none do
  past questions        "where did I live before?": does chat recall bring
                        the retired fact back, labelled (jarvis_past.py)
  as-of questions       "what did Jarvis believe on 15 January?":
                        search(known_at=...)
  the word floor        every number above twice: with the word-search
                        floor off (the old behaviour) and on - and a sweep
                        that chooses the floor on half the questions and
                        reports it on the other half, run the way a chat
                        turn recalls (the entity layer on; the memory
                        review of 2026-09-27, I6)
  the distance floor    a sweep of JARVIS_MEMORY_MAX_DISTANCE from 0.6 to
                        1.2 - only with the real embedder, because without
                        it there is no meaning search to put a floor on -
                        chosen on half the questions and reported on the
                        other half, like the word floor (I6)
  time questions        "what phone did I have in March?": a fact that was
                        not true then counts as a wrong version only when it
                        came back unlabelled (the memory review's B1)
  speed and size        search time (p50 and p95), adding a fact, embedding
                        the backlog, and the database file with its WAL
  "Always keep in mind" a pinned fact on a question that shares no words
                        with it ("Owner is vegetarian" / "what should I
                        cook tonight?"): is it among the five by search
                        alone, and is it in the prompt with the pin
                        (jarvis_memory.with_profile) - and what the pinned
                        list costs in characters
  the entity layer      (memory wave 3) every number with the floor on,
                        again with "who is my sister?" switched on: the
                        alias table, the names added to the question, and
                        the linked facts as a third list - as chat recall
                        now runs. People and alias questions are counted on
                        their own line, and so are the "don't know" facts
                        it adds

The embedder is the real one (fastembed) when this PC has it, and the
words-only fallback otherwise; the output says which, on its first line.
Numbers from the words-only fallback say nothing about meaning search.

The scoring - recall_any@k and nDCG@k - follows LongMemEval's
src/retrieval/eval_utils.py (https://github.com/xiaowu0162/LongMemEval,
MIT, Copyright (c) 2024 Di Wu; THIRD-PARTY-NOTICES.txt). No data from it is
used: the persona, the questions and the filler are all written here.

Runs from this repository. It is not copied to the backend folder.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
import statistics
import sys
import tempfile
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = HERE / "eval"

#: "Now", for questions that name a date ("in July", "last year"). Fixed, so
#: the answers the golden file expects do not change with the day it is run.
EVAL_NOW_TEXT = "2026-09-24"

K = 5                                   # JARVIS_MEMORY_K's default
FLOORS = [round(0.1 * i, 1) for i in range(0, 10)]
DISTANCES = [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2]
ANSWERABLE = {"single", "update", "date", "preference", "negation", "person",
              "paraphrase", "alias"}

#: "Always keep in mind" (memory-profile.patch): a golden fact, and a
#: question that needs it but shares none of its words. Search finds facts
#: by words and meaning, so with words alone these are expected to be
#: missed; a pinned fact is in every prompt whatever the question.
PIN_CASES = [
    ("f16", "what should I cook tonight?"),
    ("f17", "can you suggest a snack for the train?"),
    ("f15", "what should I order at the cafe this morning?"),
]

#: "Said again" (milestone 12): golden facts the made-up owner has said
#: again since, and how many times - the kind of thing a person repeats.
#: Chosen BEFORE the tie-break was measured, and not tuned on its numbers.
#: Recorded on every store (MemoryStore.said_again, a day apart after the
#: fact was told); nothing but the tie-break reads them, so every other
#: number here is the same with or without them. Only facts still in use -
#: said_again() refuses a replaced one, as it does in Jarvis.
SAID_AGAIN = {"f11": 3, "f15": 2, "f16": 2, "f20": 1, "f13": 1, "f02": 2,
              "f29": 1, "f32": 1}


# ------------------------------------------------------------- the store --

def _load_memory(scratch: Path):
    """Import jarvis_memory and jarvis_past with the store aimed at `scratch`.

    JARVIS_MEMORY_DB is set BEFORE the import, because the module reads it
    at import time. jarvis_framework is replaced by a stand-in whose config
    folder is the scratch folder and whose audit log writes nothing, so not
    even a log line lands in your real ~/.openjarvis."""
    os.environ["JARVIS_MEMORY_DB"] = str(scratch / "memory.db")
    fw = types.ModuleType("jarvis_framework")
    fw.CONFIG_DIR = scratch
    fw.LOG_DIR = scratch
    fw.audit_log = lambda *a, **k: None
    fw.load_framework = lambda *a, **k: {}
    sys.modules["jarvis_framework"] = fw
    real = os.environ.get("JARVIS_BACKEND")
    paths = ([real] if real and (Path(real) / "jarvis_memory.py").is_file() else []) \
        + [str(HERE / "rebuilt"), str(HERE)]
    for p in reversed(paths):
        sys.path.insert(0, p)
    import jarvis_memory as M          # noqa: E402
    import jarvis_past as P            # noqa: E402
    return M, P


def _day(text: str) -> float:
    """Noon on that day, local time - noon, so no time zone moves it a day."""
    y, m, d = (int(x) for x in text.split("-"))
    return time.mktime((y, m, d, 12, 0, 0, 0, 0, -1))


def _read_jsonl(path: Path) -> list:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


class _Clock:
    """The real `time` module, except that time() says `now` when it is set.
    Put in place of jarvis_memory's `time` while the made-up person's facts
    are added, so each one is added ON THE DAY it was told - through the
    real add(), the way a chat turn adds it."""

    def __init__(self, real):
        self._real = real
        self.now = None

    def time(self):
        return self._real.time() if self.now is None else self.now

    def __getattr__(self, name):
        return getattr(self._real, name)


def _put_golden(M, st, facts: list) -> dict:
    """Add the made-up person's facts, oldest told first, each through the
    real MemoryStore.add() on the day the file says it was told - and a
    replacement with supersedes= the fact it replaced, as accepting a
    correction card does. So what add() does with the words (from memory
    idea 4 on: a "true from" date the words give, and older news never
    replacing newer) is what is measured, not a copy of it here.

    Only jarvis_memory's own clock is moved, and only while adding: search
    and recall below run on the real one. The golden file's "retired" date
    is the day the replacement was told (test_memory_recall checks that),
    so a store without idea 4 gets exactly the dates the self-test always
    gave it."""
    ids = {}
    replaced = {f["replaced_by"]: f["id"] for f in facts if f.get("replaced_by")}
    clock = _Clock(M.time)
    M.time = clock
    try:
        for f in sorted(facts, key=lambda f: (f["told"], f["id"])):
            clock.now = _day(f["told"])
            old = replaced.get(f["id"])
            ids[f["id"]] = st.add(f["text"], source="eval",
                                  supersedes=ids.get(old) if old else None)
    finally:
        M.time = clock._real
    return ids


# ------------------------------------------------------------- the filler --

_TOPICS = ["astronomy", "knitting", "chess openings", "origami", "beekeeping",
           "sailing", "pottery", "calligraphy", "birdwatching", "geology",
           "woodturning", "archery", "fencing", "rowing", "orienteering",
           "kite making", "bonsai", "stargazing", "fossil hunting", "sourdough",
           "watercolours", "juggling", "bookbinding", "lock picking", "falconry",
           "canal boats", "vintage radios", "typography", "cartography", "glassblowing",
           "tai chi", "model railways", "crosswords", "sudoku", "metal detecting",
           "macrame", "embroidery", "botany", "meteorology", "volcanoes",
           "lighthouses", "windmills", "Roman coins", "medieval castles", "tide pools",
           "moss gardens", "puppetry", "magic tricks", "ham radio", "ice sculpture"]
_ADJ = ["relaxing", "fiddly", "fascinating", "expensive", "noisy", "calming",
        "tricky", "old-fashioned", "clever", "messy", "elegant", "slow",
        "surprising", "underrated", "overrated", "peaceful", "dusty", "precise",
        "colourful", "ancient"]
_THINGS = ["magnifying glass", "notebook", "toolkit", "field guide", "tripod",
           "set of brushes", "starter kit", "manual", "map", "lantern",
           "pair of binoculars", "sketchbook", "compass", "tin box", "stopwatch",
           "wooden stand", "spirit level", "whistle", "rucksack", "thermos"]
_NEUTRAL = [
    "Owner finds {t} {a}",
    "Owner once watched a documentary about {t}",
    "Owner bought a {a} {th} for {t}",
    "Owner thinks {t} looks {a}",
    "Owner read an article about {a} {t}",
    "Owner might try {t} one day",
    "Owner keeps a {th} for {t}",
    "Owner heard a podcast about {t} that was {a}",
    "Owner was given a {th} about {t}",
    "Owner said {t} is {a}",
]

_FIRST = ["Ava", "Ben", "Chloe", "Dan", "Ella", "Finn", "Grace", "Harry", "Isla",
          "Jack", "Katie", "Liam", "Mia", "Noah", "Olivia", "Pete", "Quinn", "Rosa",
          "Sam", "Tara", "Umar", "Vera", "Will", "Xena", "Yusuf", "Zara", "Aisha",
          "Bruno", "Carla", "Dmitri", "Esme", "Farid", "Gemma", "Hugo", "Ines",
          "Jamal", "Leah", "Mateo", "Nina", "Oscar", "Paula", "Rhys", "Sofia",
          "Theo", "Uma", "Viktor", "Wendy", "Yara", "Zoe", "Adam"]
_LAST = ["Brown", "Clarke", "Davies", "Evans", "Foster", "Green", "Hughes",
         "Ibrahim", "Jones", "Khan", "Lewis", "Morgan", "Novak", "Owen", "Patel",
         "Reid", "Shaw", "Taylor", "Walsh", "Young"]
_REL = ["colleague", "cousin", "friend", "old classmate", "neighbour's son",
        "gym buddy", "flatmate from uni", "team-mate", "friend from work", "pen pal"]
_TOWNS = ["Bristol", "Leeds", "Cardiff", "Durham", "Bath", "Hull", "Derby",
          "Exeter", "Carlisle", "Norwich", "Lincoln", "Chester", "Bangor", "Perth",
          "Dundee", "Wakefield", "Whitby", "Kendal", "Ripon", "Selby"]
_PETS = ["dog", "cat", "rabbit", "parrot", "tortoise", "hamster", "horse", "goldfish"]
_PETNAMES = ["Rex", "Pickle", "Mango", "Luna", "Scout", "Pepper", "Nugget", "Bramble",
             "Ziggy", "Olive", "Pip", "Maple"]
_DRINKS = ["coffee", "green tea", "hot chocolate", "sparkling water", "cola",
           "oat milk lattes", "herbal tea", "orange juice"]
_CARS = ["a blue Ford Fiesta", "a white Tesla", "a silver Honda Jazz", "a black Audi",
         "a green Mini", "a yellow Citroen", "a red Volvo", "an old Land Rover"]
_BOOKS = ["Dune", "Middlemarch", "The Hobbit", "Beloved", "Circe", "Emma",
          "Rebecca", "Stoner", "Jane Eyre", "The Road"]
_JOBS = ["teacher", "plumber", "accountant", "chef", "pharmacist", "architect",
         "bus driver", "vet", "electrician", "librarian"]
_SPORTS = ["tennis", "badminton", "football", "rugby", "netball", "squash",
           "golf", "cricket"]
_DAYS = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays",
         "Saturdays", "Sundays"]
_BANDS = ["Blur", "Coldplay", "Oasis", "Pulp", "Muse", "Doves", "Keane", "Wet Leg"]
_ALLERGY = ["cats", "pollen", "shellfish", "dust", "wasps", "penicillin"]
_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]
_SAME = [
    "Owner's {r} {n} lives in {town}",
    "Owner's {r} {n} has a {pet} called {pn}",
    "Owner's {r} {n} drinks {drink}",
    "Owner's {r} {n} drives {car}",
    "Owner's {r} {n} is reading {book}",
    "Owner's {r} {n} has a birthday on {d} {mon}",
    "Owner's {r} {n} works as a {job}",
    "Owner's {r} {n} plays {sport} on {day}",
    "Owner's {r} {n} says their favourite band is {band}",
    "Owner's {r} {n} is allergic to {allergy}",
    "Owner's {r} {n} has a manager called {n2}",
    "Owner's {r} {n} moved house to {town}",
]


def filler(kind: str, seed: int = 7):
    """An endless, repeatable stream of made-up facts, no line twice.

    neutral     about the owner, but unrelated things (hobbies nobody asks
                about). Measures what sheer volume does.
    same_topic  the SAME subjects as the golden facts - where someone lives,
                a pet called something, a car, a manager - but always about a
                named OTHER person, so none contradicts the made-up owner.
                The hard case: "what is my dog called?" now has a dog called
                Rex in memory that is not the owner's."""
    rnd = random.Random(f"{kind}-{seed}")
    seen = set()
    while True:
        if kind == "neutral":
            s = rnd.choice(_NEUTRAL).format(t=rnd.choice(_TOPICS), a=rnd.choice(_ADJ),
                                            th=rnd.choice(_THINGS))
        else:
            s = rnd.choice(_SAME).format(
                r=rnd.choice(_REL), n=f"{rnd.choice(_FIRST)} {rnd.choice(_LAST)}",
                n2=f"{rnd.choice(_FIRST)} {rnd.choice(_LAST)}", town=rnd.choice(_TOWNS),
                pet=rnd.choice(_PETS), pn=rnd.choice(_PETNAMES), drink=rnd.choice(_DRINKS),
                car=rnd.choice(_CARS), book=rnd.choice(_BOOKS), d=rnd.randint(1, 28),
                mon=rnd.choice(_MONTHS), job=rnd.choice(_JOBS), sport=rnd.choice(_SPORTS),
                day=rnd.choice(_DAYS), band=rnd.choice(_BANDS), allergy=rnd.choice(_ALLERGY))
        if s in seen:
            continue
        seen.add(s)
        yield s, _day("2025-01-01") + rnd.random() * (_day("2026-09-20") - _day("2025-01-01"))


def _add_filler(st, stream, n: int) -> dict:
    """Add n filler facts. Words are indexed as they go in; the embedding is
    done afterwards in batches (backfill_embeddings), the way a store that
    was filled before fastembed downloaded catches up - and timed."""
    if n <= 0:
        return {"added": 0, "add_ms_per_fact": None, "embed_s": None}
    vec = st._vec_ok
    st._vec_ok = False             # words now, meaning in one batch below
    rows = []
    t0 = time.perf_counter()
    try:
        for _ in range(n):
            text, when = next(stream)
            rows.append((st.add(text, source="filler"), when))
    finally:
        st._vec_ok = vec
    add_ms = (time.perf_counter() - t0) * 1000 / n
    c = st._connect()
    try:
        c.executemany("UPDATE facts SET created=?, valid_from=? WHERE id=?",
                      [(w, w, i) for i, w in rows])
    finally:
        c.close()
    embed_s = None
    if vec:
        t0 = time.perf_counter()
        st.backfill_embeddings(batch=64)
        embed_s = round(time.perf_counter() - t0, 2)
    return {"added": n, "add_ms_per_fact": round(add_ms, 2), "embed_s": embed_s}


# ------------------------------------------------------------ the scoring --

def dcg(rel: list, k: int) -> float:
    """Discounted cumulative gain at k - LongMemEval's dcg(), without numpy."""
    rel = rel[:k]
    if not rel:
        return 0.0
    return rel[0] + sum(r / math.log2(i + 1) for i, r in enumerate(rel[1:], start=2))


def ndcg(got: list, answers: set, k: int) -> float:
    """nDCG@k with binary relevance, as LongMemEval's ndcg()."""
    ideal = dcg([1] * min(len(answers), k), k)
    return dcg([1 if g in answers else 0 for g in got], k) / ideal if ideal else 0.0


def _takes(fn, name: str) -> bool:
    import inspect
    try:
        return name in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def _entity_search(st):
    """Does this jarvis_memory.py have the entity layer (search(entities=))?"""
    return _takes(st.search, "entities")


class StandInReranker:
    """NOT the real re-ranker. A stand-in for where the model cannot be
    downloaded (this repository's container): it scores a fact by the share
    of the question's content words it holds. It proves the wiring - the
    pool, the re-order, k kept, the timing hook - and says NOTHING about
    how much the real cross-encoder helps. Only a run with the real model
    (on the PC, `--reranker auto`) measures that."""

    name = "stand-in: word overlap (not the real model)"

    def __init__(self, M):
        self._words = M._words

    def score(self, query, texts):
        want = self._words(query)
        return [len(want & self._words(t)) / (1.0 + len(self._words(t)) ** 0.5)
                for t in texts]


def _score(M, P, st, qs: list, gid: dict, now: float, rerank: bool = False,
           said_again: bool = False) -> dict:
    """Every question once, as chat recall asks it. Returns per-question
    rows. Whether the entity layer is on is M._ENTITY_RECALL, set by the
    caller (jarvis_past.recall asks for it; the flag switches it). Whether
    a re-ranker is loaded is the caller's too (jarvis_memory.set_reranker):
    jarvis_past.recall asks for it whenever one is; `rerank` asks for it on
    the other questions, as that call does. `said_again` asks for the
    "said again" tie-break the same way (jarvis_past.recall always asks; it
    only acts while M._SAID_AGAIN_TIEBREAK is on)."""
    rows = []
    ent = _entity_search(st)
    rr = {"rerank": True} if rerank and _takes(st.search, "rerank") else {}
    if said_again and _takes(st.search, "said_again"):
        rr["said_again"] = True
    for q in qs:
        # "Don't know" questions through chat recall itself (the memory
        # review's I6): what a chat turn would put in front of the model,
        # past facts for a question about the past included.
        if q["type"] in ("past", "time", "abstain"):
            res = P.recall(st, q["q"], k=K, now=now)
        elif q["type"] == "belief":
            res = st.search(q["q"], k=K, known_at=_day(q["known_at"]))
        elif ent:
            res = st.search(q["q"], k=K, entities=True, **rr)
        else:
            res = st.search(q["q"], k=K, **rr)
        got = [gid.get(r["id"], "filler") for r in res]
        ans = set(q["answers"])
        first = next((i for i, g in enumerate(got) if g in ans), None)
        stale = set(q.get("stale", []))
        if q["type"] == "time":
            # "What phone did I have in March?": a fact that was NOT true
            # then is a wrong version only if it came back as if it were -
            # unlabelled. A retired one says "(no longer true since ...)",
            # a later current one "(true since ...)" (jarvis_past, the
            # memory review's B1); the golden file lists both kinds.
            wrong = any(g in stale and not (r.get("past") or r.get("later"))
                        for g, r in zip(got, res))
        else:
            wrong = any(g in stale for g in got)
        rows.append({
            "id": q["id"], "type": q["type"], "split": q["split"], "n": len(got),
            "answerable": bool(ans),
            "hit1": bool(ans) and first == 0,
            "hit5": bool(ans) and first is not None,
            "rr": 0.0 if first is None else 1.0 / (first + 1),
            "ndcg": ndcg(got, ans, K) if ans else 0.0,
            "stale": wrong,
            # "multi": every fact the answer needs is among the five.
            "all5": bool(ans) and ans <= set(got),
            "labelled": q["type"] != "past" or any(
                r.get("past") and "no longer true since" in r.get("text", "") for r in res),
            "chars": sum(len(r.get("text", "")) for r in res),
            "got": [r["id"] for r in res],
        })
    return {r["id"]: r for r in rows}


def _summary(rows: dict, split: str = None) -> dict:
    rs = [r for r in rows.values() if split is None or r["split"] == split]
    cur = [r for r in rs if r["type"] in ANSWERABLE]
    ab = [r for r in rs if r["type"] == "abstain"]
    past = [r for r in rs if r["type"] == "past"]
    bel = [r for r in rs if r["type"] == "belief" and r["answerable"]]
    bel_none = [r for r in rs if r["type"] == "belief" and not r["answerable"]]
    multi = [r for r in rs if r["type"] == "multi"]
    tq = [r for r in rs if r["type"] == "time"]
    n = len(cur) or 1

    def pct(x, d):
        return round(100.0 * x / d, 1) if d else None
    return {
        "questions": len(cur),
        "recall_at_1": pct(sum(r["hit1"] for r in cur), len(cur)),
        "recall_at_5": pct(sum(r["hit5"] for r in cur), len(cur)),
        "hits_at_5": sum(r["hit5"] for r in cur),
        "mrr": round(sum(r["rr"] for r in cur) / n, 3),
        "ndcg_at_5": round(sum(r["ndcg"] for r in cur) / n, 3),
        "replaced_came_back": sum(r["stale"] for r in cur),
        "dont_know_questions": len(ab),
        "dont_know_facts_avg": round(statistics.mean([r["n"] for r in ab]), 2) if ab else None,
        "dont_know_facts_total": sum(r["n"] for r in ab),
        "dont_know_none_pct": pct(sum(r["n"] == 0 for r in ab), len(ab)),
        "past_found": sum(r["hit5"] for r in past),
        "past_questions": len(past),
        "past_labelled": sum(r["labelled"] and r["hit5"] for r in past),
        "as_of_found": sum(r["hit5"] for r in bel),
        "as_of_questions": len(bel),
        "as_of_wrong_version": sum(r["stale"] for r in bel),
        "as_of_before_told_facts": sum(r["n"] for r in bel_none),
        "recall_tokens_avg": round(statistics.mean([r["chars"] for r in cur]) / 4) if cur else 0,
        "people_questions": len([r for r in cur if r["type"] in ("person", "alias")]),
        "people_found": sum(r["hit5"] for r in cur if r["type"] in ("person", "alias")),
        "alias_questions": len([r for r in cur if r["type"] == "alias"]),
        "alias_found": sum(r["hit5"] for r in cur if r["type"] == "alias"),
        # The bigger self-test (memory idea 2, 2026-09-26). Counted on their
        # own lines, so every number above stays comparable with older runs.
        "multi_questions": len(multi),
        "multi_all_found": sum(r["all5"] for r in multi),
        "multi_any_found": sum(r["hit5"] for r in multi),
        "time_questions": len(tq),
        "time_found": sum(r["hit5"] for r in tq),
        "time_wrong_version": sum(r["stale"] for r in tq),
    }


def _hits_total(rows: dict, split: str) -> int:
    """Every right fact found in the five, current, past and as-of."""
    return sum(r["hit5"] for r in rows.values() if r["split"] == split)


def _timings(st, qs: list, reps: int = 3, entities: bool = False,
             rerank: bool = False) -> dict:
    lat = []
    kw = {"entities": True} if entities and _entity_search(st) else {}
    if rerank and _takes(st.search, "rerank"):
        kw["rerank"] = True
    for _ in range(reps):
        for q in qs:
            t0 = time.perf_counter()
            st.search(q["q"], k=K, **kw)
            lat.append((time.perf_counter() - t0) * 1000)
    lat.sort()
    return {"search_p50_ms": round(statistics.median(lat), 2),
            "search_p95_ms": round(lat[int(0.95 * (len(lat) - 1))], 2)}


def _pin_effect(M, P, st, gid: dict, now: float) -> dict:
    """PIN_CASES: is the fact among the K a chat turn gets by search alone,
    and with it pinned (jarvis_memory.with_profile, as the chat turn calls
    it)? The pins are taken off again, so nothing else measured here sees
    them. {"available": False} on a jarvis_memory.py without the list."""
    if not hasattr(M, "with_profile") or not hasattr(st, "pin"):
        return {"available": False, "cases": []}
    ids = {v: k for k, v in gid.items()}
    cases = []
    for fact, q in PIN_CASES:
        fid = ids[fact]
        alone = [r["id"] for r in P.recall(st, q, k=K, now=now)]
        st.pin(fid)
        try:
            chosen = M.with_profile(st, P.recall(st, q, k=K, now=now), K)
            chars = sum(len(p["text"]) for p in st.profile())
        finally:
            st.unpin(fid)
        cases.append({"fact": fact, "question": q, "search_alone": fid in alone,
                      "with_pin": fid in [r["id"] for r in chosen],
                      "facts_in_prompt": len(chosen), "pinned_chars": chars})
    return {"available": True, "cases": cases, "limit": M.PROFILE_LIMIT}


def _put_said_again(st, facts: list, ids: dict) -> dict:
    """SAID_AGAIN, recorded through the real MemoryStore.said_again: {golden
    id: rows written}. Empty on a memory without it."""
    if not hasattr(st, "said_again"):
        return {}
    told = {f["id"]: f["told"] for f in facts}
    out = {}
    for g, n in SAID_AGAIN.items():
        out[g] = sum(bool(st.said_again(ids[g], _day(told[g]) + 86400.0 * (i + 1), "typed"))
                     for i in range(n))
    return out


def _moved(a: dict, b: dict) -> dict:
    """Between two _score runs: questions whose facts came back in another
    order, and whose SET of facts differs (the tie-break must never do that)."""
    order = sum(a[q]["got"] != b[q]["got"] for q in a)
    sets = sum(sorted(a[q]["got"]) != sorted(b[q]["got"]) for q in a)
    return {"questions_reordered": order, "questions_other_facts": sets}


def _db_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.parent.glob(path.name + "*") if p.is_file())


# ------------------------------------------------------------ the run --

def _pick_reranker(M, how: str):
    """(re-ranker or None, what was used or why not). `how`: "auto" - the
    real model if fastembed can load it here (it may download it once), "off",
    or "stand-in" (StandInReranker)."""
    if how == "off":
        return None, "off (--reranker off)"
    if not hasattr(M, "set_reranker"):
        return None, "this jarvis_memory.py has no re-ranker"
    if how == "stand-in":
        return StandInReranker(M), StandInReranker.name
    if hasattr(M, "FastReranker"):
        # Loaded directly, not through reranker(): the backend keeps it off
        # until this self-test shows it helps (JARVIS_MEMORY_RERANK), and
        # the self-test is how that is found out.
        try:
            m = M.FastReranker()
        except ImportError as exc:
            return None, (f"the real model could not be loaded: {type(exc).__name__}: "
                          f"fastembed is not installed or has no re-ranker")
        except Exception as exc:
            return None, (f"the real model could not be loaded: {type(exc).__name__}: "
                          f"the re-ranking model could not be loaded")
        return m, getattr(m, "name", "the real model")
    m = M.reranker(wait=True)
    if m is None:
        return None, "the real model could not be loaded: " + str(
            M.reranker_status().get("why") or "unknown")
    return m, getattr(m, "name", "the real model")


def run(sizes: list, words_only: bool, scratch: Path, *, learner_model=None,
        ollama="http://127.0.0.1:11434", reranker: str = "auto") -> dict:
    M, P = _load_memory(scratch)
    rr_model, rr_what = _pick_reranker(M, reranker)
    if hasattr(M, "set_reranker"):
        # Every number below is taken WITHOUT a re-ranker except the
        # "reranked" line, so they stay comparable with the runs before it.
        M.set_reranker(None)
    facts = _read_jsonl(EVAL / "golden_facts.jsonl")
    qs = _read_jsonl(EVAL / "golden_questions.jsonl")
    now = _day(EVAL_NOW_TEXT)
    configured_floor = M._MIN_WORD_SHARE
    configured_distance = M._MAX_VEC_DISTANCE
    # The entity layer is measured on its own line ("entities"); every
    # other number here is taken with it OFF, so they stay comparable with
    # the runs before it existed.
    has_entities = hasattr(M, "_ENTITY_RECALL")
    entities_configured = bool(getattr(M, "_ENTITY_RECALL", False))
    M._ENTITY_RECALL = False
    # The "said again" tie-break (milestone 12) likewise: its own line only,
    # off for every other number, whatever this PC's setting is.
    has_tiebreak = hasattr(M, "_SAID_AGAIN_TIEBREAK")
    tiebreak_configured = bool(getattr(M, "_SAID_AGAIN_TIEBREAK", False))
    M._SAID_AGAIN_TIEBREAK = False
    out = {"levels": [], "floor_sweep": [], "distance_sweep": []}
    for kind in ("neutral", "same_topic"):
        d = scratch / kind
        d.mkdir(parents=True, exist_ok=True)
        db = d / "memory.db"
        emb = M.HashEmbedder() if words_only else M._make_embedder()
        st = M.MemoryStore(db, embedder=emb)
        stat = st.status()
        out["embedder"] = stat["embedder"]
        out["semantic"] = bool(stat["semantic"])
        out["vector_search"] = bool(stat["vector_search"])
        out["memory_module"] = str(Path(M.__file__).resolve())
        ids = _put_golden(M, st, facts)
        out["said_again_recorded"] = _put_said_again(st, facts, ids)
        gid = {v: k for k, v in ids.items()}
        stream = filler(kind)
        have = 0
        for size in sorted(sizes):
            grow = _add_filler(st, stream, size - have)
            have = size
            total = st.status()["facts"]
            level = {"filler": kind, "filler_facts": size, "facts": total, **grow}
            for name, floor in (("before", 0.0), ("after", configured_floor)):
                M._MIN_WORD_SHARE = floor
                rows = _score(M, P, st, qs, gid, now)
                level[name] = _summary(rows)
                level[name]["word_floor"] = floor
                if name == "after":
                    level["misses_after"] = sorted(
                        r["id"] for r in rows.values()
                        if r["answerable"] and not r["hit5"])
            M._MIN_WORD_SHARE = configured_floor
            timed = [q for q in qs if q["type"] in ANSWERABLE | {"abstain"}]
            M._MIN_WORD_SHARE = 0.0
            level["before"].update(_timings(st, timed))
            M._MIN_WORD_SHARE = configured_floor
            level.update(_timings(st, timed))
            if has_entities:
                # "Who is my sister?": the floor as configured, and the
                # entity layer on - the way a chat turn now recalls.
                M._ENTITY_RECALL = True
                try:
                    rows = _score(M, P, st, qs, gid, now)
                    level["entities"] = _summary(rows)
                    level["entities"].update(_timings(st, timed, entities=True))
                    level["misses_entities"] = sorted(
                        r["id"] for r in rows.values() if r["answerable"] and not r["hit5"])
                    level["entities"]["linked_entities"] = st.status().get("entities")
                    if has_tiebreak:
                        # Milestone 12: the same, with "said again" breaking
                        # exact ties - kept only if this line beats the one
                        # above on the PC.
                        M._SAID_AGAIN_TIEBREAK = True
                        try:
                            tb = _score(M, P, st, qs, gid, now, said_again=True)
                            level["said_again"] = _summary(tb)
                            level["said_again"].update(_moved(rows, tb))
                            level["misses_said_again"] = sorted(
                                r["id"] for r in tb.values()
                                if r["answerable"] and not r["hit5"])
                        finally:
                            M._SAID_AGAIN_TIEBREAK = False
                    if rr_model is not None:
                        # Memory idea 1: the same, with the re-ranker on - the
                        # way a chat turn recalls once it has loaded.
                        M.set_reranker(rr_model)
                        try:
                            rows = _score(M, P, st, qs, gid, now, rerank=True)
                            level["reranked"] = _summary(rows)
                            level["reranked"].update(
                                _timings(st, timed, entities=True, rerank=True))
                            level["misses_reranked"] = sorted(
                                r["id"] for r in rows.values()
                                if r["answerable"] and not r["hit5"])
                        finally:
                            M.set_reranker(None)
                finally:
                    M._ENTITY_RECALL = False
            level["db_bytes"] = _db_bytes(db)
            level["pinned"] = _pin_effect(M, P, st, gid, now)
            out["levels"].append(level)
            # Both sweeps below run on the path a chat turn really uses (the
            # memory review's I6): the entity layer on, when this memory has
            # it. They used to run with it off, so the floors were tuned on
            # a search no chat turn makes.
            M._ENTITY_RECALL = has_entities
            try:
                # the word-floor sweep: every floor, both halves of the questions
                for floor in FLOORS:
                    M._MIN_WORD_SHARE = floor
                    rows = _score(M, P, st, qs, gid, now)
                    out["floor_sweep"].append({
                        "filler": kind, "filler_facts": size, "floor": floor,
                        "tune": {"hits": _hits_total(rows, "tune"), **_summary(rows, "tune")},
                        "test": {"hits": _hits_total(rows, "test"), **_summary(rows, "test")}})
                M._MIN_WORD_SHARE = configured_floor
                # the distance-floor sweep: only where there is meaning
                # search - and, like the word floor, chosen on the tune half
                # and reported on the test half (choose_distance).
                if stat["semantic"] and stat["vector_search"]:
                    for dist in DISTANCES:
                        M._MAX_VEC_DISTANCE = dist
                        rows = _score(M, P, st, qs, gid, now)
                        s = _summary(rows)
                        out["distance_sweep"].append({
                            "filler": kind, "filler_facts": size, "max_distance": dist,
                            "recall_at_5": s["recall_at_5"],
                            "dont_know_facts_avg": s["dont_know_facts_avg"],
                            "dont_know_none_pct": s["dont_know_none_pct"],
                            "tune": {"hits": _hits_total(rows, "tune"),
                                     **_summary(rows, "tune")},
                            "test": {"hits": _hits_total(rows, "test"),
                                     **_summary(rows, "test")}})
                    M._MAX_VEC_DISTANCE = configured_distance
            finally:
                M._ENTITY_RECALL = False
                M._MIN_WORD_SHARE = configured_floor
                M._MAX_VEC_DISTANCE = configured_distance
            ent = level.get("entities") or {}
            print(f"  {kind:<10} {size:>6} filler: recall@5 "
                  f"{level['before']['recall_at_5']} -> {level['after']['recall_at_5']}"
                  + (f" -> {ent['recall_at_5']} with the entity layer" if ent else "")
                  + f", don't-know facts {level['before']['dont_know_facts_avg']} -> "
                  f"{level['after']['dont_know_facts_avg']}"
                  + (f" -> {ent['dont_know_facts_avg']}" if ent else ""), flush=True)
    M._ENTITY_RECALL = entities_configured
    if has_tiebreak:
        M._SAID_AGAIN_TIEBREAK = tiebreak_configured
    out["said_again_available"] = has_tiebreak
    out["entities_available"] = has_entities
    out["reranker"] = rr_what
    out["reranker_measured"] = rr_model is not None
    out["word_floor_configured"] = configured_floor
    out["max_distance_configured"] = configured_distance
    out["word_floor_choice"] = choose_floor(out["floor_sweep"])
    out["sweeps_with_entities"] = has_entities
    if out["distance_sweep"]:
        out["distance_choice"] = choose_distance(out["distance_sweep"])
    # The learner (memory idea 2): its own scratch store, in the same
    # temporary folder. eval_learner.py says what it checks.
    try:
        import eval_learner
        out["learner"] = eval_learner.run(M, scratch, model=learner_model, ollama=ollama)
    except Exception as exc:
        out["learner"] = {"available": False, "why": f"{type(exc).__name__}: {exc}"}
    # "Where did I put ...?" and the overnight tidy's "Which is true now?"
    # (2026-09-28): eval_tidy.py says what it checks.
    try:
        import eval_tidy
        out["tidy"] = eval_tidy.run(M, scratch, model=learner_model, ollama=ollama)
    except Exception as exc:
        out["tidy"] = {"available": False, "why": f"{type(exc).__name__}: {exc}"}
    return out


def choose_floor(sweep: list) -> dict:
    """The floor the golden set supports, chosen on the TUNE half only.

    Allowed: a floor that finds every right fact floor 0 finds, at every size
    and with both fillers - not one fewer. Chosen: of those, the one that
    brings back the fewest facts for "don't know" questions; the lower floor
    on a tie. Then reported on the TEST half, which played no part."""
    by = {}
    for r in sweep:
        by.setdefault(r["floor"], []).append(r)
    base = {(r["filler"], r["filler_facts"]): r for r in by.get(0.0, [])}
    allowed = []
    for floor, rs in sorted(by.items()):
        if all(r["tune"]["hits"] >= base[(r["filler"], r["filler_facts"])]["tune"]["hits"]
               for r in rs):
            allowed.append((sum(r["tune"]["dont_know_facts_total"] for r in rs), floor))
    best = min(allowed)[1] if allowed else 0.0
    test = [{"filler": r["filler"], "filler_facts": r["filler_facts"],
             "hits_before": base[(r["filler"], r["filler_facts"])]["test"]["hits"],
             "hits_after": r["test"]["hits"],
             "dont_know_facts_before": base[(r["filler"], r["filler_facts"])]["test"][
                 "dont_know_facts_total"],
             "dont_know_facts_after": r["test"]["dont_know_facts_total"],
             "dont_know_none_before": base[(r["filler"], r["filler_facts"])]["test"][
                 "dont_know_none_pct"],
             "dont_know_none_after": r["test"]["dont_know_none_pct"]}
            for r in by.get(best, [])]
    return {"chosen": best, "allowed": sorted(f for _, f in allowed), "test_half": test}


def choose_distance(sweep: list) -> dict:
    """JARVIS_MEMORY_MAX_DISTANCE the golden set supports, chosen on the TUNE
    half only, the same rule as choose_floor (the memory review's I6).

    Allowed: a distance that finds every right fact the loosest one tried
    finds, at every size and with both fillers. Chosen: of those, the one
    with the fewest "don't know" facts; the tighter one on a tie. Reported
    on the TEST half. Only a run with meaning search has this sweep."""
    by = {}
    for r in sweep:
        if "tune" in r:
            by.setdefault(r["max_distance"], []).append(r)
    if not by:
        return {"chosen": None, "allowed": [], "test_half": []}
    loosest = max(by)
    base = {(r["filler"], r["filler_facts"]): r for r in by[loosest]}
    allowed = []
    for dist, rs in sorted(by.items()):
        if all(r["tune"]["hits"] >= base[(r["filler"], r["filler_facts"])]["tune"]["hits"]
               for r in rs):
            allowed.append((sum(r["tune"]["dont_know_facts_total"] for r in rs), dist))
    best = min(allowed)[1] if allowed else loosest
    test = [{"filler": r["filler"], "filler_facts": r["filler_facts"],
             "hits_loosest": base[(r["filler"], r["filler_facts"])]["test"]["hits"],
             "hits_chosen": r["test"]["hits"],
             "dont_know_facts_loosest": base[(r["filler"], r["filler_facts"])]["test"][
                 "dont_know_facts_total"],
             "dont_know_facts_chosen": r["test"]["dont_know_facts_total"],
             "dont_know_none_chosen": r["test"]["dont_know_none_pct"]}
            for r in by.get(best, [])]
    return {"chosen": best, "loosest": loosest,
            "allowed": sorted(d for _, d in allowed), "test_half": test}


# ------------------------------------------------------------ the report --

def markdown(res: dict) -> str:
    sem = res["semantic"] and res["vector_search"]
    lines = [
        "# Jarvis memory self-test",
        "",
        f"Run {res['ran_at']} on {res['machine']}. Embedder: **{res['embedder']}** - "
        + ("meaning AND words." if sem else
           "**words only** (the fallback; fastembed or sqlite-vec is not available here, "
           "so these numbers say nothing about meaning search)."),
        f"Memory code: `{res['memory_module']}`. Word floor now: "
        f"{res['word_floor_configured']} (JARVIS_MEMORY_MIN_WORD_SHARE). "
        f"Distance floor now: {res['max_distance_configured']} (JARVIS_MEMORY_MAX_DISTANCE).",
        "",
        "Recall@5 = the right fact is among the 5 a chat gets. \"Don't know\" = facts "
        "returned for a question memory cannot answer (every one is a wrong fact in "
        "front of the model; 0 is right). Before = word floor off, after = on.",
        "",
        "| Filler | Facts | Recall@1 | Recall@5 before -> after | MRR | Replaced came back "
        "| Don't know: facts per question, before -> after | Don't know: none returned "
        "| Past found (labelled) | As-of found | Search p50/p95 ms, before -> after | DB MB |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for lv in res["levels"]:
        a, b = lv["after"], lv["before"]
        lines.append(
            f"| {lv['filler'].replace('_', '-')} | {lv['facts']:,} | {a['recall_at_1']}% "
            f"| {b['recall_at_5']}% -> {a['recall_at_5']}% | {a['mrr']} "
            f"| {a['replaced_came_back']} | {b['dont_know_facts_avg']} -> "
            f"{a['dont_know_facts_avg']} | {b['dont_know_none_pct']}% -> "
            f"{a['dont_know_none_pct']}% | {a['past_found']}/{a['past_questions']} "
            f"({a['past_labelled']}) | {a['as_of_found']}/{a['as_of_questions']} "
            f"| {b['search_p50_ms']}/{b['search_p95_ms']} -> "
            f"{lv['search_p50_ms']}/{lv['search_p95_ms']} "
            f"| {lv['db_bytes'] / 1e6:.2f} |")
    ent_rows = [lv for lv in res["levels"] if lv.get("entities")]
    if ent_rows:
        lines += [
            "",
            "**The entity layer** (\"who is my sister?\", memory wave 3): the same "
            "questions with the word floor on, the entity layer off -> on. People = the "
            "person and alias questions; alias = the ones that name someone only by what "
            "the owner calls them (\"my sister\").",
            "",
            "| Filler | Facts | Recall@5 | People found | Alias found | MRR "
            "| Don't know: facts per question | Don't know: none returned "
            "| Search p50/p95 ms | Entries linked |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for lv in ent_rows:
            a, e = lv["after"], lv["entities"]
            lines.append(
                f"| {lv['filler'].replace('_', '-')} | {lv['facts']:,} "
                f"| {a['recall_at_5']}% -> {e['recall_at_5']}% "
                f"| {a['people_found']}/{a['people_questions']} -> "
                f"{e['people_found']}/{e['people_questions']} "
                f"| {a['alias_found']}/{a['alias_questions']} -> "
                f"{e['alias_found']}/{e['alias_questions']} "
                f"| {a['mrr']} -> {e['mrr']} "
                f"| {a['dont_know_facts_avg']} -> {e['dont_know_facts_avg']} "
                f"| {a['dont_know_none_pct']}% -> {e['dont_know_none_pct']}% "
                f"| {lv['search_p50_ms']}/{lv['search_p95_ms']} -> "
                f"{e['search_p50_ms']}/{e['search_p95_ms']} "
                f"| {e.get('linked_entities')} |")
        lines += ["", "Missed with the entity layer: "
                  + "; ".join(f"{lv['filler']} {lv['filler_facts']}: "
                              f"{', '.join(lv.get('misses_entities') or []) or 'none'}"
                              for lv in ent_rows)]
    elif res.get("entities_available") is False:
        lines += ["", "The entity layer: not measured - this jarvis_memory.py does not have it."]
    big = [lv for lv in res["levels"] if lv["after"].get("multi_questions") is not None]
    if big:
        lines += [
            "",
            "**The bigger self-test** (memory idea 2), as a chat turn recalls (the word "
            "floor on, and the entity layer when this memory has it). Two facts = a "
            "question that needs two or three facts; all of them must be among the five. "
            "Time = \"what phone did I have in June?\": the fact true THEN is among the "
            "five, and wrong version = a fact that was NOT true then came back as if it "
            "were.",
            "",
            "| Filler | Facts | Two facts: all found | ... at least one | Time: found "
            "| Time: wrong version | Don't know: facts per question | Don't know: none "
            "returned |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for lv in big:
            a = lv.get("entities") or lv["after"]
            lines.append(
                f"| {lv['filler'].replace('_', '-')} | {lv['facts']:,} "
                f"| {a['multi_all_found']}/{a['multi_questions']} "
                f"| {a['multi_any_found']}/{a['multi_questions']} "
                f"| {a['time_found']}/{a['time_questions']} | {a['time_wrong_version']} "
                f"| {a['dont_know_facts_avg']} | {a['dont_know_none_pct']}% |")
    rr_rows = [lv for lv in res["levels"] if lv.get("reranked")]
    if rr_rows:
        lines += [
            "",
            f"**The re-ranker** (memory idea 1): {res['reranker']}. The same questions as "
            "a chat turn recalls, without -> with it re-ordering the top "
            "facts before five are kept.",
            "",
            "| Filler | Facts | Recall@1 | Recall@5 | MRR | Two facts: all found "
            "| Time: found / wrong | Don't know: facts per question | Search p50/p95 ms |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for lv in rr_rows:
            a, r = lv.get("entities") or lv["after"], lv["reranked"]
            lines.append(
                f"| {lv['filler'].replace('_', '-')} | {lv['facts']:,} "
                f"| {a['recall_at_1']}% -> {r['recall_at_1']}% "
                f"| {a['recall_at_5']}% -> {r['recall_at_5']}% | {a['mrr']} -> {r['mrr']} "
                f"| {a['multi_all_found']} -> {r['multi_all_found']}/{r['multi_questions']} "
                f"| {a['time_found']}/{a['time_wrong_version']} -> "
                f"{r['time_found']}/{r['time_wrong_version']} "
                f"| {a['dont_know_facts_avg']} -> {r['dont_know_facts_avg']} "
                f"| {a.get('search_p50_ms')}/{a.get('search_p95_ms')} -> "
                f"{r['search_p50_ms']}/{r['search_p95_ms']} |")
        if "stand-in" in str(res.get("reranker")):
            lines += ["", "These re-ranker numbers are from a STAND-IN (word overlap), not "
                      "the real model: they show the wiring works, not what the model "
                      "gains. Run the self-test on the PC with fastembed to measure that."]
    elif "reranker" in res:
        lines += ["", f"The re-ranker (memory idea 1): not measured - {res['reranker']}."]
    sa_rows = [lv for lv in res["levels"] if lv.get("said_again") and lv.get("entities")]
    if sa_rows:
        lines += [
            "",
            "**\"Said again\" as a tie-breaker** (milestone 12, off in Jarvis until this "
            "helps on the PC): the entity-layer line, without -> with facts that tie "
            "exactly put in \"said again\" order. Made-up repeats: "
            + ", ".join(f"{g} x{n}" for g, n in SAID_AGAIN.items())
            + ". Reordered = questions whose facts came back in another order; other "
            "facts must be 0 (it only re-orders).",
            "",
            "| Filler | Facts | Recall@1 | Recall@5 | MRR | nDCG@5 | Don't know: facts "
            "per question | Reordered | Other facts |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for lv in sa_rows:
            a, t = lv["entities"], lv["said_again"]
            lines.append(
                f"| {lv['filler'].replace('_', '-')} | {lv['facts']:,} "
                f"| {a['recall_at_1']}% -> {t['recall_at_1']}% "
                f"| {a['recall_at_5']}% -> {t['recall_at_5']}% | {a['mrr']} -> {t['mrr']} "
                f"| {a['ndcg_at_5']} -> {t['ndcg_at_5']} "
                f"| {a['dont_know_facts_avg']} -> {t['dont_know_facts_avg']} "
                f"| {t['questions_reordered']} | {t['questions_other_facts']} |")
    if "learner" in res:
        import eval_learner
        lines += eval_learner.markdown(res["learner"])
    if "tidy" in res:
        import eval_tidy
        if res["tidy"].get("available") is False:
            lines += ["", f"\"Where did I put ...?\" and the tidy: not measured - "
                      f"{res['tidy'].get('why')}"]
        else:
            lines += eval_tidy.markdown(res["tidy"])
    ch = res["word_floor_choice"]
    lines += [
        "",
        f"**Word floor chosen on half the questions: {ch['chosen']}** "
        f"(floors that lost no right fact there: {', '.join(map(str, ch['allowed']))}"
        + ("; swept as chat recall runs, the entity layer on"
           if res.get("sweeps_with_entities") else "")
        + "). On the other half, which played no part in choosing:",
        "",
        "| Filler | Facts | Right facts found, floor off -> chosen | Don't-know facts, "
        "off -> chosen | Don't know: none returned |",
        "|---|---|---|---|---|",
    ]
    for t in ch["test_half"]:
        lines.append(f"| {t['filler'].replace('_', '-')} | {t['filler_facts']:,} filler "
                     f"| {t['hits_before']} -> {t['hits_after']} "
                     f"| {t['dont_know_facts_before']} -> {t['dont_know_facts_after']} "
                     f"| {t['dont_know_none_before']}% -> {t['dont_know_none_after']}% |")
    lines.append("")
    if res["distance_sweep"]:
        lines += ["Distance floor sweep (meaning search):", "",
                  "| Filler | Filler facts | Max distance | Recall@5 | Don't-know facts "
                  "| Don't know: none |", "|---|---|---|---|---|---|"]
        for r in res["distance_sweep"]:
            lines.append(f"| {r['filler']} | {r['filler_facts']:,} | {r['max_distance']} "
                         f"| {r['recall_at_5']}% | {r['dont_know_facts_avg']} "
                         f"| {r['dont_know_none_pct']}% |")
        dc = res.get("distance_choice") or {}
        if dc.get("chosen") is not None:
            lines += ["", f"**Distance floor chosen on half the questions: {dc['chosen']}** "
                      f"(distances that lost no right fact the loosest, {dc['loosest']}, "
                      f"found there: {', '.join(map(str, dc['allowed']))}). On the other "
                      "half, which played no part in choosing:", "",
                      "| Filler | Facts | Right facts found, loosest -> chosen "
                      "| Don't-know facts, loosest -> chosen | Don't know: none returned |",
                      "|---|---|---|---|---|"]
            for t in dc["test_half"]:
                lines.append(f"| {t['filler'].replace('_', '-')} | {t['filler_facts']:,} "
                             f"filler | {t['hits_loosest']} -> {t['hits_chosen']} "
                             f"| {t['dont_know_facts_loosest']} -> "
                             f"{t['dont_know_facts_chosen']} "
                             f"| {t['dont_know_none_chosen']}% |")
    else:
        lines.append("Distance floor sweep: skipped - there is no meaning search without "
                     "the real embedder.")
    pin_rows = [(lv, c) for lv in res["levels"] for c in lv.get("pinned", {}).get("cases", [])]
    if pin_rows:
        lines += ["", "\"Always keep in mind\": a pinned fact on a question that shares no "
                  "words with it. Found = among the facts the chat turn gets.", "",
                  "| Filler | Facts | Fact | Question | Found by search alone | With the pin "
                  "| Pinned characters |", "|---|---|---|---|---|---|---|"]
        for lv, c in pin_rows:
            lines.append(f"| {lv['filler'].replace('_', '-')} | {lv['facts']:,} | {c['fact']} "
                         f"| {c['question']} | {'yes' if c['search_alone'] else 'no'} "
                         f"| {'yes' if c['with_pin'] else 'no'} | {c['pinned_chars']} |")
    else:
        lines += ["", "\"Always keep in mind\": not measured - this jarvis_memory.py has "
                  "no pinned list."]
    lines += ["", "Missed after the floor (question ids, golden_questions.jsonl): "
              + "; ".join(f"{lv['filler']} {lv['filler_facts']}: "
                          f"{', '.join(lv['misses_after']) or 'none'}"
                          for lv in res["levels"]), ""]
    return "\n".join(lines)


#: --against: the numbers compared, where they live in a level, and which
#: way is better. Timings are left out - they vary from run to run.
#: `gate`: a worse number here makes the run FAIL (exit 1).
COMPARED = [
    ("recall@5", ("after", "recall_at_5"), "up", True),
    ("recall@5, entity layer", ("entities", "recall_at_5"), "up", True),
    ("recall@1, entity layer", ("entities", "recall_at_1"), "up", False),
    ("MRR, entity layer", ("entities", "mrr"), "up", False),
    ("replaced came back", ("after", "replaced_came_back"), "down", True),
    ("don't know: facts per question", ("entities", "dont_know_facts_avg"), "down", False),
    ("don't know: none returned", ("entities", "dont_know_none_pct"), "up", False),
    ("people found", ("entities", "people_found"), "up", False),
    ("past found", ("after", "past_found"), "up", False),
    ("as-of found", ("after", "as_of_found"), "up", False),
    ("two facts: all found", ("entities", "multi_all_found"), "up", False),
    ("time: found", ("entities", "time_found"), "up", False),
    ("time: wrong version", ("entities", "time_wrong_version"), "down", True),
]


def _level_value(lv: dict, where: tuple):
    part, key = where
    block = lv.get(part) or (lv.get("after") if part == "entities" else None) or {}
    return block.get(key)


def compare(old: dict, new: dict) -> tuple:
    """(report lines, worse): every COMPARED number of each filler and size
    both runs have, better / worse / unchanged, and the learner's cases by
    kind (how many are wrong). `worse` is True when recall@5, "replaced
    came back", "time: wrong version" or a learner kind got worse - the
    memory review's I7. Timings are never compared."""
    lines, worse = [], False
    olds = {(lv["filler"], lv["filler_facts"]): lv for lv in old.get("levels", [])}
    for lv in new.get("levels", []):
        key = (lv["filler"], lv["filler_facts"])
        was = olds.get(key)
        if was is None:
            continue
        for name, where, better, gate in COMPARED:
            a, b = _level_value(was, where), _level_value(lv, where)
            if a is None or b is None:
                continue
            if a == b:
                how = "unchanged"
            elif (b > a) == (better == "up"):
                how = "better"
            else:
                how = "WORSE"
                worse = worse or gate
            lines.append(f"| {key[0].replace('_', '-')} | {key[1]:,} | {name} | {a} | {b} "
                         f"| {how} |")
    lo = (old.get("learner") or {}).get("kinds") or {}
    ln = (new.get("learner") or {}).get("kinds") or {}
    for kind in sorted(set(lo) & set(ln)):
        a = lo[kind]["total"] - lo[kind]["right"]
        b = ln[kind]["total"] - ln[kind]["right"]
        how = "unchanged" if a == b else ("better" if b < a else "WORSE")
        worse = worse or how == "WORSE"
        lines.append(f"| learner | - | {kind}: cases wrong ({ln[kind]['total']} now) | {a} | {b} "
                     f"| {how} |")
    try:
        import eval_tidy
        for name, a, b, how, gate in eval_tidy.compared(old.get("tidy"), new.get("tidy")):
            worse = worse or (how == "WORSE" and gate)
            lines.append(f"| tidy | - | {name} | {a} | {b} | {how} |")
    except Exception:
        pass
    head = ["", "**Against an earlier run** (--against): the same numbers, earlier -> now. "
            "Timings are not compared. A worse recall@5, \"replaced came back\", \"time: "
            "wrong version\" or learner kind fails the run.", "",
            "| Filler | Filler facts | Number | Earlier | Now | |", "|---|---|---|---|---|---|"]
    return head + lines, worse


# --------------------------------------------- LoCoMo's multi-hop questions --
#
# Milestone 13 (docs/AUDIT-2026-09-28-REPO-REFS.md): "link two facts"
# questions from outside, so a later multi-hop memory change (milestone 5)
# has a number to beat that was not written by the people changing it.
#
# LoCoMo (Snap Research, ACL 2024; data CC BY-NC 4.0, test data only,
# THIRD-PARTY-NOTICES.txt) is long made-up chats between two people. Its
# multi-hop questions each cite the two or more chat turns that together
# hold the answer. backend/fixtures/locomo_multihop.json keeps five of the
# chats whole and their multi-hop questions (tools/build_locomo_fixture.py
# says exactly what and why).
#
# HOW IT IS MEASURED. Each chat gets its own new store in the scratch
# folder; every turn is one stored item ('Caroline said, "..."', plus
# "[shares <picture caption>]" as LoCoMo's own retrieval code writes it),
# dated the day its session happened. Then each question is searched, and
# scored on the turns it cites: found-any (recall_any@k, as the self-test
# above), found-all (every cited turn in the k - the number a multi-hop
# change should move) and nDCG@k, with the same dcg()/ndcg() as above, at
# k = 5 (what a chat turn gets) and 10. Twice: plain search, and with the
# entity layer on, as chat recall runs. The word floor is as configured.
# No re-ranker, and no chat model is asked anything.
#
# A LoCoMo turn is a line of chat, not a saved fact about the owner, so
# these numbers are NOT comparable with the self-test's own, nor with
# LoCoMo scores published elsewhere (those mostly judge answers, not
# retrieval). They are for comparing Jarvis's memory with itself.

LOCOMO = HERE / "fixtures" / "locomo_multihop.json"
LOCOMO_KS = (5, 10)


def load_locomo(path: Path = LOCOMO) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def locomo_text(turn: list) -> str:
    """One stored item for one chat turn: [id, speaker, text, caption?]."""
    text = f'{turn[1]} said, "{turn[2]}"'
    if len(turn) > 3 and turn[3]:
        text += f" [shares {turn[3]}]"
    return text


def _iso_day(text: str) -> float:
    y, m, d = (int(x) for x in text[:10].split("-"))
    hh, mm = (int(x) for x in text[11:16].split(":")) if len(text) >= 16 else (12, 0)
    return time.mktime((y, m, d, hh, mm, 0, 0, 0, -1))


def _put_locomo(st, chat: dict) -> dict:
    """Every turn of one chat into the store, each dated its session's day.
    Returns {fact id: turn id}. Words go in as each is added; meaning is
    embedded afterwards in batches, as _add_filler does."""
    vec = st._vec_ok
    st._vec_ok = False
    rows, back = [], {}
    try:
        for s in chat["sessions"]:
            when = _iso_day(s["date"])
            for t in s["turns"]:
                fid = st.add(locomo_text(t), source="locomo", valid_from=when)
                rows.append((when, fid))
                back[fid] = t[0]
    finally:
        st._vec_ok = vec
    c = st._connect()
    try:
        c.executemany("UPDATE facts SET created=? WHERE id=?", rows)
        c.commit()
    finally:
        c.close()
    if vec:
        st.backfill_embeddings(batch=64)
    return back


def _score_locomo(st, chat: dict, back: dict, entities: bool) -> list:
    kw = {"entities": True} if entities else {}
    rows = []
    for q in chat["questions"]:
        ev = set(q["evidence"])
        row = {"chat": chat["id"], "q": q["q"], "evidence": len(ev)}
        for k in LOCOMO_KS:
            got = [back.get(r["id"], "?") for r in st.search(q["q"], k=k, **kw)]
            row[f"any{k}"] = bool(ev & set(got))
            row[f"all{k}"] = ev <= set(got)
            row[f"ndcg{k}"] = ndcg(got, ev, k)
            row[f"found{k}"] = sorted(ev & set(got))
        rows.append(row)
    return rows


def _locomo_summary(rows: list) -> dict:
    n = len(rows)

    def pct(x):
        return round(100.0 * x / n, 1) if n else None
    out = {"questions": n,
           "evidence_avg": round(statistics.mean(r["evidence"] for r in rows), 2) if n else None}
    for k in LOCOMO_KS:
        out[f"recall_any_at_{k}"] = pct(sum(r[f"any{k}"] for r in rows))
        out[f"recall_all_at_{k}"] = pct(sum(r[f"all{k}"] for r in rows))
        out[f"ndcg_at_{k}"] = round(sum(r[f"ndcg{k}"] for r in rows) / n, 3) if n else None
    return out


def run_locomo(words_only: bool, scratch: Path, fixture: Path = LOCOMO,
               chats: int = None) -> dict:
    """LoCoMo's multi-hop questions against Jarvis's memory. `chats` keeps
    only the first so many (the test uses one); None is all of them."""
    M, _P = _load_memory(scratch)
    if hasattr(M, "set_reranker"):
        M.set_reranker(None)
    data = load_locomo(fixture)
    todo = data["chats"][:chats] if chats else data["chats"]
    ent = False
    out = {"source": data["source"], "commit": data["commit"], "ks": list(LOCOMO_KS),
           "word_floor": M._MIN_WORD_SHARE, "memory_module": str(Path(M.__file__).resolve()),
           "chats": []}
    rows = {"search": [], "entities": []}
    for chat in todo:
        d = scratch / "locomo" / chat["id"]
        d.mkdir(parents=True, exist_ok=True)
        emb = M.HashEmbedder() if words_only else M._make_embedder()
        st = M.MemoryStore(d / "memory.db", embedder=emb)
        stat = st.status()
        out["embedder"] = stat["embedder"]
        out["semantic"] = bool(stat["semantic"])
        out["vector_search"] = bool(stat["vector_search"])
        t0 = time.perf_counter()
        back = _put_locomo(st, chat)
        took = round(time.perf_counter() - t0, 1)
        ent = _entity_search(st)
        r_search = _score_locomo(st, chat, back, entities=False)
        rows["search"] += r_search
        line = {"id": chat["id"], "turns": len(back), "questions": len(chat["questions"]),
                "store_s": took, "search": _locomo_summary(r_search)}
        if ent:
            r_ent = _score_locomo(st, chat, back, entities=True)
            rows["entities"] += r_ent
            line["entities"] = _locomo_summary(r_ent)
        out["chats"].append(line)
        print(f"  {chat['id']}: {len(back)} turns, {len(chat['questions'])} questions, "
              f"found-all@5 {line['search']['recall_all_at_5']}%"
              + (f" -> {line['entities']['recall_all_at_5']}% with the entity layer"
                 if ent else ""), flush=True)
    out["entities_available"] = ent
    out["search"] = _locomo_summary(rows["search"])
    if ent:
        out["entities"] = _locomo_summary(rows["entities"])
    best = "entities" if ent else "search"
    out["misses_all_at_5"] = [f"{r['chat']}: {r['q']}" for r in rows[best] if not r["all5"]]
    return out


def locomo_markdown(res: dict) -> str:
    sem = res["semantic"] and res["vector_search"]
    lines = [
        "# Jarvis memory self-test - LoCoMo multi-hop questions",
        "",
        f"Run {res['ran_at']} on {res['machine']}. Embedder: **{res['embedder']}** - "
        + ("meaning search is ON." if sem else
           "**words only**: these numbers say nothing about meaning search."),
        "",
        f"Data: LoCoMo (Snap Research, CC BY-NC 4.0, test data only), commit "
        f"{res['commit'][:12]}. Each chat line is one stored item; a question counts as "
        "found when search brings back the chat lines LoCoMo says hold its answer. "
        "Not comparable with the main self-test or with LoCoMo scores published elsewhere.",
        "",
        "| Search | Questions | Found any @5 | Found ALL @5 | nDCG@5 | Found any @10 | "
        "Found ALL @10 | nDCG@10 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, label in (("search", "plain search"),
                        ("entities", "with the entity layer (as chat recall)")):
        s = res.get(name)
        if not s:
            continue
        lines.append(f"| {label} | {s['questions']} | {s['recall_any_at_5']}% | "
                     f"{s['recall_all_at_5']}% | {s['ndcg_at_5']} | {s['recall_any_at_10']}% | "
                     f"{s['recall_all_at_10']}% | {s['ndcg_at_10']} |")
    lines += ["", "Per chat (found ALL @5):", ""]
    for c in res["chats"]:
        lines.append(f"- {c['id']}: {c['turns']} lines, {c['questions']} questions, "
                     f"{c['search']['recall_all_at_5']}%"
                     + (f" -> {c['entities']['recall_all_at_5']}% with the entity layer"
                        if c.get("entities") else "")
                     + f" (stored in {c['store_s']} s)")
    lines.append("")
    return "\n".join(lines)


def main_locomo(a) -> int:
    scratch = Path(tempfile.mkdtemp(prefix="jarvis-memory-eval-"))
    real = Path(os.path.expanduser("~")) / ".openjarvis" / "memory.db"
    assert (scratch / "memory.db").resolve() != real.resolve()
    print(f"scratch store: {scratch} (deleted at the end; your memory.db is not opened)")
    t0 = time.time()
    try:
        res = run_locomo(a.words_only, scratch)
    finally:
        if not a.keep:
            shutil.rmtree(scratch, ignore_errors=True)
    import platform
    res["ran_at"] = time.strftime("%Y-%m-%d %H:%M")
    res["machine"] = f"{platform.system()} {platform.machine()}, Python {platform.python_version()}"
    res["seconds"] = round(time.time() - t0, 1)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (out / f"memory-eval-locomo-{stamp}.json").write_text(json.dumps(res, indent=1),
                                                          encoding="utf-8")
    md = locomo_markdown(res)
    (out / f"memory-eval-locomo-{stamp}.md").write_text(md, encoding="utf-8")
    print()
    print(md)
    print(f"Saved: {out / f'memory-eval-locomo-{stamp}.md'} and the .json beside it "
          f"({res['seconds']} s).")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sizes", default="0,100,1000,10000",
                    help="filler sizes, comma-separated (default 0,100,1000,10000)")
    ap.add_argument("--words-only", action="store_true",
                    help="use the words-only fallback even if fastembed is installed")
    ap.add_argument("--out", default=str(Path.home() / "jarvis-memory-eval"),
                    help="folder for the two result files (default: jarvis-memory-eval "
                         "in your home folder)")
    ap.add_argument("--keep", action="store_true", help="keep the scratch store")
    ap.add_argument("--learner-model", default=None,
                    help="OPTIONAL: also run the real learner on made-up conversations "
                         "with this local Ollama model (needs JARVIS_BACKEND pointing at "
                         "the backend folder, for jarvis_extract.py). Off by default: the "
                         "default run needs no model")
    ap.add_argument("--reranker", choices=("auto", "off", "stand-in"), default="auto",
                    help="auto (default): measure the real re-ranker if fastembed can load "
                         "it here - it downloads about 80 MB once; stand-in: a word-overlap "
                         "stand-in that proves the wiring only; off")
    ap.add_argument("--ollama", default="http://127.0.0.1:11434",
                    help="this PC's Ollama, for --learner-model (loopback only)")
    ap.add_argument("--against", default=None,
                    help="an earlier run's memory-eval-*.json: print each number better / "
                         "worse / unchanged, and exit 1 if recall@5, a wrong version or a "
                         "learner case got worse (timings are not compared)")
    ap.add_argument("--locomo", action="store_true",
                    help="run ONLY LoCoMo's multi-hop questions (backend/fixtures/"
                         "locomo_multihop.json) instead of the self-test; files are "
                         "memory-eval-locomo-*.md/.json. --sizes, --learner-model, "
                         "--reranker and --against do not apply")
    a = ap.parse_args(argv)
    if a.locomo:
        if a.against:
            print("--against compares the main self-test only; it cannot be used with --locomo")
            return 2
        return main_locomo(a)
    earlier = None
    if a.against:
        try:
            earlier = json.loads(Path(a.against).read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"--against: could not read {a.against}: {type(exc).__name__}: {exc}")
            return 2
    sizes = sorted({int(x) for x in a.sizes.split(",") if x.strip()})
    scratch = Path(tempfile.mkdtemp(prefix="jarvis-memory-eval-"))
    real = Path(os.path.expanduser("~")) / ".openjarvis" / "memory.db"
    assert (scratch / "memory.db").resolve() != real.resolve()
    print(f"scratch store: {scratch} (deleted at the end; your memory.db is not opened)")
    t0 = time.time()
    try:
        res = run(sizes, a.words_only, scratch, learner_model=a.learner_model,
                  ollama=a.ollama, reranker=a.reranker)
    finally:
        if not a.keep:
            shutil.rmtree(scratch, ignore_errors=True)
    import platform
    res["ran_at"] = time.strftime("%Y-%m-%d %H:%M")
    res["machine"] = f"{platform.system()} {platform.machine()}, Python {platform.python_version()}"
    res["seconds"] = round(time.time() - t0, 1)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (out / f"memory-eval-{stamp}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    md = markdown(res)
    worse = False
    if earlier is not None:
        extra, worse = compare(earlier, res)
        md += "\n".join(extra) + "\n"
    (out / f"memory-eval-{stamp}.md").write_text(md, encoding="utf-8")
    print()
    print(md)
    print(f"Saved: {out / f'memory-eval-{stamp}.md'} and the .json beside it "
          f"({res['seconds']} s).")
    if worse:
        print("WORSE than the earlier run (see \"Against an earlier run\" above).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
