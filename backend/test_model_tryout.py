"""test_model_tryout.py - the "Model tryouts" tools (tools/model_tryout/),
proven offline with a stand-in Ollama and stand-in self-test results.

    python3 backend/test_model_tryout.py

What it proves:

chat_tryout.py
  - each candidate is wrapped exactly like jarvis-primary: FROM the tag,
    jarvis-primary's own SYSTEM block word for word, num_ctx 16384 and
    num_batch 512; the sampling comes from the tag's own download and the
    Modelfile says so (or says it is Jarvis's own when the tag sets none);
  - the verdict follows the rule written down before measuring: within 10
    points of jarvis-primary's tool test and a learner test not lower is
    "worth trying"; anything else is not, with the reason;
  - the 1st, 2nd and 3rd request after loading are timed, and how much of
    the model sat on the card is read from /api/ps;
  - it never makes, changes or removes jarvis-primary; it removes only the
    jarvis-cand-* models IT made (not one that was there before), keeps
    them with --keep, and loads jarvis-primary back at the end - also when
    stopped with Ctrl+C;
  - it refuses a non-local Ollama address, a busy graphics card, and a PC
    without jarvis-primary; a model that is not downloaded, or that Ollama
    says cannot use tools, is "not tested" with a plain reason.

memory_tryout.py
  - each self-test run gets its model through the two switches, for that run
    only; the meaning-model and re-ranker verdicts follow their rules;
  - a model this fastembed does not have is not run, and the one-line
    upgrade is printed; a run that silently measured the default instead
    (an older jarvis_memory.py) is caught;
  - the scoreboard rows use docs/MEMORY-SCOREBOARD.md's table format.

No model, no network, no GPU.
"""
import contextlib
import io
import json
import shutil
import socket
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped, REPO  # noqa: E402

require_shipped("jarvis_agent.py")
sys.path.append(str(HERE / "rebuilt"))
sys.path.insert(0, str(REPO / "tools" / "tool_eval"))
sys.path.insert(0, str(REPO / "tools" / "model_tryout"))
import ollama_tool_eval as E  # noqa: E402
import behaviour_cases as BH  # noqa: E402
import jarvis_tool_cases as TC  # noqa: E402
import chat_tryout as CT  # noqa: E402
import memory_tryout as MT  # noqa: E402

FAILED, PASSED = [], []
TMP = Path(tempfile.mkdtemp(prefix="jarvis-tryout-test-"))


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class NoSocket:
    """Any network connection is a failure of the test."""

    def __enter__(self):
        self._c = socket.socket.connect

        def refuse(*a, **k):
            raise AssertionError("the tryout tried to use the network")
        socket.socket.connect = refuse
        return self

    def __exit__(self, *a):
        socket.socket.connect = self._c


SMALL = {"pick": TC.CASES[:2], "ask": TC.ASK_CASES[:1], "multi": TC.MULTI_STEP[:1],
         "injection": E.load_injections()[:2], "behaviour": BH.CASES[:2]}
SYSTEM = CT.read_system((REPO / "backend" / "jarvis-primary.Modelfile").read_text(
    encoding="utf-8"))


class FakeOllama:
    """Ollama as the tryout sees it. `tags`: the downloaded models and what
    /api/show says about each."""

    def __init__(self, shows, on_card=None):
        self.shows = dict(shows)
        self.loaded = ["jarvis-primary:latest"]
        self.calls = []
        self.modelfiles = {}
        self.on_card = on_card or {}
        self.since_load = {}

    def version(self):
        return "0.34.4"

    def show(self, model):
        return self.shows.get(model.split(":latest")[0] if model.endswith(":latest") else model)

    def ps(self):
        out = []
        for m in self.loaded:
            size = 5 * 1024 ** 3
            pct = self.on_card.get(m.split(":latest")[0], 100)
            out.append({"name": m, "size": size, "size_vram": size * pct // 100})
        return out

    def tags(self):
        return [m + ":latest" if ":" not in m else m for m in self.shows]

    def unload(self, model):
        self.calls.append(("unload", model))
        self.loaded = [m for m in self.loaded if m.split(":latest")[0] != model.split(":latest")[0]]

    def load(self, model):
        self.calls.append(("load", model))
        self.loaded = [model + ":latest"]

    def chat(self, model, messages, tools=None, think=None, options=None):
        self.calls.append(("chat", model, bool(tools), think))
        first = not any(m.split(":latest")[0] == model for m in self.loaded)
        if first:
            self.loaded = [model + ":latest"]
        return {"message": {"content": "Less daylight stops chlorophyll. Other colours show."},
                "eval_count": 40, "eval_duration": 1_000_000_000,
                "load_duration": 3_000_000_000 if first else 0,
                "prompt_eval_duration": 900_000_000 if first else 100_000_000,
                "prompt_eval_count": 3100}

    def create(self, name, path):
        assert name.startswith(CT.PREFIX), name
        self.calls.append(("create", name))
        self.modelfiles[name] = Path(path).read_text(encoding="utf-8")
        self.shows[name] = {"capabilities": ["completion", "tools"]}
        return 0

    def remove(self, name):
        assert name.startswith(CT.PREFIX), name
        self.calls.append(("remove", name))
        self.shows.pop(name, None)
        return 0

    def pull(self, tag):
        self.calls.append(("pull", tag))
        return 1


def _shows():
    return {
        "jarvis-primary": {"capabilities": ["completion", "tools", "thinking"],
                           "parameters": "num_ctx 16384\ntemperature 0.7\ntop_p 0.8"},
        "good:8b": {"capabilities": ["completion", "tools"],
                    "parameters": "temperature 0.3\ntop_p 0.9\nmin_p 0.15\nrepeat_penalty 1.05\n"
                                  "stop \"<|im_end|>\"",
                    "model_info": {"good.context_length": 32768}},
        "crashy:3b": {"capabilities": ["completion", "tools"], "parameters": "",
                      "model_info": {"crashy.context_length": 8192}},
        "forgetful:4b": {"capabilities": ["completion", "tools"],
                         "parameters": "temperature 0.6\ntop_p 0.95"},
        "notools:1b": {"capabilities": ["completion"]},
        # someone made this before the run: it must be left alone at the end
        "jarvis-cand-forgetful-4b": {"capabilities": ["completion", "tools"]},
    }


def _good_rule(messages, tools):
    return "I don't know. Canberra. Good night."


def _make_model(name, t, p):
    if name.startswith("jarvis-cand-crashy"):
        return E.scripted(lambda m, tl: ("crash",))
    return E.scripted(_good_rule)


def _learner(name, url, out_dir):
    if name == "jarvis-primary":
        return {"ran": True, "right": 9, "total": 10}
    if "forgetful" in name:
        return {"ran": True, "right": 7, "total": 10}
    return {"ran": True, "right": 9, "total": 10}


def _run(args, ol, **kw):
    buf = io.StringIO()
    with NoSocket(), contextlib.redirect_stdout(buf):
        code = CT.run(args, ol=ol, make_model=_make_model, learner=kw.pop("learner", _learner),
                      gpu_samples=kw.pop("gpu_samples", []), E=E, cases=SMALL,
                      out_root=TMP / kw.pop("sub", "chat"), say=print, wait=0, **kw)
    return code, buf.getvalue()


def _results(sub):
    d = sorted((TMP / sub).glob("chat-*"))[-1]
    return json.loads((d / "results.json").read_text(encoding="utf-8")), \
        (d / "results.txt").read_text(encoding="utf-8"), d


# ------------------------------------------------------------------ chat --

def t_the_wrapper_is_jarvis_primarys_setup():
    check("the SYSTEM block is read from jarvis-primary.Modelfile, word for word",
          SYSTEM.startswith("You are Jarvis, a private assistant") and '"""' not in SYSTEM)
    mf = CT.wrapper_modelfile("good:8b", SYSTEM, {"temperature": 0.3, "top_p": 0.9, "top_k": 40.0},
                              "from good:8b's own Ollama download")
    check("FROM the tag", "\nFROM good:8b\n" in mf)
    check("num_ctx 16384 and num_batch 512, as jarvis-primary",
          "PARAMETER num_ctx 16384" in mf and "PARAMETER num_batch 512" in mf
          and "PARAMETER num_predict 1024" in mf)
    check("the sampling is written, and where it came from is said beside it",
          "# Sampling: from good:8b's own Ollama download." in mf
          and "PARAMETER temperature 0.3" in mf and "PARAMETER top_k 40" in mf, mf)
    check("the SYSTEM block is jarvis-primary's own", f'SYSTEM """{SYSTEM}"""' in mf)
    check("names: jarvis-cand-<the tag>", CT.cand_name("lfm2.5:8b") == "jarvis-cand-lfm2.5-8b"
          and CT.cand_name("granite4.2:3b") == "jarvis-cand-granite4.2-3b")
    check("the default candidates are the research audit's four",
          CT.CANDIDATES == ("lfm2.5:8b", "granite4.2:8b", "granite4.2:3b", "qwen3.5:4b"))
    check("sampling is read from the tag's parameters",
          CT.tag_sampling(_shows()["good:8b"]) == {"temperature": 0.3, "top_p": 0.9,
                                                   "min_p": 0.15, "repeat_penalty": 1.05})


def t_the_verdict_rule():
    base = {"tools_pct": 70.0, "learner": {"ran": True, "right": 9, "total": 10}}
    same = {"tools_pct": 61.0, "learner": {"ran": True, "right": 9, "total": 10}}
    check("9 points lower on tools, same learner: worth trying (a tie)",
          CT.verdict(base, same)[0] == "worth trying", CT.verdict(base, same))
    low = dict(same, tools_pct=59.9)
    check("more than 10 points lower: not worth it, and says why",
          CT.verdict(base, low)[0] == "not worth it" and "10 points" in CT.verdict(base, low)[1])
    worse = dict(same, tools_pct=80.0, learner={"ran": True, "right": 8, "total": 10})
    check("better tools but a lower learner test: not worth it",
          CT.verdict(base, worse)[0] == "not worth it" and "learner" in CT.verdict(base, worse)[1])
    nolearn = dict(same, learner={"ran": False, "why": "set JARVIS_BACKEND"})
    check("no learner test: cannot say (never a guess)",
          CT.verdict(base, nolearn)[0] == "cannot say")
    check("a model that was not tested says so",
          CT.verdict(base, {"skipped": "not downloaded"}) == ("not tested", "not downloaded"))


def t_busy_card_and_estimate():
    check("an idle card is fine", CT.busy_from_nvidia_smi(["3\n0", "5\n1", "2\n0"]) == "")
    why = CT.busy_from_nvidia_smi(["95\n0", "90\n0", "97\n0"])
    check("a busy card is refused in plain words, with the way round it",
          "graphics card 1 is 94% busy" in why and "--even-if-busy" in why, why)
    lo, hi = CT.estimate_minutes(5, 3, 2)
    check("the estimate for the default run is hours, and says so (5-10 h)",
          lo == 340 and hi == 660, (lo, hi))


def t_a_whole_run_with_a_stand_in_ollama():
    ol = FakeOllama(_shows(), on_card={"jarvis-cand-good-8b": 88})
    code, out = _run(["--models", "good:8b", "crashy:3b", "forgetful:4b", "missing:2b",
                      "notools:1b"], ol)
    check("the run finishes", code == 0, out[-800:])
    doc, text, d = _results("chat")
    rows = {r["model"]: r for r in doc["models"]}
    check("jarvis-primary is measured first, as the baseline",
          doc["models"][0]["model"] == "jarvis-primary" and rows["jarvis-primary"]["tools_pct"])
    v = {k: (r.get("verdict") or [None])[0] for k, r in rows.items()}
    check("a model that ties on tools and learns as well: worth trying",
          v["jarvis-cand-good-8b"] == "worth trying", v)
    check("a model whose every tool call crashes: not worth it",
          v["jarvis-cand-crashy-3b"] == "not worth it", rows["jarvis-cand-crashy-3b"])
    check("a model that learns worse: not worth it",
          v["jarvis-cand-forgetful-4b"] == "not worth it")
    check("a model not downloaded: not tested, with the line to get it",
          v["jarvis-cand-missing-2b"] == "not tested"
          and "ollama pull missing:2b" in rows["jarvis-cand-missing-2b"]["verdict"][1])
    check("a model Ollama says cannot use tools: not tested, said plainly",
          v["jarvis-cand-notools-1b"] == "not tested"
          and "cannot use tools" in rows["jarvis-cand-notools-1b"]["verdict"][1])
    sp = rows["jarvis-cand-good-8b"]["speed"]
    check("the 1st, 2nd and 3rd request after loading are each timed (the 1st includes loading)",
          sp["first_word_s"] == [3.9, 0.1, 0.1], sp["first_word_s"])
    check("... words per second, and how much sat on the card",
          sp["words_per_s"] == 7.0 and sp["on_card_pct"] == 88, sp)
    check("... and a model not wholly on the card gets a plain note",
          any("88%" in n for n in rows["jarvis-cand-good-8b"]["notes"]))
    chats = [c for c in ol.calls if c[0] == "chat" and c[1] == "jarvis-cand-good-8b"]
    check("the timed requests carry Jarvis's tool list, as a real turn does",
          sum(1 for c in chats if c[2]) == 3, chats)
    thinks = [c[3] for c in ol.calls if c[0] == "chat" and c[1] == "jarvis-primary"]
    check("thinking is switched off only for a model that can think",
          set(thinks) == {False} and all(c[3] is None for c in chats), (thinks, chats))
    check("the tool test ran three times and the worst run counts",
          len(rows["jarvis-cand-good-8b"]["tools_every_run"]) == 3
          and rows["jarvis-cand-good-8b"]["tools_pct"]
          == min(rows["jarvis-cand-good-8b"]["tools_every_run"]))
    mf = ol.modelfiles["jarvis-cand-good-8b"]
    check("the Modelfile used the tag's own sampling and said where from",
          "PARAMETER temperature 0.3" in mf and "own Ollama download" in mf
          and f'SYSTEM """{SYSTEM}"""' in mf and "num_ctx 16384" in mf, mf)
    check("... and the tool test used that sampling too",
          rows["jarvis-cand-good-8b"]["tools_sampling"]["temperature"] == 0.3)
    crashy = ol.modelfiles["jarvis-cand-crashy-3b"]
    check("a tag with no sampling gets Jarvis's own values, and says so",
          "PARAMETER temperature 0.7" in crashy and "sets none" in crashy, crashy)
    check("a model made for less than 16384 tokens is tried at its own limit, and noted",
          "PARAMETER num_ctx 8192" in crashy
          and any("8192" in n for n in rows["jarvis-cand-crashy-3b"]["notes"]))
    made = [c[1] for c in ol.calls if c[0] == "create"]
    removed = [c[1] for c in ol.calls if c[0] == "remove"]
    check("jarvis-primary is never made, changed or removed",
          "jarvis-primary" not in made + removed)
    check("the models it made are removed at the end",
          set(removed) == {"jarvis-cand-good-8b", "jarvis-cand-crashy-3b"}, removed)
    check("... but not one that was there before the run",
          "jarvis-cand-forgetful-4b" not in removed)
    check("jarvis-primary is loaded back at the very end", ol.calls[-1] == ("load", "jarvis-primary"),
          ol.calls[-3:])
    check("nothing was downloaded without --pull", not any(c[0] == "pull" for c in ol.calls))
    check("the table has every model and the rule", all(m in text for m in rows)
          and "written down before anything was measured" in text
          and "Nothing was switched" in text, text)
    check("the Modelfiles are kept beside the results",
          (d / "Modelfile-jarvis-cand-good-8b").is_file())


def t_keep_pull_and_stop():
    ol = FakeOllama(_shows())
    code, out = _run(["--models", "good:8b", "--keep", "--quick"], ol, sub="keep")
    doc, text, _d = _results("keep")
    check("--keep keeps the models it made, and says so",
          not any(c[0] == "remove" for c in ol.calls) and "Kept (--keep)" in text)
    check("--quick: one run, the full list only",
          doc["repeat"] == 1 and doc["lists"] == ["full"])
    ol = FakeOllama(_shows())
    code, out = _run(["--models", "missing:2b", "--pull"], ol, sub="pull")
    check("--pull asks Ollama to download, and a failed download is not tested",
          ("pull", "missing:2b") in ol.calls and "did not work" in out, out[-400:])

    def stop(name, url, out_dir):
        if name != "jarvis-primary":
            raise KeyboardInterrupt
        return {"ran": True, "right": 9, "total": 10}
    ol = FakeOllama(_shows())
    code, out = _run(["--models", "good:8b"], ol, sub="stop", learner=stop)
    check("stopped with Ctrl+C: it still removes what it made and loads jarvis-primary back",
          ("remove", "jarvis-cand-good-8b") in ol.calls
          and ol.calls[-1] == ("load", "jarvis-primary") and "Stopped" in out, ol.calls[-4:])


def t_speed_only_for_engine_settings():
    ol = FakeOllama(_shows())
    code, out = _run(["--speed-only"], ol, sub="speed")
    lines = (TMP / "speed" / "speed-only.jsonl").read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[-1])
    check("--speed-only times jarvis-primary alone and prints one line",
          code == 0 and "jarvis-primary: first word 3.9/0.1/0.1 s" in out
          and row["model"] == "jarvis-primary", out)
    check("... makes nothing, runs no test, and loads jarvis-primary back",
          not any(c[0] in ("create", "remove") for c in ol.calls)
          and ol.calls[-1] == ("load", "jarvis-primary"))
    _run(["--speed-only"], ol, sub="speed")
    check("... and each run adds a line, so before and after sit together",
          len((TMP / "speed" / "speed-only.jsonl").read_text().splitlines()) == 2)


def t_refusals():
    ol = FakeOllama(_shows())
    code, out = _run(["--url", "http://192.168.1.5:11434"], ol, sub="r1")
    check("an Ollama that is not this PC is refused", code == 2 and "Only this PC" in out)
    code, out = _run([], ol, sub="r2", gpu_samples=["97", "95", "99"])
    check("a busy graphics card: not started, and nothing was made",
          code == 3 and "Not started" in out and not any(c[0] == "create" for c in ol.calls))
    shows = _shows()
    del shows["jarvis-primary"]
    code, out = _run([], FakeOllama(shows), sub="r3")
    check("no jarvis-primary: nothing to compare, said plainly", code == 2
          and "nothing to compare" in out)
    code, out = _run(["--models", "jarvis-cand-good-8b"], ol, sub="r4")
    check("a jarvis-cand-* name is not accepted as a model to try", code == 2)
    ol = FakeOllama(_shows())
    ol.shows["jarvis-cand-old-1b"] = {}
    code, out = _run(["--clean"], ol, sub="r5")
    check("--clean removes only jarvis-cand-* models",
          {c[1] for c in ol.calls if c[0] == "remove"}
          == {"jarvis-cand-forgetful-4b", "jarvis-cand-old-1b"}, ol.calls)
    seen = {}

    def fake_run(cmd, timeout=None):
        seen["cmd"] = cmd
        out = Path(cmd[cmd.index("--out") + 1])
        (out / "memory-eval-1.json").write_text(json.dumps(
            {"learner": {"model_part": {"ran": True, "right": 5, "total": 6}}}))
    got = CT.run_learner("jarvis-cand-x", "http://127.0.0.1:11434", TMP / "lr", run=fake_run)
    cmd = seen["cmd"]
    check("the learner test is eval_memory.py --learner-model, 0 filler, no re-ranker",
          got == {"ran": True, "right": 5, "total": 6} and cmd[cmd.index("--sizes") + 1] == "0"
          and cmd[cmd.index("--reranker") + 1] == "off"
          and cmd[cmd.index("--learner-model") + 1] == "jarvis-cand-x", (got, cmd))


# ---------------------------------------------------------------- memory --

def _res(embedder, recall, dont_know, p95, *, reranker=None, rr_recall=None, rr_mrr=0.8,
         distance_best=None, old=0):
    line = {"recall_at_5": recall, "recall_at_1": recall - 10, "mrr": 0.75,
            "dont_know_facts_avg": dont_know, "replaced_came_back": 0,
            "time_wrong_version": old, "search_p95_ms": p95, "multi_all_found": 7,
            "multi_questions": 10, "time_found": 10, "time_questions": 10}
    lv0 = {"filler": "neutral", "filler_facts": 0, "facts": 71, "after": line,
           "entities": dict(line, recall_at_5=80.9)}
    big = {"filler": "same_topic", "filler_facts": 1000, "facts": 1071, "after": line,
           "entities": line, "search_p95_ms": p95}
    if reranker:
        rr = dict(line, recall_at_5=rr_recall, mrr=rr_mrr, search_p95_ms=p95 + 100)
        big["reranked"] = rr
        lv0["reranked"] = dict(rr, recall_at_5=82.0)
    res = {"embedder": embedder, "semantic": True, "vector_search": True,
           "levels": [lv0, big], "max_distance_configured": 1.0,
           "reranker": reranker or "off (--reranker off)",
           "learner": {"kinds": {"a": {"right": 80, "total": 80}}},
           "distance_sweep": [], "distance_choice": {"chosen": None}}
    if distance_best is not None:
        res["distance_choice"] = {"chosen": distance_best}
        res["distance_sweep"] = [{"filler": "same_topic", "filler_facts": 1000,
                                  "max_distance": distance_best, "recall_at_5": recall + 1,
                                  "dont_know_facts_avg": dont_know}]
    return res


def t_the_memory_tryout():
    calls = []
    table = {
        ("BAAI/bge-small-en-v1.5", "Xenova/ms-marco-MiniLM-L-6-v2"):
            _res("BAAI/bge-small-en-v1.5", 77.7, 2.37, 40, reranker="Xenova/ms-marco-MiniLM-L-6-v2",
                 rr_recall=78.0, rr_mrr=0.76),
        ("Qwen/Qwen3-Embedding-0.6B-Q", None):
            _res("Qwen/Qwen3-Embedding-0.6B-Q+prefixes-1", 84.0, 2.0, 180, distance_best=0.9),
        ("google/embeddinggemma-300m", None):
            _res("BAAI/bge-small-en-v1.5", 77.7, 2.37, 40),      # an older jarvis_memory.py
        ("BAAI/bge-small-en-v1.5", "Xenova/ms-marco-MiniLM-L-12-v2"):
            _res("BAAI/bge-small-en-v1.5", 77.7, 2.37, 40, reranker="Xenova/ms-marco-MiniLM-L-12-v2",
                 rr_recall=80.0, rr_mrr=0.8),
    }

    def fake_run(cmd, env=None, timeout=None):
        key = (env["JARVIS_MEMORY_EMBED_MODEL"], env.get("JARVIS_MEMORY_RERANK_MODEL"))
        calls.append((key, cmd[cmd.index("--reranker") + 1]))
        out = Path(cmd[cmd.index("--out") + 1])
        (out / "memory-eval-1.json").write_text(json.dumps(table[key]))

    have = ("0.8.1", {"BAAI/bge-small-en-v1.5", "Qwen/Qwen3-Embedding-0.6B-Q",
                      "google/embeddinggemma-300m"},
            {"Xenova/ms-marco-MiniLM-L-6-v2", "Xenova/ms-marco-MiniLM-L-12-v2"})
    buf = io.StringIO()
    with NoSocket(), contextlib.redirect_stdout(buf):
        code = MT.main([], run=fake_run, lists=have, out_root=TMP / "mem")
    out = buf.getvalue()
    check("the memory tryout finishes", code == 0, out[-600:])
    check("each run gets its model through the two switches, for that run only",
          [k for k, _ in calls] == [
              ("BAAI/bge-small-en-v1.5", "Xenova/ms-marco-MiniLM-L-6-v2"),
              ("Qwen/Qwen3-Embedding-0.6B-Q", None), ("google/embeddinggemma-300m", None),
              ("BAAI/bge-small-en-v1.5", "Xenova/ms-marco-MiniLM-L-12-v2")], calls)
    check("... the meaning-model runs without a re-ranker, the re-ranker runs with it",
          [r for _k, r in calls] == ["auto", "off", "off", "auto"])
    check("a re-ranker this fastembed does not have is not run, and the upgrade line is shown",
          "jinaai/jina-reranker-v1-turbo-en" in out and "fastembed==0.8.1" in out
          and "--require-hashes" in out)
    check("a better meaning model at its own distance floor: worth trying, with what to set",
          "Qwen/Qwen3-Embedding-0.6B-Q: worth trying" in out
          and "JARVIS_MEMORY_MAX_DISTANCE=0.9" in out, out)
    check("a run that measured the default instead is caught, and says why",
          "google/embeddinggemma-300m: not tested" in out and "apply-patches.ps1" in out)
    check("the L-6 re-ranker adds too little: does not help",
          "Xenova/ms-marco-MiniLM-L-6-v2: does not help" in out)
    check("the L-12 one adds enough: helps", "Xenova/ms-marco-MiniLM-L-12-v2: helps" in out)
    check("scoreboard rows in the page's own format",
          "| the PC | 80.9% | 7/10 | 10/10 (0 wrong) | 80/80 |" in out, out)
    check("nothing was switched, and it says so", "Nothing was switched" in out)
    slow = dict(MT.read_embed(_res("x+prefixes-1", 90.0, 1.0, 400)), embedder="x")
    base = MT.read_embed(_res("BAAI/bge-small-en-v1.5", 77.7, 2.37, 40))
    check("a better but slow meaning model: keep bge-small, because of the time",
          MT.embed_verdict(base, slow)[0].startswith("keep")
          and "400" in MT.embed_verdict(base, slow)[1])
    check("the upgrade is one PowerShell line, with the wheel's hash",
          "\n" not in MT.FASTEMBED_UPGRADE and "b4f4043080af36ee820d22d2d3034df635c1a8b97"
          in MT.FASTEMBED_UPGRADE)
    said = []
    n = len(calls)
    code = MT.main([], run=fake_run, lists=(), out_root=TMP / "m2", say=said.append)
    check("no fastembed at all: said plainly, nothing run",
          code == 2 and "fastembed is not installed" in said[0] and len(calls) == n, said)


def main() -> int:
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:
                    traceback.print_exc()
                    check(f"{name} raised {type(exc).__name__}: {exc}", False)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
