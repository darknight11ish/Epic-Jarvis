"""memory_tryout.py - try other memory-search models against Jarvis's own, on
this PC. Standard library only. NOTHING SWITCHES: Jarvis keeps using
bge-small-en-v1.5 and its re-ranker setting stays as it is.

The owner chose this on 2026-09-28 ("Model tryouts"; the research audit,
docs/RESEARCH-AUDIT-2026-09-28.md section 6, item 5). Two kinds of model
help Jarvis find a saved fact:

  - the MEANING model ("embedder"): turns each fact and each question into
    numbers, so "what should I cook?" finds "Owner is vegetarian". Today:
    BAAI/bge-small-en-v1.5. Tried against it: any of the models this build
    can run (jarvis_memory.ONNX_EMBED_MODELS - fastembed 0.8.0's own
    embedding list, now run on ONNX Runtime directly). The two newer meaning
    models the first tryout named, Qwen/Qwen3-Embedding-0.6B-Q and
    google/embeddinggemma-300m, arrived in fastembed 0.8.1, which the locked
    install never took; this build does not list them, so a tryout of those
    two is no longer possible.
  - the RE-RANKER: reads the question and each of the top ~20 facts together
    and puts the best first. Today: Xenova/ms-marco-MiniLM-L-6-v2 (and off
    until the self-test shows it helps). Tried: MiniLM-L-12 and
    jina-reranker-v1-turbo-en.

It runs backend/eval_memory.py - the memory self-test, on made-up facts in a
temporary folder, never your memory - once per model, with the model named
in JARVIS_MEMORY_EMBED_MODEL / JARVIS_MEMORY_RERANK_MODEL for THAT run only,
and prints one table with a verdict per model by rules written down before
anything was measured (EMBED_RULE and RERANK_RULE below), then the rows for
docs/MEMORY-SCOREBOARD.md.

Each model is loaded once through jarvis_memory's own OnnxEmbedder or
OnnxReranker before its run - the same classes Jarvis itself uses - so a
model this build does not have, or one that cannot be downloaded on this PC,
is said plainly in words and simply not run. Nothing crashes, and nothing is
claimed for a model that never loaded.

The only downloads are the models themselves, once, the memory search's own
way (huggingface-hub inside jarvis_memory.py): about 130 MB for the default
meaning model (the others are bigger, up to about 1.2 GB) and about 80 MB
per re-ranker, from Hugging Face. Nothing about you is sent anywhere.

    py -3 tools\\model_tryout\\memory_tryout.py

Results: <your home folder>\\jarvis-model-tryout\\memory-<date-time>\\ -
results.txt and results.json, and each run's own report beside them.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
EVAL = REPO / "backend" / "eval_memory.py"

EMBED_DEFAULT = "BAAI/bge-small-en-v1.5"
EMBEDDERS = (EMBED_DEFAULT,)
RERANK_DEFAULT = "Xenova/ms-marco-MiniLM-L-6-v2"
RERANKERS = (RERANK_DEFAULT, "Xenova/ms-marco-MiniLM-L-12-v2",
             "jinaai/jina-reranker-v1-turbo-en")

#: The two meaning models the 2026-09-28 tryout named that this build cannot
#: run: they only arrived in fastembed 0.8.1, and the locked install never
#: took 0.8.1 (its list is 0.8.0's). Jarvis now runs 0.8.0's own list on ONNX
#: Runtime directly, so a tryout of these is no longer possible - said plainly
#: rather than dropped without a word.
GONE_MEANING_MODELS = {
    "Qwen/Qwen3-Embedding-0.6B": "it was only in fastembed 0.8.1, which the "
                                 "locked install never took",
    "Qwen/Qwen3-Embedding-0.6B-Q": "it was only in fastembed 0.8.1, which the "
                                   "locked install never took",
    "google/embeddinggemma-300m": "it was only in fastembed 0.8.1, which the "
                                  "locked install never took",
}

RECALL_GAIN = 2.0          # points of recall@5 a new meaning model must add
SEARCH_P95_MS = 250.0      # a spoken answer waits for this search
RERANK_GAIN = 1.0          # points of recall@5 a re-ranker must add ...
RERANK_MRR_GAIN = 0.02     # ... or this much MRR (the right fact nearer the top)
RERANK_BUDGET_MS = 1500.0  # jarvis_memory.RERANK_BUDGET_S: slower re-ranks are skipped

EMBED_RULE = (
    f"A meaning model is worth trying if, on the hardest test (the most facts about the "
    f"same things), each at its own best distance floor, it finds the right fact at least "
    f"{RECALL_GAIN:g} points more often than {EMBED_DEFAULT}, brings back no more wrong "
    f"facts for questions memory cannot answer, no more old versions, and a search takes "
    f"at most {SEARCH_P95_MS:g} ms (95 in 100 searches) - a spoken answer waits for it.")
RERANK_RULE = (
    f"A re-ranker helps if, on the hardest test, it adds at least {RERANK_GAIN:g} point of "
    f"recall@5 or {RERANK_MRR_GAIN} of MRR over the same search without it, brings back no "
    f"more old versions, and re-ranks within {RERANK_BUDGET_MS:g} ms (95 in 100) - Jarvis "
    f"does not wait longer than that.")


# --------------------------------------------------------------------------
#   Reading one eval_memory.py result (pure; tested offline)
# --------------------------------------------------------------------------

def _line(level: dict, which: str) -> dict:
    if which == "reranked":
        return level.get("reranked") or {}
    return level.get("entities") or level.get("after") or {}


def hardest(res: dict):
    lv = [x for x in res.get("levels") or [] if x.get("filler") == "same_topic"] \
        or list(res.get("levels") or [])
    return max(lv, key=lambda x: x.get("filler_facts", 0)) if lv else None


def smallest(res: dict):
    lv = list(res.get("levels") or [])
    return min(lv, key=lambda x: (x.get("filler_facts", 0), x.get("filler") != "neutral")) \
        if lv else None


def learner_cases(res: dict):
    kinds = (res.get("learner") or {}).get("kinds") or {}
    if not kinds:
        return None
    return (sum(int(k.get("right", 0)) for k in kinds.values()),
            sum(int(k.get("total", 0)) for k in kinds.values()))


def read_embed(res: dict) -> dict:
    """The numbers the embedder verdict and the scoreboard need."""
    h, s = hardest(res), smallest(res)
    if h is None:
        return {"ok": False, "why": "the self-test gave no levels"}
    a = _line(h, "entities")
    out = {"ok": True, "embedder": res.get("embedder"),
           "semantic": bool(res.get("semantic") and res.get("vector_search")),
           "facts": h.get("facts"), "recall5": a.get("recall_at_5"),
           "dont_know": a.get("dont_know_facts_avg"),
           "old_versions": int(a.get("replaced_came_back") or 0)
           + int(a.get("time_wrong_version") or 0),
           "p95_ms": a.get("search_p95_ms", h.get("search_p95_ms")),
           "distance": res.get("max_distance_configured")}
    dc = (res.get("distance_choice") or {}).get("chosen")
    if dc is not None:
        for r in res.get("distance_sweep") or []:
            if (r.get("filler"), r.get("filler_facts"), r.get("max_distance")) == \
                    (h.get("filler"), h.get("filler_facts"), dc):
                out.update(distance=dc, recall5=r.get("recall_at_5"),
                           dont_know=r.get("dont_know_facts_avg"))
    out["scoreboard"] = scoreboard_numbers(res, s, "entities")
    return out


def read_rerank(res: dict) -> dict:
    h = hardest(res)
    if h is None or not h.get("reranked"):
        return {"ok": False, "why": str(res.get("reranker") or "the re-ranker was not measured")}
    a, r = _line(h, "entities"), _line(h, "reranked")
    return {"ok": True, "model": res.get("reranker"), "facts": h.get("facts"),
            "recall5_without": a.get("recall_at_5"), "recall5": r.get("recall_at_5"),
            "mrr_without": a.get("mrr"), "mrr": r.get("mrr"),
            "old_without": int(a.get("replaced_came_back") or 0)
            + int(a.get("time_wrong_version") or 0),
            "old_versions": int(r.get("replaced_came_back") or 0)
            + int(r.get("time_wrong_version") or 0),
            "p95_ms": r.get("search_p95_ms"),
            "scoreboard": scoreboard_numbers(res, smallest(res), "reranked")}


def scoreboard_numbers(res: dict, level, which: str) -> dict:
    a = _line(level or {}, which)
    lc = learner_cases(res)
    return {"recall5_71": a.get("recall_at_5"),
            "two_fact": (a.get("multi_all_found"), a.get("multi_questions")),
            "time": (a.get("time_found"), a.get("time_questions"),
                     a.get("time_wrong_version")),
            "learner": lc}


def embed_verdict(base: dict, cand: dict) -> tuple:
    if not cand.get("ok"):
        return "not tested", cand.get("why", "")
    if not base.get("ok") or base.get("recall5") is None:
        return "cannot say", f"{EMBED_DEFAULT} was not measured, so there is nothing to compare"
    if not cand.get("semantic"):
        return "cannot say", ("meaning search did not run (the memory search packages, "
                              "the model, or sqlite-vec is missing)")
    gain = round((cand["recall5"] or 0) - (base["recall5"] or 0), 1)
    why = []
    if gain < RECALL_GAIN:
        why.append(f"recall@5 {cand['recall5']}% against {base['recall5']}% "
                   f"({gain:+g} points; {RECALL_GAIN:g} needed)")
    if (cand.get("dont_know") or 0) > (base.get("dont_know") or 0):
        why.append(f"more wrong facts for questions memory cannot answer "
                   f"({cand['dont_know']} against {base['dont_know']})")
    if cand.get("old_versions", 0) > base.get("old_versions", 0):
        why.append(f"more old versions ({cand['old_versions']} against "
                   f"{base['old_versions']})")
    if (cand.get("p95_ms") or 0) > SEARCH_P95_MS:
        why.append(f"a search takes {cand['p95_ms']} ms (at most {SEARCH_P95_MS:g})")
    if why:
        return "keep " + EMBED_DEFAULT.split("/")[-1], "; ".join(why)
    return "worth trying", (f"recall@5 {cand['recall5']}% against {base['recall5']}% "
                            f"({gain:+g} points) at distance floor {cand.get('distance')}; "
                            "switching means setting JARVIS_MEMORY_EMBED_MODEL and "
                            f"JARVIS_MEMORY_MAX_DISTANCE={cand.get('distance')}, and Jarvis "
                            "then embeds every saved fact again")


def rerank_verdict(r: dict) -> tuple:
    if not r.get("ok"):
        return "not tested", r.get("why", "")
    gain = round((r["recall5"] or 0) - (r["recall5_without"] or 0), 1)
    mrr_gain = round((r["mrr"] or 0) - (r["mrr_without"] or 0), 3)
    why = []
    if gain < RERANK_GAIN and mrr_gain < RERANK_MRR_GAIN:
        why.append(f"recall@5 {gain:+g} points and MRR {mrr_gain:+g} - not enough")
    if r["old_versions"] > r["old_without"]:
        why.append(f"more old versions ({r['old_versions']} against {r['old_without']})")
    if (r.get("p95_ms") or 0) > RERANK_BUDGET_MS:
        why.append(f"too slow: {r['p95_ms']} ms, and Jarvis waits at most "
                   f"{RERANK_BUDGET_MS:g}")
    if why:
        return "does not help", "; ".join(why)
    return "helps", f"recall@5 {gain:+g} points, MRR {mrr_gain:+g}, {r['p95_ms']} ms"


def scoreboard_row(date: str, change: str, sb: dict) -> str:
    """One row in docs/MEMORY-SCOREBOARD.md's table format."""
    tf = sb.get("two_fact") or (None, None)
    tm = sb.get("time") or (None, None, None)
    lc = sb.get("learner")
    return (f"| {date} | {change} | the PC | {sb.get('recall5_71')}% "
            f"| {tf[0]}/{tf[1]} | {tm[0]}/{tm[1]} ({tm[2]} wrong) "
            f"| {f'{lc[0]}/{lc[1]}' if lc else '-'} |")


# --------------------------------------------------------------------------
#   The engine (jarvis_memory.py, run on ONNX Runtime directly since
#   2026-10-21 - fastembed is not part of this tool or the backend any more)
# --------------------------------------------------------------------------

def load_engine():
    """The backend's own jarvis_memory module, or None.

    Searched the way backend/eval_memory.py searches it: the live backend
    folder when JARVIS_BACKEND names one, then this repository's
    backend/rebuilt, then backend. Nothing is stored and no memory database
    is opened by importing it - but as a belt and braces, JARVIS_MEMORY_DB is
    pointed at a throwaway file first, so even a future accidental store
    could never open the owner's real memory.
    """
    os.environ.setdefault(
        "JARVIS_MEMORY_DB",
        str(Path(tempfile.gettempdir()) / "jarvis-memory-tryout-not-a-store.db"))
    paths = [str(REPO / "backend" / "rebuilt"), str(REPO / "backend")]
    real = os.environ.get("JARVIS_BACKEND")
    if real and (Path(real) / "jarvis_memory.py").is_file():
        paths.insert(0, real)
    for p in reversed(paths):
        sys.path.insert(0, p)
    try:
        import jarvis_memory as M
        return M
    except Exception:
        return None


def engine_installed() -> bool:
    """Are the packages the memory search runs on actually importable here?"""
    try:
        import onnxruntime  # noqa: F401
        import tokenizers  # noqa: F401
        return True
    except Exception:
        return False


def memory_lists(engine) -> tuple:
    """(onnxruntime version, meaning models, re-rankers) this build can run.

    The lists are jarvis_memory's own static registries - ONNX_EMBED_MODELS
    and ONNX_RERANK_MODELS - so they are exactly the models the backend has,
    not a library's list that could drift from it.
    """
    try:
        from importlib.metadata import version
        ver = version("onnxruntime")
    except Exception:
        ver = "unknown version"
    return (ver, set(engine.ONNX_EMBED_MODELS), set(engine.ONNX_RERANK_MODELS))


def load_model(engine, model: str, *, rerank: bool = False) -> tuple:
    """(True, "") if this PC can load `model`, else (False, why in plain words).

    Loaded through the backend's OWN class - jarvis_memory.OnnxEmbedder or
    jarvis_memory.OnnxReranker - so the tryout can never disagree with what
    Jarvis would load, and a model that is not on this PC yet is fetched by
    the same code that fetches it for Jarvis (once; the run beside it then
    uses the cached copy). A model this build does not have, or one that
    cannot be downloaded or loaded, comes back as a plain sentence for the
    caller to print - never as a crash.
    """
    try:
        maker = engine.OnnxReranker if rerank else engine.OnnxEmbedder
        maker(model)        # loading is the whole check; the object is thrown away
    except Exception as exc:
        plain = isinstance(exc, getattr(engine, "EmbedModelUnavailable", ()))
        return False, (str(exc) if plain else
                       f"the model could not be loaded on this PC "
                       f"({type(exc).__name__})")
    return True, ""


def run_eval(out_dir: Path, sizes: str, embed: str, rerank, run=subprocess.run) -> dict:
    """One eval_memory.py run with the two switches set for it alone."""
    out_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, JARVIS_MEMORY_EMBED_MODEL=embed)
    env.pop("JARVIS_MEMORY_RERANK_MODEL", None)
    env.pop("JARVIS_NO_EMBED", None)
    # Measure the real re-ranker for THIS run: JARVIS_MEMORY_RERANK=1 lets the
    # self-test load it even though the owner keeps the setting off otherwise.
    # For this run only - the owner's setting is never touched, and the tools
    # switch nothing.
    env.pop("JARVIS_MEMORY_RERANK", None)
    if rerank:
        env["JARVIS_MEMORY_RERANK_MODEL"] = rerank
        env["JARVIS_MEMORY_RERANK"] = "1"
    cmd = [sys.executable, str(EVAL), "--sizes", sizes, "--reranker",
           "auto" if rerank else "off", "--out", str(out_dir)]
    try:
        run(cmd, env=env, timeout=6 * 3600)
    except Exception as exc:
        return {"_error": f"eval_memory.py did not finish ({type(exc).__name__})"}
    got = sorted(out_dir.glob("memory-eval-*.json"))
    if not got:
        return {"_error": "eval_memory.py wrote no results"}
    return json.loads(got[-1].read_text(encoding="utf-8"))


def table(rows: list, head: tuple) -> str:
    widths = [max(len(str(x[i])) for x in [head] + rows) for i in range(len(head))]
    fmt = "  ".join("{:<%d}" % w for w in widths)
    return "\n".join([fmt.format(*head), fmt.format(*("-" * w for w in widths))]
                     + [fmt.format(*r) for r in rows])


def _v(x, unit=""):
    return "-" if x is None else f"{x}{unit}"


def _not_run(why: str) -> dict:
    return {"ok": False, "why": why}


def main(argv=None, *, run=subprocess.run, engine=None, out_root=None, say=print) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--embedders", nargs="+", default=list(EMBEDDERS),
                    help="meaning models to try (any name jarvis_memory.ONNX_EMBED_MODELS "
                         "has; default: bge-small only)")
    ap.add_argument("--rerankers", nargs="+", default=list(RERANKERS),
                    help="re-rankers to try (any name jarvis_memory.ONNX_RERANK_MODELS has)")
    ap.add_argument("--sizes", default="0,100,1000",
                    help="filler sizes for the self-test (default 0,100,1000; add 10000 "
                         "for the full test, several hours with the bigger models)")
    a = ap.parse_args(argv)
    if engine is None:
        if not engine_installed():
            say("the memory search needs the onnxruntime and tokenizers packages, and "
                "one of them is not installed, so there is no meaning model to try. "
                "Run apply-patches.ps1 first (docs/INSTALL.md).")
            return 2
        engine = load_engine()
        if engine is None:
            say("the memory search's own module (jarvis_memory.py) could not be imported "
                "here, so there is no meaning model to try. Run apply-patches.ps1 first "
                "(docs/INSTALL.md).")
            return 2
    if not (hasattr(engine, "ONNX_EMBED_MODELS") and hasattr(engine, "ONNX_RERANK_MODELS")
            and hasattr(engine, "OnnxEmbedder") and hasattr(engine, "OnnxReranker")):
        say("the jarvis_memory.py in your Jarvis folder is older than this tryout - it "
            "does not run the memory models on ONNX Runtime directly, so there is "
            "nothing to try. Run apply-patches.ps1 first (docs/INSTALL.md).")
        return 2
    ver, emb_have, rr_have = memory_lists(engine)
    embedders = [EMBED_DEFAULT] + [m for m in a.embedders if m != EMBED_DEFAULT]
    rerankers = [RERANK_DEFAULT] + [m for m in a.rerankers if m != RERANK_DEFAULT]
    missing = [m for m in embedders if m not in emb_have] + \
              [m for m in rerankers if m not in rr_have]
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = Path(out_root or (Path.home() / "jarvis-model-tryout")) / f"memory-{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    src = getattr(engine, "__file__", None)
    if src:
        say(f"jarvis_memory.py: {Path(src).resolve()}")
    say(f"onnxruntime {ver} is installed.")
    if missing:
        say("Not a model this build can run, so not tried: " + ", ".join(missing) + ".")
        gone = [m for m in missing if m in GONE_MEANING_MODELS]
        if gone:
            say("That includes " + ", ".join(gone) + ": " + GONE_MEANING_MODELS[gone[0]]
                + ". Jarvis now runs fastembed 0.8.0's own model list directly on ONNX "
                "Runtime, and those two are not in it - so no tryout of them is possible.")
    n = 1 + len([m for m in embedders[1:] if m in emb_have]) + \
        len([m for m in rerankers[1:] if m in rr_have])
    say(f"{n} self-test run(s), about 1 to 3 hours in all (longer the first time: the models "
        f"download once). Results go in {out}")
    ok, why = load_model(engine, EMBED_DEFAULT)
    if not ok:
        say(f"\nThe meaning model Jarvis uses cannot be loaded on this PC, so there is "
            f"nothing to compare against: {why}")
        return 2
    base_rr = RERANK_DEFAULT if RERANK_DEFAULT in rr_have else None
    if base_rr:
        ok, why = load_model(engine, RERANK_DEFAULT, rerank=True)
        if not ok:
            say(f"\nThe re-ranker Jarvis uses cannot be loaded on this PC, so the first run "
                f"measures the meaning model without it: {why}")
            base_rr = None
    base_res = run_eval(out / "embed-bge-small", a.sizes, EMBED_DEFAULT, base_rr, run)
    base = read_embed(base_res) if "_error" not in base_res else _not_run(base_res["_error"])
    emb_rows = [(EMBED_DEFAULT, base, base_res)]
    for m in embedders[1:]:
        if m not in emb_have:
            emb_rows.append((m, _not_run("not a model this build can run"), {}))
            continue
        say(f"\n=== meaning model {m} ===")
        ok, why = load_model(engine, m)
        if not ok:
            say(f"It was not tried: {why}")
            emb_rows.append((m, _not_run(why), {}))
            continue
        res = run_eval(out / ("embed-" + m.split("/")[-1]), a.sizes, m, None, run)
        got = read_embed(res) if "_error" not in res else _not_run(res["_error"])
        if got.get("ok") and not str(got.get("embedder") or "").startswith(m):
            got = _not_run(f"the self-test used {got.get('embedder')} instead: "
                           "the model could not be loaded, or the jarvis_memory.py "
                           "in your Jarvis folder is older than this tryout (run "
                           "apply-patches.ps1 first)")
        emb_rows.append((m, got, res))
    rr_rows = [(RERANK_DEFAULT, read_rerank(base_res) if "_error" not in base_res
                else _not_run(base_res["_error"]), base_res)]
    for m in rerankers[1:]:
        if m not in rr_have:
            rr_rows.append((m, _not_run("not a model this build can run"), {}))
            continue
        say(f"\n=== re-ranker {m} ===")
        ok, why = load_model(engine, m, rerank=True)
        if not ok:
            say(f"It was not tried: {why}")
            rr_rows.append((m, _not_run(why), {}))
            continue
        res = run_eval(out / ("rerank-" + m.split("/")[-1]), a.sizes, EMBED_DEFAULT, m, run)
        got = read_rerank(res) if "_error" not in res else _not_run(res["_error"])
        if got.get("ok") and got.get("model") != m:
            got = _not_run(f"the self-test measured {got.get('model')} instead: the "
                           "jarvis_memory.py in your Jarvis folder is older than "
                           "this tryout (run apply-patches.ps1 first)")
        rr_rows.append((m, got, res))
    date = datetime.date.today().isoformat()
    lines = ["MEANING MODELS (on the hardest test; each at its own best distance floor)", ""]
    t = []
    for m, r, _res in emb_rows:
        vd = ("(today's)", "") if m == EMBED_DEFAULT else embed_verdict(base, r)
        t.append((m, _v(r.get("recall5"), "%"), _v(r.get("dont_know")),
                  _v(r.get("old_versions")), _v(r.get("p95_ms"), " ms"),
                  _v(r.get("distance")), vd[0]))
    lines.append(table(t, ("Model", "Recall@5", "Wrong facts (don't know)", "Old versions",
                           "Search p95", "Distance floor", "Verdict")))
    lines.append("")
    for m, r, _res in emb_rows[1:]:
        vd = embed_verdict(base, r)
        lines.append(f"{m}: {vd[0]} - {vd[1]}")
    lines += ["", "RE-RANKERS (on the hardest test, with bge-small; without -> with)", ""]
    t = []
    for m, r, _res in rr_rows:
        vd = rerank_verdict(r)
        t.append((m, f"{_v(r.get('recall5_without'), '%')} -> {_v(r.get('recall5'), '%')}",
                  f"{_v(r.get('mrr_without'))} -> {_v(r.get('mrr'))}",
                  _v(r.get("p95_ms"), " ms"), vd[0]))
    lines.append(table(t, ("Model", "Recall@5", "MRR", "p95 with it", "Verdict")))
    lines.append("")
    for m, r, _res in rr_rows:
        vd = rerank_verdict(r)
        lines.append(f"{m}: {vd[0]} - {vd[1]}")
    lines += ["", "The rules, written down before anything was measured:", "- " + EMBED_RULE,
              "- " + RERANK_RULE, "",
              "Rows for docs/MEMORY-SCOREBOARD.md (the 71-fact numbers, as that page shows):"]
    for m, r, _res in emb_rows:
        if r.get("ok"):
            lines.append(scoreboard_row(date, f"Tryout: meaning model {m}", r["scoreboard"]))
    for m, r, _res in rr_rows:
        if r.get("ok"):
            lines.append(scoreboard_row(date, f"Tryout: re-ranker {m} (on)", r["scoreboard"]))
    lines += ["", "Nothing was switched: Jarvis still uses bge-small-en-v1.5, and the "
              "re-ranker setting is as it was. Changing either is your decision; "
              "tools/model_tryout/README.md has the lines."]
    text = "\n".join(lines)
    (out / "results.txt").write_text(text + "\n", encoding="utf-8")
    (out / "results.json").write_text(json.dumps(
        {"onnxruntime": ver, "sizes": a.sizes, "embed_rule": EMBED_RULE,
         "rerank_rule": RERANK_RULE,
         "embedders": [{"model": m, **r} for m, r, _ in emb_rows],
         "rerankers": [{"model": m, **r} for m, r, _ in rr_rows]}, indent=1),
        encoding="utf-8")
    say("\n" + text)
    say(f"\nSaved: {out / 'results.txt'} and results.json beside it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
