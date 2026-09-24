#!/usr/bin/env python3
"""Writes jarvis-desktop/tests/fixtures/second-card-cases.json, and the
phone's identical copy in jarvis-client/app/src/test/resources/contract/:
what GET /api/second-card really answers, in six named situations.

    python3 tools/gen_second_card_cases.py            # write the file
    python3 tools/gen_second_card_cases.py --check    # compare only

Every case is backend/jarvis_second_card.status() itself, run with the
outside world replaced: nvidia-smi's output (in its real CSV format), the
answers Ollama gives on 127.0.0.1, and a stand-in for starting a process.
Nothing is written by hand, so the desktop and the phone build against the
producer's real output. backend/test_second_card.py fails when the committed
file differs from a fresh run.

WHAT THE nvidia-smi LINES ARE. The format is nvidia-smi's own
(`--query-gpu=index,uuid,name,memory.total,memory.free,compute_cap,
display_active --format=csv,noheader,nounits`). The values - names, memory
sizes, ids - are made up to look like the owner's cards. They were NOT
captured on the owner's PC: that output has not been seen yet.
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FIXTURE = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "second-card-cases.json"
# The phone's copy, byte for byte the same, read by SecondCardContractTest.kt
# from its test resources (the way contract/pending-rows.json is shared).
# Written and checked together with the desktop's, so neither can drift.
PHONE_FIXTURE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
                 / "second-card-cases.json")
COPIES = (FIXTURE, PHONE_FIXTURE)
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import jarvis_compute as CP  # noqa: E402
import jarvis_second_card as SC  # noqa: E402

FULL = CP.FIELDS_FULL
U_2080S = "GPU-3f2a9c1e-7b1d-4e8a-9c55-0d4b2e6a8f10"
U_2060 = "GPU-8b7e2d44-1c9a-4f3e-a2b6-5e9d0c7f1a23"
U_2080TI = "GPU-51c0e8aa-6d2f-4b19-8e37-2a4c9f0b6d58"
U_1080 = "GPU-0a9d3b72-e4c1-4a6f-b85e-7c2d1f9e4b36"
U_P100 = "GPU-c6e1f057-3a8b-49d2-9f14-b0e7a25d8c61"

SMI = {
    "one_card": f"0, {U_2080S}, NVIDIA GeForce RTX 2080 SUPER, 8192, 6120, 7.5, Enabled\n",
    "2080s_2060": (f"0, {U_2080S}, NVIDIA GeForce RTX 2080 SUPER, 8192, 6120, 7.5, Enabled\n"
                   f"1, {U_2060}, NVIDIA GeForce RTX 2060, 12288, 12030, 7.5, Disabled\n"),
    # The 2060 in the first slot: nvidia-smi calls it 0. The monitor decides.
    "2060_first": (f"0, {U_2060}, NVIDIA GeForce RTX 2060, 12288, 12030, 7.5, Disabled\n"
                   f"1, {U_2080S}, NVIDIA GeForce RTX 2080 SUPER, 8192, 6120, 7.5, Enabled\n"),
    "2080s_2080ti": (f"0, {U_2080S}, NVIDIA GeForce RTX 2080 SUPER, 8192, 6120, 7.5, Enabled\n"
                     f"1, {U_2080TI}, NVIDIA GeForce RTX 2080 Ti, 11264, 11010, 7.5, Disabled\n"),
    "2080s_p100": (f"0, {U_2080S}, NVIDIA GeForce RTX 2080 SUPER, 8192, 6120, 7.5, Enabled\n"
                   f"1, {U_P100}, Tesla P100-PCIE-16GB, 16384, 16270, 6.0, Disabled\n"),
    "2080s_1080": (f"0, {U_2080S}, NVIDIA GeForce RTX 2080 SUPER, 8192, 6120, 7.5, Enabled\n"
                   f"1, {U_1080}, NVIDIA GeForce GTX 1080, 8192, 8010, 6.1, Disabled\n"),
    "2080s_2060_6gb": (f"0, {U_2080S}, NVIDIA GeForce RTX 2080 SUPER, 8192, 6120, 7.5, Enabled\n"
                       f"1, {U_1080[:-4]}ab12, NVIDIA GeForce RTX 2060, 6144, 5900, 7.5, Disabled\n"),
}
# An older driver: the full query is refused, the one without compute_cap works.
SMI_OLD_DRIVER = (f"0, {U_2080S}, NVIDIA GeForce RTX 2080 SUPER, 8192, 6120, Enabled\n"
                  f"1, {U_2060}, NVIDIA GeForce RTX 2060, 12288, 12030, Disabled\n")


class FakeProc:
    def __init__(self, world, args, kwargs):
        self.world, self.args, self.kwargs = world, args, kwargs
        self.pid = 900001          # never a real process: nothing signals it
        self.alive = True
        world.started.append(self)

    def poll(self):
        return None if self.alive else 1

    def kill(self):
        self.alive = False

    def terminate(self):
        self.alive = False

    def wait(self, timeout=None):
        return 0


class World:
    """Everything outside the module, replaced. `install()` puts it in;
    `remove()` takes it out again."""

    def __init__(self, smi, *, old_driver=None, installed=("qwen3:8b", "qwen3:14b"),
                 foreign_on_port=False, lane_answers=True, spawn_now=True,
                 user_env=None, windows=False, apps="", tags_answer=True):
        self.smi, self.old_driver = smi, old_driver
        self.installed = list(installed)
        self.foreign_on_port, self.lane_answers = foreign_on_port, lane_answers
        self.spawn_now, self.user_env, self.windows = spawn_now, user_env, windows
        self.apps, self.tags_answer = apps, tags_answer
        self.started, self.killed, self.http = [], [], []
        self.dir = Path(tempfile.mkdtemp(prefix="jarvis-second-card-"))
        self._saved = {}

    def run_smi(self, args):
        q = args[0]
        if q == f"--query-gpu={CP.FIELDS_FULL}":
            return None if self.old_driver is not None else self.smi
        if q == f"--query-gpu={CP.FIELDS_OLD}":
            return self.old_driver
        return None

    def running(self):
        return any(p.alive for p in self.started)

    def http_json(self, url, payload=None, timeout=2.0):
        self.http.append((url, payload))
        if not SC._is_loopback_url(url):
            raise AssertionError("a non-loopback address was asked: " + url)
        lane = url.startswith("http://127.0.0.1:11435")
        if url.endswith("/api/version"):
            if lane and (self.foreign_on_port or (self.lane_answers and self.running())):
                return {"version": "0.12.3"}
            raise OSError("connection refused")
        if url.endswith("/api/tags"):
            if not self.tags_answer or (lane and not self.running()):
                raise OSError("connection refused")
            return {"models": [{"name": n, "model": n} for n in self.installed]}
        if url.endswith("/api/generate"):
            return {"response": "<think></think>{\"facts\": []}"}
        raise OSError("not answered here")

    def popen(self, args, **kwargs):
        return FakeProc(self, args, kwargs)

    def kill_tree(self, p):
        self.killed.append(p)
        p.alive = False

    def install(self):
        SC._reset_for_tests()
        CP._cache.update(at=-1e9, cards=None, fields="")
        repl = {
            (CP, "_run_smi"): self.run_smi,
            (SC, "_primary"): lambda cards: CP.primary(cards, configured=""),
            (SC, "_cfg"): lambda key, default=None: default,
            (SC, "_state_path"): lambda: self.dir / "second-card.json",
            (SC, "_log_path"): lambda: self.dir / "second-card-ollama.log",
            (SC, "_http_json"): self.http_json,
            (SC, "_port_taken"): lambda port: False,
            (SC, "_popen"): self.popen,
            (SC, "_which"): lambda name: "/usr/local/bin/ollama",
            (SC, "_kill_tree"): self.kill_tree,
            (SC, "_spawn"): (lambda fn: fn()) if self.spawn_now else (lambda fn: None),
            (SC, "_sleep"): lambda s: None,
            (SC, "_user_env"): lambda name: self.user_env,
            (SC, "_ON_WINDOWS"): self.windows,
            (SC, "_smi_apps"): lambda: self.apps,
            (SC, "_audit"): lambda event, detail: None,
            (SC, "_tier"): lambda action: "ask",
            (SC, "_main_ollama_url"): lambda: "http://127.0.0.1:11434",
            # `_sleep` does nothing here, so a start that never answers would
            # spin for the real 30 seconds.
            (SC._LaneProcess, "START_SECONDS"): 0.3,
        }
        for (mod, name), val in repl.items():
            self._saved[(mod, name)] = getattr(mod, name)
            setattr(mod, name, val)
        return self

    def remove(self):
        try:
            SC._reset_for_tests()
        finally:
            for (mod, name), val in self._saved.items():
                setattr(mod, name, val)
            CP._cache.update(at=-1e9, cards=None, fields="")

    def switches(self, master=False, **features):
        data = {"master": master, "features": {f: bool(features.get(f)) for f in SC.FEATURE_IDS}}
        (self.dir / "second-card.json").write_text(json.dumps(data), encoding="utf-8")

    def __enter__(self):
        return self.install()

    def __exit__(self, *exc):
        self.remove()


def cases() -> dict:
    out = {}
    with World(SMI["one_card"]) as w:
        out["one_card"] = SC.status()
    with World(SMI["2080s_2060"], windows=True, user_env=None) as w:
        out["capable_off"] = SC.status()
    with World(SMI["2080s_2060"], windows=True, user_env=U_2080S) as w:
        w.switches(master=True)
        # The card is raised and waits: `spawn` does nothing here, so no
        # answer ever comes back, which is what "waiting" is.
        SC.request_change("long_context", True, spawn=lambda fn: None)
        out["capable_pending"] = SC.status()
    with World(SMI["2080s_2060"], windows=True, user_env=U_2080S) as w:
        w.switches(master=True, long_context=True)
        out["running_long_context"] = SC.status()
    with World(SMI["one_card"]) as w:
        w.switches(master=True, long_context=True, vision=True)
        out["card_missing_but_enabled"] = SC.status()
    with World(SMI["2080s_1080"], windows=True) as w:
        out["not_capable_old_card"] = SC.status()
    return out


def render() -> str:
    body = {
        "_about": ("Real output of backend/jarvis_second_card.status() (GET "
                   "/api/second-card), one per named case, made by "
                   "tools/gen_second_card_cases.py. The nvidia-smi lines behind them are "
                   "in nvidia-smi's real format with made-up values; they were not "
                   "captured on the owner's PC. Do not edit by hand: re-run the tool."),
        "cases": cases(),
    }
    return json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        stale = []
        for path in COPIES:
            have = path.read_text(encoding="utf-8") if path.is_file() else ""
            if have.replace("\r\n", "\n") != text:
                stale.append(path)
        for path in stale:
            print(f"{path.relative_to(ROOT)} is out of date: run "
                  f"python3 tools/gen_second_card_cases.py")
        if stale:
            return 1
        print("second-card-cases.json matches the producer (desktop and phone copies).")
        return 0
    for path in COPIES:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
