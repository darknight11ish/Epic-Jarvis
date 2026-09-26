"""test_memory_review.py - the backend fixes from the memory review of
2026-09-27 (docs/MEMORY-REVIEW-2026-09-27.md), one check per bug.

    python3 backend/test_memory_review.py

Every check named "B<n>" failed on the code before its fix (run and seen
failing, 2026-09-26); the checks named "guard" passed before and must keep
passing - they are what the fix must not break.

  B1   a question about a past time labels a CURRENT fact that only became
       true after that time: "(true since <date>)" when the owner's words
       gave the date, "(known since <date>)" when it is only the day Jarvis
       was told.
  B2   month names do not count towards the word floor ("What phone did I
       have in June?" finds "... a Pixel 8 in June 2026"), and are still
       framing words for names and nicknames ("May" is never a name).
  B3   the learner's candidate list finds the fact a correction is about,
       even after chatty messages.
  B4   Jarvis's own memory_search tool recalls what chat recalls.
  B10  "I live in Leeds" and "Owner lives in Leeds" are one fact when
       compared (never when saved).
  B13  a fact saved after a sensitive card keeps its topic, so read-aloud
       and web search still treat it as sensitive.
  B15  a forgotten fact never comes back in a question about the past; a
       corrected one does, labelled.
  B17  both memory models are kept in Jarvis's own folder, not %TEMP%.
  I1   "boss" finds the manager, "GP" the doctor - on lookup only.
  I6   the distance floor is chosen on half the questions, like the word
       floor, and reported on the other half.
  I7   eval_memory.py --against: better / worse / unchanged, and a worse
       recall@5, wrong version or learner case fails the run.
  I13  "for whose wedding?": the fact that says who the person in the top
       fact is, as at most two extra facts - only for a question that asks
       who.

Elsewhere: B5-B9, B11, I3, I4 are cases in backend/eval/learner_cases.jsonl
(test_memory_recall.py runs them all and needs every one right); B12 is in
test_memory_true_from.py; I12 in test_memory_said_again.py; B14 and I5 in
jarvis_sensitive.py --measure (sensitive_cases/probes-2026-09-27.jsonl).
"""
import json
import os
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("rebuilt/jarvis_memory.py", "jarvis_past.py", "jarvis_intake.py")
sys.path.insert(0, str(HERE / "rebuilt"))
os.environ.setdefault("JARVIS_NO_EMBED", "1")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-memory-review-"))
_AUDIT = []
_fw = sys.modules.get("jarvis_framework")
if _fw is None:
    _fw = types.ModuleType("jarvis_framework")
    _fw.LOG_DIR = _TMP
    _fw.load_framework = lambda *a, **k: {}
    sys.modules["jarvis_framework"] = _fw
_fw.CONFIG_DIR = _TMP
_fw.audit_log = lambda event, data=None, **k: _AUDIT.append((event, data))

import jarvis_memory as M  # noqa: E402
import jarvis_past as P    # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


_n = [0]


def store():
    _n[0] += 1
    return M.MemoryStore(_TMP / f"m{_n[0]}.db", embedder=M.HashEmbedder())


def day(text, hour=12):
    y, m, d = (int(x) for x in text.split("-"))
    return time.mktime((y, m, d, hour, 0, 0, 0, 0, -1))


class Clock:
    """jarvis_memory's `time`, with time() fixed - to add a fact on a day."""

    def __init__(self, at):
        self.at = at
        self._real = M.time

    def time(self):
        return self.at

    def __getattr__(self, n):
        return getattr(self._real, n)

    def __enter__(self):
        M.time = self
        return self

    def __exit__(self, *a):
        M.time = self._real


NOW = day("2026-09-24")


def texts(hits):
    return [h["text"] for h in hits]


# ================================================================= B1 ==

def t_b1_a_later_fact_is_labelled_in_a_question_about_the_past():
    st = store()
    with Clock(day("2025-06-20")):
        old = st.add("Owner lives in Harrogate", source="test")
    with Clock(day("2026-03-01")):
        st.add("Owner lives in York", source="test", supersedes=old)
    got = texts(P.recall(st, "Where did I live in February?", k=5, now=NOW))
    check("B1: \"where did I live in February?\" - York, which began in March, is "
          "labelled, never bare", "Owner lives in York" not in got
          and "Owner lives in York (known since 2026-03-01)" in got, got)
    check("guard: Harrogate still comes back, labelled as before",
          "Owner lives in Harrogate (no longer true since 2026-03-01)" in got, got)
    may = texts(P.recall(st, "Where did I live in May?", k=5, now=NOW))
    check("guard: \"... in May?\" - York was true then: no label",
          "Owner lives in York" in may, may)
    now = texts(P.recall(st, "Where do I live?", k=5, now=NOW))
    check("guard: an ordinary question is exactly as before", now == ["Owner lives in York"], now)


def t_b1_a_date_from_the_owners_words_says_true_since():
    st = store()
    with Clock(day("2025-08-01")):
        old = st.add("Owner's phone is an iPhone 12", source="test")
    with Clock(day("2026-07-20")):
        st.add("Owner's phone has been a Pixel 8 since June 2026", source="test",
               supersedes=old)
    got = texts(P.recall(st, "What phone did I have in March?", k=5, now=NOW))
    check("B1: the Pixel (true from 1 June, by the owner's words) is labelled \"true since\"",
          "Owner's phone has been a Pixel 8 since June 2026 (true since 2026-06-01)" in got, got)


# ================================================================= B2 ==

def t_b2_a_month_in_the_question_counts_for_the_word_floor():
    st = store()
    for t in ("Owner's phone case is blue", "Owner lost a phone charger on the bus",
              "Owner's sister got a new phone", "Owner likes the phone shop on Gillygate"):
        st.add(t, source="test")
    fid = st.add("Owner switched from the iPhone 12 to a Pixel 8 in June 2026", source="test")
    got = [h["id"] for h in st.search("What phone did I have in June?", k=5)]
    check("B2: \"what phone did I have in June?\" finds \"... a Pixel 8 in June 2026\"",
          fid in got, got)


def t_b2_months_are_still_never_names():
    found = M.find_entities("Owner's sister Ana moved to Leeds in May")
    names = [n for n, _ in found["names"]]
    check("guard: \"May\" is still not a name (months stay framing words for names)",
          "May" not in names and "Ana" in names, found)
    check("guard: and never an alias", not M._alias_ok("may") and not M._alias_ok("june"))


# ================================================================= B3 ==

CHATTY = ["The weather's awful today", "Work was busy, loads of meetings",
          "Anyway I watched a film last night"]


def t_b3_the_learner_sees_the_fact_a_correction_is_about():
    import jarvis_intake as I
    st = store()
    for t in ("Owner lives in York", "Owner likes jazz", "Owner's cat is called Biscuit",
              "Owner drinks tea, not coffee", "Owner works night shifts on weekends"):
        st.add(t, source="test")
    move = "I don't live in York any more, I moved to Leeds last week"
    alone = [c["text"] for c in I.candidates(st, [{"role": "user", "content": move}])]
    check("guard: said alone, York is among the facts the learner is shown",
          "Owner lives in York" in alone, alone)
    msgs = [{"role": "user", "content": t} for t in CHATTY + [move]]
    got = [c["text"] for c in I.candidates(st, msgs)]
    check("B3 (L-C1): after three chatty messages, York is still shown", "Owner lives in York"
          in got, got)


# ================================================================= B4 ==

def t_b4_the_memory_search_tool_recalls_what_chat_recalls():
    st = store()
    for t in ("Owner's sister is called Priya", "Priya's wedding is in Lisbon next May",
              "Owner's cat is called Biscuit", "Owner lives in York"):
        st.add(t, source="test")
    keep = getattr(M, "_store", None)
    M._store = st
    try:
        import jarvis_agent
        tool = jarvis_agent._run_memory_search({"query": "What's my sister called?", "k": 5})
    finally:
        M._store = keep
    chat = [h["id"] for h in P.recall(st, "What's my sister called?", k=5)]
    got = [f["id"] for f in tool.get("facts", [])]
    check("B4: memory_search returns the facts chat recall does", got == chat,
          f"tool {got} chat {chat}")
    check("B4: ... including the sister, found through the people layer",
          any("Priya" in f["text"] for f in tool.get("facts", [])), tool)


# ================================================================ B13 ==

#: Words the patterns read as "a person" and nothing else (B14 now catches
#: "tried to kill himself" by its words; this is the kind they still miss,
#: which only the local model sees).
LIAM = "my best mate Liam was in a bad place in May"
LIAM_FACT = "Owner's best mate Liam was in a bad place in May"


def _world(tag):
    """The self-test's learner world (eval_learner.World): a scratch store,
    chat log and the jarvis_extract functions the patch stack writes."""
    import eval_learner as E
    import jarvis_auto_learn as A
    A._reset_for_tests()
    w = E.World(M, _TMP / f"world-{tag}")
    w.fresh()
    return E, A, w


def _learn(E, A, w, turn, fact, model_says):
    import jarvis_sensitive as S
    cid = w.conversation()
    w.say(cid, [], {"text": turn})
    q = w.queue(fact)
    keep = S.ASK_MODEL
    S.ASK_MODEL = lambda prompt: json.dumps(model_says)
    try:
        return q, A.after_pass([q], [{"role": "user", "content": turn}],
                               conversation_id=cid, model="qwen3:8b", ollama=E.LOCAL,
                               learning_on=True, extract=w.x, publish=lambda ids: None)
    finally:
        S.ASK_MODEL = keep


def t_b13_an_accepted_sensitive_card_stays_sensitive_when_used():
    import jarvis_sensitive as S
    E, A, w = _world("card")
    try:
        check("guard: its words alone look everyday to read-aloud (the bug's cause)",
              S.topic(LIAM_FACT) == "", S.topic(LIAM_FACT))
        q, res = _learn(E, A, w, LIAM, LIAM_FACT, {"sensitive": True, "category": "health"})
        check("guard: the local model says health, so it is a card", not res["saved"]
              and "health" in next(iter(res["cards"].values()), ""), res)
        with __import__("contextlib").closing(w.store._connect()) as c:
            row = dict(c.execute("SELECT * FROM proposals WHERE id=?", (q["id"],)).fetchone())
            fid = w.x._accept(c, w.store, row)          # the owner presses Accept
            c.commit()
        saved = w.store.get(fid)
        check("B13: accepted, the fact keeps the topic it was held back for",
              json.loads(saved["meta"] or "{}").get("sensitive") == "health", saved)
        check("B13: read-aloud treats it as sensitive (is_sensitive_fact)",
              A.is_sensitive_fact(LIAM_FACT), A.sensitivity(LIAM_FACT))
        import jarvis_search as WS
        check("B13: ... and so does web search (fact_topic)", WS.fact_topic(LIAM_FACT) != "",
              WS.fact_topic(LIAM_FACT))
        check("B13: ... also when recalled labelled, as a past fact",
              A.is_sensitive_fact(LIAM_FACT + " (no longer true since 2026-09-01)"))
    finally:
        w.close()


def t_b13_saved_under_the_switch_keeps_its_topic():
    E, A, w = _world("switch")
    keep = A.settings
    A.settings = lambda: {"auto": True, "auto_sensitive": True, "why": ""}
    try:
        _q, res = _learn(E, A, w, LIAM, LIAM_FACT, {"sensitive": True, "category": "health"})
        check("guard: with \"Also remember sensitive topics automatically\" on it is saved",
              len(res["saved"]) == 1, res)
        if res["saved"]:
            meta = json.loads(w.store.get(res["saved"][0])["meta"] or "{}")
            check("B13: ... with its topic", meta.get("sensitive") == "health", meta)
        check("B13: and is not read aloud", A.is_sensitive_fact(LIAM_FACT))
    finally:
        A.settings = keep
        w.close()


def t_b13_everyday_facts_about_people_stay_normal():
    E, A, w = _world("everyday")
    try:
        turn, fact = "my sister Ana likes jazz", "Owner's sister Ana likes jazz"
        _q, res = _learn(E, A, w, turn, fact, {"sensitive": False, "category": "none"})
        check("guard: an everyday fact about someone is saved (2026-09-26)",
              len(res["saved"]) == 1, res)
        if res["saved"]:
            meta = json.loads(w.store.get(res["saved"][0])["meta"] or "{}")
            check("guard: ... with no topic kept", "sensitive" not in meta, meta)
        check("guard: ... and may be read aloud", not A.is_sensitive_fact(fact))
    finally:
        w.close()


# ================================================================ B17 ==

def t_b17_the_models_are_kept_in_jarvis_own_folder():
    """fastembed stubbed: what folder is each model asked to live in?"""
    seen = {}

    class TextEmbedding:
        def __init__(self, model_name=None, **kw):
            seen["embed"] = kw.get("cache_dir")

        def embed(self, texts):
            return [[0.1, 0.2, 0.3] for _ in texts]

    class TextCrossEncoder:
        def __init__(self, model_name=None, **kw):
            seen["rerank"] = kw.get("cache_dir")

        def rerank(self, q, texts):
            return [0.0 for _ in texts]

    fe = types.ModuleType("fastembed")
    fe.TextEmbedding = TextEmbedding
    rr = types.ModuleType("fastembed.rerank")
    ce = types.ModuleType("fastembed.rerank.cross_encoder")
    ce.TextCrossEncoder = TextCrossEncoder
    keep = {k: sys.modules.get(k) for k in ("fastembed", "fastembed.rerank",
                                             "fastembed.rerank.cross_encoder")}
    sys.modules.update({"fastembed": fe, "fastembed.rerank": rr,
                        "fastembed.rerank.cross_encoder": ce})
    old_env = os.environ.pop("FASTEMBED_CACHE_PATH", None)
    try:
        M.FastEmbedder()
        M.FastReranker()
        want = str(Path(_fw.CONFIG_DIR) / "models")
        check("B17: the meaning model is kept in Jarvis's own folder, not the temp folder",
              seen.get("embed") == want, seen)
        check("B17: ... and so is the re-ranker", seen.get("rerank") == want, seen)
        os.environ["FASTEMBED_CACHE_PATH"] = str(_TMP / "elsewhere")
        M.FastEmbedder()
        check("B17: FASTEMBED_CACHE_PATH still wins when it is set",
              seen.get("embed") == str(_TMP / "elsewhere"), seen)
    finally:
        os.environ.pop("FASTEMBED_CACHE_PATH", None)
        if old_env is not None:
            os.environ["FASTEMBED_CACHE_PATH"] = old_env
        for k, v in keep.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


# ============================================================ I1, I13 ==

def _people_store():
    st = store()
    for t in ("Owner's sister is called Priya", "Priya's wedding is in Lisbon next May",
              "Owner's partner is called Jonas", "Jonas works as a nurse at the county hospital",
              "Owner's new manager is called Tom", "Owner's doctor is Dr Singh at Priory",
              "Owner wants to learn Portuguese before Priya's wedding",
              "Owner is learning to play the cello"):
        st.add(t, source="test")
    return st


def t_i1_other_words_for_the_same_person_on_lookup():
    st = _people_store()
    boss = texts(st.search("What's my boss called?", k=5, entities=True))
    check("I1: \"my boss\" finds the manager", "Owner's new manager is called Tom" in boss, boss)
    gp = texts(st.search("Who is my GP?", k=5, entities=True))
    check("I1: \"my GP\" finds the doctor", "Owner's doctor is Dr Singh at Priory" in gp, gp)
    wife = texts(st.search("What does my wife do?", k=5, entities=True))
    check("guard: \"my wife\" never finds the partner (not a synonym on purpose)",
          not any("Jonas" in t for t in wife), wife)
    check("guard: only when looking up - the alias table holds the owner's own words",
          not M._alias_ok("") and "boss" not in {r[0] for r in st._connect().execute(
              "SELECT alias FROM entity_aliases")})


def t_i13_one_step_out_from_a_person_for_a_who_question():
    st = _people_store()
    got = texts(st.search("Which language am I learning, and for whose wedding?", k=5,
                          entities=True))
    check("I13: \"for whose wedding?\" also brings who Priya is",
          "Owner's sister is called Priya" in got, got)
    check("I13: ... as at most two extra facts", len(got) <= 5 + M.ENTITY_WHO_MAX, got)
    other = texts(st.search("Which hospital was I born in?", k=5, entities=True))
    check("guard: a question that does not ask who gets no extra fact",
          "Owner's partner is called Jonas" not in other, other)
    plain = texts(st.search("Which language am I learning, and for whose wedding?", k=5))
    check("guard: only with the people layer (chat recall), never a plain search",
          "Owner's sister is called Priya" not in plain or len(plain) <= 5, plain)


# ================================================================ B10 ==

def t_b10_i_and_owner_are_the_same_when_comparing():
    import jarvis_intake as I
    check("B10: \"I live in Leeds\" and \"Owner lives in Leeds\" are one fact",
          I.shape("I live in Leeds") == I.shape("Owner lives in Leeds"))
    check("B10: \"my cat is called Biscuit\" and \"Owner's cat is called Biscuit\" too",
          I.shape("my cat is called Biscuit") == I.shape("Owner's cat is called Biscuit"))
    check("guard: the owner and their sister are still two people",
          I.shape("I like hiking") != I.shape("my sister likes hiking"))
    check("guard: subject and object swapped are still different",
          I.shape("Mario is Dana's boss") != I.shape("Dana is Mario's boss"))
    check("guard: a \"not\" still counts",
          I.shape("I don't live in Leeds") != I.shape("Owner lives in Leeds"))


# ============================================================= I6, I7 ==

def t_i6_the_distance_floor_is_chosen_on_half_and_reported_on_the_other():
    import eval_memory as E

    def row(dist, tune_hits, tune_dk, test_hits, test_dk):
        return {"filler": "neutral", "filler_facts": 0, "max_distance": dist,
                "tune": {"hits": tune_hits, "dont_know_facts_total": tune_dk},
                "test": {"hits": test_hits, "dont_know_facts_total": test_dk,
                         "dont_know_none_pct": 50.0}}
    sweep = [row(0.6, 40, 2, 39, 3), row(0.8, 45, 5, 44, 6), row(1.0, 45, 9, 45, 9),
             row(1.2, 45, 14, 45, 15)]
    got = E.choose_distance(sweep)
    check("I6: the tightest distance that loses no right fact on the tune half is chosen",
          got["chosen"] == 0.8 and got["allowed"] == [0.8, 1.0, 1.2], got)
    check("I6: ... and reported on the test half",
          got["test_half"] and got["test_half"][0]["hits_chosen"] == 44
          and got["test_half"][0]["dont_know_facts_loosest"] == 15, got)


def t_i7_against_an_earlier_run():
    import eval_memory as E

    def run(r5, wrong, gate_right):
        lv = {"filler": "neutral", "filler_facts": 0,
              "after": {"recall_at_5": r5, "replaced_came_back": 0},
              "entities": {"recall_at_5": r5, "time_wrong_version": wrong,
                           "dont_know_facts_avg": 1.47, "search_p50_ms": 1.0}}
        return {"levels": [lv], "learner": {"kinds": {"gate": {"right": gate_right,
                                                                "total": 37}}}}
    lines, worse = E.compare(run(80.9, 0, 37), run(80.9, 0, 37))
    check("I7: the same numbers: all unchanged, and not worse",
          not worse and all("unchanged" in l for l in lines if l.startswith("| neutral")), lines)
    _l, worse = E.compare(run(80.9, 0, 37), run(78.7, 0, 37))
    check("I7: recall@5 down: worse (the run fails)", worse)
    _l, worse = E.compare(run(80.9, 0, 37), run(80.9, 1, 37))
    check("I7: a wrong version more: worse", worse)
    _l, worse = E.compare(run(80.9, 0, 37), run(80.9, 0, 36))
    check("I7: a learner case wrong: worse", worse)
    _l, worse = E.compare(run(78.7, 1, 36), run(80.9, 0, 37))
    check("I7: better is not worse", not worse)


# ================================================================ B15 ==

def t_b15_a_forgotten_fact_never_comes_back_in_the_past():
    st = store()
    with Clock(day("2026-02-03")):
        fid = st.add("Owner has been seeing a therapist on Tuesdays", source="test")
    with Clock(day("2026-09-20")):
        st.retire(fid)                              # Forget, as the route calls it
    got = texts(P.recall(st, "What did I use to do on Tuesdays?", k=5, now=NOW))
    check("B15 (F-1): a forgotten fact is not brought back by \"what did I use to do?\"",
          not any("therapist" in t for t in got), got)
    old = texts(P.recall(st, "What did I tell you in June about Tuesdays?", k=5, now=NOW))
    check("B15: nor by a question about what Jarvis was told then",
          not any("therapist" in t for t in old), old)
    row = st.get(fid)
    check("B15: the row is kept (Forget never deletes) and marked forgotten",
          row is not None and json.loads(row["meta"] or "{}").get("forgotten_at"), row)


def t_b15_a_corrected_fact_still_comes_back_labelled():
    st = store()
    with Clock(day("2025-03-01")):
        old = st.add("Owner worked at Globex", source="test")
    with Clock(day("2026-02-01")):
        st.add("Owner works at Initech", source="test", supersedes=old)
    got = texts(P.recall(st, "Where did I use to work?", k=5, now=NOW))
    check("guard (F-2): a fact replaced by a correction is still history, labelled",
          "Owner worked at Globex (no longer true since 2026-02-01)" in got, got)


def t_b15_a_dated_correction_is_not_a_forget():
    """The desktop's Reword with a date: retire(valid_to) FIRST, then
    add(supersedes). The first call looks like a Forget; the second makes
    it a correction, which stays recallable."""
    st = store()
    with Clock(day("2025-03-01")):
        old = st.add("Owner worked at Globex", source="test")
    with Clock(day("2026-02-01")):
        st.retire(old, valid_to=day("2026-01-10"))
        st.add("Owner works at Initech", source="test", supersedes=old)
    row = st.get(old)
    check("guard: a dated correction clears the Forget mark",
          not json.loads(row["meta"] or "{}").get("forgotten_at") and row["retired_by"], row)
    got = texts(P.recall(st, "Where did I use to work?", k=5, now=NOW))
    check("guard: and the old job comes back as history",
          any(t.startswith("Owner worked at Globex (no longer true since") for t in got), got)


def t_b15_an_end_date_in_the_future_is_not_a_forget():
    st = store()
    fid = st.add("Owner rents the flat on Micklegate", source="test")
    st.retire(fid, valid_to=time.time() + 30 * 86400)
    row = st.get(fid)
    check("guard: a fact that ends later is not marked forgotten",
          not json.loads(row["meta"] or "{}").get("forgotten_at"), row)


if __name__ == "__main__":
    import shutil
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
        sys.exit(1)
