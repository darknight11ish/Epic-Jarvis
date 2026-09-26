"""Obsidian as a note target and as a searchable folder - with the owner's rules.

    python3 test_obsidian_notes.py            # check
    python3 test_obsidian_notes.py --write    # regenerate the shared fixture

No Obsidian, no network, no real gate: a temp folder with a `.obsidian`
folder in it is the vault, and a fake gate answers. What is pinned, in plain
words:

1. #obs FILES TO TODAY'S DAILY NOTE, where Obsidian's own settings say it is
   (`.obsidian/daily-notes.json`: folder, and a date format it can write out
   exactly), and refuses - saying why - for any format it cannot.
2. IT ONLY EVER ADDS. Earlier text byte for byte intact; the file is made
   only if missing; a link or a `..` that would lead out of the vault is
   refused; a vault is never created.
3. THE CARD says the exact file and text, and that nothing leaves this PC.
4. THE VAULT SEARCH reads the folder - title and text, ignoring case - and
   never `.obsidian/`, `.trash/`, or a link out of the vault, within its caps.
5. RULE 1: what the search finds goes to the LOCAL model only. The real
   search output is put through jarvis_agent's real tool loop and through
   cloud-one-turn.patch's own lines: it reaches Ollama's local address and
   nothing else, and a cloud lane's request never carries it.
6. WHICH TARGETS ARE SET UP: names only, never a path or token. The answer
   the clients read (GET /api/notes/capture with no id) is written from the
   real functions to one fixture the desktop's and the phone's tests decode.
"""
import datetime as dt
import json
import os
import socket
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_note_capture.py", "jarvis_notes.py", "jarvis_agent.py")
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-obsidian-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
CONFIG = {}
fw.load_framework = lambda: CONFIG
AUDIT = []
fw.audit_log = lambda e, d: AUDIT.append((e, json.dumps(d)))
sys.modules["jarvis_framework"] = fw

import jarvis_note_capture as NC  # noqa: E402
import jarvis_notes as N  # noqa: E402

FIXTURE = (REPO / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
           / "note-targets.json")
FAILED, PASSED = [], []
DAY = dt.datetime(2026, 9, 24, 9, 30)
SECRET = "the lighthouse key is under the blue stone"
TOKEN = "j0pl1n-t0ken-9f3"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class NoNetwork:
    """Nothing in this file may open a socket."""
    def __enter__(self):
        self.real = socket.socket.connect
        def boom(*a, **k):
            raise AssertionError("a socket was opened")
        socket.socket.connect = boom
        return self

    def __exit__(self, *a):
        socket.socket.connect = self.real
        return False


class Verdict:
    def __init__(self, allowed, outcome, reason=""):
        self.allowed, self.outcome, self.reason = allowed, outcome, reason


def clear_env():
    for k in (N.OBSIDIAN_VAULT_ENV, N.BACKEND_ENV, N.JOPLIN_TOKEN_ENV, N.OBSIDIAN_KEY_ENV,
              NC.LOGSEQ_GRAPH_ENV, NC.JOPLIN_URL_ENV, "JOPLIN_TOKEN", "MY_JOPLIN"):
        os.environ.pop(k, None)
    CONFIG.clear()


def vault(settings=None, name=None) -> Path:
    """A fresh vault, set as THE vault. `settings` becomes daily-notes.json."""
    clear_env()
    v = _TMP / (name or f"vault{time.time_ns()}")
    (v / ".obsidian").mkdir(parents=True)
    if settings is not None:
        (v / ".obsidian" / "daily-notes.json").write_text(
            settings if isinstance(settings, str) else json.dumps(settings), encoding="utf-8")
    os.environ[N.OBSIDIAN_VAULT_ENV] = str(v)
    return v


# ---- 1. where today's daily note is -----------------------------------------

def t_default_settings_file_in_the_vault_root():
    v = vault()
    with NoNetwork():
        p = NC.plan("obs", "call the plumber", now=DAY)
        card = NC.describe(p)
    real = Path(os.path.realpath(v))
    check("#obs maps to Obsidian; no daily-notes.json means YYYY-MM-DD in the vault's top folder",
          p.target == "obsidian" and p.file == str(real / "2026-09-24.md") and not p.reason_empty,
          repr(p))
    check("the card shows the exact text", "\ncall the plumber\n" in card, card)
    check("the card shows the exact file", str(real / "2026-09-24.md") in card, card)
    check("the card says nothing leaves this PC", "Nothing leaves this PC" in card)
    check("the card says a new file gets no template",
          "not there yet" in card and "template" in card and "is not applied" in card, card)
    check("the card says what refusing costs", "If you say no: nothing is written" in card)
    check("the gate action is append_obsidian_daily", NC.ACTIONS["obsidian"] == "append_obsidian_daily")


def t_settings_are_followed():
    cases = [
        ({"folder": "Daily", "format": "YYYY-MM-DD"}, "Daily/2026-09-24.md"),
        ({"folder": "", "format": ""}, "2026-09-24.md"),               # "" = the default
        ({"format": ""}, "2026-09-24.md"),
        ({"folder": "/Journal/", "format": "YYYY/MM/YYYY-MM-DD"}, "Journal/2026/09/2026-09-24.md"),
        ({"folder": "Calendar/Daily notes", "format": "YYYY/YYYY-MM-DD"},
         "Calendar/Daily notes/2026/2026-09-24.md"),                    # a real vault's file
        ({"format": "YYYY/[Daily]/MM/YYYY-MM-DD"}, "2026/Daily/09/2026-09-24.md"),  # another
        ({"format": "D-M-YY"}, "24-9-26.md"),
        ({"format": "YYYY-MM-DD-"}, "2026-09-24-.md"),
        ({"format": "YYYY-MM-DD[.md]"}, "2026-09-24.md"),               # .md not doubled
        ({"folder": "  Notes ", "autorun": False, "template": "T"}, "Notes/2026-09-24.md"),
    ]
    for settings, want in cases:
        v = vault(settings)
        p = NC.plan("obsidian", "x", now=DAY)
        got = os.path.relpath(p.file, os.path.realpath(v)).replace(os.sep, "/") if p.file else ""
        check(f"{json.dumps(settings)} -> {want}", got == want and not p.reason_empty,
              repr((got, p.reason_empty)))


def t_formats_it_cannot_write_out_are_refused_with_the_reason():
    for fmt, part in (("YYYY-MMM-DD", "MMM"), ("dddd", "dddd"), ("Do MMMM", "Do"),
                      ("YYYY-[W]ww", "ww"), ("YYYY:MM:DD", ":"), ("[a/b]YYYY", "[a/b]"),
                      ("YYYY-MM-DD [unclosed", "no \"]\""),
                      # moment reads the "m" of ".md" as minutes, the "d" as a weekday
                      ("YYYY-MM-DD.md", '"m"')):
        vault({"format": fmt})
        p = NC.plan("obsidian", "x", now=DAY)
        check(f"format {fmt!r}: refused, naming {part!r}, no file guessed",
              p.reason_empty and part in p.reason_empty and not p.file, repr(p.reason_empty))
    vault({"format": "YYYY-MMM-DD"})
    code, out = NC.capture("obsidian", "x", gate_check=lambda *a: Verdict(True, "approved"))
    check("and a capture with that format says why, in plain words",
          code == 503 and "MMM" in out["message"] and out["state"] == "not_filed", repr(out))


def t_broken_or_foreign_settings_are_refused():
    vault("{not json")
    check("an unreadable daily-notes.json is refused, not guessed around",
          "could not be read" in NC.plan("obsidian", "x", now=DAY).reason_empty)
    vault('["a"]')
    check("a daily-notes.json of the wrong shape is refused",
          "expected shape" in NC.plan("obsidian", "x", now=DAY).reason_empty)
    vault({"folder": "../outside"})
    check("a folder setting with .. is refused",
          '".."' in NC.plan("obsidian", "x", now=DAY).reason_empty)
    v = vault({"format": "YYYY-MM-DD"})
    (v / ".obsidian" / "community-plugins.json").write_text('["dataview", "periodic-notes"]')
    check("Periodic Notes turned on: refused (it may name the note instead)",
          "Periodic Notes" in NC.plan("obsidian", "x", now=DAY).reason_empty)
    pn = v / ".obsidian" / "plugins" / "periodic-notes"
    pn.mkdir(parents=True)
    (pn / "data.json").write_text('{"daily": {"enabled": false}}')
    check("but not when its own settings say its daily notes are off",
          not NC.plan("obsidian", "x", now=DAY).reason_empty)


def t_no_vault_no_write_and_never_created():
    clear_env()
    p = NC.plan("obsidian", "x", now=DAY)
    check("no vault set: refused, saying where to set it",
          "vault_directory" in p.reason_empty and N.OBSIDIAN_VAULT_ENV in p.reason_empty)
    missing = _TMP / f"nope{time.time_ns()}"
    os.environ[N.OBSIDIAN_VAULT_ENV] = str(missing)
    p = NC.plan("obsidian", "x", now=DAY)
    check("a vault folder that does not exist: refused", "there is no folder" in p.reason_empty)
    check("and run() does not create it",
          NC.run(p, approved=True)["ok"] is False and not missing.exists())
    plain = _TMP / f"plain{time.time_ns()}"
    plain.mkdir()
    os.environ[N.OBSIDIAN_VAULT_ENV] = str(plain)
    check("a folder with no .obsidian inside is not a vault",
          ".obsidian" in NC.plan("obsidian", "x", now=DAY).reason_empty)
    check("and nothing was made in it", list(plain.iterdir()) == [])
    clear_env()
    v = _TMP / f"cfgvault{time.time_ns()}"
    (v / ".obsidian").mkdir(parents=True)
    CONFIG["notes"] = {"obsidian": {"vault_directory": str(v)}}
    check("[notes.obsidian] vault_directory in the config is read",
          NC.plan("obsidian", "x", now=DAY).file == str(Path(os.path.realpath(v)) / "2026-09-24.md"))
    CONFIG.clear()


# ---- 2. only ever adds --------------------------------------------------------

def t_appends_and_never_overwrites():
    v = vault({"folder": "Daily", "format": "YYYY/MM/YYYY-MM-DD"})
    p = NC.plan("obsidian", "first thought", now=DAY)
    card = NC.describe(p)
    check("the card says which folder will be made", '"Daily/2026/09"' in card, card)
    check("run() without approval writes nothing",
          NC.run(p)["ok"] is False and not (v / "Daily").exists())
    with NoNetwork():
        out = NC.run(p, approved=True)
    f = v / "Daily" / "2026" / "09" / "2026-09-24.md"
    check("an approved note makes the folders and the file",
          out.get("ok") is True and f.read_text(encoding="utf-8") == "first thought\n", repr(out))
    check("the answer names the file inside the vault, not the whole disk path",
          out.get("file") == "Daily/2026/09/2026-09-24.md", repr(out))
    f.write_bytes(b"# 2026-09-24\n\n- [ ] tasks\nno newline at end")
    before = f.read_bytes()
    p2 = NC.plan("obsidian", "second\nline two", now=DAY)
    check("the card for an existing note says it is added at the end",
          "added at the end" in NC.describe(p2))
    out = NC.run(p2, approved=True)
    after = f.read_bytes()
    check("earlier text byte for byte intact, then a blank line, then the note",
          out.get("ok") and after == before + b"\n\nsecond\nline two\n", repr(after))
    NC.run(NC.plan("obsidian", "third", now=DAY), approved=True)
    check("a file already ending in a newline gets one blank line, not two",
          f.read_bytes().endswith(b"line two\n\nthird\n"), repr(f.read_bytes()[-30:]))
    big = "y" * (NC.MAX_NOTE_CHARS + 500)
    check("the same length bound as Logseq", len(NC.plan("obsidian", big, now=DAY).text)
          == NC.MAX_NOTE_CHARS)
    check("an empty note is refused", NC.plan("obsidian", "  ", now=DAY).reason_empty == "the note is empty")


def t_links_out_of_the_vault_are_refused():
    outside = _TMP / f"outside{time.time_ns()}"
    outside.mkdir()
    v = vault({"folder": "Daily"})
    try:
        (v / "Daily").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        return check("SKIP - cannot make a symlink here", True)
    p = NC.plan("obsidian", "x", now=DAY)
    check("a daily folder that is a link out of the vault: refused at plan time",
          "outside the vault" in p.reason_empty, repr(p))
    check("and nothing was written out there",
          NC.run(p, approved=True)["ok"] is False and list(outside.iterdir()) == [])
    v = vault()
    target = outside / "victim.md"
    target.write_text("do not touch")
    (v / "2026-09-24.md").symlink_to(target)
    p = NC.plan("obsidian", "x", now=DAY)
    check("today's note that is a link out of the vault: refused",
          "outside the vault" in p.reason_empty and target.read_text() == "do not touch",
          repr(p.reason_empty))
    inside = v / "real.md"
    inside.write_text("mine")
    os.remove(v / "2026-09-24.md")
    (v / "2026-09-24.md").symlink_to(inside)
    out = NC.run(NC.plan("obsidian", "x", now=DAY), approved=True)
    check("even a link that stays inside is not written through (a plain file only)",
          out["ok"] is False and inside.read_text() == "mine", repr(out))
    # The disk changing between the card and the write: run() checks again.
    v = vault({"folder": "Later"})
    p = NC.plan("obsidian", "x", now=DAY)
    (v / "Later").symlink_to(outside, target_is_directory=True)
    out = NC.run(p, approved=True)
    check("a link made after the card was shown is still refused at write time",
          out["ok"] is False and list(outside.iterdir()) == [target], repr(out))


# ---- 3. through the gate, from the route --------------------------------------

def t_capture_through_the_gate():
    v = vault()
    seen = []

    def gate(action, detail, prompt):
        seen.append((action, detail["text"], prompt))
        return Verdict(True, "auto")
    code, out = NC.capture("obsidian", "from the widget", gate_check=gate)
    check("filed, and the status says where", code == 200 and out["state"] == "filed"
          and "Filed in Obsidian, " in out["message"], repr(out))
    check("the gate was asked under append_obsidian_daily",
          seen and seen[0][0] == "append_obsidian_daily")
    check("the gate saw the card with the exact text", "from the widget" in seen[0][1])
    check("the gate's prompt does not repeat the note", "from the widget" not in seen[0][2])
    check("the note is really there", (v / "2026-09-24.md").exists() or any(
        "from the widget" in f.read_text() for f in v.glob("*.md")))
    check("the status never carries the note's text", "from the widget" not in json.dumps(out))
    g = vault()
    code, out = NC.capture("obsidian", "no", gate_check=lambda *a: Verdict(False, "denied"))
    check("a refused capture writes nothing", out["state"] == "not_filed"
          and not list(g.glob("*.md")))
    clear_env()
    code, out = NC.capture("obsidian", "x", gate_check=lambda *a: Verdict(True, "auto"))
    check("an Obsidian that is not set up: 503, and the message says so plainly",
          code == 503 and out["message"].startswith("Not filed: Obsidian isn't set up on your PC"),
          repr(out))


def t_the_agent_tool():
    import jarvis_agent as AG
    check("append_obsidian_daily is a tool, gated under its own name",
          "append_obsidian_daily" in AG.TOOLS
          and AG.TOOLS["append_obsidian_daily"].gate_lookup_name({}) == "append_obsidian_daily")
    check("it is not one that needs a person whatever the config says (the tier decides)",
          "append_obsidian_daily" not in AG.NEEDS_A_PERSON)
    v = vault()
    state, card = AG.TOOLS["append_obsidian_daily"].prepare({"text": "from chat"})
    check("prepare() gives the same card the route shows", "from chat" in card
          and "Nothing leaves this PC" in card)
    check("execute() writes the prepared plan",
          AG.TOOLS["append_obsidian_daily"].execute({}, state).get("ok") is True
          and "from chat\n" in next(v.glob("*.md")).read_text())


def t_the_config_and_the_gate_patch_name_it():
    toml = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check("jarvis-framework.toml gives append_obsidian_daily the tier auto",
          'append_obsidian_daily     = "auto"' in toml)
    check("and has [notes.obsidian] vault_directory", "[notes.obsidian]" in toml
          and 'vault_directory = ""' in toml)
    patch = (HERE / "note-capture.patch").read_text(encoding="utf-8")
    check("note-capture.patch gives the gate its risk line: stays on this PC",
          '+    "append_obsidian_daily": ("yes", "local"' in patch)
    check("and maps the tool to the action",
          '+    "append_obsidian_daily": "append_obsidian_daily",' in patch)


# ---- 4. the vault search ------------------------------------------------------

def make_search_vault():
    v = vault()
    (v / "Projects").mkdir()
    (v / "Projects" / "Budget 2026.md").write_text("Rent and food.\n" + SECRET + "\n")
    (v / "Journal.md").write_text("Walked to the lighthouse. The BUDGET is tight.")
    (v / "unrelated.md").write_text("Nothing here.")
    (v / "notes.txt").write_text("budget in a text file")
    (v / ".obsidian" / "workspace.md").write_text("budget in settings")
    (v / ".trash").mkdir()
    (v / ".trash" / "old budget.md").write_text("budget in the bin")
    return v


def t_vault_search_reads_the_folder():
    v = make_search_vault()
    with NoNetwork():
        p = N.plan("budget", 10)
        card = N.describe(p)
        out = N.run(p, approved=True)
    check("a configured vault is the backend, no key needed", p.backend == "vault"
          and p.folder == os.path.realpath(v) and not p.reason_empty, repr(p))
    check("the card names the folder and says nothing leaves", str(os.path.realpath(v)) in card
          and "What leaves this machine: nothing" in card, card)
    refs = [r["ref"] for r in out["results"]]
    check("title and text both match, ignoring case; title matches first",
          refs == ["Projects/Budget 2026.md", "Journal.md"], repr(out))
    check("the normal result shape: title, snippet, ref",
          all(set(r) == {"title", "snippet", "ref"} for r in out["results"])
          and out["results"][0]["title"] == "Budget 2026")
    check("the snippet is text from around the match",
          "BUDGET is tight" in out["results"][1]["snippet"], repr(out["results"][1]))
    check(".obsidian, .trash and non-.md files are never read",
          not any(x in json.dumps(out) for x in ("settings", "the bin", "text file")))
    check("every word must match", [r["ref"] for r in N.run(N.plan("walked budget"),
                                                             approved=True)["results"]]
          == ["Journal.md"])
    check("run() without approval searches nothing", N.run(p)["ok"] is False)


def t_vault_is_preferred_and_the_rest_still_work():
    make_search_vault()
    os.environ[N.OBSIDIAN_KEY_ENV] = "k"
    os.environ[N.JOPLIN_TOKEN_ENV] = TOKEN
    check("with a vault AND a REST key set, the folder is used", N.plan("x").backend == "vault")
    os.environ[N.BACKEND_ENV] = "obsidian"
    check("JARVIS_NOTES_BACKEND still picks the REST plugin", N.plan("x").backend == "obsidian")
    os.environ[N.BACKEND_ENV] = "joplin"
    check("or Joplin", N.plan("x").backend == "joplin")
    clear_env()
    os.environ[N.OBSIDIAN_KEY_ENV] = "k"
    check("with no vault, the REST plugin path is unchanged", N.plan("x").backend == "obsidian")
    clear_env()


def t_vault_search_skips_links_out_and_respects_caps():
    v = make_search_vault()
    outside = _TMP / f"out{time.time_ns()}"
    outside.mkdir()
    (outside / "budget leak.md").write_text("budget outside the vault")
    try:
        (v / "linked").symlink_to(outside, target_is_directory=True)
        (v / "file-link.md").symlink_to(outside / "budget leak.md")
        out = N.run(N.plan("budget"), approved=True)
        check("folders and files that link out of the vault are never read",
              "outside the vault" not in json.dumps(out), repr(out))
    except (OSError, NotImplementedError):
        check("SKIP - cannot make a symlink here", True)
    real = (N.VAULT_MAX_FILES, N.VAULT_MAX_FILE_BYTES)
    try:
        N.VAULT_MAX_FILES = 1
        out = N.run(N.plan("budget"), approved=True)
        check("a file cap stops the walk, and the answer says so",
              out["files_searched"] == 1 and "stopped early" in out.get("stopped_early", ""),
              repr(out))
        N.VAULT_MAX_FILES = real[0]
        N.VAULT_MAX_FILE_BYTES = 5
        out = N.run(N.plan("lighthouse"), approved=True)
        check("only the first bytes of each file are read",
              out["results"] == [], repr(out))
    finally:
        N.VAULT_MAX_FILES, N.VAULT_MAX_FILE_BYTES = real
    ticks = iter(range(0, 1000, 10))
    out = N._search_vault(N.plan("budget"), clock=lambda: next(ticks))
    check("a time budget stops a slow walk", "stopped_early" in out and "seconds" in out["stopped_early"],
          repr(out))
    p = N.plan("budget", 1)
    check("results are capped by the plan's limit", len(N.run(p, approved=True)["results"]) == 1)


# ---- 5. rule 1: the vault's text reaches the local model only -----------------

def t_search_results_reach_the_local_model_only():
    import jarvis_agent as AG
    import _ollama_wire as W
    import test_cloud_one_turn as COT
    make_search_vault()
    LOCAL = "http://127.0.0.1:11434"
    rounds = iter([
        [("tool_calls", [{"id": "c1", "name": "notes_search",
                          "arguments": {"query": "budget"}}]), ("done", "stop")],
        [("content", "You wrote about rent."), ("done", "stop")],
    ])
    sent, streamed, steps, gate_saw = [], [], [], []

    def opener(url, payload):
        sent.append((url, json.dumps(payload)))
        return W.FakeResponse(W.stream(next(rounds)))

    def gate(action, detail, prompt):
        gate_saw.append(json.dumps([action, detail, prompt]))
        return Verdict(True, "auto")
    real = (AG._post, AG._open_stream, AG._get_json)
    AG._post = AG._open_stream = AG._get_json = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("a real request ran"))
    try:
        with NoNetwork():
            AG.run_local_turn([{"role": "user", "content": "what did I write about my budget?"}],
                              "qwen3:8b", ollama_url=LOCAL, stream_out=streamed.append,
                              enabled_tools={"notes_search"}, gate_check=gate,
                              open_stream=opener, record_chain=lambda s: None,
                              on_step=steps.append, context_length=32768)
    finally:
        AG._post, AG._open_stream, AG._get_json = real
    check("CONTROL: the vault's words really were found and handed to the model",
          len(sent) == 2 and SECRET in sent[1][1], repr([u for u, _ in sent]))
    check("every request carrying them went to the local model's address, and nowhere else",
          all(u.startswith(LOCAL + "/") for u, _ in sent))
    check("the phone/desktop get the model's answer, not the file",
          SECRET not in b"".join(streamed).decode("utf-8", "replace"))
    check("the event bus (which reaches a lock screen) carries no note text",
          SECRET not in json.dumps(steps) and steps, repr(steps))
    check("the approval gate's card and log carry no note text", SECRET not in "".join(gate_saw))
    convo = json.loads(sent[1][1])
    check("CONTROL: the local lane keeps the conversation, tool result included",
          SECRET in json.dumps(COT.RUN("qwen3:8b", "qwen3:8b", convo)))
    check("a cloud lane (cloud-one-turn.patch's own lines) gets none of it",
          SECRET not in json.dumps(COT.RUN("jarvis-escalate", "qwen3:8b", convo)))
    patch = (HERE / "chat-stream.patch").read_text(encoding="utf-8")
    check("and tools run only on the local lane (chat-stream.patch)",
          "use_tools = (lane == local_model" in patch and "+                     and _agent_ok)" in patch)


def t_the_router_keeps_notes_questions_local():
    sys.path.insert(0, str(HERE / "rebuilt"))
    import jarvis_router as RT
    for q in ("search my Obsidian vault for the budget", "what's in joplin about Sam"):
        check(f"{q!r} is kept local by the private backstop", RT.is_private(q))


# ---- 6. which targets are set up ---------------------------------------------

def _graph():
    g = _TMP / f"graph{time.time_ns()}"
    (g / "journals").mkdir(parents=True)
    return g



class _Joplin:
    """A stand-in for Joplin's Web Clipper service on 127.0.0.1: records the
    token each request carried, answers an empty list."""

    def __enter__(self):
        import threading
        import urllib.parse
        from http.server import BaseHTTPRequestHandler, HTTPServer
        seen = self.seen = []

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                seen.append((self.path.split("?")[0], (q.get("token") or [""])[0]))
                body = b'{"items": [], "has_more": false}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()
        return False


def t_search_and_capture_agree_on_joplins_token_and_address():
    # Bug audit 3, K11. The capture read the toml's [notes.joplin] token_env
    # (default JOPLIN_TOKEN, as the shipped settings file says) and port; the
    # search read only JARVIS_JOPLIN_TOKEN and always used 41184. So an owner
    # who followed the settings file could file notes in Joplin and never
    # search them. Both now use jarvis_notes.joplin_token() / joplin_base().
    for label, cfg, var in (
            ("the settings file's own default (JOPLIN_TOKEN)",
             {"token_env": "JOPLIN_TOKEN"}, "JOPLIN_TOKEN"),
            ("no token_env in the settings file at all", {}, "JOPLIN_TOKEN"),
            ("a token_env name of the owner's choosing", {"token_env": "MY_JOPLIN"}, "MY_JOPLIN")):
        clear_env()
        os.environ.pop("MY_JOPLIN", None)
        with _Joplin() as j:
            CONFIG["notes"] = {"joplin": dict(cfg, port=j.port)}
            os.environ[var] = TOKEN
            p = N.plan("groceries")
            check(f"{label}: the search picks Joplin, authenticated",
                  p.backend == "joplin" and p.authenticated, repr(p))
            check(f"{label}: the search uses the settings file's port",
                  p.url.startswith(f"http://127.0.0.1:{j.port}/search?"), p.url)
            check(f"{label}: the capture is set up for Joplin, at the same address",
                  "joplin" in NC.available_targets()
                  and NC._joplin_base() == f"http://127.0.0.1:{j.port}")
            N._default_fetch(p)
            NC._joplin_call("GET", NC._joplin_base(), "/folders", {})
            check(f"{label}: both sent the same token to the same Joplin",
                  j.seen == [("/search", TOKEN), ("/folders", TOKEN)], repr(j.seen))
            check(f"{label}: the search's error scrubbing hides that token too",
                  TOKEN not in N._scrub_secrets(f"boom ?token={TOKEN}"))
        os.environ.pop(var, None)
    clear_env()
    os.environ[N.JOPLIN_TOKEN_ENV] = "the-jarvis-one"
    os.environ["JOPLIN_TOKEN"] = TOKEN
    check("JARVIS_JOPLIN_TOKEN still wins over the settings file's, for both",
          N.joplin_token() == "the-jarvis-one" and NC._joplin_token() == "the-jarvis-one")
    os.environ[N.JOPLIN_URL_ENV] = "http://127.0.0.1:5555/"
    CONFIG["notes"] = {"joplin": {"port": 6666}}
    check("JARVIS_JOPLIN_URL still wins over the settings file's port, for both",
          N.joplin_base() == NC._joplin_base() == "http://127.0.0.1:5555")
    os.environ.pop(N.JOPLIN_URL_ENV)
    CONFIG["notes"] = {"joplin": {"port": "not a port"}}
    check("a port that is not a number falls back to Joplin's own 41184",
          N.joplin_base() == "http://127.0.0.1:41184")
    clear_env()

def scenarios() -> dict:
    """GET /api/notes/capture (no id), from the real functions, per setup."""
    out = {}
    clear_env()
    out["none"] = NC.capture_status("")
    os.environ[NC.LOGSEQ_GRAPH_ENV] = str(_graph())
    out["logseq_only"] = NC.capture_status("")
    v = _TMP / "fixture-vault"
    (v / ".obsidian").mkdir(parents=True, exist_ok=True)
    os.environ[N.OBSIDIAN_VAULT_ENV] = str(v)
    os.environ[N.JOPLIN_TOKEN_ENV] = TOKEN
    out["all"] = NC.capture_status("")
    os.environ.pop(NC.LOGSEQ_GRAPH_ENV)
    os.environ.pop(N.JOPLIN_TOKEN_ENV)
    out["obsidian_only"] = NC.capture_status("")
    # A backend from before this change answered a bare GET with the "no such
    # note" branch - the same one an unknown id still takes today.
    out["older_backend"] = NC.capture_status("note_from_an_older_backend")
    clear_env()
    code, body = NC.capture("obsidian", "x")
    out["capture_not_set_up"] = (code, body)
    return {k: {"status": c, "body": b} for k, (c, b) in out.items()}


def t_available_targets():
    s = scenarios()
    check("nothing set up: an empty list", s["none"] == {"status": 200,
          "body": {"ok": True, "targets": []}}, repr(s["none"]))
    check("each target listed exactly when it is set up",
          s["logseq_only"]["body"]["targets"] == ["logseq"]
          and s["all"]["body"]["targets"] == ["logseq", "joplin", "obsidian"]
          and s["obsidian_only"]["body"]["targets"] == ["obsidian"], repr(s))
    blob = json.dumps(s["all"])
    check("names only: no path and no token in the answer",
          TOKEN not in blob and str(_TMP) not in blob and "/" not in "".join(
              s["all"]["body"]["targets"]), blob)
    os.environ[NC.JOPLIN_TOKEN_ENV] = TOKEN
    os.environ[NC.JOPLIN_URL_ENV] = "http://192.168.1.9:41184"
    check("a Joplin address that is not this PC is not 'set up'",
          "joplin" not in NC.available_targets())
    clear_env()
    with NoNetwork():
        NC.available_targets()
    check("working it out opened no socket", True)


def build_fixture() -> dict:
    return {"_about": ("Written by backend/test_obsidian_notes.py --write from "
                       "jarvis_note_capture's real functions. Do not edit by hand."),
            **scenarios()}


def t_the_fixture_is_what_the_producer_makes_today():
    try:
        have = json.loads(FIXTURE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return check("the shared fixture exists", False,
                     f"{exc} - run: python3 test_obsidian_notes.py --write")
    check("the shared fixture matches the producer (else run with --write)",
          have == json.loads(json.dumps(build_fixture())))


if __name__ == "__main__":
    if "--write" in sys.argv:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps(build_fixture(), indent=2) + "\n", encoding="utf-8")
        print(f"wrote {FIXTURE}")
    tests = [v for k, v in list(globals().items()) if k.startswith("t_") and callable(v)]
    for fn in tests:
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
