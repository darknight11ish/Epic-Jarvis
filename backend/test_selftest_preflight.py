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
    unload, plus one read of jarvis-primary's stored rules (POST /api/show,
    which reads and loads nothing);
  * jarvis-primary running an older copy of its rules (I134, 2026-09-27) is
    a WARN, with the `ollama create` line to fix it - never a FAIL, since the
    model still answers;
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
  * a check that raises is its own FAIL and the rest still run;
  * the phone-reach check (newcomer play test, 2026-09-27): no phone
    address is a WARN, a home-network one a FAIL, Tailscale/Meshnet off or
    moved a FAIL, Jarvis not listening there a FAIL with the fix that fits
    where the address came from, and a missing firewall rule a WARN with
    the exact one-line fix - every Windows call faked.
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

require_shipped("jarvis_token_store.py", "jarvis_agent.py")

import _stack  # noqa: E402
import jarvis_agent as AG  # noqa: E402
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
    def __init__(self, system=None):
        self.gets, self.posts = [], []
        # The rules /api/show reports for jarvis-primary; None means "today's",
        # so a normal run never warns (I134, 2026-09-27).
        self.system = system

    def fetch(self, url):
        self.gets.append(url)
        path = url[len(OLLAMA):]
        return {"/api/version": {"version": "0.12.0"},
                "/api/tags": {"models": [{"name": MODEL}]},
                "/api/ps": {"models": [{"name": MODEL, "size": 100, "size_vram": 100,
                                        "context_length": 16384}]}}[path]

    def post(self, url, body):
        self.posts.append((url, body))
        if url.endswith("/api/show"):
            return {"system": self.system if self.system is not None else AG.LANE_SYSTEM}
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
            "reach", "home", "sleep", "phone", "data_health", "credentials", "screen",
            "engine_config"]
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
    check("Ollama: three reads, the one question, and the rules read (I134)",
          len(ollama.gets) == 3 and len(ollama.posts) == 2, (ollama.gets, ollama.posts))
    kinds = {url.rsplit("/", 1)[-1] for url, _sent in ollama.posts}
    check("the two POSTs are /api/chat and /api/show, nothing else",
          kinds == {"chat", "show"}, ollama.posts)
    chat_sent = next(sent for url, sent in ollama.posts if url.endswith("/api/chat"))
    opts = chat_sent.get("options") or {}
    check("the question sends no size (nothing reloads) and no unload",
          "num_ctx" not in opts and "keep_alive" not in chat_sent, chat_sent)
    check("and offers the model no tools", "tools" not in chat_sent, chat_sent)
    show_sent = next(sent for url, sent in ollama.posts if url.endswith("/api/show"))
    check("the rules read asks only for the model's name - nothing generated, nothing unloaded",
          show_sent == {"model": MODEL}, show_sent)


def t_model_rules_freshness():
    """I134 (2026-09-27): jarvis-primary running an older copy of its rules
    is a WARN with the ollama create fix line, not a FAIL - the model still
    answered. A model already running today's rules never warns for this."""
    # only={"model"} skips "backend"/"handshake", which is where live.status
    # would normally be filled in from a real /api/status - so it is given
    # directly, the same shape pf_model reads it in.
    live, fake, ollama = _live(FakeJarvis(), FakeOllama(system="You are Jarvis (an old draft)."))
    live.status = {"lane": "local", "model": MODEL}
    _, _, _, _, rows, _ = _run(live, only={"model"})
    model_rows = _rows(rows, "model")
    check("a stale rules block: WARN with the fix line",
          any(st == S.WARN and "older copy of Jarvis's rules" in what
              and "ollama create jarvis-primary" in d for st, what, d in model_rows), model_rows)
    check("never a FAIL for this on its own", not any(st == S.FAIL for st, _w, _d in model_rows))

    live, fake, ollama = _live(FakeJarvis(), FakeOllama(system=AG.LANE_SYSTEM))
    live.status = {"lane": "local", "model": MODEL}
    _, _, _, _, rows, _ = _run(live, only={"model"})
    check("today's rules, word for word: no warning about them",
          not any("older copy of Jarvis's rules" in what for _st, what, _d in _rows(rows, "model")))

    live, fake, ollama = _live(FakeJarvis(), FakeOllama())
    live.status = {"lane": "local", "model": MODEL}
    check("FakeOllama's own default is today's rules (so every other test stays quiet)",
          ollama.system is None)
    _, _, _, _, rows, _ = _run(live, only={"model"})
    check("... and it really is quiet",
          not any("older copy of Jarvis's rules" in what for _st, what, _d in _rows(rows, "model")))


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


def t_screen_says_not_built_yet():
    """"Look at this" and "Watch with me" (2026-09-28): build steps 1 and 2
    are the rules only, so the check says plainly that it is not built on
    this PC yet - a skip, never a PASS it has not earned, never a FAIL."""
    live, _fake, _ollama = _live()
    _p, f, _w, _s, rows, text = _run(live, only={"backend", "screen"})
    sc = _rows(rows, "screen")
    check("one screen row, a skip", len(sc) == 1 and sc[0][0] == S.SKIP, sc)
    check("... that says it is not built on this PC yet",
          sc and "not built on this PC yet" in sc[0][1], sc)
    check("... and that there is nothing to fix", sc and "Nothing to fix" in sc[0][2], sc)


def t_data_health():
    """data-health.patch and jarvis_data_health.py (feasibility I97): the
    check turns the route's own "ok"/"warn" rows into PASS/WARN, never
    FAIL - and without the route at all (no data-health.patch), it says so
    with a WARN, not a FAIL, exactly like pf_folders without documents.patch."""
    fake = FakeJarvis()
    live, _f, _o = _live(fake)
    _p, f, _w, _s, rows, _t = _run(live, only={"backend", "data_health"})
    dh = _rows(rows, "data_health")
    check("no data-health.patch: a WARN saying how, never a FAIL",
          dh[0][0] == S.WARN and "apply-patches.ps1" in dh[0][2] and f == 0, dh)
    fake.routes[("GET", "/api/data-health")] = (200, {"available": True, "warn": 1, "checks": [
        {"status": "ok", "what": "the chat history database opens and checks out", "detail": ""},
        {"status": "warn", "what": "the memory store database may be damaged",
         "detail": "DatabaseError: file is not a database"},
    ]})
    live, _f, _o = _live(fake)
    _p, f, _w, _s, rows, _t = _run(live, only={"backend", "data_health"})
    dh = _rows(rows, "data_health")
    check("an ok row: PASS, never FAIL", dh[0] == (S.PASS,
          "the chat history database opens and checks out", ""), dh)
    check("a warn row: WARN, never FAIL", dh[1][0] == S.WARN
          and "may be damaged" in dh[1][1], dh)
    check("still no FAIL anywhere in this check (WARN, never fix, never fail)", f == 0, dh)
    fake.routes[("GET", "/api/data-health")] = (404, {"error": "no such route"})
    live, _f, _o = _live(fake)
    _p, f, _w, _s, rows, _t = _run(live, only={"backend", "data_health"})
    check("a 404 (module not installed): WARN, not FAIL", _rows(rows, "data_health")[0][0]
          == S.WARN and f == 0)


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


def t_sleep_on_mains_power_is_a_warning():
    """Ease-of-use audit 2026-09-27 #8d: alarms ring on the PC, so a PC that
    sleeps on mains power is a WARN (never a FAIL - a laptop may want it)."""
    # powercfg's block, in two languages: only the numbers are read.
    english = ("Power Setting GUID: 29f6c1db-86da-48c5-9fdb-f2b67b1f44da  (Sleep after)\n"
               "  Minimum Possible Setting: 0x00000000\n"
               "  Maximum Possible Setting: 0xffffffff\n"
               "  Possible Settings increment: 0x00000001\n"
               "  Possible Settings units: Seconds\n"
               "Current AC Power Setting Index: 0x00000708\n"
               "Current DC Power Setting Index: 0x00000384\n")
    german = english.replace("Current AC Power Setting Index", "Aktueller Wechselstromindex") \
                    .replace("Current DC Power Setting Index", "Aktueller Gleichstromindex")
    check("30 minutes on mains power is read, in any language",
          S.sleep_after_on_mains(english) == 1800 and S.sleep_after_on_mains(german) == 1800)
    rows = S.pf_sleep(S.Live(power=lambda: english))
    check("... and is a WARN with the one line that keeps it awake",
          rows[0][0] == S.WARN and "30 minute" in rows[0][1]
          and "powercfg /change standby-timeout-ac 0" in rows[0][2], rows)
    never = english.replace("0x00000708", "0x00000000")
    check("never sleeping on mains power: PASS", S.pf_sleep(S.Live(power=lambda: never))[0][0] == S.PASS)
    check("not Windows: SKIP", S.pf_sleep(S.Live(power=lambda: None))[0][0] == S.SKIP)
    check("an answer it cannot read: WARN, never a FAIL",
          S.pf_sleep(S.Live(power=lambda: "nothing here"))[0][0] == S.WARN)


def t_a_hidden_llama_cpp_settings_file_is_a_warning():
    """The research audit, 2026-09-28 (section 6, item 3): Ollama's engine
    reads llama.cpp's config.ini from %PROGRAMDATA% and %APPDATA% - a hidden
    place for a setting to come from. WARN (never FAIL), with the names of
    the settings in it (never their values) and the one line that renames it."""
    d = Path(tempfile.mkdtemp(prefix="jarvis-llama-ini-"))
    try:
        pd, ad = d / "ProgramData", d / "AppData"
        pd.mkdir()
        ad.mkdir()
        env = {"PROGRAMDATA": str(pd), "APPDATA": str(ad)}
        rows = S.pf_engine_config(S.Live(env=env))
        check("no config.ini: PASS", rows[0][0] == S.PASS and len(rows) == 1, rows)
        (ad / "llama.cpp").mkdir()
        (ad / "llama.cpp" / "config.ini").write_text(
            "; mine\n[server]\nctx-size = 2048\ncache-ram=99999\nsecret-thing = hunter2\n",
            encoding="utf-8")
        rows = S.pf_engine_config(S.Live(env=env))
        check("an %APPDATA% config.ini: one WARN naming it", len(rows) == 1
              and rows[0][0] == S.WARN and "%APPDATA%\\llama.cpp\\config.ini" in rows[0][1],
              rows)
        check("... listing the settings' names, never their values",
              "ctx-size, cache-ram, secret-thing" in rows[0][2] and "hunter2" not in rows[0][2]
              and "2048" not in rows[0][2], rows[0][2])
        check("... with the one PowerShell line that renames it",
              "Rename-Item -Path" in rows[0][2] and "config.ini.off" in rows[0][2]
              and "\n" not in rows[0][2], rows[0][2])
        (pd / "llama.cpp").mkdir()
        (pd / "llama.cpp" / "config.ini").write_text("", encoding="utf-8")
        rows = S.pf_engine_config(S.Live(env=env))
        check("both places: a WARN for each, %PROGRAMDATA% first",
              [r[0] for r in rows] == [S.WARN, S.WARN] and "PROGRAMDATA" in rows[0][1], rows)
        check("not Windows: SKIP", S.pf_engine_config(S.Live(env={}))[0][0] == S.SKIP)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def t_a_folder_without_jarvis_hud_says_so_once():
    """Ease-of-use audit 2026-09-27 #8b: the wrong folder is ONE message
    with the line to run, not a FAIL per check."""
    empty = Path(tempfile.mkdtemp(prefix="jarvis-not-backend-"))
    try:
        said = S.wrong_folder(empty, "--preflight")
        check("a folder without jarvis_hud.py: one message, with the one line to run",
              "jarvis_hud.py is not in" in said and "Nothing was checked" in said
              and "$env:JARVIS_BACKEND" in said and "selftest.py --preflight" in said
              and "py -3" in said and "python " not in said, said)
        (empty / "jarvis_hud.py").write_text("# stand-in", encoding="utf-8")
        check("... and nothing to say once it is there", S.wrong_folder(empty) == "")
        keep = S.BACKEND
        S.BACKEND = empty / "nowhere"
        try:
            import contextlib
            import io
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = S.preflight_main(["--preflight"])
            out = buf.getvalue()
        finally:
            S.BACKEND = keep
        check("preflight stops before any check, with exit code 2",
              code == 2 and "FAIL" not in out and "pass," not in out, (code, out))
    finally:
        shutil.rmtree(empty, ignore_errors=True)


def t_readme_line_is_one_line():
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    lines = [l for l in readme.splitlines() if "selftest.py --preflight" in l
             and l.startswith("$env:")]
    check("backend/README.md gives the owner a one-line command", len(lines) >= 1, lines)
    check("and it says where the output goes", any("preflight.txt" in l for l in lines), lines)


# ------------------------------------------------------- the phone check --

def _phone_live(*, up=True, desktop=None, env=None, owns=True, listed=("100.101.1.2",),
                connects=True, firewall=("Jarvis backend (private mesh only)",), backend=None):
    calls = {"connects": [], "firewall": []}

    def connect(addr, port):
        calls["connects"].append((addr, port))
        return connects

    def fw(port):
        calls["firewall"].append(port)
        return None if firewall is None else list(firewall)

    live = S.Live(env=dict(env or {}), backend=backend or tempfile.mkdtemp(prefix="jarvis-pf-"),
                  phone={"desktop": lambda: desktop,
                         "addresses": lambda: None if listed is None else list(listed),
                         "owns": lambda addr: owns,
                         "connects": connect,
                         "firewall": fw})
    live.up = up
    return live, calls


def _statuses(rows):
    return [r[0] for r in rows]


def t_phone_no_address_is_a_warning_with_the_address_to_type():
    live, calls = _phone_live(desktop=None)
    rows = S.pf_phone(live)
    check("no phone address: one WARN, nothing else asked",
          _statuses(rows) == [S.WARN] and not calls["connects"] and not calls["firewall"], rows)
    check("and the fix names the box and this PC's own mesh address",
          "Let my phone reach this" in rows[0][2] and "100.101.1.2" in rows[0][2], rows)
    # This PC only (the default) is no phone address either.
    live, _c = _phone_live(desktop={"bind_address": "127.0.0.1"}, env={"JARVIS_HUD_BIND": "127.0.0.1"})
    check("127.0.0.1 counts as no phone address", _statuses(S.pf_phone(live)) == [S.WARN])


def t_phone_home_network_address_fails():
    live, calls = _phone_live(desktop={"bind_address": "192.168.1.20", "supervise": True})
    rows = S.pf_phone(live)
    check("a home-network address is a FAIL", _statuses(rows) == [S.FAIL], rows)
    check("and it says which box it came from and what to type",
          "Let my phone reach this" in rows[0][2] and "100.101.1.2" in rows[0][2], rows)
    check("nothing was connected to", not calls["connects"])


def t_phone_all_good():
    live, calls = _phone_live(desktop={"bind_address": "100.101.1.2", "supervise": True})
    rows = S.pf_phone(live)
    check("address set, mesh on, Jarvis listening, firewall rule: all PASS",
          _statuses(rows) == [S.PASS] * 4, rows)
    check("it connected to the mesh address on Jarvis's port, once",
          calls["connects"] == [("100.101.1.2", S.DEFAULT_PORT)], calls)
    check("the firewall was asked about Jarvis's port", calls["firewall"] == [S.DEFAULT_PORT])


def t_phone_mesh_off_or_moved():
    live, calls = _phone_live(desktop={"bind_address": "100.101.1.2"}, owns=False, listed=[])
    rows = S.pf_phone(live)
    check("Tailscale/Meshnet off on the PC: FAIL, listening skipped, firewall still read",
          _statuses(rows) == [S.PASS, S.FAIL, S.SKIP, S.PASS] and not calls["connects"], rows)
    check("and the fix says to switch it on", "switch it on" in rows[1][2], rows)
    live, _c = _phone_live(desktop={"bind_address": "100.101.1.2"}, owns=False,
                           listed=["192.168.1.20", "100.90.0.7"])
    rows = S.pf_phone(live)
    check("the mesh address moved: FAIL naming the new one",
          rows[1][0] == S.FAIL and "100.90.0.7" in rows[1][1] and "100.90.0.7" in rows[1][2], rows)


def t_phone_not_listening_gives_the_fix_that_fits():
    live, _c = _phone_live(desktop={"bind_address": "100.101.1.2", "supervise": False},
                           connects=False)
    rows = S.pf_phone(live)
    check("not listening, desktop not starting Jarvis: FAIL naming the switch",
          rows[2][0] == S.FAIL and "Let Jarvis Desktop start and stop Jarvis" in rows[2][2], rows)
    live, _c = _phone_live(desktop={"bind_address": "100.101.1.2", "supervise": True},
                           connects=False)
    rows = S.pf_phone(live)
    check("not listening, desktop starts Jarvis: restart it there",
          rows[2][0] == S.FAIL and "Stop, then Start" in rows[2][2], rows)
    live, _c = _phone_live(env={"JARVIS_HUD_BIND": "100.101.1.2"}, connects=False)
    rows = S.pf_phone(live)
    check("an address from JARVIS_HUD_BIND is found, and the fix is a restart",
          "JARVIS_HUD_BIND" in rows[0][1] and rows[2][0] == S.FAIL
          and rows[2][2] == "Restart Jarvis so it reads the address.", rows)
    live, calls = _phone_live(desktop={"bind_address": "100.101.1.2"}, up=False)
    rows = S.pf_phone(live)
    check("Jarvis down: listening is skipped, not failed",
          rows[2][0] == S.SKIP and not calls["connects"], rows)


def t_phone_firewall():
    live, _c = _phone_live(desktop={"bind_address": "100.101.1.2", "supervise": True},
                           firewall=[])
    rows = S.pf_phone(live)
    line = S.FIREWALL_LINE.replace("PORT", str(S.DEFAULT_PORT))
    check("no firewall rule: WARN (a rule for Python may still let it in)",
          rows[-1][0] == S.WARN, rows)
    check("with the exact one-line fix from INSTALL.md, run as administrator",
          line in rows[-1][2] and "administrator" in rows[-1][2] and "\n" not in rows[-1][2], rows)
    install = (HERE.parent / "docs" / "INSTALL.md").read_text(encoding="utf-8")
    check("that line is the one INSTALL.md gives", line in install)
    live, _c = _phone_live(desktop={"bind_address": "100.101.1.2", "supervise": True},
                           firewall=None)
    check("rules that cannot be read: WARN", S.pf_phone(live)[-1][0] == S.WARN)
    if os.name != "nt":
        live, _c = _phone_live(desktop={"bind_address": "100.101.1.2", "supervise": True})
        live.phone.pop("firewall")
        check("not Windows: the firewall row is a skip", S.pf_phone(live)[-1][0] == S.SKIP)


def t_phone_address_sources():
    appdata = Path(tempfile.mkdtemp(prefix="jarvis-appdata-"))
    try:
        store = appdata / S.DESKTOP_ID / S.DESKTOP_STORE
        store.parent.mkdir(parents=True)
        store.write_text(json.dumps({"bind_address": " 100.64.0.9 ", "supervise": True}),
                         encoding="utf-8")
        desktop = S._desktop_settings({"APPDATA": str(appdata)})
        check("Jarvis Desktop's own settings file is read from %APPDATA%",
              S.phone_address(desktop, {}, appdata) == ("100.64.0.9", "desktop", True), desktop)
        check("no APPDATA: no desktop settings", S._desktop_settings({}) is None)
        backend = appdata / "backend"
        backend.mkdir()
        (backend / "jarvis-framework.toml").write_text(
            '[security]\nbind_address = "100.70.1.1"\n', encoding="utf-8")
        got = S.phone_address(None, {}, backend)
        check("[security] bind_address in the settings file counts (Python 3.11+)",
              got[:2] == ("100.70.1.1", "config") or sys.version_info < (3, 11), got)
        check("the desktop box comes first",
              S.phone_address({"bind_address": "100.64.0.9"}, {"JARVIS_HUD_BIND": "100.70.2.2"},
                              backend)[1] == "desktop")
    finally:
        shutil.rmtree(appdata, ignore_errors=True)
    check("mesh addresses are 100.64.0.0/10 only",
          S.mesh_address("100.64.0.1") and S.mesh_address("100.127.255.255")
          and not S.mesh_address("100.128.0.1") and not S.mesh_address("100.63.0.1")
          and not S.mesh_address("192.168.1.2") and not S.mesh_address("100.64.0")
          and not S.mesh_address("100.64.0.256") and not S.mesh_address("my-pc.nord"))


def t_phone_powershell_is_windows_only():
    if os.name != "nt":
        check("no PowerShell call off Windows", S._powershell("Get-Date") is None)
    check("the firewall query and address query are one line each",
          "\n" not in S.FIREWALL_QUERY and "\n" not in S.ADDRESS_QUERY)


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
