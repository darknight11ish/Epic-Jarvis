"""eval_memory.py - Jarvis's memory self-test. Does search find the right fact?

    python eval_memory.py                      # the full run, about 2-10 minutes
    python eval_memory.py --sizes 0,100        # a quick one
    python eval_memory.py --words-only         # as on day one, before fastembed
    python eval_memory.py --out C:\\somewhere   # where the two result files go

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
                        reports it on the other half
  the distance floor    a sweep of JARVIS_MEMORY_MAX_DISTANCE from 0.6 to
                        1.2 - only with the real embedder, because without
                        it there is no meaning search to put a floor on
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


def _put_golden(st, facts: list) -> dict:
    """Add the made-up person's facts, then give each the dates the file
    says - when Jarvis was told, and for a replaced fact when it stopped
    being true and what replaced it. Straight into the scratch store's own
    table: this is the ONLY way to have facts that were told last year."""
    ids = {}
    for f in facts:
        ids[f["id"]] = st.add(f["text"], source="eval")
    c = st._connect()
    try:
        for f in facts:
            told = _day(f["told"])
            c.execute("UPDATE facts SET created=?, valid_from=? WHERE id=?",
                      (told, told, ids[f["id"]]))
        for f in facts:
            if f.get("retired"):
                when = _day(f["retired"])
                c.execute("UPDATE facts SET valid_to=?, retired_at=?, retired_by=? WHERE id=?",
                          (when, when, ids[f["replaced_by"]], ids[f["id"]]))
    finally:
        c.close()
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


def _entity_search(st):
    """Does this jarvis_memory.py have the entity layer (search(entities=))?"""
    import inspect
    try:
        return "entities" in inspect.signature(st.search).parameters
    except (TypeError, ValueError):
        return False


def _score(M, P, st, qs: list, gid: dict, now: float) -> dict:
    """Every question once, as chat recall asks it. Returns per-question
    rows. Whether the entity layer is on is M._ENTITY_RECALL, set by the
    caller (jarvis_past.recall asks for it; the flag switches it)."""
    rows = []
    ent = _entity_search(st)
    for q in qs:
        if q["type"] == "past":
            res = P.recall(st, q["q"], k=K, now=now)
        elif q["type"] == "belief":
            res = st.search(q["q"], k=K, known_at=_day(q["known_at"]))
        elif ent:
            res = st.search(q["q"], k=K, entities=True)
        else:
            res = st.search(q["q"], k=K)
        got = [gid.get(r["id"], "filler") for r in res]
        ans = set(q["answers"])
        first = next((i for i, g in enumerate(got) if g in ans), None)
        rows.append({
            "id": q["id"], "type": q["type"], "split": q["split"], "n": len(got),
            "answerable": bool(ans),
            "hit1": bool(ans) and first == 0,
            "hit5": bool(ans) and first is not None,
            "rr": 0.0 if first is None else 1.0 / (first + 1),
            "ndcg": ndcg(got, ans, K) if ans else 0.0,
            "stale": any(g in set(q.get("stale", [])) for g in got),
            "labelled": q["type"] != "past" or any(
                r.get("past") and "no longer true since" in r.get("text", "") for r in res),
            "chars": sum(len(r.get("text", "")) for r in res),
        })
    return {r["id"]: r for r in rows}


def _summary(rows: dict, split: str = None) -> dict:
    rs = [r for r in rows.values() if split is None or r["split"] == split]
    cur = [r for r in rs if r["type"] in ANSWERABLE]
    ab = [r for r in rs if r["type"] == "abstain"]
    past = [r for r in rs if r["type"] == "past"]
    bel = [r for r in rs if r["type"] == "belief" and r["answerable"]]
    bel_none = [r for r in rs if r["type"] == "belief" and not r["answerable"]]
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
    }


def _hits_total(rows: dict, split: str) -> int:
    """Every right fact found in the five, current, past and as-of."""
    return sum(r["hit5"] for r in rows.values() if r["split"] == split)


def _timings(st, qs: list, reps: int = 3, entities: bool = False) -> dict:
    lat = []
    kw = {"entities": True} if entities and _entity_search(st) else {}
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


def _db_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.parent.glob(path.name + "*") if p.is_file())


# ------------------------------------------------------------ the run --

def run(sizes: list, words_only: bool, scratch: Path) -> dict:
    M, P = _load_memory(scratch)
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
        ids = _put_golden(st, facts)
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
                finally:
                    M._ENTITY_RECALL = False
            level["db_bytes"] = _db_bytes(db)
            level["pinned"] = _pin_effect(M, P, st, gid, now)
            out["levels"].append(level)
            # the word-floor sweep: every floor, both halves of the questions
            for floor in FLOORS:
                M._MIN_WORD_SHARE = floor
                rows = _score(M, P, st, qs, gid, now)
                out["floor_sweep"].append({
                    "filler": kind, "filler_facts": size, "floor": floor,
                    "tune": {"hits": _hits_total(rows, "tune"), **_summary(rows, "tune")},
                    "test": {"hits": _hits_total(rows, "test"), **_summary(rows, "test")}})
            M._MIN_WORD_SHARE = configured_floor
            # the distance-floor sweep: only where there is meaning search
            if stat["semantic"] and stat["vector_search"]:
                for dist in DISTANCES:
                    M._MAX_VEC_DISTANCE = dist
                    s = _summary(_score(M, P, st, qs, gid, now))
                    out["distance_sweep"].append({
                        "filler": kind, "filler_facts": size, "max_distance": dist,
                        "recall_at_5": s["recall_at_5"],
                        "dont_know_facts_avg": s["dont_know_facts_avg"],
                        "dont_know_none_pct": s["dont_know_none_pct"]})
                M._MAX_VEC_DISTANCE = configured_distance
            ent = level.get("entities") or {}
            print(f"  {kind:<10} {size:>6} filler: recall@5 "
                  f"{level['before']['recall_at_5']} -> {level['after']['recall_at_5']}"
                  + (f" -> {ent['recall_at_5']} with the entity layer" if ent else "")
                  + f", don't-know facts {level['before']['dont_know_facts_avg']} -> "
                  f"{level['after']['dont_know_facts_avg']}"
                  + (f" -> {ent['dont_know_facts_avg']}" if ent else ""), flush=True)
    M._ENTITY_RECALL = entities_configured
    out["entities_available"] = has_entities
    out["word_floor_configured"] = configured_floor
    out["max_distance_configured"] = configured_distance
    out["word_floor_choice"] = choose_floor(out["floor_sweep"])
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
    ch = res["word_floor_choice"]
    lines += [
        "",
        f"**Word floor chosen on half the questions: {ch['chosen']}** "
        f"(floors that lost no right fact there: {', '.join(map(str, ch['allowed']))}). "
        "On the other half, which played no part in choosing:",
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
    a = ap.parse_args(argv)
    sizes = sorted({int(x) for x in a.sizes.split(",") if x.strip()})
    scratch = Path(tempfile.mkdtemp(prefix="jarvis-memory-eval-"))
    real = Path(os.path.expanduser("~")) / ".openjarvis" / "memory.db"
    assert (scratch / "memory.db").resolve() != real.resolve()
    print(f"scratch store: {scratch} (deleted at the end; your memory.db is not opened)")
    t0 = time.time()
    try:
        res = run(sizes, a.words_only, scratch)
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
    (out / f"memory-eval-{stamp}.md").write_text(md, encoding="utf-8")
    print()
    print(md)
    print(f"Saved: {out / f'memory-eval-{stamp}.md'} and the .json beside it "
          f"({res['seconds']} s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
