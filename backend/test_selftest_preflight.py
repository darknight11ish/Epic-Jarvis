"""test_selftest_preflight.py - `selftest.py --preflight`, with stand-ins.

    python3 backend/test_selftest_preflight.py

The owner's decision of 2026-09-25 (CLAUDE.md, after the "Build Your Own
Jarvis" prompt pack): a live preflight check on the PC - every real chain
tested end to end against the RUNNING Jarvis, "N pass, N fail, N warn", one
new check per real incident.

No network here. A stand-in Jarvis answers the HTTP calls (and records
every one), a stand-in Ollama answers doctor()'s three reads and the one
question, and a folder built from this repository plays the owner's
backend folder: every shipped module copied in, and the owner's own files
made from the whole patch stack (backend/_stack.py). What is proved:

  * the registry: every check the owner asked for is there, in order, and
    two checks cannot share a name;
  * a healthy Jarvis gives no FAIL, and the summary line is "N pass, N fail,
    N warn";
  * READ-ONLY: in a whole run the only POSTs are the one chat question and
    Test search - never an approval, a denial, a power or model change, or
    Stop everything - and Ollama is asked one question with no size and no
    unload;
  * the pairing token is sent, and never printed;
  * each check FAILs (or WARNs) on the thing it is there for: Jarvis down,
    no token, a token nobody accepts, a request with no token accepted, a
    private file served over HTTP, a patch missing or half there, a module
    that differs or is missing or changed after the start, the owner check
    in the files but not switched on, the scheduler stopped, a silent event
    stream, voice not installed (a warning only), the desktop app older than
    this repository;
  * the chat question is skipped while tools are on, unless --with-chat;
  * calendar and email are only said to be set up, unless --with-reads;
    web search is tested only when it is on and a provider is chosen;
  * a check that raises is its own FAIL and the rest still run.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import SHIPPED, require_shipped  # noqa: E402

require_shipped("jarvis_token_store.py")

import _stack  # noqa: E402
import selftest as S  # noqa: E402

PASSED, FAILED = [], []
TOKEN = "preflight-test-token"      # a stand-in, not key-shaped
OLLAMA = "http://127.0.0.1:11434"
MODEL = "jarvis-primary:latest"
OWNER_FILES = ("jarvis_hud.py", "jarvis_gate.py", "jarvis_extract.py", "jarvis_models.py",
               "jarvis_skills.py")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


# ------------------------------------------------------------ stand-ins --

_BACKEND = None


def backend_folder() -> Path:
    """A backend folder as apply-patches.ps1 leaves it: every shipped module,
    and the owner's five files as the whole patch stack makes them."""
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND
    d = Path(tempfile.mkdtemp(prefix="jarvis-preflight-backend-"))
    for rel in SHIPPED:
        shutil.copy2(HERE / rel, d / rel.rsplit("/", 1)[-1])
    for f in OWNER_FILES:
        text, log = _stack.stand_in(f)
        assert text is not None, log
        (d / f).write_text(text, encoding="utf-8")
    _BACKEND = d
    return d


class FakeJarvis:
    """The running backend, as far as the preflight can see it."""

    def __init__(self, **over):
        self.calls = []
        self.down = False
        self.no_token_ok = False
        started = time.time() + 3600      # after every file's time: nothing "changed since"
        self.routes = {
            ("GET", "/api/status"): (200, {"lane": "local", "model": MODEL, "power": "active",
                                          "activity": "idle"}),
            ("GET", "/api/version"): (200, {"api": 1, "started": started, "capabilities": {
                "approvals": True, "owner_check": "backend", "stop_all": True,
                "temporary_chat": True}}),
            ("GET", "/api/pending"): (200, {"pending": []}),
            ("GET", "/api/reach"): (200, {"available": True, "rows": [
                {"id": "calendar", "state": "on", "state_words": "On"},
                {"id": "email_read", "state": "not_set_up", "state_words": "Not set up"}],
                "tools": []}),
            ("POST", "/api/chat"): (200, {"choices": [{"message": {"content": "ready"}}]},
                                    {"x-jarvis-route": json.dumps({"where": "local"})}),
            ("GET", "/api/schedule"): (200, {"available": True, "running": True, "jobs": []}),
            ("GET", "/api/voice/status"): (200, {"stt": {"available": True},
                                                "tts": {"available": True}}),
            ("GET", "/api/search"): (200, {"available": True, "provider": "searxng"}),
            ("POST", "/api/search/test"): (200, {"ok": True, "state": "works", "said": "It works."}),
        }
        self.routes.update(over)
        self.events = "retry: 3000\n\nevent: hello\ndata: {}\n"

    def http(self, method, url, headers, body, timeout):
        assert url.startswith("http://127.0.0.1:"), url
        path = url.split("127.0.0.1:", 1)[1].split("/", 1)[1]
        path = "/" + path
        self.calls.append((method, path, headers.get("X-Jarvis-Token"), body))
        if self.down:
            raise ConnectionRefusedError("refused")
        route = path.split("?", 1)[0]
        if route.startswith("/api/") and route != "/api/version":
            if headers.get("X-Jarvis-Token") != TOKEN and not (
                    self.no_token_ok and not headers.get("X-Jarvis-Token")):
                return 401, {}, b'{"error": "bad or missing X-Jarvis-Token"}'
        got = self.routes.get((method, route))
        if got is None:
            return 404, {}, b'{"error": "no such route"}'
        if callable(got):
            got = got(headers, body)
        code, obj = got[0], got[1]
        hdrs = got[2] if len(got) > 2 else {}
        raw = obj if isinstance(obj, bytes) else json.dumps(obj).encode("utf-8")
        return code, hdrs, raw

    def stream_head(self, url, headers, timeout):
        self.calls.append(("GET", "/api/events", headers.get("X-Jarvis-Token"), None))
        if self.down:
            raise ConnectionRefusedError("refused")
        return self.events

    def posts(self):
        return [p for m, p, _t, _b in self.calls if m == "POST"]


class FakeOllama:
    def __init__(self):
        self.gets, self.posts = [], []

    def fetch(self, url):
        self.gets.append(url)
        path = url[len(OLLAMA):]
        return {"/api/version": {"version": "0.12.0"},
                "/api/tags": {"models": [{"name": MODEL}]},
                "/api/ps": {"models": [{"name": MODEL, "size": 100, "size_vram": 100,
                                        "context_length": 16384}]}}[path]

    def post(self, url, body):
        self.posts.append((url, body))
        return {"message": {"content": "ready"}, "done": True}


class FakeStore:
    def __init__(self, target):
        self.target = target

    def read(self):
        return None


def _live(fake=None, ollama=None, **kw):
    fake = fake or FakeJarvis()
    ollama = ollama or FakeOllama()
    args = dict(http=fake.http, stream_head=fake.stream_head, ollama=ollama.fetch,
                ollama_post=ollama.post, ollama_base=OLLAMA,
                tokens=[("Windows Credential Manager (the backend's own)", TOKEN)],
                backend=backend_folder(), env={"OLLAMA_KV_CACHE_TYPE": "q8_0"},
                log_dir=Path(tempfile.mkdtemp(prefix="jarvis-preflight-logs-")),
                token_store=FakeStore)
    args.update(kw)
    return S.Live(**args), fake, ollama


class _FakeGate(types.ModuleType):
    def __init__(self, allowed=False):
        super().__init__("jarvis_gate")
        self._allowed = allowed

    def check(self, action, detail, timeout=None, **_):
        return types.SimpleNamespace(allowed=self._allowed, tier="never", outcome="refused")


def _run(live, only=None):
    lines = []
    sys.modules["jarvis_gate"] = _FakeGate()
    p, f, w, s, rows = S.run_preflight(live, only=only, out=lines.append)
    return p, f, w, s, rows, "\n".join(lines)


def _rows(rows, key):
    return [(st, what, d) for k, st, what, d in rows if k == key]


# ---------------------------------------------------------------- tests --

def t_the_registry():
    keys = [k for k, _t, _f in S.PREFLIGHT]
    want = ["backend", "handshake", "model", "chat", "patches", "modules", "private_files",
            "gate", "stop_all", "scheduler", "folders", "instant_email", "events", "voice",
            "reach", "home", "credentials"]
    check("every check the owner asked for is registered, in order", keys == want, keys)
    check("each has a title", all(t for _k, t, _f in S.PREFLIGHT))
    try:
        S.preflight_check("backend", "again")(lambda live: [])
        check("two checks cannot share a name", False)
    except ValueError:
        check("two checks cannot share a name", True)
    check("the shape of a new check is one function", len(S.PREFLIGHT) == len(want))


def t_a_healthy_jarvis_passes_and_says_so():
    live, fake, ollama = _live()
    p, f, w, s, rows, text = _run(live)
    check("a healthy Jarvis: no FAIL", f == 0,
          "\n".join(f"{k}: {st} {what} {d}" for k, st, what, d in rows if st == S.FAIL))
    check("the last line is 'N pass, N fail, N warn'",
          text.strip().splitlines()[-1].startswith(f"{p} pass, 0 fail, {w} warn"),
          text.strip().splitlines()[-1])
    check("each row reads PASS / FAIL / WARN / skip",
          all(line.startswith(("  PASS  ", "  FAIL  ", "  WARN  ", "  skip  ", "          "))
              for line in text.splitlines() if line.startswith("  ")))
    check("the pairing token was sent", any(t == TOKEN for _m, _p, t, _b in fake.calls))
    check("and never printed", TOKEN not in text)
    check("the patches row counts every patch",
          any("patches are in your files" in what for st, what, _d in _rows(rows, "patches")
              if st == S.PASS), _rows(rows, "patches"))
    check("the model answered", any(st == S.PASS and "answered a one-word question" in what
                                    for st, what, _d in _rows(rows, "model")))
    check("the chat question went through, as a temporary chat",
          any(st == S.PASS and "temporary chat" in what for st, what, _d in _rows(rows, "chat")))
    print("\n----- example output (stand-ins) -----")
    print(text)
    print("----- end of example -----\n")


def t_read_only():
    fake = FakeJarvis()
    fake.routes[("GET", "/api/reach")] = (200, {"rows": [], "tools": [
        {"id": "web_search", "name": "Web search"}]})
    live, fake, ollama = _live(fake, with_chat=True)
    _run(live)
    posts = fake.posts()
    check("the only POSTs are the chat question and Test search",
          sorted(set(posts)) == ["/api/chat", "/api/search/test"], posts)
    for bad in ("/api/approve", "/api/deny", "/api/power", "/api/stop_all",
                "/api/task/stop", "/api/models/switch", "/api/models/unload"):
        check(f"never {bad}", not any(p.startswith(bad) for _m, p, _t, _b in fake.calls))
    chat = [b for m, p, _t, b in fake.calls if m == "POST" and p == "/api/chat"]
    body = json.loads(chat[0]) if chat else {}
    check("the chat question is a temporary chat (nothing kept, nothing learned)",
          body.get("temporary") is True, body)
    check("and it is the one fixed question",
          body.get("messages") == [{"role": "user", "content": S.READY_QUESTION}], body)
    check("Ollama: three reads and one question",
          len(ollama.gets) == 3 and len(ollama.posts) == 1, (ollama.gets, ollama.posts))
    url, sent = ollama.posts[0]
    opts = sent.get("options") or {}
    check("the question sends no size (nothing reloads) and no unload",
          "num_ctx" not in opts and "keep_alive" not in sent, sent)
    check("and offers the model no tools", "tools" not in sent, sent)


def t_jarvis_down():
    fake = FakeJarvis()
    fake.down = True
    live, _f, _o = _live(fake)
    p, f, w, s, rows, text = _run(live)
    first = _rows(rows, "backend")
    check("Jarvis down: the first check FAILs and says how to start it",
          first and first[0][0] == S.FAIL and "not answering" in first[0][1]
          and "desktop app" in first[0][2], first)
    check("the checks that need it are skipped, not failed",
          all(st == S.SKIP for st, *_ in _rows(rows, "events") + _rows(rows, "scheduler")))


def t_tokens():
    live, fake, _o = _live(tokens=[])
    _p, f, _w, _s, rows, _t = _run(live, only={"backend"})
    check("no token anywhere: FAIL", f == 1 and "no pairing token" in rows[0][2], rows)
    live, fake, _o = _live(tokens=[("HUD_TOKEN in this window", "some-other-stand-in"),
                                   ("Windows Credential Manager (the backend's own)", TOKEN)])
    _p, f, _w, _s, rows, text = _run(live, only={"backend"})
    check("a refused token, then the right one: PASS, naming where it came from",
          f == 0 and "Credential Manager" in rows[0][2], rows)
    check("neither token is printed", TOKEN not in text and "some-other-stand-in" not in text)
    live, fake, _o = _live(tokens=[("HUD_TOKEN in this window", "some-other-stand-in")])
    _p, f, _w, _s, rows, text = _run(live, only={"backend"})
    check("only a wrong token: FAIL, and it is not shown",
          f == 1 and "accepts none" in rows[0][2] and "some-other-stand-in" not in text, rows)
    fake = FakeJarvis()
    fake.no_token_ok = True
    live, _f, _o = _live(fake)
    _p, f, _w, _s, rows, _t = _run(live, only={"backend"})
    check("a request with NO token accepted: FAIL",
          any(st == S.FAIL and "NO TOKEN" in what for _k, st, what, _d in rows), rows)


def t_a_private_file_served_fails_loudly():
    path, markers = S._settings_marker(backend_folder())
    content = (Path(path).read_text(encoding="utf-8") if path
               else "[autonomy.tiers]\nweb_research = \"auto\"\n")
    fake = FakeJarvis()
    fake.routes[("GET", "/../jarvis-framework.toml")] = (200, content.encode("utf-8"))
    live, _f, _o = _live(fake)
    _p, f, _w, _s, rows, text = _run(live, only={"backend", "private_files"})
    row = _rows(rows, "private_files")
    check("the settings file served over HTTP: FAIL", row and row[0][0] == S.FAIL, row)
    check("loudly, naming the address", "SERVES A PRIVATE FILE" in row[0][1]
          and "/../jarvis-framework.toml" in row[0][1], row)
    # The HUD page answers any path it knows with HTML: not a leak.
    fake = FakeJarvis()
    html = b"<!doctype html><html><body>jarvis hud, def not python</body></html>"
    for probe in S.PRIVATE_PROBES:
        fake.routes[("GET", probe)] = (200, html)
    live, _f, _o = _live(fake)
    _p, f, _w, _s, rows, _t = _run(live, only={"backend", "private_files"})
    check("a web page at those addresses is not called a leak", f == 0, rows)
    fake = FakeJarvis()
    fake.routes[("GET", "/token")] = (200, TOKEN.encode("utf-8"))
    live, _f, _o = _live(fake)
    _p, f, _w, _s, rows, text = _run(live, only={"backend", "private_files"})
    check("the token itself served: FAIL, without printing it",
          f == 1 and TOKEN not in text, rows)


def _backend_copy() -> Path:
    d = Path(tempfile.mkdtemp(prefix="jarvis-preflight-backend-copy-"))
    for p in backend_folder().iterdir():
        if p.is_file():
            shutil.copy2(p, d / p.name)
    return d


def _unique_adds(patch: str, target: str) -> list:
    """The lines `patch` adds to `target` that no other patch adds."""
    mine, others = set(), set()
    for name in _stack.order():
        text = (HERE / name).read_text(encoding="utf-8")
        for h, _p in _stack.hunks(text, target):
            adds = {l[1:].strip() for l in h.splitlines()
                    if l.startswith("+") and not l.startswith("+++") and len(l[1:].strip()) >= 12}
            (mine if name == patch else others).update(adds)
    return sorted(mine - others)


def _without(d: Path, target: str, lines) -> None:
    drop = set(lines)
    text = (d / target).read_text(encoding="utf-8").splitlines()
    (d / target).write_text("\n".join(l for l in text if l.strip() not in drop),
                            encoding="utf-8")


def t_patches():
    check("every patch in the stack is 'applied' in the full stand-in",
          all(s in ("applied", "nothing to look for")
              for _n, _f, s, _p, _t in S.patch_states(backend_folder())),
          [x for x in S.patch_states(backend_folder()) if x[2] not in ("applied",
                                                                     "nothing to look for")])
    d = _backend_copy()
    _without(d, "jarvis_hud.py", _unique_adds("stop-all.patch", "jarvis_hud.py"))
    states = {(n, f): s for n, f, s, _p, _t in S.patch_states(d)}
    check("a patch taken out of the file: 'not applied' (a line it shares with "
          "another patch proves nothing)",
          states.get(("stop-all.patch", "jarvis_hud.py")) == "not applied",
          states.get(("stop-all.patch", "jarvis_hud.py")))
    check("and the others still 'applied'",
          states.get(("owner-check.patch", "jarvis_hud.py")) == "applied")
    live, _f, _o = _live(backend=d)
    _p, f, _w, _s, rows, _t = _run(live, only={"patches"})
    check("the patches check FAILs, naming it and the fix",
          any(st == S.FAIL and "stop-all.patch" in what and "apply-patches.ps1" in d_
              for _k, st, what, d_ in rows), rows)
    # Half of one: partly.
    d2 = _backend_copy()
    lines = _unique_adds("owner-check.patch", "jarvis_gate.py")
    _without(d2, "jarvis_gate.py", lines[: len(lines) // 2])
    st = {(n, f): (s, p, t) for n, f, s, p, t in S.patch_states(d2)}
    got = st.get(("owner-check.patch", "jarvis_gate.py"))
    check("a patch half there: 'partly', with the count",
          got and got[0] == "partly" and 0 < got[1] < got[2], got)
    live, _f, _o = _live(backend=d2)
    _p, f, _w, _s, rows, _t = _run(live, only={"patches"})
    check("and the check says 'only part of', an older version or a hand edit",
          any(st == S.FAIL and "only part of owner-check.patch" in what and "older" in d_
              for _k, st, what, d_ in rows), rows)


def t_modules():
    d = _backend_copy()
    (d / "jarvis_stop_all.py").write_text("# an older copy\n", encoding="utf-8")
    (d / "jarvis_reach.py").unlink()
    live, _f, _o = _live(backend=d)
    _p, f, _w, _s, rows, _t = _run(live, only={"backend", "handshake", "modules"})
    mod = _rows(rows, "modules")
    check("a module that differs: FAIL with both short hashes",
          any(st == S.FAIL and "jarvis_stop_all.py" in what and "there," in what
              for st, what, _d in mod), mod)
    check("a module that is missing: FAIL",
          any(st == S.FAIL and "jarvis_reach.py is not in" in what for st, what, _d in mod), mod)
    fake = FakeJarvis()
    fake.routes[("GET", "/api/version")] = (200, {"api": 1, "started": time.time() - 3600,
                                                  "capabilities": {"stop_all": True}})
    d3 = _backend_copy()
    now = time.time()
    for f3 in d3.iterdir():   # copy2 keeps the checkout's dates; make them "just edited"
        os.utime(f3, (now, now))
    live, _f, _o = _live(fake, backend=d3)
    _p, f, _w, _s, rows, _t = _run(live, only={"backend", "handshake", "modules"})
    mod = _rows(rows, "modules")
    check("files newer than the running Jarvis: WARN, restart it",
          any(st == S.WARN and "changed after Jarvis started" in what and "Restart" in d_
              for st, what, d_ in mod), mod)


def t_owner_check_and_stop_all():
    fake = FakeJarvis()
    fake.routes[("GET", "/api/version")] = (200, {"api": 1, "started": time.time() + 3600,
                                                  "capabilities": {"owner_check": False}})
    live, _f, _o = _live(fake)
    _p, f, _w, _s, rows, _t = _run(live, only={"backend", "handshake", "gate", "stop_all"})
    gate = _rows(rows, "gate")
    check("owner-check in the files but not switched on: FAIL",
          any(st == S.FAIL and "did not switch it on" in what for st, what, _d in gate), gate)
    stop = _rows(rows, "stop_all")
    check("Stop everything not reaching Jarvis: a WARN, not a FAIL",
          stop and stop[0][0] == S.WARN, stop)
    logs = Path(tempfile.mkdtemp(prefix="jarvis-preflight-logs-"))
    (logs / "backend.log").write_text(
        "  approvals  risky ones from this PC ask Windows Hello\n"
        "  approvals  NOT CHECKED (ModuleNotFoundError) - every approval is refused\n",
        encoding="utf-8")
    live, _f, _o = _live(log_dir=logs)
    _p, f, _w, _s, rows, _t = _run(live, only={"backend", "handshake", "gate"})
    gate = _rows(rows, "gate")
    check("the newest start-up line says NOT CHECKED: FAIL",
          any(st == S.FAIL and "NOT CHECKED" in what for st, what, _d in gate), gate)
    sys.modules["jarvis_gate"] = _FakeGate(allowed=True)
    rows = S.pf_gate(live)
    check("a 'never' action allowed: FAIL", rows[0][0] == S.FAIL, rows)


def t_scheduler_events_voice():
    fake = FakeJarvis()
    fake.routes[("GET", "/api/schedule")] = (200, {"available": True, "running": False})
    fake.routes[("GET", "/api/voice/status")] = (200, {"stt": {"available": False,
                                                              "status": "not installed"},
                                                      "tts": {"available": True}})
    fake.events = ": keepalive\n"
    live, _f, _o = _live(fake)
    _p, f, w, _s, rows, _t = _run(live, only={"backend", "scheduler", "events", "voice"})
    check("the scheduler's loop stopped: FAIL",
          _rows(rows, "scheduler")[0][0] == S.FAIL, _rows(rows, "scheduler"))
    check("an event stream with no hello: FAIL", _rows(rows, "events")[0][0] == S.FAIL)
    voice = _rows(rows, "voice")
    check("voice not installed: a WARN, never a FAIL",
          any(st == S.WARN for st, *_ in voice) and not any(st == S.FAIL for st, *_ in voice),
          voice)


def t_folders_and_instant_email():
    fake = FakeJarvis()
    live, _f, _o = _live(fake)
    _p, f, _w, _s, rows, _t = _run(live, only={"backend", "folders", "instant_email"})
    check("no documents.patch: a WARN saying how, never a FAIL",
          _rows(rows, "folders")[0][0] == S.WARN and f == 0, _rows(rows, "folders"))
    check("no email watch: the instant check is skipped", _rows(rows, "instant_email")[0][0]
          == S.SKIP)
    fake.routes[("GET", "/api/folders")] = (200, {"available": True, "folders": [
        {"path": "C:\\Docs", "exists": True}, {"path": "C:\\Gone", "exists": False}],
        "documents": {"ready": False}})
    job = {"kind": "tellme", "watches": "email", "state": "active",
           "note": "Until Friday. Instant watch not connected (the connection dropped "
                   "(ConnectionError)) - looking every few minutes instead."}
    fake.routes[("GET", "/api/schedule")] = (200, {"available": True, "running": True,
                                                   "jobs": [job]})
    live, _f, _o = _live(fake)
    _p, f, _w, _s, rows, _t = _run(live, only={"backend", "folders", "instant_email"})
    folders = _rows(rows, "folders")
    check("two folders listed, one gone from the PC, MarkItDown missing: PASS, WARN, WARN",
          [st for st, *_ in folders] == [S.PASS, S.WARN, S.WARN]
          and "MarkItDown is not installed" in folders[2][1], folders)
    inst = _rows(rows, "instant_email")
    check("an email watch whose connection is down: a WARN with its own line",
          inst[0][0] == S.WARN and "connection dropped" in inst[0][2], inst)
    job["note"] = "Until Friday. Instant: your mail server tells Jarvis the moment mail arrives."
    live, _f, _o = _live(fake)
    _p, f, _w, _s, rows, _t = _run(live, only={"backend", "instant_email"})
    check("connected: PASS", _rows(rows, "instant_email")[0][0] == S.PASS)


def t_chat_waits_for_tools():
    fake = FakeJarvis()
    fake.routes[("GET", "/api/reach")] = (200, {"rows": [], "tools": [
        {"id": "email_check", "name": "Email"}]})
    live, _f, _o = _live(fake)
    _p, f, _w, _s, rows, _t = _run(live, only={"backend", "handshake", "chat"})
    chat = _rows(rows, "chat")
    check("tools on: the chat question is skipped, saying why and how",
          chat[0][0] == S.SKIP and "--with-chat" in chat[0][2], chat)
    check("and nothing was sent to the chat", "/api/chat" not in fake.posts())
    live, _f, _o = _live(fake, with_chat=True)
    _run(live, only={"backend", "handshake", "chat"})
    check("--with-chat: it is sent", "/api/chat" in fake.posts())
    fake = FakeJarvis()
    fake.routes[("POST", "/api/chat")] = (200, {"choices": [{"message": {"content": "ready"}}]},
                                          {"x-jarvis-route": json.dumps({"where": "cloud"})})
    live, _f, _o = _live(fake)
    _p, f, w, _s, rows, _t = _run(live, only={"backend", "handshake", "chat"})
    check("answered by the cloud lane: WARN", _rows(rows, "chat")[0][0] == S.WARN)
    fake = FakeJarvis()
    fake.routes[("GET", "/api/version")] = (200, {"api": 1, "capabilities": {}})
    live, _f, _o = _live(fake)
    _run(live, only={"backend", "handshake", "chat"})
    check("no temporary chat on this PC: not sent (it would be kept and learned from)",
          "/api/chat" not in fake.posts())


def t_reads_and_search():
    called = []
    reads = {"calendar": lambda: called.append("calendar") or {"ok": True, "events": [1, 2]},
             "email": lambda: called.append("email") or {"ok": True, "count": 3}}
    live, fake, _o = _live(reads=reads)
    _p, f, _w, _s, rows, _t = _run(live, only={"backend", "handshake", "chat", "reach"})
    reach = _rows(rows, "reach")
    check("calendar set up: said, not read", any(st == S.PASS and "not read" in what
                                                  for st, what, _d in reach) and not called, reach)
    check("email not set up: skipped", any(st == S.SKIP and "Email reading" in what
                                           for st, what, _d in reach), reach)
    check("web search off: nothing searched", "/api/search/test" not in fake.posts())
    live, fake, _o = _live(reads=reads, with_reads=True)
    _p, f, _w, _s, rows, _t = _run(live, only={"backend", "handshake", "chat", "reach"})
    check("--with-reads: the calendar is read once, as a number",
          called == ["calendar"] and any("2 event(s)" in what for _k, _st, what, _d in rows), rows)
    fake = FakeJarvis()
    fake.routes[("GET", "/api/reach")] = (200, {"rows": [], "tools": [
        {"id": "web_search", "name": "Web search"}]})
    live, _f, _o = _live(fake, with_chat=False)
    _p, f, _w, _s, rows, _t = _run(live, only={"backend", "reach"})
    check("web search on with a provider: ONE Test search",
          fake.posts().count("/api/search/test") == 1, fake.posts())
    fake.routes[("GET", "/api/search")] = (200, {"available": True, "provider": None,
                                                 "why": "settings damaged"})
    before = fake.posts().count("/api/search/test")
    live, _f, _o = _live(fake)
    _run(live, only={"backend", "reach"})
    check("no provider chosen: nothing searched",
          fake.posts().count("/api/search/test") == before)


def t_home_assistant_token_and_weather():
    """I81 (2026-09-26): a WARN when Jarvis's Home Assistant token is an
    administrator's; the weather read once only with --with-reads."""
    weather = []
    home = {"check": lambda: {"state": "admin", "why": "the token belongs to an administrator"},
            "weather": lambda: weather.append(1) or {"ok": True, "days": [1, 2, 3],
                                                     "entity_id": "weather.forecast_home"}}
    live, _f, _o = _live(home=home)
    _p, f, w, _s, rows, text = _run(live, only={"home"})
    got = _rows(rows, "home")
    check("an administrator's token: a WARN that says what to do, and points to the guide",
          got[0][0] == S.WARN and "administrator" in got[0][1] and S.HOME_USER_GUIDE in got[0][2]
          and f == 0, got)
    check("... and the weather is not read without --with-reads", not weather
          and any("--with-reads" in what for _st, what, _d in got))
    home["check"] = lambda: {"state": "user", "why": ""}
    live, _f, _o = _live(home=home, with_reads=True)
    _p, f, w, _s, rows, _t = _run(live, only={"home"})
    got = _rows(rows, "home")
    check("a plain user's token: PASS, no WARN", got[0][0] == S.PASS and w == 0, got)
    check("--with-reads: the weather once, as a number of days", weather == [1]
          and any("3 day(s)" in what for _st, what, _d in got), got)
    home["check"] = lambda: {"state": "refused", "why": ""}
    live, _f, _o = _live(home=home)
    _p, f, _w, _s, rows, _t = _run(live, only={"home"})
    check("a token Home Assistant refuses: FAIL", f == 1, _rows(rows, "home"))
    home["check"] = lambda: {"state": "not_set_up", "why": ""}
    live, _f, _o = _live(home=home)
    _p, f, _w, s, rows, _t = _run(live, only={"home"})
    check("no Home Assistant: skipped", s == 1 and f == 0)


def t_desktop_version_and_a_broken_check():
    logs = Path(tempfile.mkdtemp(prefix="jarvis-preflight-logs-"))
    (logs / "jarvis-desktop.log").write_text(
        "\n===== Jarvis Desktop 0.0.9 starting ===== (logs in x)\n", encoding="utf-8")
    live, _f, _o = _live(log_dir=logs)
    _p, f, _w, _s, rows, _t = _run(live, only={"backend", "handshake"})
    hs = _rows(rows, "handshake")
    check("an older desktop app: WARN, with how to update",
          any(st == S.WARN and "0.0.9" in what for st, what, _d in hs), hs)

    def broken(live):
        raise RuntimeError("a bug in a check")
    S.PREFLIGHT.append(("broken_for_test", "A check with a bug", broken))
    try:
        live, _f, _o = _live()
        _p, f, _w, _s, rows, _t = _run(live, only={"backend", "broken_for_test", "events"})
    finally:
        S.PREFLIGHT.pop()
    check("a check that raises is its own FAIL",
          any(k == "broken_for_test" and st == S.FAIL for k, st, *_ in rows), rows)
    check("and the checks after it still run", _rows(rows, "events")[0][0] == S.PASS)


def t_readme_line_is_one_line():
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    lines = [l for l in readme.splitlines() if "selftest.py --preflight" in l
             and l.startswith("$env:")]
    check("backend/README.md gives the owner a one-line command", len(lines) >= 1, lines)
    check("and it says where the output goes", any("preflight.txt" in l for l in lines), lines)


def main() -> int:
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            try:
                fn()
            except Exception as exc:
                import traceback
                traceback.print_exc()
                check(f"{name} raised {type(exc).__name__}: {exc}", False)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if _BACKEND is not None:
        shutil.rmtree(_BACKEND, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
