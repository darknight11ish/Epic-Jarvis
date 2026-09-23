"""The self-test's "doctor" step: Ollama, the model, and the graphics card.

    python3 test_selftest_doctor.py

No pytest, no Ollama, no network. `doctor()` in selftest.py takes its fetcher
as a parameter; here it is a fake that records every URL and answers from a
canned table, so what the step ASKS is checked as closely as what it SAYS.

The promises being held to:
  - read-only and loads nothing: only /api/version, /api/tags and /api/ps,
    all GET, never /api/generate, /api/chat, /api/pull or /api/show;
  - only this PC: an Ollama address elsewhere is not contacted at all;
  - "skip", not a guess, when no model is loaded;
  - the cache-size checks can only ever warn, never fail.
"""
import sys
import traceback
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import selftest as ST  # noqa: E402

FAILED, PASSED = [], []
BASE = "http://127.0.0.1:11434"
GB = 1024 ** 3


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class Fake:
    def __init__(self, tags=None, ps=None, down=False):
        self.urls = []
        self.table = {"/api/version": {"version": "0.12.0"},
                      "/api/tags": {"models": [{"name": n} for n in (tags or [])]},
                      "/api/ps": {"models": ps or []}}
        self.down = down

    def __call__(self, url):
        self.urls.append(url)
        if self.down:
            raise ConnectionRefusedError("[WinError 10061] refused")
        path = url[len(BASE):] if url.startswith(BASE) else url
        if path not in self.table:
            raise AssertionError(f"asked for something it should not: {url}")
        return self.table[path]


def loaded(name, total_gb=5.5, vram_gb=5.5, ctx=16384):
    return {"name": name, "size": int(total_gb * GB), "size_vram": int(vram_gb * GB),
            "context_length": ctx}


GOOD_ENV = {"OLLAMA_KV_CACHE_TYPE": "q8_0"}


def statuses(rows):
    return [r[0] for r in rows]


def run(fake, model="jarvis-primary", env=GOOD_ENV, base=BASE):
    return ST.doctor(fetch=fake, base=base, model=model, env=env)


def t_all_well():
    f = Fake(tags=["jarvis-primary:latest", "qwen3:8b"], ps=[loaded("jarvis-primary:latest")])
    rows = run(f)
    check("everything good is all passes", statuses(rows) == [ST.PASS] * 3,
          f"{rows}")
    check("it asks exactly three questions",
          [u[len(BASE):] for u in f.urls] == list(ST.OLLAMA_PATHS), f"{f.urls}")
    check("'jarvis-primary' and 'jarvis-primary:latest' are the same model",
          any("downloaded" in r[1] for r in rows if r[0] == ST.PASS))


def t_it_loads_nothing():
    """The fetcher is the only way out, and it only ever GETs three paths."""
    seen = []

    class R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"models": []}'

    real = urllib.request.urlopen

    def spy(req, timeout=None):
        seen.append((req.get_method(), req.full_url, req.data))
        return R()
    urllib.request.urlopen = spy
    try:
        ST.doctor(base=BASE, model="jarvis-primary", env=GOOD_ENV)
    finally:
        urllib.request.urlopen = real
    check("the real fetcher only ever GETs", seen and all(m == "GET" and d is None
                                                         for m, _, d in seen), f"{seen}")
    check("and only the three read-only paths",
          {u[len(BASE):] for _, u, _ in seen} <= set(ST.OLLAMA_PATHS), f"{seen}")
    loaders = ("/api/generate", "/api/chat", "/api/pull", "/api/show", "/api/embed")
    check("never anything that loads or downloads a model",
          not any(p in u for _, u, _ in seen for p in loaders))


def t_nothing_loaded_is_skipped():
    f = Fake(tags=["jarvis-primary:latest"], ps=[])
    rows = run(f)
    check("no model loaded: the graphics-card check is skipped, not failed",
          statuses(rows)[-1] == ST.SKIP and ST.FAIL not in statuses(rows), f"{rows}")
    check("and it says how to check it", "Ask Jarvis" in rows[-1][2])


def t_spill_is_caught():
    f = Fake(tags=["jarvis-primary"], ps=[loaded("jarvis-primary", 8.0, 5.2)])
    rows = run(f)
    fails = [r for r in rows if r[0] == ST.FAIL]
    check("part of the model on the CPU is a failure", len(fails) == 1, f"{rows}")
    check("with the percentage", fails and "65%" in fails[0][1], f"{fails}")

    f = Fake(tags=["jarvis-primary"], ps=[loaded("jarvis-primary", 5.5, 0)])
    rows = run(f)
    check("all of it on the CPU is a failure too",
          any(r[0] == ST.FAIL and "CPU" in r[1] for r in rows), f"{rows}")

    f = Fake(tags=["jarvis-primary"], ps=[loaded("jarvis-primary", 0, 0)])
    check("a model still loading (size 0) is not called a spill",
          ST.FAIL not in statuses(run(f)))


def t_cache_checks_only_warn():
    f = Fake(tags=["jarvis-primary"], ps=[loaded("jarvis-primary", ctx=4096)])
    rows = run(f, env={})
    warns = [r for r in rows if r[0] == ST.WARN]
    check("a 4096 context is a warning", any("4096" in r[1] for r in warns), f"{rows}")
    check("an unset cache type is a warning", any("OLLAMA_KV_CACHE_TYPE" in r[1]
                                                  for r in warns), f"{rows}")
    check("and neither is ever a failure", ST.FAIL not in statuses(rows), f"{rows}")
    rows = run(f, env={"OLLAMA_KV_CACHE_TYPE": "f16"})
    check("a different cache type is a warning, not a failure",
          ST.FAIL not in statuses(rows) and any("'f16'" in r[1] for r in rows))
    f = Fake(tags=["jarvis-primary"], ps=[loaded("jarvis-primary", ctx=16384)])
    check("CONTROL: the intended setup has no cache warning",
          ST.WARN not in statuses(run(f)))


def t_ollama_down():
    f = Fake(down=True)
    rows = run(f)
    check("Ollama not answering is a failure", rows[0][0] == ST.FAIL, f"{rows}")
    check("that says how to start it", "ollama serve" in rows[0][2])
    check("and the rest is skipped, not asked", len(f.urls) == 1
          and rows[-1][0] == ST.SKIP, f"{f.urls}")


def t_not_downloaded():
    f = Fake(tags=["llama3.2:3b"], ps=[])
    rows = run(f, model="qwen3:8b")
    fail = [r for r in rows if r[0] == ST.FAIL]
    check("a model that is not downloaded is a failure", len(fail) == 1, f"{rows}")
    check("that says the command to get it", fail and "ollama pull qwen3:8b" in fail[0][2])
    rows = run(Fake(tags=[], ps=[]), model="jarvis-primary")
    check("for jarvis-primary it names the Modelfile, since it cannot be pulled",
          any("jarvis-primary.Modelfile" in r[2] for r in rows if r[0] == ST.FAIL))


def t_other_model_loaded():
    f = Fake(tags=["jarvis-primary"], ps=[loaded("llava:7b", 8, 2)])
    rows = run(f)
    check("someone else's model spilling is a warning, not Jarvis failing",
          ST.FAIL not in statuses(rows) and rows[-1][0] == ST.WARN, f"{rows}")


def t_only_this_pc():
    for base in ("http://192.168.1.50:11434", "http://100.101.102.103:11434",
                 "http://ollama.example.com"):
        f = Fake()
        rows = ST.doctor(fetch=f, base=base, model="jarvis-primary", env=GOOD_ENV)
        check(f"not contacted: {base}", f.urls == [] and rows[0][0] == ST.WARN, f"{rows}")
    check("localhost counts as this PC", ST._is_loopback("http://localhost:11434"))


def t_where_ollama_is():
    import os
    keep = {k: os.environ.get(k) for k in ("OLLAMA_URL", "OLLAMA_HOST")}
    try:
        os.environ.pop("OLLAMA_URL", None)
        os.environ["OLLAMA_HOST"] = "0.0.0.0:11434"
        check("OLLAMA_HOST=0.0.0.0 means this PC",
              ST._ollama_base() == "http://127.0.0.1:11434", ST._ollama_base())
        os.environ["OLLAMA_URL"] = "http://127.0.0.1:9999/"
        check("OLLAMA_URL wins", ST._ollama_base() == "http://127.0.0.1:9999")
    finally:
        for k, v in keep.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def t_never_raises():
    for body in (None, [], "text", {"models": None}, {"models": ["x", 3]}):
        f = Fake()
        f.table["/api/tags"] = body
        f.table["/api/ps"] = body
        try:
            run(f)
            ok = True
        except Exception as exc:
            ok = False
            print(f"        {body!r}: {exc!r}")
        check(f"a strange answer ({str(body)[:20]}) does not crash it", ok)
    rows = ST.doctor(fetch=Fake(), base=BASE, model=None, env=GOOD_ENV)
    check("no configured model: skipped, with the reason",
          rows[-1][0] == ST.SKIP and "which model" in rows[-1][1], f"{rows}")


if __name__ == "__main__":
    for fn in (t_all_well, t_it_loads_nothing, t_nothing_loaded_is_skipped,
               t_spill_is_caught, t_cache_checks_only_warn, t_ollama_down,
               t_not_downloaded, t_other_model_loaded, t_only_this_pc,
               t_where_ollama_is, t_never_raises):
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
