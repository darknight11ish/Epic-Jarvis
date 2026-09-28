"""chat_tryout.py - try other chat models against Jarvis's own, on this PC.
Standard library only. NOTHING SWITCHES: Jarvis keeps using jarvis-primary.

The owner chose this on 2026-09-28 ("Model tryouts"; the research audit,
docs/RESEARCH-AUDIT-2026-09-28.md section 6). For each model named (default:
the four the audit picked), it

  1. wraps the model the way jarvis-primary is wrapped - a Modelfile with
     `FROM <the model>`, jarvis-primary's own SYSTEM block, num_ctx 16384 and
     num_batch 512 - and makes it with `ollama create jarvis-cand-<name>`.
     The sampling values (temperature, top_p, ...) are the ones the model's
     own Ollama download sets - the closest thing to the maker's advice this
     PC can read - and the Modelfile says so beside them. A model whose
     download sets none gets Jarvis's own, and the file says that instead;
  2. times it: the 1st request after loading, then the 2nd and the 3rd (one
     known bug makes a first request slow on this kind of card), each with
     Jarvis's rules and full tool list in front, as a real turn has; words per
     second; and how much of the model sat on the graphics card (Ollama's
     /api/ps, size_vram of size);
  3. runs Jarvis's tool test (tools/tool_eval/ollama_tool_eval.py) three
     times and keeps the WORST run;
  4. runs the learner test (backend/eval_memory.py --learner-model: does the
     model pick the right facts out of a conversation);

and prints ONE table, with a verdict per model by a rule written down before
anything was measured (RULE below):

    "worth trying" = ties or beats Jarvis's current model on the tool test
    (within 10 points counts as a tie) AND does not lower the learner test.
    Anything else is "not worth it", with the reason.

It never changes jarvis-primary, a setting, or any file of Jarvis's. It
removes the jarvis-cand-* models it made at the end (--keep keeps them), and
loads jarvis-primary back onto the card. While it runs, the graphics card is
busy with the tryout, so Jarvis answers slowly or not at all - run it when
you do not need Jarvis (overnight). It refuses to start while the graphics
card is already busy (Jarvis answering, a game), unless --even-if-busy.

NOTHING LEAVES THE PC except `ollama pull` (with --pull), which downloads a
model from Ollama's own library exactly as typing it would. Everything else
talks to Ollama at 127.0.0.1 only.

    py -3 tools\\model_tryout\\chat_tryout.py --pull

Results: <your home folder>\\jarvis-model-tryout\\chat-<date-time>\\ -
results.txt (the table) and results.json (every number).

Offline self-test with a stand-in Ollama (no model, no network):
    python3 backend/test_model_tryout.py
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
BACKEND_DIR = REPO / "backend"
TOOL_EVAL_DIR = REPO / "tools" / "tool_eval"

#: The research audit's four (docs/RESEARCH-AUDIT-2026-09-28.md, section 6).
CANDIDATES = ("lfm2.5:8b", "granite4.2:8b", "granite4.2:3b", "qwen3.5:4b")
BASELINE = "jarvis-primary"
PREFIX = "jarvis-cand-"
NUM_CTX = 16384            # jarvis-primary.Modelfile
NUM_BATCH = 512            # jarvis-primary.Modelfile: 1024+ spills on this card
NUM_PREDICT = 1024         # jarvis-primary.Modelfile
TIE_POINTS = 10            # "within 10 points counts as a tie"
JARVIS_SAMPLING = {"temperature": 0.7, "top_p": 0.8}
SAMPLING_KEYS = ("temperature", "top_p", "top_k", "min_p", "repeat_penalty",
                 "presence_penalty")

RULE = ("Worth trying = the tool test ties or beats jarvis-primary (within "
        f"{TIE_POINTS} points is a tie; the worst of the runs counts) AND the learner "
        "test is not lower. Speed and how much sits on the card are shown, not judged.")

#: The timed question: no tool fits it, so the answer is words.
SPEED_QUESTION = "In two short sentences: why do leaves change colour in autumn?"
#: A copy-heavy job (a note tidied), where "guess ahead" settings help most.
REWRITE_TEXT = ("Tidy this note without changing its meaning: buy milk, eggs and bread; "
                "call the garage about the brakes on Tuesday; book the dentist for the "
                "kids; pay the water bill before the 12th; ask Sam about the weekend.")


# --------------------------------------------------------------------------
#   Pure parts (tested offline)
# --------------------------------------------------------------------------

def cand_name(tag: str) -> str:
    """lfm2.5:8b -> jarvis-cand-lfm2.5-8b."""
    body = re.sub(r"[^a-z0-9._-]+", "-", tag.lower()).strip("-.")
    return PREFIX + (body or "model")


def read_system(modelfile_text: str) -> str:
    """jarvis-primary's SYSTEM block, word for word."""
    m = re.search(r'^SYSTEM\s+"""(.*?)"""', modelfile_text, re.S | re.M)
    if not m:
        raise ValueError("backend/jarvis-primary.Modelfile has no SYSTEM \"\"\"...\"\"\" block")
    return m.group(1)


def tag_sampling(show: dict) -> dict:
    """The sampling values a model's own Ollama download sets (the
    `parameters` text of /api/show), as numbers."""
    out = {}
    for line in str((show or {}).get("parameters") or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] in SAMPLING_KEYS:
            try:
                out[parts[0]] = float(parts[1])
            except ValueError:
                pass
    return out


def tag_context_limit(show: dict):
    """The longest conversation the model was made for, or None."""
    info = (show or {}).get("model_info") or {}
    for k, v in info.items():
        if str(k).endswith(".context_length") and isinstance(v, int) and v > 0:
            return v
    return None


def capabilities(show: dict) -> set:
    return {str(c) for c in (show or {}).get("capabilities") or []}


def wrapper_modelfile(tag: str, system: str, sampling: dict, source: str,
                      num_ctx: int = NUM_CTX) -> str:
    """The Modelfile for one candidate. `source`: where `sampling` came from,
    in words, written beside it."""
    if '"""' in system:
        raise ValueError("the SYSTEM block may not contain three quote marks")
    lines = [
        f"# Made by tools/model_tryout/chat_tryout.py on {datetime.date.today()} to TRY",
        f"# {tag} the way jarvis-primary is set up. Jarvis does not use this model;",
        "# the tryout deletes it at the end unless it was run with --keep.",
        f"FROM {tag}",
        "",
        "# The same as jarvis-primary.Modelfile.",
        f"PARAMETER num_ctx {num_ctx}",
        f"PARAMETER num_batch {NUM_BATCH}",
        f"PARAMETER num_predict {NUM_PREDICT}",
        "",
        f"# Sampling: {source}.",
    ]
    for k in SAMPLING_KEYS:
        if k in sampling:
            v = sampling[k]
            lines.append(f"PARAMETER {k} {int(v) if k == 'top_k' else v}")
    lines += ["", "# jarvis-primary's own rules, word for word.",
              f'SYSTEM """{system}"""', ""]
    return "\n".join(lines)


def tools_score(summary: dict):
    """(passes, out of, percent) over every list and part of one tool-test
    summary, or None."""
    if not isinstance(summary, dict) or not summary:
        return None
    p = n = 0
    for suites in summary.values():
        for line in (suites or {}).values():
            p += int(line.get("pass", 0))
            n += int(line.get("of", 0))
    return (p, n, round(100.0 * p / n, 1)) if n else None


def verdict(base: dict, cand: dict) -> tuple:
    """("worth trying" | "not worth it" | "cannot say", why) by RULE."""
    if cand.get("skipped"):
        return "not tested", cand["skipped"]
    bt, ct = base.get("tools_pct"), cand.get("tools_pct")
    if ct is None:
        return "cannot say", "its tool test did not run"
    if bt is None:
        return "cannot say", "jarvis-primary's tool test did not run, so there is nothing to compare"
    bl, cl = base.get("learner"), cand.get("learner")
    if ct < bt - TIE_POINTS:
        return "not worth it", (f"tool test {ct}% against jarvis-primary's {bt}% - more than "
                                f"{TIE_POINTS} points lower")
    if not (bl and bl.get("ran") and cl and cl.get("ran")):
        return "cannot say", ("tools are fine, but the learner test did not run "
                              + ("for jarvis-primary" if not (bl and bl.get("ran"))
                                 else "for this model")
                              + " (see its note)")
    b = bl["right"] / bl["total"] if bl.get("total") else 0.0
    c = cl["right"] / cl["total"] if cl.get("total") else 0.0
    if c < b:
        return "not worth it", (f"learner test {cl['right']}/{cl['total']} against "
                                f"jarvis-primary's {bl['right']}/{bl['total']}")
    how = "beats" if ct > bt else ("the same as" if ct == bt else "within 10 points of")
    return "worth trying", (f"tool test {ct}% ({how} jarvis-primary's {bt}%), learner "
                            f"{cl['right']}/{cl['total']} (jarvis-primary "
                            f"{bl['right']}/{bl['total']})")


def estimate_minutes(n_models: int, repeat: int, lists: int) -> tuple:
    """(low, high) minutes. The tool test takes 20-40 minutes per run with
    both lists (tools/tool_eval/README.md); the learner test and the timing
    about 8 more per model."""
    lo = n_models * (repeat * 10 * lists + 8)
    hi = n_models * (repeat * 20 * lists + 12)
    return lo, hi


def _cell(v, fmt="{}"):
    return "-" if v is None else fmt.format(v)


def table(rows: list) -> str:
    """The one table: a row per model, then each verdict with its reason."""
    head = ("Model", "Tools", "Learner", "1st word: 1st/2nd/3rd request (s)",
            "Words/s", "On card", "Verdict")
    body = []
    for r in rows:
        sp = r.get("speed") or {}
        fw = sp.get("first_word_s") or []
        firsts = "/".join(_cell(x, "{:.1f}") for x in fw) if fw else "-"
        ln = r.get("learner") or {}
        body.append((
            r["model"],
            _cell(r.get("tools_pct"), "{}%"),
            f"{ln['right']}/{ln['total']}" if ln.get("ran") else "-",
            firsts,
            _cell(sp.get("words_per_s"), "{:.1f}"),
            _cell(sp.get("on_card_pct"), "{}%"),
            r.get("verdict", ["-"])[0],
        ))
    widths = [max(len(str(x[i])) for x in [head] + body) for i in range(len(head))]
    fmt = "  ".join("{:<%d}" % w for w in widths)
    out = [fmt.format(*head), fmt.format(*("-" * w for w in widths))]
    out += [fmt.format(*b) for b in body]
    out.append("")
    for r in rows:
        if r.get("verdict"):
            out.append(f"{r['model']}: {r['verdict'][0]} - {r['verdict'][1]}")
        for note in r.get("notes") or []:
            out.append(f"    note: {note}")
    out += ["", "The rule, written down before anything was measured: " + RULE]
    return "\n".join(out)


def busy_from_nvidia_smi(samples: list) -> str:
    """samples: nvidia-smi's utilization lines, one reading per list item
    ("12\\n3" for two cards). A plain reason when a card is busy, else ""."""
    per_card = {}
    for s in samples:
        for i, line in enumerate(str(s).strip().splitlines()):
            try:
                per_card.setdefault(i, []).append(float(line.strip()))
            except ValueError:
                continue
    for i, vals in per_card.items():
        if vals and sum(vals) / len(vals) >= 30:
            return (f"graphics card {i + 1} is {round(sum(vals) / len(vals))}% busy right now "
                    "(Jarvis answering, a game or a video). The tryout would be measured "
                    "against it and would slow it down. Try again when the PC is idle, or add "
                    "--even-if-busy.")
    return ""


# --------------------------------------------------------------------------
#   Ollama on this PC
# --------------------------------------------------------------------------

def is_local(url: str) -> bool:
    return bool(re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?/?$", url.strip()))


class Ollama:
    """The HTTP API at 127.0.0.1 (never through a proxy), and the `ollama`
    program for create / rm / pull."""

    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self._open = urllib.request.build_opener(urllib.request.ProxyHandler({})).open

    def _call(self, path, body=None, timeout=600):
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data,
                                     method="GET" if body is None else "POST",
                                     headers={"Content-Type": "application/json"})
        with self._open(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "{}")

    def version(self):
        return self._call("/api/version", timeout=5).get("version")

    def show(self, model):
        try:
            return self._call("/api/show", {"model": model}, timeout=30)
        except urllib.error.HTTPError:
            return None

    def ps(self):
        return self._call("/api/ps", timeout=10).get("models") or []

    def tags(self):
        return [m.get("name") or m.get("model") for m in
                self._call("/api/tags", timeout=10).get("models") or []]

    def unload(self, model):
        self._call("/api/generate", {"model": model, "keep_alive": 0}, timeout=120)

    def load(self, model):
        """Load it with its own settings (no options, no keep_alive: the
        same as Jarvis's own warm-up)."""
        self._call("/api/generate", {"model": model}, timeout=600)

    def chat(self, model, messages, tools=None, think=None, options=None):
        body = {"model": model, "messages": messages, "stream": False,
                "options": options or {}}
        if tools:
            body["tools"] = tools
        if think is not None:
            body["think"] = think
        return self._call("/api/chat", body, timeout=900)

    def _cli(self, *args):
        exe = shutil.which("ollama")
        if not exe:
            raise RuntimeError("the `ollama` program is not on this PC's PATH")
        env = dict(os.environ, OLLAMA_HOST=self.base.replace("http://", ""))
        return subprocess.run([exe, *args], env=env).returncode

    def create(self, name, modelfile_path):
        if not name.startswith(PREFIX):
            raise ValueError(f"the tryout only makes {PREFIX}* models")
        return self._cli("create", name, "-f", str(modelfile_path))

    def remove(self, name):
        if not name.startswith(PREFIX):
            raise ValueError(f"the tryout only removes {PREFIX}* models")
        return self._cli("rm", name)

    def pull(self, tag):
        return self._cli("pull", tag)


def nvidia_smi_samples(n=3):
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    out = []
    for i in range(n):
        try:
            out.append(subprocess.run(
                [exe, "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10).stdout)
        except Exception:
            return []
        if i < n - 1:
            time.sleep(1)
    return out


# --------------------------------------------------------------------------
#   The three measurements
# --------------------------------------------------------------------------

def _timing(reply: dict):
    """Ollama's own clock, from a native /api/chat reply (nanoseconds)."""
    ec, ed = reply.get("eval_count"), reply.get("eval_duration")
    if not isinstance(ec, int) or not isinstance(ed, int) or ec <= 0 or ed <= 0:
        return None
    ld = reply.get("load_duration") if isinstance(reply.get("load_duration"), int) else 0
    pd = reply.get("prompt_eval_duration") if isinstance(
        reply.get("prompt_eval_duration"), int) else 0
    words = len(str((reply.get("message") or {}).get("content") or "").split())
    return {"first_word_s": round((ld + pd) / 1e9, 2), "load_s": round(ld / 1e9, 2),
            "tokens_per_s": round(ec / (ed / 1e9), 1),
            "words_per_s": round(words / (ed / 1e9), 1) if words else None,
            "prompt_tokens": reply.get("prompt_eval_count")}


def measure_speed(ol, model: str, tools: list, can_think: bool) -> dict:
    """Off the card first, then three requests in a row with Jarvis's full
    tool list in front (the 1st includes loading), then one copy-heavy job,
    then how much of it is on the card."""
    for m in ol.ps():
        name = m.get("name") or m.get("model")
        if name:
            ol.unload(name)
    think = False if can_think else None
    opts = {"num_predict": 128, "temperature": 0, "seed": 7}
    reqs = []
    for _ in range(3):
        r = ol.chat(model, [{"role": "user", "content": SPEED_QUESTION}], tools, think, opts)
        reqs.append(_timing(r) or {})
    rw = _timing(ol.chat(model, [{"role": "user", "content": REWRITE_TEXT}], None, think,
                         dict(opts, num_predict=160))) or {}
    on_card = size_gb = None
    for m in ol.ps():
        if (m.get("name") or m.get("model") or "").split(":latest")[0] == model.split(":latest")[0]:
            size, vram = m.get("size"), m.get("size_vram")
            if isinstance(size, int) and size > 0 and isinstance(vram, int):
                on_card = round(100 * vram / size)
                size_gb = round(size / 1024 ** 3, 2)
    later = [x for x in reqs[1:] if x.get("tokens_per_s")]
    wps = [x["words_per_s"] for x in later if x.get("words_per_s")]
    return {"requests": reqs,
            "first_word_s": [x.get("first_word_s") for x in reqs],
            "tokens_per_s": round(sum(x["tokens_per_s"] for x in later) / len(later), 1)
            if later else None,
            "words_per_s": round(sum(wps) / len(wps), 1) if wps else None,
            "rewrite_tokens_per_s": rw.get("tokens_per_s"),
            "prompt_tokens": (reqs[0] or {}).get("prompt_tokens"),
            "on_card_pct": on_card, "size_gb": size_gb}


def load_tool_eval():
    sys.path.insert(0, str(TOOL_EVAL_DIR))
    import ollama_tool_eval as E
    return E


def run_tool_test(E, make_model, model: str, sampling: dict, repeat: int, lists,
                  cases=None, say=print) -> dict:
    """The tool test `repeat` times; the WORST run counts."""
    tries = []
    for i in range(repeat):
        say(f"  tool test, run {i + 1} of {repeat} ...")
        result = E.run_all(make_model(model, sampling["temperature"], sampling["top_p"]),
                           E.SUITES, lists, cases=cases)
        tries.append(E.summary(result))
    scored = [(tools_score(s), s) for s in tries]
    scored = [x for x in scored if x[0]]
    if not scored:
        return {"tools_pct": None}
    worst = min(scored, key=lambda x: x[0][2])
    return {"tools_pct": worst[0][2], "tools_pass": worst[0][0], "tools_of": worst[0][1],
            "tools_every_run": [x[0][2] for x in scored], "tools_summary": worst[1],
            "tools_sampling": sampling}


def run_learner(model: str, url: str, out_dir: Path, run=subprocess.run) -> dict:
    """backend/eval_memory.py --learner-model <model>, with no filler and no
    re-ranker (the search numbers do not depend on the chat model): only the
    learner's and the tidy's model parts matter here."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(BACKEND_DIR / "eval_memory.py"), "--sizes", "0",
           "--reranker", "off", "--learner-model", model, "--ollama", url,
           "--out", str(out_dir)]
    try:
        run(cmd, timeout=3 * 3600)
    except Exception as exc:
        return {"ran": False, "why": f"eval_memory.py did not finish ({type(exc).__name__})"}
    got = sorted(out_dir.glob("memory-eval-*.json"))
    if not got:
        return {"ran": False, "why": "eval_memory.py wrote no results"}
    try:
        res = json.loads(got[-1].read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ran": False, "why": f"its results could not be read ({type(exc).__name__})"}
    mp = (res.get("learner") or {}).get("model_part") or {}
    if not mp.get("ran"):
        return {"ran": False, "why": str(mp.get("why") or "the learner's model part did not run")}
    return {"ran": True, "right": int(mp.get("right", 0)), "total": int(mp.get("total", 0))}


# --------------------------------------------------------------------------
#   The run
# --------------------------------------------------------------------------

def prepare(ol, tag: str, system: str, out_dir: Path, *, pull: bool, jarvis_sampling: bool,
            existed: set, say=print) -> dict:
    """Make jarvis-cand-<tag>. A row with `skipped` when it cannot be."""
    name = cand_name(tag)
    row = {"model": name, "tag": tag, "notes": []}
    show = ol.show(tag)
    if show is None and pull:
        say(f"Downloading {tag} (ollama pull) ...")
        if ol.pull(tag) != 0:
            row["skipped"] = f"`ollama pull {tag}` did not work - is the name right?"
            return row
        show = ol.show(tag)
    if show is None:
        row["skipped"] = (f"{tag} is not downloaded. Add --pull, or run: ollama pull {tag}")
        return row
    caps = capabilities(show)
    if caps and "tools" not in caps:
        row["skipped"] = f"Ollama says {tag} cannot use tools, and Jarvis needs them"
        return row
    row["can_think"] = "thinking" in caps
    limit = tag_context_limit(show)
    ctx = NUM_CTX if not limit else min(NUM_CTX, limit)
    if ctx < NUM_CTX:
        row["notes"].append(f"made for at most {limit} tokens of conversation, so tried at {ctx}")
    samp = tag_sampling(show)
    if jarvis_sampling or not ("temperature" in samp and "top_p" in samp):
        why = ("Jarvis's own values (--jarvis-sampling)" if jarvis_sampling else
               f"Jarvis's own values - {tag}'s download sets none")
        samp = dict(JARVIS_SAMPLING)
        row["notes"].append("sampling: " + why)
    else:
        why = (f"from {tag}'s own Ollama download (`ollama show {tag}`), the closest "
               "thing to the maker's advice this PC can read - it may be the values for "
               "the model's 'thinking' mode, which Jarvis switches off")
        row["notes"].append(f"sampling from its own download: temperature "
                            f"{samp['temperature']}, top_p {samp['top_p']}")
    row["sampling"] = samp
    mf = out_dir / f"Modelfile-{name}"
    mf.write_text(wrapper_modelfile(tag, system, samp, why, ctx), encoding="utf-8")
    say(f"Making {name} from {tag} ...")
    if ol.create(name, mf) != 0:
        row["skipped"] = f"`ollama create {name}` did not work (the Modelfile is at {mf})"
        return row
    row["made"] = name not in existed
    return row


def measure(ol, E, row: dict, *, url, out_dir, repeat, lists, tools, make_model,
            learner=run_learner, cases=None, say=print) -> None:
    name = row["model"]
    say(f"\n=== {name} ===")
    say("  timing (1st, 2nd and 3rd request after loading) ...")
    try:
        row["speed"] = measure_speed(ol, name, tools, row.get("can_think", False))
    except Exception as exc:
        row["notes"].append(f"timing did not work: {type(exc).__name__}: {exc}")
    samp = row.get("sampling") or dict(JARVIS_SAMPLING)
    row.update(run_tool_test(E, make_model, name, samp, repeat, lists, cases=cases, say=say))
    say("  learner test ...")
    row["learner"] = learner(name, url, out_dir / f"memory-{name}")
    if not row["learner"].get("ran"):
        row["notes"].append("learner test: " + str(row["learner"].get("why")))
    sp = row.get("speed") or {}
    if isinstance(sp.get("on_card_pct"), int) and sp["on_card_pct"] < 100:
        row["notes"].append(f"only {sp['on_card_pct']}% of it fits on the graphics card; the "
                            "rest runs on the processor, which is much slower")


def save(out_dir: Path, rows: list, meta: dict) -> None:
    doc = dict(meta, rule=RULE, models=rows)
    (out_dir / "results.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False),
                                          encoding="utf-8")


def speed_only(ol, E, out_root, say) -> int:
    """Time jarvis-primary alone, print one line, add it to speed-only.jsonl."""
    say(f"Timing {BASELINE} (about 2 minutes) ...")
    try:
        sp = measure_speed(ol, BASELINE, E.TOOLS,
                           "thinking" in capabilities(ol.show(BASELINE)))
    finally:
        try:
            ol.load(BASELINE)
        except Exception:
            pass
    root = Path(out_root or (Path.home() / "jarvis-model-tryout"))
    root.mkdir(parents=True, exist_ok=True)
    env = {k: os.environ.get(k) for k in ("LLAMA_ARG_CACHE_RAM", "LLAMA_ARG_SPEC_TYPE")}
    row = dict(sp, at=datetime.datetime.now().isoformat(timespec="seconds"),
               model=BASELINE, settings_in_this_window=env)
    with open(root / "speed-only.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    fw = "/".join(_cell(x, "{:.1f}") for x in sp["first_word_s"])
    say(f"{BASELINE}: first word {fw} s (1st/2nd/3rd request after loading), "
        f"{_cell(sp['words_per_s'])} words/s, {_cell(sp['tokens_per_s'])} tokens/s, "
        f"tidying a note {_cell(sp['rewrite_tokens_per_s'])} tokens/s, "
        f"{_cell(sp['on_card_pct'], '{}%')} on the graphics card.")
    say(f"Added to {root / 'speed-only.jsonl'} - each run is one line, so before and after "
        "sit next to each other.")
    return 0


def run(argv=None, *, ol=None, make_model=None, learner=run_learner, gpu_samples=None,
        E=None, cases=None, out_root=None, say=print, wait=10) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--models", nargs="+", default=list(CANDIDATES),
                    help="Ollama model names to try (default: " + ", ".join(CANDIDATES) + ")")
    ap.add_argument("--url", default="http://127.0.0.1:11434")
    ap.add_argument("--repeat", type=int, default=3, help="tool-test runs per model (default 3)")
    ap.add_argument("--quick", action="store_true",
                    help="one tool-test run, full tool list only: a first look, about a third "
                         "of the time")
    ap.add_argument("--pull", action="store_true", help="download models that are not here yet")
    ap.add_argument("--keep", action="store_true", help="keep the jarvis-cand-* models afterwards")
    ap.add_argument("--jarvis-sampling", action="store_true",
                    help="give every model Jarvis's own temperature and top_p (0.7, 0.8)")
    ap.add_argument("--even-if-busy", action="store_true")
    ap.add_argument("--speed-only", action="store_true",
                    help="only time jarvis-primary (about 2 minutes): for trying an engine "
                         "setting before and after (docs/MODEL-TOPOLOGY.md)")
    ap.add_argument("--clean", action="store_true",
                    help="only remove jarvis-cand-* models an earlier, stopped run left behind")
    a = ap.parse_args(argv)
    if not is_local(a.url):
        say("Only this PC's own Ollama (http://127.0.0.1:...) is allowed.")
        return 2
    ol = ol or Ollama(a.url)
    try:
        say(f"Ollama {ol.version()} is answering at {a.url}.")
    except Exception as exc:
        say(f"Ollama is not answering at {a.url} ({type(exc).__name__}). Start Ollama first.")
        return 2
    if a.clean:
        left = [t for t in ol.tags() if str(t).startswith(PREFIX)]
        for t in left:
            ol.remove(t.split(":latest")[0])
        say(f"Removed {len(left)} tryout model(s)." if left else "No tryout models were left.")
        return 0
    if a.repeat < 1:
        say("--repeat must be 1 or more.")
        return 2
    repeat, lists = (1, ("full",)) if a.quick else (a.repeat, ("full", "short"))
    tags = [t for t in a.models if t != BASELINE]
    bad = [t for t in tags if t.startswith(PREFIX)]
    if bad:
        say(f"Name the downloaded models (e.g. {CANDIDATES[0]}), not {bad[0]}.")
        return 2
    if ol.show(BASELINE) is None:
        say(f"{BASELINE} is not in Ollama, so there is nothing to compare with. "
            "docs/INSTALL.md says how it is made.")
        return 2
    if not a.even_if_busy:
        why = busy_from_nvidia_smi(nvidia_smi_samples() if gpu_samples is None else gpu_samples)
        if why:
            say("Not started: " + why)
            return 3
    E = E or load_tool_eval()
    if a.speed_only:
        return speed_only(ol, E, out_root, say)
    make_model = make_model or (lambda m, t, p: E.ollama(a.url.rstrip("/"), m, t, p))
    system = read_system((BACKEND_DIR / "jarvis-primary.Modelfile").read_text(encoding="utf-8"))
    lo, hi = estimate_minutes(len(tags) + 1, repeat, len(lists))
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = Path(out_root or (Path.home() / "jarvis-model-tryout")) / f"chat-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    say(f"Trying {', '.join(tags) or 'no other model'} against {BASELINE}.")
    say(f"This takes about {lo // 60}h{lo % 60:02d} to {hi // 60}h{hi % 60:02d}"
        + (" plus the downloads" if a.pull else "")
        + ". Jarvis answers slowly or not at all until it ends. "
          "Press Ctrl+C to stop; it cleans up after itself either way.")
    say(f"Results go in {out_dir}")
    if wait:
        time.sleep(wait)
    existed = {str(t).split(":latest")[0] for t in ol.tags()}
    rows, made = [], []
    meta = {"started": datetime.datetime.now().isoformat(timespec="seconds"),
            "repeat": repeat, "lists": list(lists), "num_ctx": NUM_CTX}
    try:
        base = {"model": BASELINE, "tag": BASELINE, "notes": [],
                "sampling": dict(JARVIS_SAMPLING),
                "can_think": "thinking" in capabilities(ol.show(BASELINE))}
        rows.append(base)
        measure(ol, E, base, url=a.url, out_dir=out_dir, repeat=repeat, lists=lists,
                tools=E.TOOLS, make_model=make_model, learner=learner, cases=cases, say=say)
        save(out_dir, rows, meta)
        for tag in tags:
            row = prepare(ol, tag, system, out_dir, pull=a.pull,
                          jarvis_sampling=a.jarvis_sampling, existed=existed, say=say)
            rows.append(row)
            if row.get("made"):
                made.append(row["model"])
            if not row.get("skipped"):
                measure(ol, E, row, url=a.url, out_dir=out_dir, repeat=repeat, lists=lists,
                        tools=E.TOOLS, make_model=make_model, learner=learner, cases=cases,
                        say=say)
                try:
                    ol.unload(row["model"])
                except Exception:
                    pass
            save(out_dir, rows, meta)
    except KeyboardInterrupt:
        say("\nStopped. Cleaning up; the models finished so far are in the table.")
    finally:
        for name in ([] if a.keep else made):
            try:
                ol.remove(name)
            except Exception as exc:
                say(f"Could not remove {name} ({type(exc).__name__}); "
                    "`py -3 tools\\model_tryout\\chat_tryout.py --clean` removes it.")
        try:
            say(f"Loading {BASELINE} back onto the graphics card ...")
            ol.load(BASELINE)
        except Exception:
            say(f"{BASELINE} could not be loaded back; Jarvis loads it on its next question.")
    for r in rows:
        if r["model"] != BASELINE:
            r["verdict"] = list(verdict(rows[0], r))
    meta["finished"] = datetime.datetime.now().isoformat(timespec="seconds")
    save(out_dir, rows, meta)
    text = table(rows)
    if a.keep and made:
        text += "\n\nKept (--keep): " + ", ".join(made)
    text += ("\n\nNothing was switched: Jarvis still uses jarvis-primary. Changing its model "
             "stays your decision, made later with an approval card; the Modelfile-* files in "
             "this folder show exactly how each model was set up for the tryout.")
    (out_dir / "results.txt").write_text(text + "\n", encoding="utf-8")
    say("\n" + text)
    say(f"\nSaved: {out_dir / 'results.txt'} and results.json beside it.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
