"""Memory recall: the word-search floor, search as Jarvis knew it, and
questions about the past. Plus the memory self-test itself.

    python3 test_memory_recall.py

Memory wave 1 (2026-09-24). Four things, each tested against the REAL code -
the rebuilt jarvis_memory.py, the shipped jarvis_past.py, and past-recall.patch
lifted out of the whole patch stack:

  1. F3, the word floor. "What is my dog called?" used to come back with
     "Owner's cat is called Biscuit": word search added every hit, with no
     cut-off, and the two share "called". MemoryStore.search() now drops a
     word hit that matches too little of the question (_MIN_WORD_SHARE,
     JARVIS_MEMORY_MIN_WORD_SHARE). find_one() - which decides what a
     correction retires - keeps its own stricter rule and no floor.
  2. search(known_at=t): only facts Jarvis BELIEVED at t, the same condition
     known_at() uses, and combinable with at=.
  3. Past-tense recall in chat (jarvis_past.py + past-recall.patch): a
     question about the past also gets matching retired facts, labelled
     "(no longer true since <date>)"; an ordinary question gets exactly
     what it got before.
  4. backend/eval_memory.py and its golden set: made-up data only, the
     scratch store only, and the numbers it prints.

Every check in 1-3 fails on the code before this change (checked by running
this file against it): the floor, known_at= and jarvis_past did not exist.
The find_one and "ordinary question unchanged" checks are guards - they pass
on the old code too, and must keep passing.

No network, no model.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("rebuilt/jarvis_memory.py", "jarvis_past.py")
sys.path.insert(0, str(HERE / "rebuilt"))
os.environ.setdefault("JARVIS_NO_EMBED", "1")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-recall-"))
_fw = types.ModuleType("jarvis_framework")
_fw.CONFIG_DIR = _TMP
_fw.LOG_DIR = _TMP
_fw.audit_log = lambda *a, **k: None
_fw.load_framework = lambda *a, **k: {}
sys.modules.setdefault("jarvis_framework", _fw)

import jarvis_memory as M  # noqa: E402
import jarvis_past as P    # noqa: E402
import _stack              # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


_n = [0]


def store():
    _n[0] += 1
    return M.MemoryStore(_TMP / f"m{_n[0]}.db", embedder=M.HashEmbedder())


def day(text):
    y, m, d = (int(x) for x in text.split("-"))
    return time.mktime((y, m, d, 12, 0, 0, 0, 0, -1))


def dated(st, fid, told, retired=None, by=None):
    """Give a fact the dates a real one would have had."""
    c = st._connect()
    try:
        c.execute("UPDATE facts SET created=?, valid_from=? WHERE id=?", (day(told), day(told), fid))
        if retired:
            c.execute("UPDATE facts SET valid_to=?, retired_at=?, retired_by=? WHERE id=?",
                      (day(retired), day(retired), by, fid))
    finally:
        c.close()


def texts(hits):
    return [h["text"] for h in hits]


# ================================================================ 1. F3 ==

def t_the_dog_question_no_longer_gets_the_cat():
    st = store()
    st.add("Owner's cat is called Biscuit")
    st.add("Owner lives in Leeds")
    st.add("Owner drinks tea, not coffee")
    got = st.search("What is my dog called?", k=5)
    check("F3: 'what is my dog called?' brings back no fact", got == [], texts(got))
    old = st.search("What is my dog called?", k=5, word_floor=0.0)
    check("F3: with the floor off (the old behaviour) it was the cat",
          texts(old) == ["Owner's cat is called Biscuit"], texts(old))
    check("the right fact is still found on one word ('live' / 'lives')",
          texts(st.search("Where do I live?", k=5)) == ["Owner lives in Leeds"])
    check("and on the question's own words",
          texts(st.search("What's my cat called?", k=5))[:1] == ["Owner's cat is called Biscuit"])


def t_the_floor_weighs_rare_words_more():
    st = store()
    for t in ("Owner plays football on Thursdays", "Owner's colleague plays chess",
              "Owner's cousin plays golf", "Owner's friend plays tennis"):
        st.add(t)
    # At an explicit 0.4: "plays" is in every fact, so it weighs less than
    # "tennis" (in one) - a hit on "plays" alone is about a third of the
    # question, a hit on both is all of it.
    got = texts(st.search("Who do I know that plays tennis?", k=5, word_floor=0.4))
    check("a fact that matches only a word every fact has ('plays') weighs less "
          "than one with the rare word ('tennis')",
          got == ["Owner's friend plays tennis"], got)
    old = texts(st.search("Who do I know that plays tennis?", k=5, word_floor=0.0))
    check("with the floor off, all four came back", len(old) == 4, old)


def t_frame_words_do_not_count():
    st = store()
    a = st.add("Owner lives in Harrogate")
    b = st.add("Owner lives in York")
    dated(st, a, "2025-06-20", "2026-03-01", b)
    dated(st, b, "2026-03-01")
    got = st.search("Where did I live before?", k=5, include_retired=True)
    check("'before' is a frame word: the old address is not floored away for lacking it",
          "Owner lives in Harrogate" in texts(got), texts(got))
    check("a question made only of frame words keeps its hits (nothing to judge by)",
          M._floor_terms(["name", "called", "2025", "june"]) == [])


def t_find_one_keeps_its_own_rule():
    st = store()
    st.add("Mario's editor is Vim")
    st.add("Mario drives a 1998 Volvo")
    was = M._MIN_WORD_SHARE
    M._MIN_WORD_SHARE = 0.9
    try:
        hit = st.find_one("Mario drives a 2005 Honda")
        check("guard: find_one still identifies the fact a correction replaces, "
              "whatever the recall floor", hit is not None and "Volvo" in hit["text"], hit)
        check("guard: and still refuses a vague one",
              st.find_one("Mario's allergy") is None)
    finally:
        M._MIN_WORD_SHARE = was


def t_the_setting_never_stops_the_backend():
    code = "import jarvis_memory as M; print(M._MIN_WORD_SHARE)"
    for raw, want in (("", "0.1"), ("half", "0.1"), ("nan", "0.1"), ("5", "1.0"),
                      ("-1", "0.0"), ("0", "0.0"), ("0.3", "0.3")):
        env = dict(os.environ, JARVIS_MEMORY_MIN_WORD_SHARE=raw, JARVIS_NO_EMBED="1",
                   PYTHONPATH=os.pathsep.join([str(HERE / "rebuilt"), str(HERE)]))
        r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                           text=True, cwd=str(_TMP))
        check(f"JARVIS_MEMORY_MIN_WORD_SHARE={raw!r} -> {want}, and the module imports",
              r.returncode == 0 and r.stdout.strip() == want, r.stdout + r.stderr[-300:])


def t_the_default_is_the_measured_one():
    src = (HERE / "rebuilt" / "jarvis_memory.py").read_text(encoding="utf-8")
    m = re.search(r'_share_env\("JARVIS_MEMORY_MIN_WORD_SHARE", ([\d.]+)\)', src)
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    check("the default word floor is written in backend/README.md's memory self-test section",
          m and f"JARVIS_MEMORY_MIN_WORD_SHARE` is **{m.group(1)}**" in readme,
          m.group(1) if m else "no default found")


# ======================================================= 2. known_at ==

def t_search_as_jarvis_knew_it():
    st = store()
    old = st.add("Owner's manager is called Marta")
    new = st.add("Owner's new manager is called Tom")
    dated(st, old, "2025-07-01", "2026-04-10", new)
    dated(st, new, "2026-04-10")
    q = "Who is my manager?"
    feb = st.search(q, k=5, known_at=day("2026-02-01"))
    check("known_at in February: Marta, not Tom", texts(feb) == ["Owner's manager is called Marta"],
          texts(feb))
    may = st.search(q, k=5, known_at=day("2026-05-01"))
    check("known_at in May: Tom, not Marta", texts(may) == ["Owner's new manager is called Tom"],
          texts(may))
    check("known_at before either was told: nothing",
          st.search(q, k=5, known_at=day("2025-01-01")) == [])
    ids = {r["id"] for r in st.known_at(day("2026-02-01"))}
    check("the same condition as known_at(): every hit is in its list",
          {h["id"] for h in feb} <= ids)
    both = st.search(q, k=5, known_at=day("2026-02-01"), at=day("2026-02-01"))
    check("combinable with at=: believed AND true in February -> Marta",
          texts(both) == ["Owner's manager is called Marta"], texts(both))
    none = st.search(q, k=5, known_at=day("2026-02-01"), at=day("2026-06-01"))
    check("believed in February but asked what was true in June -> nothing",
          none == [], texts(none))
    check("without known_at, search is as before: the current fact only",
          texts(st.search(q, k=5)) == ["Owner's new manager is called Tom"])


# ======================================================= 3. the past ==

NOW = day("2026-09-24")


def _moved():
    st = store()
    a = st.add("Owner lives in Harrogate")
    b = st.add("Owner lives in York")
    c = st.add("Owner lived in Hull as a student")      # current fact, about the past
    d = st.add("Owner lives in Bath")                    # an earlier address, retired long ago
    dated(st, d, "2024-01-10", "2024-06-01", a)
    dated(st, a, "2024-06-01", "2026-03-01", b)
    dated(st, b, "2026-03-01")
    dated(st, c, "2025-02-02")
    return st


def t_is_it_about_the_past():
    for q in ("Where did I live before?", "Where did I use to live?",
              "What car did I drive last year?", "Who was my manager back in 2025?",
              "What did I believe about my laptop?", "Where was I living two years ago?",
              "Wo habe ich früher gewohnt?", "¿Dónde vivía el año pasado?",
              "Où habitais-je l'année dernière ?", "Dove abitavo prima?",
              "Onde eu morava antigamente?", "Waar woonde ik vroeger?",
              "Gdzie mieszkałem w zeszłym roku?", "What was my address in June 2025?"):
        check(f"past: {q!r}", P.is_past_question(q, NOW))
    for q in ("Where do I live?", "Remind me in June", "Remind me before tomorrow",
              "Book a table before the meeting", "What's my cat called?",
              "Is it la prima volta?", "What is on in May?", ""):
        check(f"ordinary: {q!r}", not P.is_past_question(q, NOW))
    check("belief: 'what did I tell you ...'", P.is_belief_question("What did I tell you in June?"))
    check("not belief: 'where did I live'", not P.is_belief_question("Where did I live?"))


def t_the_dates_are_read_by_a_fixed_parser():
    def w(q):
        r = P.when(q, NOW)
        return r and tuple(time.strftime("%Y-%m-%d", time.localtime(x)) for x in r)
    check("'in June' is the most recent June that has begun",
          w("where did I live in June") == ("2026-06-01", "2026-07-01"), w("where did I live in June"))
    check("'in October' (not begun this year) is last year's",
          w("what did I say in October") == ("2025-10-01", "2025-11-01"), w("in October"))
    check("'last June' is the most recent June that has ended",
          w("last June") == ("2026-06-01", "2026-07-01"))
    check("'last year'", w("what car did I drive last year") == ("2025-01-01", "2026-01-01"))
    check("'last year' in German", w("letztes Jahr") == ("2025-01-01", "2026-01-01"))
    check("'June 2025'", w("back in June 2025") == ("2025-06-01", "2025-07-01"))
    check("'in 2024'", w("where did I live in 2024") == ("2024-01-01", "2025-01-01"))
    check("'last month'", w("last month") == ("2026-08-01", "2026-09-01"))
    check("a future year is no window", w("in 2031") is None)
    check("no date, no window", w("where did I live before") is None)
    check("'may' the verb is not a month", w("I may have said") is None)


def t_chat_recall_brings_the_old_address_back_labelled():
    st = _moved()
    got = P.recall(st, "Where did I live before?", k=5, now=NOW)
    t = texts(got)
    check("the current fact first, as always", t[:1] == ["Owner lives in York"], t)
    check("then the old one, labelled with when it stopped being true",
          "Owner lives in Harrogate (no longer true since 2026-03-01)" in t, t)
    check("every retired one is labelled, and the label is only on them",
          all(("(no longer true since" in h["text"]) == bool(h.get("past")) for h in got), t)
    check("at most PAST_K old facts", sum(1 for h in got if h.get("past")) <= P.PAST_K)


def t_a_date_narrows_it():
    st = _moved()
    t = texts(P.recall(st, "Where did I live in 2025?", k=5, now=NOW))
    check("2025: Harrogate (true then) is back", any(x.startswith("Owner lives in Harrogate")
                                                     for x in t), t)
    check("2025: Bath (retired in 2024) is not", not any(x.startswith("Owner lives in Bath")
                                                         for x in t), t)
    t = texts(P.recall(st, "Where did I live back in 2024?", k=5, now=NOW))
    check("2024: both old addresses were true then", sum(x.startswith(("Owner lives in Bath",
                                                         "Owner lives in Harrogate")) for x in t) == 2, t)


def t_what_did_jarvis_believe_uses_known_at():
    st = store()
    a = st.add("Owner's laptop runs Ubuntu")
    b = st.add("Owner switched the laptop from Ubuntu to Fedora")
    dated(st, a, "2025-09-01", "2026-05-15", b)
    dated(st, b, "2026-05-15")
    got = texts(P.recall(st, "What did I tell you about my laptop in January?", k=5, now=NOW))
    check("belief + January: the Ubuntu fact Jarvis held then comes back, labelled",
          "Owner's laptop runs Ubuntu (no longer true since 2026-05-15)" in got, got)


def t_ordinary_questions_are_unchanged():
    st = _moved()
    for q in ("Where do I live?", "Remind me in June where I live", "lives"):
        check(f"guard: {q!r} gets exactly store.search()",
              P.recall(st, q, k=5, now=NOW) == st.search(q, k=5))
    check("k=0 is none at all, past question or not",
          P.recall(st, "Where did I live before?", k=0, now=NOW) == [])
    class Boom:
        def search(self, q, k=8, **kw):
            if kw:
                raise RuntimeError("the past half broke")
            return [{"id": 1, "text": "Owner lives in York", "current": True}]
    check("if the past half fails, the current facts still come back",
          texts(P.recall(Boom(), "Where did I live before?", k=5, now=NOW))
          == ["Owner lives in York"])


# temporary-chat.patch (later in the order) adds a temporary-chat check to
# these lines; an ordinary request is not one.
_NOT_TEMPORARY = {"_temporary_chat": lambda body: False, "body": {}}


def _patched_block():
    hud, log = _stack.stand_in("jarvis_hud.py")
    i = hud.find("# past-recall.patch")
    check("past-recall.patch is in the stacked jarvis_hud.py", i >= 0)
    if i < 0:
        return None, hud
    start = hud.rfind("\n", 0, i) + 1
    end = hud.index("if hits:", i)
    end = hud.rfind("\n", 0, end) + 1
    return textwrap.dedent(hud[start:end]), hud


def t_the_stacked_chat_turn_calls_it():
    block, hud = _patched_block()
    if block is None:
        return
    check("it replaced the plain search in the recall block, and kept it as the fallback",
          block.count("jarvis_memory.store().search(query, k=MEMORY_K)") == 1
          and "_past.recall(jarvis_memory.store(), query, k=MEMORY_K)" in block, block)
    st = _moved()
    fake = types.SimpleNamespace(store=lambda: st)
    ns = {"jarvis_memory": fake, "query": "Where did I live before?", "MEMORY_K": 5,
          **_NOT_TEMPORARY}
    exec(compile(block, "<past-recall block>", "exec"), ns)
    check("the stacked lines bring the old address back, labelled",
          any("Owner lives in Harrogate (no longer true since" in h["text"] for h in ns["hits"]),
          texts(ns["hits"]))
    ns = {"jarvis_memory": fake, "query": "Where do I live?", "MEMORY_K": 5, **_NOT_TEMPORARY}
    exec(compile(block, "<past-recall block>", "exec"), ns)
    check("and an ordinary question gets exactly the old search",
          ns["hits"] == st.search("Where do I live?", k=5))
    real = sys.modules.get("jarvis_past")
    sys.modules["jarvis_past"] = None                      # the import fails
    try:
        ns = {"jarvis_memory": fake, "query": "Where did I live before?", "MEMORY_K": 5,
          **_NOT_TEMPORARY}
        exec(compile(block, "<past-recall block>", "exec"), ns)
    finally:
        sys.modules["jarvis_past"] = real
    check("without jarvis_past.py: the old search, no old facts",
          ns["hits"] == st.search("Where did I live before?", k=5), texts(ns["hits"]))
    after = hud[hud.find("# past-recall.patch"):]
    check("the labelled text is what reaches the FACTS block (chosen_facts reads h['text'])",
          '"text": h["text"]' in after[:3000])


def t_the_patch_applies_forwards_and_backwards():
    import shutil
    git = shutil.which("git")
    if not git:
        return check("SKIP - git is not installed", True)
    order = _stack.order()
    before = order[:order.index("past-recall.patch")]
    text, log = _stack.stand_in("jarvis_hud.py", before)
    check("jarvis_hud.py: the stack before past-recall.patch builds", text is not None)
    if text is None:
        return
    # The stack up to and including this patch: a later patch (hardware.patch,
    # 2026-09-25) may change the same file, and that is not this test's business.
    full, flog = _stack.stand_in("jarvis_hud.py", order[:order.index("past-recall.patch") + 1])
    check("its one hunk found its context in the stack (none made up)",
          not any("past-recall" in str(line) for line in flog),
          [line for line in flog if "past-recall" in str(line)])
    d = Path(tempfile.mkdtemp(prefix="jarvis-past-recall-patch-", dir=_TMP))
    (d / "jarvis_hud.py").write_text(text, encoding="utf-8", newline="\n")
    (d / "p.patch").write_bytes((HERE / "past-recall.patch").read_bytes().replace(b"\r\n", b"\n"))
    for extra in (["--check"], [], ["--check", "--reverse"], ["--reverse"], []):
        r = subprocess.run([git, "apply", *extra, "p.patch"], cwd=d, capture_output=True,
                           text=True)
        check(f"git apply {' '.join(extra) or '(forwards)'} past-recall.patch",
              r.returncode == 0, r.stderr.strip())
    # The stack up to and including this patch: memory-profile.patch
    # (2026-09-24) comes after it and edits two of its lines.
    upto = _stack.stand_in("jarvis_hud.py", order[:order.index("past-recall.patch") + 1])[0]
    check("forwards gives the stack's own text",
          (d / "jarvis_hud.py").read_text(encoding="utf-8") == upto)


# ============================================== 4. the self-test itself ==

def t_the_golden_set_is_made_up_and_complete():
    facts = [json.loads(x) for x in (HERE / "eval" / "golden_facts.jsonl")
             .read_text(encoding="utf-8").splitlines() if x.strip()]
    qs = [json.loads(x) for x in (HERE / "eval" / "golden_questions.jsonl")
          .read_text(encoding="utf-8").splitlines() if x.strip()]
    ids = {f["id"] for f in facts}
    check("about 60 facts", 55 <= len(facts) <= 70, len(facts))
    check("about 120 questions", 115 <= len(qs) <= 135, len(qs))
    check("about 25 'don't know' questions",
          sum(q["type"] == "abstain" for q in qs) >= 25)
    check("past-belief questions carry a known_at date",
          all(q.get("known_at") for q in qs if q["type"] == "belief")
          and sum(q["type"] == "belief" for q in qs) >= 5)
    check("every answer and stale id is a golden fact",
          all(set(q["answers"]) | set(q.get("stale", [])) <= ids for q in qs))
    check("every replaced fact names its replacement",
          all(f["replaced_by"] in ids for f in facts if f.get("retired")))
    check("people, a changed address, replaced facts, negations, dates, preferences",
          {"person", "replaced", "update", "negation", "date", "preference"}
          <= {f["kind"] for f in facts})
    for t in {q["type"] for q in qs}:
        n = [q["split"] for q in qs if q["type"] == t]
        check(f"type {t}: split evenly into tune and test",
              abs(n.count("tune") - n.count("test")) <= 1, n)
    # Not the owner's data: nothing from the real setup the repo describes.
    blob = " ".join(f["text"] for f in facts).lower()
    check("nothing about the owner's real machine or project",
          not any(w in blob for w in ("2080", "2060", "jarvis", "kotlin", "tauri", "pcadmin")))


def t_the_self_test_runs_on_a_scratch_store_only():
    out = _TMP / "eval-out"
    home = _TMP / "home"
    (home / ".openjarvis").mkdir(parents=True)
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home),
               PYTHONDONTWRITEBYTECODE="1")
    env.pop("JARVIS_MEMORY_DB", None)
    r = subprocess.run([sys.executable, str(HERE / "eval_memory.py"), "--sizes", "0,20",
                        "--words-only", "--out", str(out)], env=env, capture_output=True,
                       text=True, timeout=600)
    check("eval_memory.py --sizes 0,20 --words-only runs", r.returncode == 0,
          (r.stdout + r.stderr)[-1500:])
    js = sorted(out.glob("memory-eval-*.json"))
    md = sorted(out.glob("memory-eval-*.md"))
    check("it writes one .json and one .md", len(js) == 1 and len(md) == 1)
    if not js:
        return
    res = json.loads(js[0].read_text(encoding="utf-8"))
    check("it says which embedder it used", res["embedder"] == "hash-v1"
          and "words only" in md[0].read_text(encoding="utf-8"))
    check("two fillers x two sizes", len(res["levels"]) == 4, len(res["levels"]))
    lv = res["levels"][0]
    for key in ("recall_at_1", "recall_at_5", "mrr", "ndcg_at_5", "replaced_came_back",
                "dont_know_facts_avg", "dont_know_none_pct", "past_found", "as_of_found"):
        check(f"measures {key}", key in lv["after"] and key in lv["before"])
    check("timings and size", all(k in lv for k in ("search_p50_ms", "search_p95_ms",
                                                    "db_bytes")))
    check("a replaced fact never comes back for a question about now",
          all(x["after"]["replaced_came_back"] == 0 for x in res["levels"]))
    check("every past question finds its old fact, labelled, on the golden set alone",
          lv["after"]["past_found"] == lv["after"]["past_questions"]
          == lv["after"]["past_labelled"], lv["after"])
    check("every as-of question finds what Jarvis believed then, never the later version",
          lv["after"]["as_of_found"] == lv["after"]["as_of_questions"]
          and lv["after"]["as_of_wrong_version"] == 0
          and lv["after"]["as_of_before_told_facts"] == 0, lv["after"])
    check("the word floor was chosen on one half and reported on the other",
          "chosen" in res["word_floor_choice"] and res["word_floor_choice"]["test_half"])
    check("the distance sweep is skipped, and says so, without meaning search",
          res["distance_sweep"] == [] and "skipped" in md[0].read_text(encoding="utf-8"))
    check("the home folder's .openjarvis was never written to",
          list((home / ".openjarvis").iterdir()) == [])


def t_listed_where_it_must_be():
    import _where
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("jarvis_past.py is shipped by apply-patches.ps1 and in _where.SHIPPED",
          "'jarvis_past.py'" in ps1 and "jarvis_past.py" in _where.SHIPPED)
    # Only the order that matters (its context is memory-prefix's search call
    # and memory-noise's lines), so a new patch added last need not edit this.
    o = [str(p).replace("\\", "/").split("/")[-1] for p in _stack.order()]
    check("past-recall.patch is applied, after memory-prefix and memory-noise",
          "past-recall.patch" in o
          and o.index("past-recall.patch") > o.index("memory-prefix.patch")
          and o.index("past-recall.patch") > o.index("memory-noise.patch"), o[-3:])
    check("memory-profile.patch (it edits past-recall's search lines) comes after it",
          "memory-profile.patch" not in o
          or o.index("memory-profile.patch") > o.index("past-recall.patch"), o[-3:])
    notices = (REPO / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8")
    check("LongMemEval's scoring is credited", "LongMemEval" in notices
          and "eval_memory.py" in notices)


def main():
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                print(f"FAIL  {name} raised\n{traceback.format_exc()}")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
