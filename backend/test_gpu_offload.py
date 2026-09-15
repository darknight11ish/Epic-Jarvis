"""Does anything tell you the model fell off the graphics card?

    python3 test_gpu_offload.py

No pytest, no network, no Ollama. `_get` is replaced with a function that
returns a canned /api/ps body.

The failure being caught: llama.cpp fits what it can on the card and runs the
rest on the CPU. Ollama reports the model loaded and healthy either way, so
the only symptom is that answers take fifteen seconds instead of two, and the
owner blames the assistant rather than the fit. Jan detects the all-CPU case by
counting devices; /api/ps carries `size` and `size_vram` per model, so partial
spill - the commoner one - is a subtraction.
"""
import json, sys, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_models as MM

HUD = HERE / "jarvis_hud.py"
BRAIN_JS = HERE.parent / "jarvis-desktop" / "src" / "brain.js"

FAILED, PASSED = [], []
MB = 1024 * 1024


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class Canned:
    """Stands in for `_get`, and records that loopback was the only URL asked
    for - a diagnostic that phoned out would be a rule-one violation."""

    def __init__(self, body):
        self.body = body
        self.urls = []

    def __call__(self, url, timeout=12.0, headers=None):
        self.urls.append(url)
        return self.body


def with_ps(models):
    return Canned(json.dumps({"models": models}))


def run(canned):
    real = MM._get
    MM._get = canned
    try:
        return MM.offload_status()
    finally:
        MM._get = real


def t_all_on_the_gpu():
    c = with_ps([{"name": "qwen3:8b", "size": 6000 * MB, "size_vram": 6000 * MB}])
    out = run(c)
    check("a fully offloaded model reads gpu", out["status"] == "gpu", f"got {out}")
    check("and 100 percent", out.get("on_gpu_percent") == 100)
    check("and it only ever asked loopback",
          all("127.0.0.1" in u or "localhost" in u for u in c.urls), f"asked {c.urls}")


def t_all_on_the_cpu():
    out = run(with_ps([{"name": "qwen3:8b", "size": 6000 * MB, "size_vram": 0}]))
    check("a model with no VRAM reads cpu", out["status"] == "cpu", f"got {out}")
    check("and says so in words a person can act on",
          "CPU" in out["note"] and "slower" in out["note"], f"note={out['note']}")
    check("and does not blame the user",
          "video memory" in out["note"] or "too big" in out["note"])


def t_partial_spill():
    """The case Jan's device-count check cannot see."""
    # 5200/8000 is 65% exactly. Deliberately not 5000/8000: that is 62.5, and
    # Python rounds halves to even, so the first version of this test asserted
    # 63 and the code correctly said 62. A test whose expected value depends on
    # a tie-breaking rule is testing the rule, not the behaviour.
    out = run(with_ps([{"name": "qwen3:8b", "size": 8000 * MB, "size_vram": 5200 * MB}]))
    check("a half-offloaded model reads partial", out["status"] == "partial", f"got {out}")
    check("and reports the percentage", out.get("on_gpu_percent") == 65,
          f"got {out.get('on_gpu_percent')}")
    check("and the percentage is in the sentence", "65%" in out["note"],
          f"note={out['note']}")
    check("and says how big the model is against the budget",
          "8000 MB" in out["note"], f"note={out['note']}")


def t_the_worst_model_wins():
    out = run(with_ps([
        {"name": "good", "size": 1000 * MB, "size_vram": 1000 * MB},
        {"name": "bad", "size": 1000 * MB, "size_vram": 0},
    ]))
    check("one model on the CPU is reported even when another is fine",
          out["status"] == "cpu", f"got {out}")
    check("and both are listed", len(out["models"]) == 2)


def t_nothing_loaded():
    out = run(with_ps([]))
    check("no loaded model is 'idle', not a warning", out["status"] == "idle",
          f"got {out}")
    check("and explains that this is normal",
          "normal" in out["note"] or "unloads" in out["note"], f"note={out['note']}")


def t_it_never_raises():
    for body in (None, "", "not json at all", "{}", '{"models": null}',
                 '{"models": [{"size": 0, "size_vram": 0}]}',
                 '{"models": [{"size": "big", "size_vram": None}]}'):
        try:
            out = run(Canned(body))
            ok = isinstance(out, dict) and "status" in out
        except Exception as exc:
            ok = False
            print(f"        {body!r} raised {type(exc).__name__}: {exc}")
        check(f"a broken answer ({body!r:28.28}) is survived", ok)


def t_a_zero_size_model_does_not_divide_by_zero():
    """Real, and seen while a model is still loading."""
    out = run(with_ps([{"name": "loading", "size": 0, "size_vram": 0}]))
    check("a zero-size model does not crash and is not called a failure",
          out["status"] == "gpu", f"got {out}")


def t_it_is_surfaced():
    if not HUD.is_file():
        check("the models view carries it", False, f"no {HUD}")
    else:
        src = HUD.read_text(encoding="utf-8")
        check("the models view carries it", '"offload": offload' in src)
        check("and a failure there does not take the view down",
              "could not be checked" in src)
    if not BRAIN_JS.is_file():
        check("the Brain shows a banner", False, f"no {BRAIN_JS}")
        return
    js = BRAIN_JS.read_text(encoding="utf-8")
    check("the Brain shows a banner",
          'off.status === "cpu"' in js and 'off.status === "partial"' in js)
    check("and says nothing when it is fine",
          'off.status === "gpu"' not in js,
          "a banner on the healthy path is noise on every visit")


def main():
    for fn in (t_all_on_the_gpu, t_all_on_the_cpu, t_partial_spill,
               t_the_worst_model_wins, t_nothing_loaded, t_it_never_raises,
               t_a_zero_size_model_does_not_divide_by_zero, t_it_is_surfaced):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
