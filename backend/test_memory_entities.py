"""test_memory_entities.py - "who is my sister?": the entity layer.

    python3 backend/test_memory_entities.py

Memory wave 3 (2026-09-25; docs/ARCHITECTURE.md section 5, JARVIS-API.md
section 6 `/api/memory/entities`, backend/README.md "Memory wave 3"). What
must hold, from the research sketch's seven rules:

  * three tables in memory.db - entities, entity_aliases, fact_entities -
    made from SAVED facts only, by fixed rules on every save;
  * grounded or dropped: every name and alias is in its fact word for word,
    whoever found it (the rules, or the optional local model);
  * an alias ("sister" -> Priya) only from a fact with BOTH words in it, and
    it records that fact's id; Forget, a correction and Erase take the
    alias and the links away - Erase also every name no other fact says,
    measured by reading memory.db and its -wal as raw bytes;
  * merging: an exact match after normalising is one entry; a likely typo
    is ONE "are these the same?" card per pair, ever, and a yes joins that
    one pair (a pointer, never a delete); there is no list form;
  * recall: the alias table, the names added to the question, and the
    linked facts as a third list - the sister's-wedding case goes from
    missing to found; k and the floors unchanged; no model call anywhere on
    that path; a temporary chat still recalls nothing; the pinned list is
    unchanged;
  * the optional model pass is OFF by default, one call per pass, this
    PC's model only, and can only add grounded links;
  * memory-entities.patch: GET /api/memory/entities, the card hidden from
    /api/memory/pending unless ?merge_cards=1, and accepting it adds no
    fact - lifted from the whole patch stack's stand-in and run.

Every check below fails on the code before this change: the tables, the
functions, the patch and the route did not exist (the "guard" checks pass on
both, and must). No pytest, no network, no model.
"""
from __future__ import annotations

import json
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import time
import traceback
import types
import urllib.request
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("rebuilt/jarvis_memory.py", "jarvis_past.py", "jarvis_entities.py")

try:
    import jarvis_memory as M
except ImportError:
    sys.path.append(str(REPO / "backend" / "rebuilt"))
    import jarvis_memory as M
import jarvis_past as P  # noqa: E402
import jarvis_entities as E  # noqa: E402

import _stack  # noqa: E402

PASSED, FAILED = [], []
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-entities-"))

SISTER = "My sister is called Priya"
WEDDING = "Priya is getting married in Goa on 14 March 2027"
SPEECH = "Priya asked me to give a speech at the reception"
MARIO = "I went to Mario's wedding last year and it rained"
FILLER = ["I need to book flights to Goa before January", "My brother Arjun works at Siemens",
          "I prefer tabs over spaces", "My dentist appointment is on Friday",
          "Mario is my manager at work"]


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def fresh(name: str):
    d = _TMP / name
    d.mkdir(parents=True, exist_ok=True)
    st = M.MemoryStore(path=d / "memory.db", embedder=M.HashEmbedder())
    M._store = st
    return st


def rows(st, sql, args=()):
    with closing(st._connect()) as c:
        return [tuple(r) for r in c.execute(sql, args)]


def entity_names(st):
    return sorted(r[0] for r in rows(st, "SELECT name FROM entities"))


def aliases(st):
    return sorted(rows(st, "SELECT alias, e.name, a.fact_id FROM entity_aliases a"
                           " JOIN entities e ON e.id = a.entity_id WHERE a.fact_id IS NOT NULL"))


def wedding_store(name):
    st = fresh(name)
    ids = {"sister": st.add(SISTER), "wedding": st.add(WEDDING), "speech": st.add(SPEECH),
           "mario": st.add(MARIO)}
    for t in FILLER:
        st.add(t)
    return st, ids


# ================================================================ tables ==

def t_the_three_tables_are_the_sketchs():
    st = fresh("tables")
    with closing(st._connect()) as c:
        def cols(t):
            return [r[1] for r in c.execute(f"PRAGMA table_info({t})")]
        check("entities (id, name, kind, created, merged_into)",
              cols("entities") == ["id", "name", "kind", "created", "merged_into"],
              cols("entities"))
        check("entity_aliases (alias, entity_id, fact_id)",
              cols("entity_aliases") == ["alias", "entity_id", "fact_id"])
        check("fact_entities (fact_id, entity_id)",
              cols("fact_entities") == ["fact_id", "entity_id"])
        idx = {r[1] for r in c.execute("PRAGMA index_list(fact_entities)")}
        check("ix_fe_entity is there", "ix_fe_entity" in idx, idx)
        check("the fact tables are untouched: facts still has its own columns",
              "entity_id" not in cols("facts"))


def t_an_older_store_is_linked_once():
    d = _TMP / "old"
    d.mkdir()
    db = d / "memory.db"
    with closing(sqlite3.connect(db)) as c:
        c.execute("CREATE TABLE facts (id INTEGER PRIMARY KEY, text TEXT NOT NULL, source TEXT,"
                  " created REAL NOT NULL, valid_from REAL NOT NULL, valid_to REAL,"
                  " retired_at REAL, retired_by INTEGER, embedded INTEGER NOT NULL DEFAULT 0,"
                  " meta TEXT)")
        now = time.time()
        c.execute("INSERT INTO facts (text, created, valid_from) VALUES (?, ?, ?)",
                  (SISTER, now, now))
        c.execute("INSERT INTO facts (text, created, valid_from, valid_to) VALUES (?, ?, ?, ?)",
                  ("Owner's boss is called Gregor", now, now, now - 1))
        c.commit()
    st = M.MemoryStore(path=db, embedder=M.HashEmbedder())
    check("a store from before the entity layer has its current facts linked",
          entity_names(st) == ["Priya"], entity_names(st))
    check("...and a forgotten fact of it is not linked", "Gregor" not in entity_names(st))
    M.MemoryStore(path=db, embedder=M.HashEmbedder())
    check("...once: opening it again changes nothing",
          len(rows(st, "SELECT * FROM entities")) == 1)


# ============================================================== linking ==

def t_linked_on_save_by_fixed_rules():
    st = fresh("link")
    f1 = st.add(SISTER)
    f2 = st.add("Priya's wedding is in Lisbon next May")
    check("a saved fact is linked when it is saved",
          entity_names(st) == ["Lisbon", "Priya"], entity_names(st))
    check("the same name (possessive folded) is ONE entry",
          len(rows(st, "SELECT id FROM entities WHERE name='Priya'")) == 1)
    check("both facts link to it",
          sorted(r[0] for r in rows(st, "SELECT fact_id FROM fact_entities fe JOIN entities e"
                                        " ON e.id=fe.entity_id WHERE e.name='Priya'")) == [f1, f2])
    check("\"sister\" is an alias of Priya, taught by that fact",
          aliases(st) == [("sister", "Priya", f1)], aliases(st))
    got = M.find_entities("Owner's best friend Kofi lives in Glasgow")
    check("apposition and a modifier: \"best friend\" and \"friend\" -> Kofi",
          ("best friend", "Kofi") in got["aliases"] and ("friend", "Kofi") in got["aliases"], got)
    got = M.find_entities("Mario is my manager at work")
    check("the other way round: \"Mario is my manager\"", ("manager", "Mario") in got["aliases"],
          got)
    got = M.find_entities("Owner's cello teacher is called Mrs Okafor")
    check("a title stays on the name: one entry, \"Mrs Okafor\"",
          [n for n, _ in got["names"]] == ["Mrs Okafor"], got)
    got = M.find_entities("My former manager Marta moved to Spain")
    check("\"former manager\" is an alias, bare \"manager\" is not",
          ("former manager", "Marta") in got["aliases"]
          and ("manager", "Marta") not in got["aliases"], got)
    got = M.find_entities("Tomorrow is Friday and I am in March")
    check("sentence starters, days and months are not names", got["names"] == [], got)


def t_grounded_or_dropped():
    st = fresh("grounded")
    fid = st.add("Priya is getting married in Goa")
    out = st.link_entities(fid, {"names": [("Priyanka", "person"), ("Goa", "place")],
                                 "aliases": [("sister", "Priya")]})
    check("a name that is not in the fact word for word is dropped",
          "Priyanka" not in entity_names(st), entity_names(st))
    check("an alias whose word is not in the fact is dropped", aliases(st) == [], aliases(st))
    check("a grounded name is linked", out is not None and "Goa" in entity_names(st))
    other = st.add("My sister is getting married")
    st.link_entities(other, {"names": [("Priya", "person")], "aliases": [("sister", "Priya")]})
    check("\"sister\" is never taught by a fact without the name in it",
          aliases(st) == [], aliases(st))
    check("guard: _grounded is whole words, case aside",
          M._grounded("Priya's wedding", "priya") and not M._grounded("Priyanka", "Priya"))


def t_alias_only_from_a_fact_with_both_and_it_records_that_fact():
    st = fresh("alias")
    st.add("Priya lives in Leeds")
    st.add("My sister is lovely")
    check("no fact has both words: no alias", aliases(st) == [], aliases(st))
    fid = st.add(SISTER)
    check("a fact with both: the alias, with that fact's id",
          aliases(st) == [("sister", "Priya", fid)], aliases(st))


# ========================================================= forget, erase ==

def t_forget_and_corrections_take_the_links():
    st = fresh("forget")
    f1 = st.add(SISTER)
    f2 = st.add(WEDDING)
    st.retire(f1)
    check("Forget takes the alias it taught", aliases(st) == [], aliases(st))
    check("...and its links", rows(st, "SELECT 1 FROM fact_entities WHERE fact_id=?", (f1,)) == [])
    check("...but Priya stays: another current fact still says her name",
          entity_names(st) == ["Goa", "Priya"], entity_names(st))
    st.retire(f2)
    check("with no fact left linked, the entry goes", entity_names(st) == [], entity_names(st))
    st = fresh("twice")
    a = st.add(SISTER)
    b = st.add("My sister is called Priya and she lives in Leeds")
    st.retire(a)
    check("an alias another current fact also teaches comes back from that fact",
          aliases(st) == [("sister", "Priya", b)], aliases(st))
    st = fresh("correct")
    old = st.add("Owner's manager is called Marta")
    new = st.add("Owner's manager is called Tom", supersedes=old)
    check("a correction moves the alias to the new wording",
          aliases(st) == [("manager", "Tom", new)], aliases(st))
    check("...and the old name goes with the old wording", "Marta" not in entity_names(st))
    st = fresh("edit")
    fid = st.add("Owner's partner is called Jonas")
    st.edit(fid, "Owner's partner is called Jonah")
    check("an edit in place relinks the new words",
          aliases(st) == [("partner", "Jonah", fid)] and "Jonas" not in entity_names(st),
          (aliases(st), entity_names(st)))
    before = rows(st, "SELECT id FROM entities WHERE name='Jonah'")
    st.edit(fid, "Owner's partner Jonah is a nurse")
    check("...and a name both wordings say keeps its entry (its merges and cards with it)",
          rows(st, "SELECT id FROM entities WHERE name='Jonah'") == before
          and aliases(st) == [("partner", "Jonah", fid)], (before, aliases(st)))
    long_q = " ".join(["word"] * 150) + " where is my partner working"
    with closing(st._connect()) as c:
        roots, names = st._entity_hits(c, long_q, time.time())
    check("a long message is looked up in full, not just its first words", names == ["Jonah"],
          names)
    st = fresh("lease")
    fid = st.add("Owner's landlord is called Ms Byrne")
    st.retire(fid, valid_to=time.time() + 86400 * 30)
    check("guard: a lease that ends next month keeps its links until then",
          aliases(st) == [("landlord", "Ms Byrne", fid)])


def t_erase_wipes_the_names_that_only_it_said():
    st = fresh("erase")
    secret = "Owner's therapist is called Zebulon Quackenbush"
    fid = st.add(secret)
    keep = st.add("Priya's wedding is in Lisbon")
    x = types.ModuleType("jarvis_extract")
    cards = []
    x.propose_merge = lambda text: cards.append(text) or 900 + len(cards)
    sys.modules["jarvis_extract"] = x
    try:
        typo = st.add("Zebulon Quackenbushh sent a card")   # a likely typo: a card with the name
    finally:
        sys.modules.pop("jarvis_extract", None)
    check("a card was raised with the name in it (the thing erase must wipe)",
          len(cards) == 1 and "Quackenbush" in cards[0], cards)
    with closing(st._connect()) as c:
        c.execute("CREATE TABLE IF NOT EXISTS proposals (id INTEGER PRIMARY KEY, text TEXT,"
                  " replaces TEXT, confidence REAL, source TEXT, created REAL, state TEXT"
                  " DEFAULT 'pending', decided REAL, fact_id INTEGER, replaces_id INTEGER,"
                  " replaces_text TEXT)")
        c.execute("INSERT INTO proposals (id, text, source, created) VALUES (901, ?, ?, ?)",
                  (cards[0], M.MERGE_SOURCE, time.time()))
    out = st.erase(fid)
    check("erase reports the card copy it wiped", out["copies"] >= 1, out)
    left = entity_names(st)
    check("the entry named only by the erased fact is gone", "Zebulon Quackenbush" not in left,
          left)
    check("...its alias \"therapist\" too", all(a[0] != "therapist" for a in aliases(st)))
    check("...the card is turned down and its words wiped",
          rows(st, "SELECT text, state FROM proposals WHERE id=901")
          == [(M.ERASED_TEXT, "rejected")])
    check("...and the waiting question about the pair is gone",
          rows(st, "SELECT * FROM entity_merge_asks") == [])
    check("a name another fact still says stays",
          "Priya" in left and "Lisbon" in left and "Zebulon Quackenbushh" in left, left)
    # The other spelling is still said by a fact of its own; erase that too,
    # and then no byte of either name may be left in the file.
    st.erase(typo)
    raw = b"".join(p.read_bytes() for p in st.path.parent.glob("memory.db*") if p.is_file())
    for word in (b"Zebulon", b"zebulon", b"Quackenbush", b"quackenbush", b"therapist"):
        check(f"raw bytes of memory.db and its -wal: no {word.decode()!r}", word not in raw)
    check("guard: the fact that stays is still findable",
          any(h["id"] == keep for h in st.search("Lisbon wedding")))


def t_erase_after_forget_leaves_nothing():
    st = fresh("erase-forgotten")
    fid = st.add("Owner's cousin is called Ottoline Wibberley")
    st.retire(fid)
    st.erase(fid)
    raw = b"".join(p.read_bytes() for p in st.path.parent.glob("memory.db*") if p.is_file())
    check("forgotten first, erased later: the name is not in the file",
          b"Ottoline" not in raw and b"ottoline" not in raw and b"Wibberley" not in raw)


# ================================================================ merging ==

def t_exact_match_joins_by_itself():
    st = fresh("exact")
    st.add("Hull City won on Saturday")
    st.add("Owner supports HULL CITY")
    check("the same name in other capitals is one entry",
          rows(st, "SELECT COUNT(*) FROM entities") == [(1,)], entity_names(st))


def t_a_likely_typo_is_one_card_per_pair():
    check("Graphiti's threshold: a doubled last letter on a long name is likely the same",
          M.likely_same("Priya Sharma", "Priya Sharmaa"))
    check("...a short name is not specific enough to guess (stays apart)",
          not M.likely_same("Priya", "Priyaa"))
    check("...different names are not", not M.likely_same("Priya Sharma", "Priya Patel"))
    st = fresh("typo")
    st.add("Priya Sharma is my sister")
    st.add("Priya Sharmaa sent flowers")
    asks = rows(st, "SELECT a, b, state FROM entity_merge_asks")
    check("without the patch in this process: one question waits, no card is guessed",
          len(asks) == 1 and asks[0][2] == "waiting", asks)
    x = types.ModuleType("jarvis_extract")
    cards = []
    x.propose_merge = lambda text: cards.append(text) or 500 + len(cards)
    sys.modules["jarvis_extract"] = x
    try:
        st.add("Priya Sharmaa likes jazz")
        st.add("Priya Sharma lives in Leeds")
        check("ONE card for the pair, however many facts name them", len(cards) == 1, cards)
        check("the card asks in plain words, with both names",
              cards and cards[0].startswith("Are these the same person?")
              and "Priya Sharma" in cards[0] and "Priya Sharmaa" in cards[0], cards)
        check("the question is marked asked, with the card's id",
              rows(st, "SELECT state, proposal_id FROM entity_merge_asks") == [("asked", 501)])
        st.raise_merge_cards()
        check("asking again raises nothing", len(cards) == 1)
    finally:
        sys.modules.pop("jarvis_extract", None)
    q = "where does Priya Sharmaa live?"
    before = [h["text"] for h in st.search(q, k=5, entities=True)]
    out = st.merge_from_card(501)
    check("yes on that card joins that one pair", out and out["changed"], out)
    check("a merge is a pointer: both entries are still there",
          len(rows(st, "SELECT id FROM entities WHERE name LIKE 'Priya Sharma%'")) == 2)
    after = [h["text"] for h in st.search(q, k=5, entities=True)]
    check("after the yes, a question about one finds the other's facts",
          "Priya Sharma lives in Leeds" in after, (before, after))
    import inspect
    check("merge takes exactly two entries - there is no list form",
          list(inspect.signature(st.merge).parameters) == ["keep", "other"])
    check("guard: nothing in the store merges without a card (no bulk, no auto-merge)",
          "def merge_all" not in Path(M.__file__).read_text(encoding="utf-8"))


def t_no_means_never_asked_again():
    st = fresh("no")
    with closing(st._connect()) as c:
        c.execute("CREATE TABLE proposals (id INTEGER PRIMARY KEY, text TEXT, source TEXT,"
                  " state TEXT DEFAULT 'pending', decided REAL)")
    x = types.ModuleType("jarvis_extract")
    cards = []

    def propose(text):
        with closing(st._connect()) as c:
            pid = c.execute("INSERT INTO proposals (text, source) VALUES (?, ?)",
                            (text, M.MERGE_SOURCE)).lastrowid
        cards.append(pid)
        return pid
    x.propose_merge = propose
    sys.modules["jarvis_extract"] = x
    try:
        st.add("Bartholomew Jones fixed the boiler")
        st.add("Bartholomew Joness came round")
        with closing(st._connect()) as c:
            c.execute("UPDATE proposals SET state='rejected' WHERE id=?", (cards[0],))
        st.add("Bartholomew Joness phoned again")
        st.raise_merge_cards()
    finally:
        sys.modules.pop("jarvis_extract", None)
    check("\"different\" is remembered and the pair is never asked about again",
          len(cards) == 1 and rows(st, "SELECT state FROM entity_merge_asks") == [("different",)],
          (cards, rows(st, "SELECT state FROM entity_merge_asks")))


# ================================================================= recall ==

def t_the_sisters_wedding():
    st, ids = wedding_store("wedding")
    q = "what did I say about my sister's wedding"
    old = [h["id"] for h in st.search(q, k=5)]
    new = [h["id"] for h in st.search(q, k=5, entities=True)]
    check("before: the wedding fact is NOT found (only Mario's wedding)",
          ids["wedding"] not in old, old)
    check("with the entity layer: Priya's wedding and speech are found",
          ids["wedding"] in new and ids["speech"] in new, new)
    check("...and the other person's wedding is no longer first",
          new.index(ids["mario"]) > new.index(ids["wedding"]) if ids["mario"] in new else True, new)
    with closing(st._connect()) as c:
        roots, names = st._entity_hits(c, q, time.time())
    check("the query rewrite: \"my sister's\" -> Priya, by the alias table",
          names == ["Priya"], names)
    via = [h["id"] for h in P.recall(st, q, k=5)]
    check("chat recall (jarvis_past.recall) uses it", ids["wedding"] in via, via)


def t_k_and_floors_unchanged():
    st, ids = wedding_store("k")
    q = "what did I say about my sister's wedding"
    check("k still caps it", len(st.search(q, k=2, entities=True)) <= 2)
    check("k=0 is still nothing", st.search(q, k=0, entities=True) == [])
    check("guard: the floors are the same numbers",
          M._MIN_WORD_SHARE == M._share_env("JARVIS_MEMORY_MIN_WORD_SHARE", 0.1)
          and M._MAX_VEC_DISTANCE == float(__import__("os").environ.get(
              "JARVIS_MEMORY_MAX_DISTANCE", "1.0")))
    st.retire(ids["wedding"])
    check("a forgotten fact is not brought back by a link",
          ids["wedding"] not in [h["id"] for h in st.search(q, k=5, entities=True)])
    saved = M._ENTITY_RECALL
    M._ENTITY_RECALL = False
    try:
        check("JARVIS_MEMORY_ENTITIES=0 turns it off: the old search exactly",
              st.search(q, k=5, entities=True) == st.search(q, k=5))
    finally:
        M._ENTITY_RECALL = saved
    check("guard: other callers (find_one, timeline) do not ask for it",
          "entities=True" not in Path(M.__file__).read_text(encoding="utf-8")
          .split("def find_one", 1)[1].split("def current_facts", 1)[0])


def t_an_ambiguous_alias_says_nothing():
    st = fresh("ambiguous")
    for n in ("Ava Brown", "Ben Clarke", "Chloe Davies"):
        st.add(f"Owner's friend {n} plays tennis")
    with closing(st._connect()) as c:
        roots, _ = st._entity_hits(c, "what does my friend play?", time.time())
    check("\"friend\" naming three people is ignored", roots == [], roots)


def t_no_model_on_the_chat_path():
    st, ids = wedding_store("nomodel")
    calls = []
    real_open, real_conn = urllib.request.urlopen, socket.create_connection
    urllib.request.urlopen = lambda *a, **k: calls.append("urlopen")
    socket.create_connection = lambda *a, **k: calls.append("socket")
    try:
        P.recall(st, "what did I say about my sister's wedding", k=5)
        st.search("where is my sister getting married", k=5, entities=True)
    finally:
        urllib.request.urlopen, socket.create_connection = real_open, real_conn
    check("recall with the entity layer opens no connection at all", calls == [], calls)
    src = Path(M.__file__).read_text(encoding="utf-8")
    check("jarvis_memory imports no model or network code",
          "import jarvis_entities" not in src and "urllib.request" not in src
          and "http.client" not in src and "import socket" not in src)


def t_temporary_chat_and_pins_unchanged():
    hud, log = _stack.stand_in("jarvis_hud.py")
    check("the whole jarvis_hud.py stack builds with memory-entities.patch",
          hud is not None and '"/api/memory/entities"' in hud, "\n".join(log or [])[-300:])
    if hud is None:
        return
    check("every memory-entities hunk found its context (none made up)",
          not any("memory-entities" in line for line in log or []), log)
    at = hud.index("if _temporary_chat(body):\n                        hits = []")
    check("a temporary chat still searches nothing, before any recall (and so no entities)",
          at < hud.index("hits = _past.recall(jarvis_memory.store(), query, k=MEMORY_K)"))
    check("the chat turn has no other search that asks for entities",
          "entities=True" not in hud)
    st, ids = wedding_store("pins")
    st.pin(ids["speech"])
    hits = P.recall(st, "what did I say about my sister's wedding", k=5)
    chosen = M.with_profile(st, hits, 5)
    check("the pinned list is unchanged: pinned first, once",
          chosen[0]["id"] == ids["speech"] and chosen[0]["pinned"]
          and [h["id"] for h in chosen].count(ids["speech"]) == 1)


# ================================================================ the list ==

def t_the_list_for_about():
    st, ids = wedding_store("view")
    v = st.entities_view()
    priya = next((e for e in v["entities"] if e["name"] == "Priya"), None)
    check("Priya is listed with \"sister\" and her three facts, newest first",
          priya and priya["aliases"] == ["sister"] and priya["kind"] == "person"
          and priya["fact_ids"] == sorted([ids["sister"], ids["wedding"], ids["speech"]],
                                          reverse=True), priya)
    check("the list carries no fact's words - only names and ids",
          "married" not in json.dumps(v) and "speech" not in json.dumps(v))
    st.retire(ids["wedding"])
    priya = next(e for e in st.entities_view()["entities"] if e["name"] == "Priya")
    check("a forgotten fact leaves it", ids["wedding"] not in priya["fact_ids"])
    code, body = M.handle_entities_get()
    check("handle_entities_get: 200 and the same shape", code == 200 and "entities" in body)


# ============================================================ model pass ==

def t_the_model_pass():
    check("OFF by default", E.enabled() is False)
    check("off: the learner hook does nothing and starts no thread",
          E.after_learner_pass([1, 2]) is False)
    st = fresh("model")
    fid = st.add("my sister priya is getting married in goa")
    check("guard: lower-case names are not found by the fixed rules",
          entity_names(st) == [], entity_names(st))
    asked = []

    def ask(prompt):
        asked.append(prompt)
        return json.dumps({"entities": [
            {"name": "priya", "kind": "person", "aliases": ["sister", "sibling"]},
            {"name": "Priyanka", "kind": "person", "aliases": []},
            {"name": "goa", "kind": "place", "aliases": []}]})
    out = E.run_pass([fid], ask=ask, store=st)
    check("ONE call for the pass", len(asked) == 1 and out["ran"], out)
    check("the facts go in the prompt, word for word", "my sister priya" in asked[0])
    check("a grounded name from the model is linked", "priya" in entity_names(st), entity_names(st))
    check("a name that is not in the fact is dropped", "Priyanka" not in entity_names(st))
    check("an alias not in the fact (\"sibling\") is dropped; \"sister\" is kept",
          [a[0] for a in aliases(st)] == ["sister"], aliases(st))
    out = E.run_pass([fid], ollama="http://10.0.0.5:11434", model="llama3:8b", store=st,
                     force=True)
    check("a model not on this PC is never asked", not out["ran"] and out["why"], out)
    out = E.run_pass([fid], ollama="http://127.0.0.1:11434", model="gpt-oss:120b-cloud",
                     store=st, force=True)
    check("a cloud model is never asked", not out["ran"] and out["why"], out)
    check("the schema is the sketch's: entities of {name, kind, aliases}",
          E.SCHEMA["properties"]["entities"]["items"]["required"] == ["name", "kind", "aliases"])
    check("guard: nonsense back from the model links nothing",
          E.parse("not json") == [] and E.parse({"entities": "x"}) == [])
    src = (HERE / "jarvis_auto_learn.py").read_text(encoding="utf-8")
    check("the learner calls it once per pass, after the facts are saved",
          "_entity_model_pass(result[\"saved\"], ollama, model)" in src)


# ================================================================ the patch ==

class _Handler:
    def __init__(self, path):
        self.path = path
        self.sent = None

    def _send(self, code, body):
        self.sent = (code, body)
        return self.sent


def _fragment(src, start, stop):
    i = src.index(start)
    i = src.rfind("\n", 0, i) + 1
    j = src.index(stop, i)
    j = src.rfind("\n", 0, j) + 1
    return textwrap.dedent(src[i:j])


def t_the_route_and_the_pending_filter():
    hud, _ = _stack.stand_in("jarvis_hud.py")
    block = _fragment(hud, '        if path == "/api/memory/entities":',
                      '        if path == "/api/memory/profile":')
    st, ids = wedding_store("route")

    def call(url, *, origin=True, token=True, memory=True, module=M):
        ns = {"_origin_ok": lambda s: origin, "_token_ok": lambda s: token, "MEMORY": memory,
              "json": json, "jarvis_memory": module}
        exec(compile("def handle(self, path):\n" + textwrap.indent(block, "    "),
                     "<memory/entities>", "exec"), ns)
        h = _Handler(url)
        ns["handle"](h, url.split("?", 1)[0])
        return h.sent
    url = "/api/memory/entities"
    check("another site's page is refused (403)", call(url, origin=False)[0] == 403)
    check("no or a wrong token (401)", call(url, token=False)[0] == 401)
    check("memory not running (503)", call(url, memory=False)[0] == 503)
    code, body = call(url)
    check("200: the list", code == 200 and any(e["name"] == "Priya" for e in body["entities"]),
          (code, body))
    code, body = call(url, module=types.SimpleNamespace(store=M.store))
    check("an older jarvis_memory.py: 501 in words", code == 501 and "jarvis_memory.py"
          in body["error"])
    at = hud.index("# memory-entities.patch: an \"are these the same?\" card")
    filt = hud[hud.rfind("\n", 0, at) + 1:hud.index("return self._send(200, {\"available\": True,"
                                                    " \"pending\": rows,", at)]
    filt = textwrap.dedent(filt)
    rows_in = [{"id": 1, "source": "conversation"}, {"id": 2, "source": "entity_merge"}]
    for q, want in (("", [1]), ("?merge_cards=1", [1, 2]), ("?merge_cards=yes", [1]),
                    ("?retire_cards=1&sleep_offer=1", [1]),
                    ("?retire_cards=1&sleep_offer=1&merge_cards=1", [1, 2])):
        from urllib.parse import parse_qs
        ns = {"rows": list(rows_in), "self": types.SimpleNamespace(path="/api/memory/pending" + q),
              "parse_qs": parse_qs, "jarvis_extract": types.SimpleNamespace()}
        exec(compile(filt, "<pending filter>", "exec"), ns)
        check(f"/api/memory/pending{q or ''}: merge cards {'shown' if 2 in want else 'hidden'}",
              [r["id"] for r in ns["rows"]] == want, ns["rows"])


def t_accepting_the_card_adds_no_fact():
    x, _ = _stack.stand_in("jarvis_extract.py")
    check("the jarvis_extract.py stack builds with memory-entities.patch",
          x is not None and "def propose_merge(text: str)" in x)
    st = fresh("accept")
    with closing(st._connect()) as c:
        c.execute("CREATE TABLE proposals (id INTEGER PRIMARY KEY, text TEXT, replaces TEXT,"
                  " confidence REAL, source TEXT, created REAL, state TEXT DEFAULT 'pending',"
                  " decided REAL, fact_id INTEGER, replaces_id INTEGER, replaces_text TEXT)")
    ns = {"M": M, "closing": closing, "time": time, "Optional": __import__("typing").Optional,
          "_init": lambda c: None, "_cfg": lambda k, d=None: d, "_dropped_full": 0,
          "RETIRE_SOURCE": "feedback_retire", "_accept_retire": None}
    code = "\n".join([next(line for line in x.splitlines() if line.startswith("MERGE_SOURCE = ")),
                      _stack.function_text(x, "propose_merge"),
                      _stack.function_text(x, "_accept_merge"),
                      _stack.function_text(x, "_accept")])
    exec(compile(code, "<extract merge>", "exec"), ns)
    sys.modules["jarvis_extract"] = types.SimpleNamespace(propose_merge=ns["propose_merge"])
    try:
        st.add("Florentina Castellanos plays chess")
        st.add("Florentina Castellanoss won again")
    finally:
        sys.modules.pop("jarvis_extract", None)
    cards = rows(st, "SELECT id, source, state, replaces_id FROM proposals")
    check("the patched propose_merge queued ONE card, source entity_merge, no replaces_id",
          len(cards) == 1 and cards[0][1:] == ("entity_merge", "pending", None), cards)
    facts_before = rows(st, "SELECT COUNT(*) FROM facts")
    with closing(st._connect()) as c:
        row = dict(c.execute("SELECT * FROM proposals WHERE id=?", (cards[0][0],)).fetchone())
        got = ns["_accept"](c, st, row)
    check("accepting it adds no fact", rows(st, "SELECT COUNT(*) FROM facts") == facts_before
          and got == 0)
    check("...and joins that pair", len(rows(st, "SELECT id FROM entities WHERE merged_into IS"
                                              " NOT NULL")) == 1)
    check("...and the card is accepted, with no fact id",
          rows(st, "SELECT state, fact_id FROM proposals") == [("accepted", None)])


def t_listed_and_applies():
    names = [str(p).replace("\\", "/").split("/")[-1] for p in _stack.order()]
    check("memory-entities.patch is in apply-patches.ps1's order, after temporary-chat "
          "(whose route lines are its context)",
          "memory-entities.patch" in names
          and names.index("memory-entities.patch") > names.index("temporary-chat.patch"))
    import _where
    check("jarvis_entities.py is shipped whole", "jarvis_entities.py" in _where.SHIPPED)
    git = shutil.which("git")
    if not git:
        return check("SKIP - git is not installed", True)
    order = _stack.order()
    at = order.index("memory-entities.patch")
    for target in ("jarvis_hud.py", "jarvis_extract.py"):
        text, _ = _stack.stand_in(target, order[:at])
        d = Path(tempfile.mkdtemp(prefix="jarvis-entities-patch-", dir=_TMP))
        (d / target).write_text(text, encoding="utf-8", newline="\n")
        (d / "p.patch").write_bytes((HERE / "memory-entities.patch").read_bytes()
                                    .replace(b"\r\n", b"\n"))
        for extra in (["--check"], [], ["--check", "--reverse"]):
            r = subprocess.run([git, "apply", "--include", target, *extra, "p.patch"], cwd=d,
                               capture_output=True, text=True)
            check(f"{target}: git apply {' '.join(extra) or '(forwards)'}",
                  r.returncode == 0, r.stderr.strip())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
