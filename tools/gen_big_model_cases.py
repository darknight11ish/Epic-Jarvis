#!/usr/bin/env python3
"""Writes jarvis-desktop/tests/fixtures/big-model-cases.json, and the phone's
identical copy in jarvis-client/app/src/test/resources/contract/: what GET
/api/big-model, GET /api/deep and their POSTs really answer, in named cases.

    python3 tools/gen_big_model_cases.py            # write the files
    python3 tools/gen_big_model_cases.py --check    # compare only

Every case is backend/jarvis_big_model.py itself - status(), deep_status(),
request_change(), ask() - run with the outside world replaced: whether
colibri's files and the model folders are there, how much memory and disk
there is, what kind of drive a folder is on, the process that would be
started (recorded, never started), and colibri's answers on 127.0.0.1.
Nothing is written by hand, so the desktop and the phone build against the
producer's real output. backend/test_big_model.py fails when the committed
files differ from a fresh run.

WHAT THE NUMBERS ARE. Made up to look like the owner's PC (32 GB of memory,
a SATA drive D: and an NVMe drive E:, colibri unpacked in C:\\colibri). They
were NOT read on the owner's PC, and no colibri has answered here: the
answers are a stand-in in colibri's documented shape (docs/api.md).
"""
import json
import sys
import tempfile
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FIXTURE = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "big-model-cases.json"
PHONE_FIXTURE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
                 / "big-model-cases.json")
COPIES = (FIXTURE, PHONE_FIXTURE)
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import jarvis_big_model as BM  # noqa: E402

GB = 1024 ** 3
NOW = 1_800_000_000.0
COLI = "C:\\colibri"
KEY = "KEY-sekrit-Zx81-do-not-print-me"
U_2060 = "GPU-8b7e2d44-1c9a-4f3e-a2b6-5e9d0c7f1a23"

MEDIUM = {"id": "qwen36", "name": "Qwen3.6-35B-A3B", "dir": "D:\\models\\qwen36_i4_gs64",
          "kind": "medium"}
GIANT = {"id": "dsv4-flash", "name": "DeepSeek V4 Flash", "dir": "E:\\models\\DeepSeek-V4-Flash",
         "kind": "giant"}


class FakeProc:
    def __init__(self, world, args, kwargs):
        self.world, self.args, self.kwargs = world, args, kwargs
        self.pid = 900002          # never a real process: nothing signals it
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


class FakeStore:
    def __init__(self, world):
        self.world = world

    def read(self):
        return self.world.stored_key

    def write(self, v):
        self.world.stored_key = v


class World:
    """Everything outside jarvis_big_model, replaced."""

    def __init__(self, *, colibri=True, python=True, models=(MEDIUM, GIANT),
                 missing=(), no_config=(), ram=(31.9, 25.3), free=None, drives=None,
                 cfg=None, ready=True, spawn_now=True, second=None, windows=True,
                 answer="Because the sky scatters blue light more than red.",
                 answer_tokens=12, chat_error=None, finish="stop", store=True,
                 port_taken=False, chat_seconds=8.0, real_http=False):
        self.colibri, self.python = colibri, python
        self.models = [dict(m) for m in models]
        self.missing, self.no_config = set(missing), set(no_config)
        self.ram = ram
        self.free = free if free is not None else {"D:": 3100.0, "E:": 290.0}
        self.drives = drives if drives is not None else {"D:": "SATA SSD", "E:": "NVMe"}
        self.cfg = dict(cfg or {})
        self.ready, self.spawn_now = ready, spawn_now
        self.second = second or {"capable": False, "uuid": None, "name": None, "lane": "off",
                                 "why": "only one graphics card found (the NVIDIA GeForce "
                                        "RTX 2080 SUPER)"}
        self.windows = windows
        self.answer, self.answer_tokens, self.finish = answer, answer_tokens, finish
        self.chat_error = chat_error
        self.store = store
        self.stored_key = None
        self.port_taken = port_taken
        self.chat_seconds = chat_seconds
        self.real_http = real_http
        self.audits = []
        self.clock = 1000.0
        self.started, self.killed, self.http, self.events = [], [], [], []
        self.on_chat = None
        self.answer_fn = None
        self.on_sleep = None
        self.dir = Path(tempfile.mkdtemp(prefix="jarvis-big-model-"))
        self._saved = {}
        self._ids = 0

    # -- the replaced functions --
    def section(self):
        s = {"coli_path": COLI, "models": self.models}
        s.update(self.cfg)
        return s

    def isfile(self, p):
        p = str(p).replace("/", "\\")
        if p in (COLI + "\\coli.cmd", COLI + "\\coli"):
            return self.colibri
        for m in self.models:
            if p == str(m.get("dir")) + "\\config.json":
                return m["id"] not in self.missing and m["id"] not in self.no_config
        return False

    def isdir(self, p):
        p = str(p)
        return any(p == m.get("dir") and m["id"] not in self.missing for m in self.models)

    def which(self, name):
        if not self.python:
            return None
        if name == "py" and self.windows:
            return "C:\\Windows\\py.exe"
        if name == "python3" and not self.windows:
            return "/usr/bin/python3"
        return None

    def run(self, cmd, timeout):
        return (0, "3\n") if self.python else (None, "")

    def memory(self):
        t, a = self.ram
        return (None if t is None else int(t * GB), None if a is None else int(a * GB))

    def disk_free(self, path):
        d = BM._drive_of(str(path))
        v = self.free.get(d)
        return None if v is None else int(v * GB)

    def drive_type(self, drive):
        return self.drives.get(drive, "unknown")

    def popen(self, args, **kwargs):
        return FakeProc(self, args, kwargs)

    def kill_tree(self, p):
        self.killed.append(p)
        p.alive = False

    def sleep(self, s):
        self.clock += s
        if self.on_sleep:
            self.on_sleep()

    def mono(self):
        return self.clock

    def http_(self, method, url, payload=None, *, key=None, timeout=5.0):
        self.http.append((method, url, payload, key))
        if not BM._is_ours(url):
            raise AssertionError("a non-loopback address was asked: " + url)
        alive = any(p.alive for p in self.started)
        if url.endswith("/v1/models"):
            if not (self.ready and alive):
                raise OSError("timed out")
            return {"object": "list", "data": [{"id": m["id"], "object": "model"}
                                                for m in self.models]}
        if url.endswith("/v1/chat/completions"):
            if self.on_chat:
                self.on_chat()
            if self.chat_error is not None:
                raise self.chat_error
            self.clock += self.chat_seconds
            content = self.answer_fn(payload) if self.answer_fn else self.answer
            return {"id": "chatcmpl-1", "object": "chat.completion", "model": payload["model"],
                    "choices": [{"index": 0, "finish_reason": self.finish,
                                 "message": {"role": "assistant", "content": content}}],
                    "usage": {"prompt_tokens": 60, "completion_tokens": self.answer_tokens,
                              "total_tokens": 60 + self.answer_tokens}}
        raise OSError("not answered here")

    def new_id(self):
        self._ids += 1
        return f"deep_{self._ids:06d}"

    def install(self):
        BM._reset_for_tests()
        repl = {
            "_section": self.section,
            "_config_dir": lambda: self.dir,
            "_isfile": self.isfile,
            "_isdir": self.isdir,
            "_which": self.which,
            "_run": self.run,
            "_memory": self.memory,
            "_disk_free": self.disk_free,
            "_drive_type": self.drive_type,
            "_port_taken": lambda port: self.port_taken,
            "_popen": self.popen,
            "_kill_tree": self.kill_tree,
            "_spawn": (lambda fn: fn()) if self.spawn_now else (lambda fn: None),
            "_sleep": self.sleep,
            "_now": lambda: NOW,
            "_mono": self.mono,
            "_http": self.http_,
            "_second_card": lambda: dict(self.second),
            "_key_store": (lambda: FakeStore(self)) if self.store else (lambda: None),
            "_make_key": lambda: KEY,
            "_publish": lambda kind, data: self.events.append((kind, dict(data))),
            "_audit": lambda event, detail: self.audits.append((event, dict(detail))),
            "_tier": lambda action: "ask",
            "_start_reaper": lambda: None,
            "_new_id": self.new_id,
            "_ON_WINDOWS": self.windows,
        }
        if self.real_http:
            # A real server on 127.0.0.1 answers, in real time.
            del repl["_http"]
            del repl["_mono"]
        for name, val in repl.items():
            self._saved[name] = getattr(BM, name)
            setattr(BM, name, val)
        return self

    def remove(self):
        try:
            BM._reset_for_tests()
        finally:
            for name, val in self._saved.items():
                setattr(BM, name, val)

    def switches(self, **on):
        data = {s: bool(on.get(s)) for s in BM.SWITCHES}
        (self.dir / "big-model.json").write_text(json.dumps(data), encoding="utf-8")

    def __enter__(self):
        return self.install()

    def __exit__(self, *exc):
        self.remove()


class Verdict:
    def __init__(self, allowed, tier="ask", outcome=None, request_id="r1", reason=""):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome
        self.request_id, self.reason = request_id, reason


def _post(code_body) -> dict:
    code, body = code_body
    return {"status": code, "body": body}


def cases() -> dict:
    out = {}
    with World(colibri=False):
        out["status_not_installed"] = BM.status()
    with World(python=False):
        out["status_no_python"] = BM.status()
    with World():
        out["status_ready_off"] = BM.status()
        out["deep_off"] = BM.deep_status()
        out["ask_refused_off"] = _post(BM.ask("Why is the sky blue?"))
    with World() as w:
        out["post_master_on_pending"] = _post(BM.request_change("master", True,
                                                                spawn=lambda fn: None))
        out["post_master_on_again_409"] = _post(BM.request_change("master", True,
                                                                  spawn=lambda fn: None))
        out["status_pending"] = BM.status()
        out["post_master_off"] = _post(BM.request_change("master", False))
    with World() as w:
        w.switches(master=True, wiki=True, deep_questions=True)
        out["status_on_idle"] = BM.status()
    with World(spawn_now=False) as w:
        w.switches(master=True, deep_questions=True)
        BM.lane_for("deep_questions")
        out["status_loading"] = BM.status()
    with World() as w:
        w.switches(master=True, deep_questions=True)
        BM.lane_for("deep_questions")
        out["status_running"] = BM.status()
    with World(ram=(31.9, 12.4)) as w:
        w.switches(master=True, wiki=True, deep_questions=True)
        BM.lane_for("wiki")
        out["status_not_enough_free_memory"] = BM.status()
    with World(ram=(16.0, 11.0)) as w:
        out["status_too_little_memory"] = BM.status()
    with World(models=(dict(GIANT, dir="D:\\models\\DeepSeek-V4-Flash"),)) as w:
        out["status_giant_on_sata"] = BM.status()
    with World(cfg={"cuda": "on"}) as w:
        w.switches(master=True, deep_questions=True)
        BM.lane_for("deep_questions")
        out["status_cuda_refused"] = BM.status()
    with World(models=(MEDIUM,), missing=("qwen36",)) as w:
        out["status_model_folder_missing"] = BM.status()
    # Deep questions: every state, each seen as it happened.
    with World() as w:
        w.switches(master=True, deep_questions=True)
        out["ask_accepted"] = _post(BM.ask("Why is the sky blue?", spawn=lambda fn: None))
        out["ask_empty_400"] = _post(BM.ask("   "))
        out["ask_too_long_400"] = _post(BM.ask("x" * (BM.MAX_QUESTION_CHARS + 1)))
        out["deep_queued"] = BM.deep_status()
        seen = {}
        w.ready = False

        def while_loading():
            if "loading" not in seen:
                seen["loading"] = BM.deep_status()
                w.ready = True
        w.on_sleep = while_loading

        def while_thinking():
            seen.setdefault("thinking", BM.deep_status())
        w.on_chat = while_thinking
        BM._DEEP_WORKER["running"] = True
        BM._deep_worker()
        out["deep_loading"] = seen["loading"]
        out["deep_thinking"] = seen["thinking"]
        out["deep_done"] = BM.deep_status()
        out["status_after_one_answer"] = BM.status()
        w.on_sleep = w.on_chat = None
        w.chat_error = urllib.error.HTTPError(BM._ENGINE.url() + "/v1/chat/completions", 500,
                                              "boom", None, None)
        BM.ask("And why are sunsets red?")
        out["deep_failed"] = BM.deep_status()
    return out


def render() -> str:
    body = {
        "_about": ("Real output of backend/jarvis_big_model.py (GET /api/big-model, GET "
                   "/api/deep, and the POST answers), one per named case, made by "
                   "tools/gen_big_model_cases.py. The PC behind them (memory, drives, "
                   "folders) is made up to look like the owner's, and colibri's answers "
                   "are a stand-in in its documented shape; neither was captured on the "
                   "owner's PC. Do not edit by hand: re-run the tool."),
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
                  f"python3 tools/gen_big_model_cases.py")
        if stale:
            return 1
        print("big-model-cases.json matches the producer (desktop and phone copies).")
        return 0
    for path in COPIES:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
