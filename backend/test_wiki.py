"""The wiki builder: plan, validate, describe, the gate, run, the routes'
answers, and the patch.

    python3 test_wiki.py

Runs anywhere. No model, no graphics card, no Obsidian: the vault is a real
folder made for each test, the second card's lane is a stand-in Lane on
127.0.0.1, and the model is either an injected `call` or, once, a tiny HTTP
server on 127.0.0.1 answering in Ollama's /api/chat shape.

What it proves:

  - lane_for("wiki") None: GET says unavailable and why, POST is 503, plan()
    refuses, and no model is asked.
  - the source list: new, changed, in_wiki, too_big, unreadable (other
    formats, not UTF-8, empty, a link out of Sources).
  - plan() writes nothing, asks only the lane (loopback, the lane's model and
    num_ctx, a JSON-schema `format`, think off), and refuses - whole - on:
    path traversal, a link out of the wiki, too many pages, an oversize page,
    bad JSON, an answer cut short, schema drift, a create over an existing
    page, an update to a page it was not shown, HTML that loads something.
  - describe(): the source, every page with its summary, the .versions
    promise, "Nothing leaves this PC", what saying no costs.
  - the gate: exactly one card, action wiki_update; no -> nothing written;
    yes -> written; the gate failing -> nothing written.
  - run(): not without approved=True; .versions keeps the old page;
    frontmatter sources merged, the owner's own keys kept; index.md and
    log.md appended, never rewritten; the cache; a rerun on an unchanged
    source is skipped ("already in the wiki"); a page changed while the card
    was up stops it; a failed run says what was written, and running the
    same plan again carries on.
  - wiki.patch applies after second-card.patch to what the earlier patches
    wrote, and reverses; the install lists and the toml have it.
  - the committed jarvis-desktop fixture equals a fresh run.
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, missing, require_shipped  # noqa: E402

for p in (REPO / "tools", HERE / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.append(str(p))

require_shipped("jarvis_wiki.py", "jarvis_notes.py", "jarvis_second_card.py")

import jarvis_second_card as SC  # noqa: E402
import jarvis_wiki as W  # noqa: E402

FAILED, PASSED = [], []
LANE = SC.Lane(url="http://127.0.0.1:11435", model="qwen3:14b", num_ctx=16384,
               why="Wiki builder: qwen3:14b on the RTX 2060")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class Verdict:
    def __init__(self, allowed, outcome, tier="ask", reason=""):
        self.allowed, self.outcome, self.tier, self.reason = allowed, outcome, tier, reason


def answer(obj, **extra) -> dict:
    out = {"model": LANE.model, "done": True, "done_reason": "stop", "prompt_eval_count": 500,
           "message": {"role": "assistant",
                       "content": obj if isinstance(obj, str) else json.dumps(obj)}}
    out.update(extra)
    return out


ANALYSIS = {"summary": "Notes about the allotment.",
            "entities": [{"name": "Margaret Hale", "kind": "person", "why": "the chair"}],
            "existing_pages": ["Allotment Society"], "contradictions": []}


def pages(*items):
    return {"pages": [dict(zip(("action", "path", "summary", "body"), i)) for i in items]}


GOOD = pages(("update", "Pages/Allotment Society.md", "The society.",
              "Meets every two weeks. Chair: [[Margaret Hale]]."),
             ("create", "Pages/Margaret Hale.md", "The chair.",
              "Chair of the [[Allotment Society]]."))


class Model:
    """An injected `call`: answers the analysis, then the pages."""

    def __init__(self, pages_answer=None, analysis=None, raw_pages=None):
        self.bodies, self.lanes = [], []
        self.pages_answer = GOOD if pages_answer is None else pages_answer
        self.analysis = ANALYSIS if analysis is None else analysis
        self.raw_pages = raw_pages

    def __call__(self, lane, body):
        self.lanes.append(lane)
        self.bodies.append(body)
        if body["format"] is W.ANALYSIS_SCHEMA:
            return answer(self.analysis)
        return self.raw_pages if self.raw_pages is not None else answer(self.pages_answer)


class Vault:
    def __init__(self, *, wiki=True):
        self.dir = Path(tempfile.mkdtemp(prefix="jarvis-wiki-test-"))
        (self.dir / ".obsidian").mkdir()
        self.wiki = self.dir / W.WIKI_DIR
        self.src = self.wiki / W.SOURCES_DIR
        self.pages = self.wiki / W.PAGES_DIR
        if wiki:
            self.src.mkdir(parents=True)
            self.pages.mkdir()
            (self.src / "meeting.md").write_text("Margaret Hale is the new chair. The society "
                                                 "now meets every two weeks.\n",
                                                 encoding="utf-8")
            (self.pages / "Allotment Society.md").write_text(
                '---\nsources: ["old.md"]\ntags: [garden]\n---\n\nMeets monthly.\n',
                encoding="utf-8")
            (self.wiki / W.INDEX_NAME).write_text(
                "# Jarvis Wiki\n\n- [[Allotment Society]] - the society\n", encoding="utf-8")
            (self.wiki / W.LOG_NAME).write_text(
                "## [2026-09-01] ingest | old.md\n\n- created [[Allotment Society]]\n",
                encoding="utf-8")
        self._env = os.environ.get("JARVIS_OBSIDIAN_VAULT")
        os.environ["JARVIS_OBSIDIAN_VAULT"] = str(self.dir)
        W._reset_for_tests()

    def snapshot(self) -> dict:
        out = {}
        for d, _, files in os.walk(self.dir):
            for f in files:
                p = Path(d) / f
                out[str(p.relative_to(self.dir))] = p.read_bytes()
        return out

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self._env is None:
            os.environ.pop("JARVIS_OBSIDIAN_VAULT", None)
        else:
            os.environ["JARVIS_OBSIDIAN_VAULT"] = self._env
        shutil.rmtree(self.dir, ignore_errors=True)
        W._reset_for_tests()


def _plan(model=None, source="meeting.md", lane=LANE):
    return W.plan(source, lane=lane, call=model or Model())


# ------------------------------------------------------------ the lane --

def t_no_lane_means_nothing_runs():
    with Vault() as v:
        m = Model()
        s = W.status(lane_for=lambda: None, why=lambda: "Off.")
        check("GET: unavailable, with the reason", s["available"] is False and s["why"] == "Off.")
        check("GET still lists the sources (so the owner sees what is waiting)",
              [x["name"] for x in s["sources"]] == ["meeting.md"])
        code, body = W.ingest("meeting.md", lane_for=lambda: None, call=m)
        check("POST: 503 with a sentence, state refused",
              code == 503 and body["state"] == "refused" and body["error"], body)
        orig = W._lane
        W._lane = lambda: None
        try:
            p = W.plan("meeting.md", call=m)
        finally:
            W._lane = orig
        check("plan() refuses when lane_for is None", bool(p.reason_empty) and not p.changes)
        check("and no model was asked", m.bodies == [])
        p = W.plan("meeting.md", lane=SC.Lane("http://10.0.0.5:11435", "x", 16384, ""), call=m)
        check("a lane that is not on this PC is refused, unasked",
              "not on this PC" in p.reason_empty and m.bodies == [])
        check("_post_json refuses a non-loopback address",
              _raises(lambda: W._post_json("http://192.168.1.2:11435/api/chat", {}), ValueError))
    orig = W._lane
    try:
        import jarvis_second_card
        saved = jarvis_second_card.lane_for
        jarvis_second_card.lane_for = lambda f: None if f == "wiki" else LANE
        check("_lane() asks jarvis_second_card for the 'wiki' feature only", W._lane() is None)
        jarvis_second_card.lane_for = lambda f: LANE if f == "wiki" else None
        check("... and returns its lane", W._lane() is LANE)
    finally:
        jarvis_second_card.lane_for = saved
        W._lane = orig


def _raises(fn, exc):
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


# ------------------------------------------------------------- sources --

def t_the_source_list():
    with Vault() as v:
        (v.src / "notes.txt").write_text("plain text\n", encoding="utf-8")
        (v.src / "scan.pdf").write_bytes(b"%PDF")
        (v.src / "latin1.md").write_bytes("caf\xe9".encode("latin-1"))
        (v.src / "empty.md").write_text("  \n", encoding="utf-8")
        (v.src / "huge.md").write_text("word " * 10000, encoding="utf-8")
        (v.src / ".hidden.md").write_text("x", encoding="utf-8")
        outside = v.dir.parent / (v.dir.name + "-outside.md")
        outside.write_text("secret", encoding="utf-8")
        try:
            os.symlink(outside, v.src / "link.md")
            linked = True
        except OSError:
            linked = False
        W._write_atomic(v.wiki / W.CACHE_NAME, json.dumps({"sources": {
            "notes.txt": {"sha256": W._sha(b"plain text\n"), "added": "2026-09-20"},
            "meeting.md": {"sha256": "0" * 64, "added": "2026-09-20"}}}))
        s = {x["name"]: x for x in W.status(lane_for=lambda: LANE)["sources"]}
        check("an unchanged source is 'in_wiki' and says so", s["notes.txt"]["state"] == "in_wiki"
              and "Already in the wiki" in s["notes.txt"]["why"])
        check("an edited source is 'changed'", s["meeting.md"]["state"] == "changed")
        check("a .pdf is listed as unreadable, saying only .md and .txt are read",
              s["scan.pdf"]["state"] == "unreadable" and ".md and .txt" in s["scan.pdf"]["why"])
        check("text that is not UTF-8 is unreadable, with the fix",
              s["latin1.md"]["state"] == "unreadable" and "UTF-8" in s["latin1.md"]["why"])
        check("an empty file is unreadable", s["empty.md"]["state"] == "unreadable")
        check("a source bigger than the lane's room is too_big, with numbers, never cut",
              s["huge.md"]["state"] == "too_big" and "16,384" in s["huge.md"]["why"]
              and "cut short" in s["huge.md"]["why"])
        check("hidden files are not listed", ".hidden.md" not in s)
        if linked:
            check("a link out of Sources is unreadable, not read",
                  s["link.md"]["state"] == "unreadable" and "outside" in s["link.md"]["why"])
        else:
            check("SKIP - symlinks not allowed here", True)
        outside.unlink()
        big = SC.Lane(LANE.url, LANE.model, 32768, "")
        s2 = {x["name"]: x for x in W.status(lane_for=lambda: big)["sources"]}
        check("the same source fits a 32K lane (the limit is the lane's num_ctx)",
              s2["huge.md"]["state"] == "new")


def t_the_folder():
    with Vault(wiki=False) as v:
        s = W.status(lane_for=lambda: LANE)
        check("no Jarvis Wiki folder: vault_folder_ok false and what to make",
              s["vault_folder_ok"] is False and '"Jarvis Wiki"' in s["folder_why"]
              and '"Sources"' in s["folder_why"])
        check("GET wrote nothing", not (v.dir / W.WIKI_DIR).exists())
        outside = Path(tempfile.mkdtemp(prefix="jarvis-wiki-elsewhere-"))
        try:
            os.symlink(outside, v.dir / W.WIKI_DIR)
            s = W.status(lane_for=lambda: LANE)
            check("a Jarvis Wiki folder that links out of the vault is refused",
                  s["vault_folder_ok"] is False and "outside the vault" in s["folder_why"])
        except OSError:
            check("SKIP - symlinks not allowed here", True)
        finally:
            shutil.rmtree(outside, ignore_errors=True)
    env = os.environ.pop("JARVIS_OBSIDIAN_VAULT", None)
    try:
        import jarvis_notes
        saved = jarvis_notes.obsidian_vault
        jarvis_notes.obsidian_vault = lambda: None
        s = W.status(lane_for=lambda: LANE)
        check("no vault configured: said plainly", s["vault_folder_ok"] is False
              and "No Obsidian vault" in s["folder_why"])
    finally:
        jarvis_notes.obsidian_vault = saved
        if env is not None:
            os.environ["JARVIS_OBSIDIAN_VAULT"] = env


# ---------------------------------------------------------------- plan --

def t_plan_writes_nothing_and_asks_only_the_lane():
    with Vault() as v:
        before = v.snapshot()
        m = Model()
        p = _plan(m)
        check("the plan has the two pages", not p.reason_empty and
              [(c.action, c.path) for c in p.changes] ==
              [("update", "Pages/Allotment Society.md"), ("create", "Pages/Margaret Hale.md")],
              p.reason_empty)
        check("plan() wrote nothing at all", v.snapshot() == before)
        check("two model calls, both to the lane", len(m.bodies) == 2
              and all(l is LANE for l in m.lanes))
        b = m.bodies[1]
        check("each asks the lane's model, at the lane's num_ctx, think off, temperature 0",
              all(x["model"] == LANE.model and x["options"]["num_ctx"] == LANE.num_ctx
                  and x["think"] is False and x["options"]["temperature"] == 0
                  and x["stream"] is False for x in m.bodies))
        check("structured output: a JSON schema in `format`",
              m.bodies[0]["format"] is W.ANALYSIS_SCHEMA and b["format"] is W.PAGES_SCHEMA)
        check("step 1 is given the index", "Allotment Society" in m.bodies[0]["messages"][1]
              ["content"].split("SOURCE")[0])
        check("step 2 is shown the page it may update, in full",
              "Meets monthly." in b["messages"][1]["content"])
        new = next(c for c in p.changes if c.action == "create")
        check("a new page's frontmatter names its source",
              new.text.startswith('---\nsources: ["meeting.md"]\n---\n\n'))
        upd = next(c for c in p.changes if c.action == "update")
        check("an updated page's sources are merged and the owner's other keys kept",
              upd.text.startswith('---\nsources: ["old.md", "meeting.md"]\ntags: [garden]\n---'),
              upd.text[:80])


def t_plan_refuses_whole():
    def refused(model, why_part, name, setup=None):
        with Vault() as v:
            if setup:
                setup(v)
            before = v.snapshot()
            p = _plan(model)
            ok = bool(p.reason_empty) and not p.changes and why_part in p.reason_empty
            check(name, ok and v.snapshot() == before, p.reason_empty)

    for path, part in (("Pages/../evil.md", ".."), ("../evil.md", "not directly in Pages"),
                       ("Pages/sub/evil.md", "not directly in Pages"),
                       ("Pages/.hidden.md", "dot"), ("Pages/CON.md", "device"),
                       ("Pages/x.txt", "not a .md"), ("C:/Windows/x.md", ":"),
                       ("Pages\\x.md", "\\"), ("/etc/x.md", "not directly in Pages"),
                       ("Pages/a<b>.md", "character")):
        refused(Model(pages(("create", path, "s", "body"))), part,
                f"path {path!r} is refused")

    def link_pages(v):
        out = Path(tempfile.mkdtemp(prefix="jarvis-wiki-out-"))
        shutil.rmtree(v.pages)
        os.symlink(out, v.pages)
    try:
        refused(Model(pages(("create", "Pages/New.md", "s", "body"))), "outside",
                "a Pages folder that links out of the wiki is refused", setup=link_pages)
    except OSError:
        check("SKIP - symlinks not allowed here", True)

    def link_page(v):
        out = v.dir.parent / (v.dir.name + "-target.md")
        out.write_text("x", encoding="utf-8")
        os.symlink(out, v.pages / "Linked.md")
    try:
        refused(Model(pages(("create", "Pages/Linked.md", "s", "body"))), "link",
                "a page that is a symlink is refused", setup=link_page)
    except OSError:
        check("SKIP - symlinks not allowed here", True)
    refused(Model(pages(*[("create", f"Pages/P{i}.md", "s", "b") for i in range(13)])),
            "at most 12", "13 pages are refused (at most 12)")
    refused(Model(pages(("create", "Pages/Big.md", "s", "x" * 6001))), "at most 6,000",
            "a page over the size cap is refused")
    refused(Model(raw_pages=answer("{not json")), "not valid JSON", "bad JSON is refused")
    refused(Model(raw_pages=answer(GOOD, done_reason="length")), "ran out of room",
            "an answer the model stopped early is refused")
    refused(Model(raw_pages=answer(GOOD, prompt_eval_count=16384)), "whole context",
            "a question that filled the whole context is refused")
    refused(Model({"pages": [{"action": "create", "path": "Pages/A.md", "summary": "s"}]}),
            'without "body"', "schema drift: a page with no body")
    refused(Model(pages(("delete", "Pages/Allotment Society.md", "s", "b"))),
            'action "delete"', "schema drift: an action that is not create or update")
    refused(Model({"files": []}), "no pages list", "schema drift: no pages list")
    refused(Model(analysis={"summary": "s", "entities": "lots"}), "analysis",
            "schema drift in the analysis")
    refused(Model({"pages": []}), "no pages", "no pages at all is refused")
    refused(Model(pages(("create", "Pages/Allotment Society.md", "s", "b"))),
            "already a page", "create over an existing page is refused")
    refused(Model(pages(("create", "Pages/allotment society.md", "s", "b"))),
            "already a page", "... compared ignoring case, as Windows does")
    refused(Model(pages(("update", "Pages/Nowhere.md", "s", "b"))), "not a page",
            "update of a page that is not there is refused")
    refused(Model(pages(("update", "Pages/Allotment Society.md", "s", "b")),
                  analysis=dict(ANALYSIS, existing_pages=[])),
            "without having been shown it", "update of a page the model was not shown")
    refused(Model(pages(("create", "Pages/A.md", "s", "b"), ("create", "Pages/a.md", "s", "b"))),
            "twice", "the same page twice is refused")
    refused(Model(pages(("create", "Pages/A.md", "s", 'hi <img src="https://x/y.png">'))),
            "<img>", "HTML that loads something is refused")
    refused(Model(pages(("create", "Pages/A.md", "s", "<script>alert(1)</script>"))),
            "<script>", "a script tag is refused")


def t_safe_links():
    with Vault():
        p = _plan(Model(pages(("create", "Pages/A.md", "s",
                               "see ![chart](https://evil.example/c.png?d=1) and "
                               "![[https://evil.example/x.png]] and [site](https://ok.example)"))))
        text = p.changes[0].text if p.changes else ""
        check("a remote picture becomes a plain link, so opening the page fetches nothing",
              "![" not in text and "[chart](https://evil.example/c.png?d=1)" in text
              and "[site](https://ok.example)" in text, p.reason_empty or text)
    with Vault():
        p = _plan(Model(pages(("create", "Pages/A.md", "s",
                               "---\nsources: [evil]\n---\nBody [[B]]"))))
        check("frontmatter the model wrote is replaced by ours",
              p.changes and p.changes[0].text == '---\nsources: ["meeting.md"]\n---\n\nBody [[B]]\n',
              p.changes and p.changes[0].text)


def t_describe():
    with Vault():
        p = _plan()
        text = W.describe(p)
        check("the card names the source", '"meeting.md"' in text)
        check("every page, with its one-line summary",
              "Pages/Allotment Society.md - The society." in text
              and "Pages/Margaret Hale.md - The chair." in text)
        check("new and changed pages are told apart",
              "new page     Pages/Margaret Hale.md" in text
              and "change page  Pages/Allotment Society.md" in text)
        check("it says the old copy is kept in .versions", ".versions" in text)
        check("it says nothing leaves this PC", "Nothing leaves this PC." in text)
        check("and what saying no costs", "If you say no: nothing is written" in text)
        check("and which model, on this PC", "qwen3:14b, on this PC" in text)
    p = W.Plan(source="x.md", reason_empty="it is empty")
    check("a refused plan's card says nothing would be written",
          W.describe(p).endswith("Nothing would be written."))


# ---------------------------------------------------------------- gate --

def _ingest(gate, model=None, source="meeting.md"):
    calls = []

    def g(action, detail, prompt):
        calls.append((action, detail, prompt))
        return gate(action, detail, prompt)
    code, body = W.ingest(source, lane_for=lambda: LANE, call=model or Model(), gate_check=g,
                          spawn=lambda fn: fn())
    return code, body, calls


def t_the_gate():
    with Vault() as v:
        before = v.snapshot()
        code, body, calls = _ingest(lambda a, d, p: Verdict(False, "denied"))
        check("POST answers 202 with a job id and pending", code == 202 and body["pending"]
              and body["id"].startswith("wiki_"), body)
        check("exactly one card, action wiki_update", len(calls) == 1 and calls[0][0] == "wiki_update")
        d = calls[0][1]
        check("the card's detail: the card text, the pages, nothing leaves",
              d["text"] == W.describe(_plan()) and d["leaves_this_pc"] is False
              and [x["path"] for x in d["pages"]] == ["Pages/Allotment Society.md",
                                                     "Pages/Margaret Hale.md"])
        _, job = W.ingest_status(body["id"])
        check("no: refused, 'You said no', nothing written",
              job["state"] == "refused" and "You said no" in job["message"]
              and v.snapshot() == before, job)
        check("the job never carries a page's text",
              "every two weeks" not in json.dumps(job) and "Meets" not in json.dumps(job))
    with Vault() as v:
        before = v.snapshot()
        code, body, calls = _ingest(lambda a, d, p: Verdict(False, "timed_out"))
        _, job = W.ingest_status(body["id"])
        check("nobody answered: refused, nothing written", job["state"] == "refused"
              and "in time" in job["message"] and v.snapshot() == before)
    with Vault() as v:
        before = v.snapshot()
        orig = sys.modules.get("jarvis_gate")
        sys.modules["jarvis_gate"] = None      # import fails
        try:
            code, body = W.ingest("meeting.md", lane_for=lambda: LANE, call=Model(),
                                  spawn=lambda fn: fn())
        finally:
            if orig is None:
                sys.modules.pop("jarvis_gate", None)
            else:
                sys.modules["jarvis_gate"] = orig
        _, job = W.ingest_status(body["id"])
        check("no approval gate here: fails closed, nothing written",
              job["state"] == "refused" and v.snapshot() == before, job)
    with Vault() as v:
        code, body, calls = _ingest(lambda a, d, p: Verdict(True, "approved"))
        _, job = W.ingest_status(body["id"])
        check("yes: done, and the pages are there",
              job["state"] == "done" and (v.pages / "Margaret Hale.md").is_file(), job)
        code, body = W.ingest("meeting.md", lane_for=lambda: LANE, call=Model())
        check("adding it again: 409, 'already in the wiki'", code == 409
              and "already in the wiki" in body["error"], body)
    with Vault() as v:
        model = Model(raw_pages=answer("nope"))
        code, body, calls = _ingest(lambda a, d, p: Verdict(True, "approved"), model=model)
        _, job = W.ingest_status(body["id"])
        check("a plan the model got wrong raises no card at all",
              calls == [] and job["state"] == "refused" and "not valid JSON" in job["message"])
    with Vault() as v:
        W.ingest("meeting.md", lane_for=lambda: LANE, call=Model(), spawn=lambda fn: None)
        (v.src / "other.md").write_text("more\n", encoding="utf-8")
        code, body = W.ingest("other.md", lane_for=lambda: LANE, call=Model(),
                              spawn=lambda fn: None)
        check("one job at a time: a second is 409 while the first is reading",
              code == 409 and "already working" in body["error"])
        check("GET /api/wiki says what is running",
              W.status(lane_for=lambda: LANE)["running"]["source"] == "meeting.md")
    with Vault() as v:
        for bad in ("", "../x.md", "a/b.md", ".hidden.md", "C:x.md", "a\\b.md", None, 5):
            code, body = W.ingest(bad, lane_for=lambda: LANE)
            if code != 400:
                break
        check("a source that is not a plain name in Sources is 400", code == 400, (bad, body))
        (v.src / "scan.pdf").write_bytes(b"%PDF")
        code, body = W.ingest("scan.pdf", lane_for=lambda: LANE)
        check("an unreadable source is 400 with the reason",
              code == 400 and ".md and .txt" in body["error"])
        check("handle_post: not an object is 400", W.handle_post([1])[0] == 400)
        check("ingest_status: an unknown id is 404", W.ingest_status("wiki_nope")[0] == 404)


# ----------------------------------------------------------------- run --

def t_run():
    with Vault() as v:
        p = _plan()
        before = v.snapshot()
        out = W.run(p)
        check("run() without approved=True writes nothing",
              not out["ok"] and v.snapshot() == before)
        out = W.run(p, approved=True)
        check("run(approved=True) writes", out["ok"], out)
        vers = list((v.wiki / W.VERSIONS_DIR).iterdir())
        check(".versions keeps the page exactly as it was",
              len(vers) == 1 and vers[0].name.startswith("Allotment Society.")
              and vers[0].read_bytes() == before[f"{W.WIKI_DIR}/{W.PAGES_DIR}/Allotment Society.md"
                                                 .replace("/", os.sep)])
        check("the updated page is the planned text",
              (v.pages / "Allotment Society.md").read_text(encoding="utf-8") == p.changes[0].text)
        idx = (v.wiki / W.INDEX_NAME).read_text(encoding="utf-8")
        check("index.md: appended, the old line kept, one line for the new page",
              idx.startswith("# Jarvis Wiki\n\n- [[Allotment Society]] - the society\n")
              and idx.endswith("- [[Margaret Hale]] - The chair.\n")
              and idx.count("[[Allotment Society]]") == 1, idx)
        log = (v.wiki / W.LOG_NAME).read_text(encoding="utf-8")
        check("log.md: appended, one entry in the agreed form",
              log.startswith("## [2026-09-01] ingest | old.md")
              and re.search(r"\n## \[\d{4}-\d\d-\d\d\] ingest \| meeting\.md\n\n"
                            r"- created \[\[Margaret Hale\]\]\n- updated \[\[Allotment Society\]\]\n$",
                            log) is not None, log)
        check("the source itself is untouched",
              (v.src / "meeting.md").read_bytes() == before[f"{W.WIKI_DIR}/{W.SOURCES_DIR}/meeting.md"
                                                            .replace("/", os.sep)])
        cache = json.loads((v.wiki / W.CACHE_NAME).read_text(encoding="utf-8"))
        check("the cache records the source's SHA-256",
              cache["sources"]["meeting.md"]["sha256"] == p.source_sha)
        m = Model()
        p2 = _plan(m)
        check("a rerun on the unchanged source is skipped, and no model is asked",
              p2.already and "already in the wiki" in p2.reason_empty and m.bodies == [])
        s = {x["name"]: x for x in W.status(lane_for=lambda: LANE)["sources"]}
        check("... and the list shows it as in_wiki", s["meeting.md"]["state"] == "in_wiki")
        check("GET shows the new log line and the page count",
              W.status(lane_for=lambda: LANE)["recent"][-1].endswith("ingest | meeting.md")
              and W.status(lane_for=lambda: LANE)["pages"] == 2)
        found = []
        import jarvis_notes
        rp = jarvis_notes.plan("Margaret")
        if not rp.reason_empty and getattr(rp, "folder", ""):
            found = [r["ref"] for r in jarvis_notes._search_vault(rp)["results"]]
        check("the notes search finds the new page, and never .versions",
              any(r.endswith("Margaret Hale.md") for r in found)
              and not any(".versions" in r for r in found), found)


def t_run_refuses_a_changed_disk():
    with Vault() as v:
        p = _plan()
        (v.pages / "Allotment Society.md").write_text("I edited this meanwhile.\n",
                                                     encoding="utf-8")
        before = v.snapshot()
        out = W.run(p, approved=True)
        check("a page edited while the card was up stops the run, nothing written",
              not out["ok"] and "changed after the card" in out["reason"]
              and v.snapshot() == before and out["written"] == [], out)
    with Vault() as v:
        p = _plan()
        (v.pages / "Margaret Hale.md").write_text("someone made it\n", encoding="utf-8")
        out = W.run(p, approved=True)
        check("a page that appeared while the card was up stops the run",
              not out["ok"] and "appeared" in out["reason"])
    with Vault() as v:
        p = _plan()
        (v.src / "meeting.md").write_text("changed\n", encoding="utf-8")
        out = W.run(p, approved=True)
        check("a source edited while the card was up stops the run",
              not out["ok"] and "changed after the card" in out["reason"])


def t_run_resumes():
    with Vault() as v:
        p = _plan()
        real = W._write_atomic
        n = {"i": 0}

        def flaky(path, data):
            if path.name == "Margaret Hale.md" and n["i"] == 0:
                n["i"] += 1
                raise OSError("disk full")
            return real(path, data)
        W._write_atomic = flaky
        try:
            out = W.run(p, approved=True)
        finally:
            W._write_atomic = real
        check("a failed write says what was and was not written",
              not out["ok"] and out["written"] == ["Pages/Allotment Society.md"]
              and "Pages/Margaret Hale.md" in out["not_written"]
              and "index.md" in out["not_written"], out)
        check("and the source is not marked as in the wiki",
              not (v.wiki / W.CACHE_NAME).exists())
        out = W.run(p, approved=True)
        check("running the same plan again carries on and finishes", out["ok"], out)
        check("with one .versions copy (the original), not a copy of its own write",
              len(list((v.wiki / W.VERSIONS_DIR).iterdir())) == 1
              and "Meets monthly." in next((v.wiki / W.VERSIONS_DIR).iterdir())
              .read_text(encoding="utf-8"))
        log = (v.wiki / W.LOG_NAME).read_text(encoding="utf-8")
        check("one log entry, not two", log.count("ingest | meeting.md") == 1)


def t_worker_reports_partial_failure():
    with Vault() as v:
        real = W._write_atomic

        def flaky(path, data):
            if path.name == "Margaret Hale.md":
                raise OSError("disk full")
            return real(path, data)
        W._write_atomic = flaky
        try:
            code, body, calls = _ingest(lambda a, d, p: Verdict(True, "approved"))
        finally:
            W._write_atomic = real
        _, job = W.ingest_status(body["id"])
        check("the job says honestly what was written and where the old copies are",
              job["state"] == "failed" and "Written: Pages/Allotment Society.md" in job["message"]
              and ".versions" in job["message"] and "fresh plan" in job["message"], job)


# --------------------------------------------------- a real HTTP model --

class _Ollama(BaseHTTPRequestHandler):
    seen = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Ollama.seen.append((self.path, body))
        obj = ANALYSIS if body["format"].get("required", [None])[0] == "summary" else GOOD
        data = json.dumps(answer(obj)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def t_real_http_on_loopback():
    srv = HTTPServer(("127.0.0.1", 0), _Ollama)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    real_connect = socket.socket.connect
    remote = []

    def guarded(self, addr):
        if isinstance(addr, tuple) and addr[0] not in ("127.0.0.1", "::1", "localhost"):
            remote.append(addr)
            raise OSError("test: only loopback")
        return real_connect(self, addr)
    socket.socket.connect = guarded
    try:
        with Vault():
            lane = SC.Lane(f"http://127.0.0.1:{srv.server_address[1]}", "qwen3:14b", 16384, "")
            p = W.plan("meeting.md", lane=lane)
            check("the real /api/chat call works against an Ollama-shaped server",
                  not p.reason_empty and len(p.changes) == 2, p.reason_empty)
            check("it went to /api/chat with the schema, and nowhere else",
                  [s[0] for s in _Ollama.seen] == ["/api/chat", "/api/chat"]
                  and all(s[1]["format"]["type"] == "object" for s in _Ollama.seen)
                  and remote == [])
    finally:
        socket.socket.connect = real_connect
        srv.shutdown()


# ------------------------------------------------------------ the patch --

def _rehearse():
    """Stand-ins built from the patches before this one, then second-card,
    then wiki. Returns (ok, error, before, after, gate_before, gate_after)."""
    import _skeleton
    import test_second_card as TS
    git = shutil.which("git")
    d = Path(tempfile.mkdtemp(prefix="jarvis-wiki-"))
    try:
        with open(d / "jarvis_hud.py", "w", encoding="utf-8", newline="\n") as f:
            f.write(TS._stand_in())
        (d / "jarvis_gate.py").write_text(
            _skeleton.build("ui-control-wiring.patch", target="jarvis_gate.py"), encoding="utf-8")
        for name, inc in (("note-capture.patch", ["--include=jarvis_gate.py"]),
                          ("second-card.patch", [])):
            lf = d / name
            lf.write_bytes((HERE / name).read_bytes().replace(b"\r\n", b"\n"))
            r = subprocess.run([git, "apply", *inc, str(lf)], cwd=d, capture_output=True,
                               text=True)
            if r.returncode != 0:
                return False, f"{name}: {r.stderr}", "", "", "", ""
        before = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        gate_before = (d / "jarvis_gate.py").read_text(encoding="utf-8")
        lf = d / "wiki.patch"
        lf.write_bytes((HERE / "wiki.patch").read_bytes().replace(b"\r\n", b"\n"))
        after = gate_after = ""
        for args in (["apply", "--check"], ["apply"], ["apply", "--check", "--reverse"]):
            r = subprocess.run([git, *args, str(lf)], cwd=d, capture_output=True, text=True)
            if r.returncode != 0:
                return False, f"git {' '.join(args)}: {r.stderr}", before, "", gate_before, ""
            if args == ["apply"]:
                after = (d / "jarvis_hud.py").read_text(encoding="utf-8")
                gate_after = (d / "jarvis_gate.py").read_text(encoding="utf-8")
        # Both patches off again, newest first: second-card must still reverse.
        for name in ("wiki.patch", "second-card.patch"):
            r = subprocess.run([git, "apply", "--reverse", str(d / name)], cwd=d,
                               capture_output=True, text=True)
            if r.returncode != 0:
                return False, f"reverse {name}: {r.stderr}", before, after, gate_before, gate_after
        return True, "", before, after, gate_before, gate_after
    finally:
        shutil.rmtree(d, ignore_errors=True)


def t_the_patch():
    if not shutil.which("git"):
        return check("SKIP - git is not installed", True)
    ok, err, before, after, gb, ga = _rehearse()
    check("wiki.patch applies after second-card.patch to what the earlier patches wrote, "
          "reverses, and second-card still reverses after it", ok, err)
    if not ok:
        return
    i = after.index('if path in ("/api/wiki", "/api/wiki/ingest"):')
    w = after[i:i + 1800]
    check("GET /api/wiki and /api/wiki/ingest check origin and token",
          "_origin_ok(self)" in w and "_token_ok(self)" in w)
    check("GET /api/wiki answers status(); ?id= answers ingest_status",
          "jarvis_wiki.status()" in w and "jarvis_wiki.ingest_status(wid)" in w)
    i = after.index('if route == "/api/wiki/ingest":')
    w = after[i:i + 1600]
    check("POST /api/wiki/ingest checks origin and token and hands the body over",
          "_origin_ok(self)" in w and "_token_ok(self)" in w and "jarvis_wiki.handle_post(body)" in w)
    check("the routes sit after second-card's",
          after.index('if path == "/api/second-card":') < after.index('"/api/wiki"')
          and after.index('if route == "/api/second-card":')
          < after.index('if route == "/api/wiki/ingest":'))
    check("second-card's blocks are untouched",
          before[before.index('if route == "/api/second-card":'):].split("\n\n")[0]
          == after[after.index('if route == "/api/second-card":'):].split("\n\n")[0])
    check("the approval notice knows wiki_update stays on this PC",
          '"wiki_update": ("yes", "local",' in ga and '"second_card_enable"' in ga)
    # The added GET block is valid Python inside a method.
    block = after[after.index('        if path in ("/api/wiki"'):
                  after.index('        if path in ("/api/memory/pending"')]
    try:
        compile("def f(self, path):\n" + block, "<patched block>", "exec")
        check("the patched GET block compiles", True)
    except SyntaxError as exc:
        check("the patched GET block compiles", False, str(exc))
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    names = [l.strip().strip("'") for l in ps1[start:ps1.index("\n)", start)].splitlines()
             if l.strip().startswith("'")]
    check("apply-patches.ps1 applies wiki.patch last, after second-card.patch",
          names and names[-1] == "wiki.patch"
          and names.index("second-card.patch") < names.index("wiki.patch"))
    check("apply-patches.ps1 copies jarvis_wiki.py in",
          "'jarvis_wiki.py'" in ps1[ps1.index("$SHIPPED = @("):])
    import _where
    check("_where.SHIPPED has it too", "jarvis_wiki.py" in _where.SHIPPED)


def t_the_toml():
    toml = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check('the shipped toml has wiki_update = "ask", with a comment',
          re.search(r'^wiki_update\s*=\s*"ask"', toml, re.M) is not None
          and "Jarvis Wiki" in toml[:toml.index("wiki_update")].rsplit("---", 1)[-1])
    try:
        import jarvis_framework as fw
        got = fw.action_tier("wiki_update")
        check("jarvis_framework reads it as 'ask' from the shipped file", got == "ask", got)
    except Exception as exc:
        check("jarvis_framework reads it", False, repr(exc))


def t_the_second_card_switch_says_what_it_does():
    what = next(f["what"] for f in SC.FEATURES if f["id"] == "wiki")
    check("the wiki switch no longer says the builder is not made",
          "not made" not in what and "Jarvis Wiki/Sources" in what)


def t_the_fixture():
    import gen_wiki_cases as G
    rc = G.main(["--check"])
    check("jarvis-desktop/tests/fixtures/wiki-cases.json equals a fresh run", rc == 0,
          "run python3 tools/gen_wiki_cases.py")
    data = json.loads(G.FIXTURE.read_text(encoding="utf-8"))["cases"]
    states = {x["state"] for x in data["status_ready"]["body"]["sources"]}
    check("the ready case has every source state",
          states == {"new", "changed", "in_wiki", "too_big", "unreadable"}, states)
    check("each job state is there",
          {data[k]["body"].get("state") for k in data if k.startswith("job_")}
          >= {"reading", "waiting", "done", "refused", "failed"})


def t_the_real_file():
    if missing("jarvis_hud.py"):
        return check("SKIP - no jarvis_hud.py here; the rehearsal above is the proof", True)
    s = (BACKEND / "jarvis_hud.py").read_text(encoding="utf-8")
    check("the backend's jarvis_hud.py has /api/wiki (wiki.patch applied)", '"/api/wiki"' in s)


if __name__ == "__main__":
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
