#!/usr/bin/env python3
"""Writes jarvis-desktop/tests/fixtures/wiki-cases.json: what the wiki
builder's three routes really answer, in named situations.

    python3 tools/gen_wiki_cases.py            # write the file
    python3 tools/gen_wiki_cases.py --check    # compare only

Every case is backend/jarvis_wiki.py's own status(), ingest() and
ingest_status(), run against a real folder made for the purpose (a vault with
a `.obsidian` folder and `Jarvis Wiki/Sources` holding real files). What is
replaced, and only this:

  - the second card. "off" cases are jarvis_second_card.status()'s real
    words, from tools/gen_second_card_cases.py's World (one graphics card);
    "ready" cases hand jarvis_wiki a Lane like the one lane_for("wiki")
    returns on a 12 GB card.
  - the model: an injected call that answers in Ollama's /api/chat shape.
  - the approval gate: an injected check that says yes, no, or snapshots the
    job while its card is up.
  - the clock and the random job id, fixed, so the file is the same on every
    run; and the made-up vault's folder, shown as /home/owner/Vault.

The desktop's page tests (jarvis-desktop/tests/wiki.mjs) and the phone's JVM
tests (WikiContractTest.kt) read this one file. backend/test_wiki.py fails
when it differs from a fresh run.
"""
import json
import os
import shutil
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FIXTURE = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "wiki-cases.json"
for p in (BACKEND, BACKEND / "rebuilt", ROOT / "tools"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import jarvis_second_card as SC  # noqa: E402
import jarvis_wiki as W  # noqa: E402

SHOWN_VAULT = "/home/owner/Vault"
NOW = 1790000000.0
DAY = "2026-09-24"
LANE = SC.Lane(url="http://127.0.0.1:11435", model="qwen3:14b", num_ctx=16384,
               why="Wiki builder: qwen3:14b on the NVIDIA GeForce RTX 2060")

ANALYSIS = {"summary": "Notes from the allotment society's spring meeting.",
            "entities": [{"name": "Allotment Society", "kind": "organisation",
                          "why": "who met"},
                         {"name": "Margaret Hale", "kind": "person", "why": "the new chair"}],
            "existing_pages": ["Allotment Society"],
            "contradictions": [{"page": "Allotment Society",
                                "what": "the page says meetings are monthly; the notes say "
                                        "every two weeks"}]}
PAGES = {"pages": [
    {"action": "update", "path": "Pages/Allotment Society.md",
     "summary": "The allotment society: who runs it and when it meets.",
     "body": "The society meets every two weeks (it used to be monthly). Chair: "
             "[[Margaret Hale]]."},
    {"action": "create", "path": "Pages/Margaret Hale.md",
     "summary": "Chair of the allotment society since spring.",
     "body": "Chair of the [[Allotment Society]] since the spring meeting."}]}


def answer(obj) -> dict:
    """An /api/chat answer, in Ollama's shape."""
    return {"model": LANE.model, "message": {"role": "assistant", "content": json.dumps(obj)},
            "done": True, "done_reason": "stop", "prompt_eval_count": 900}


def fake_call(lane, body):
    return answer(ANALYSIS if body["format"] is W.ANALYSIS_SCHEMA else PAGES)


class Verdict:
    def __init__(self, allowed, outcome):
        self.allowed, self.outcome, self.tier, self.reason = allowed, outcome, "ask", ""


class Vault:
    """A real vault on disk, with the wiki folder and a few sources."""

    def __init__(self, *, wiki=True):
        self.dir = Path(tempfile.mkdtemp(prefix="jarvis-wiki-cases-"))
        (self.dir / ".obsidian").mkdir()
        self.wiki = self.dir / W.WIKI_DIR
        if wiki:
            src = self.wiki / W.SOURCES_DIR
            src.mkdir(parents=True)
            (src / "spring-meeting.md").write_text(
                "# Spring meeting\n\nMargaret Hale was elected chair. The society will now "
                "meet every two weeks.\n", encoding="utf-8")
            (src / "seed-list.txt").write_text("Beans, peas, two kinds of kale.\n",
                                               encoding="utf-8")
            (src / "planting-dates.md").write_text("Sow broad beans in late October.\n",
                                                   encoding="utf-8")
            (src / "plot-map.pdf").write_bytes(b"%PDF-1.4 not read yet")
            (src / "old-minutes.md").write_text("x " * 40000, encoding="utf-8")
            pages = self.wiki / W.PAGES_DIR
            pages.mkdir()
            (pages / "Allotment Society.md").write_text(
                '---\nsources: ["seed-list.txt"]\n---\n\nMeets monthly.\n', encoding="utf-8")
            (self.wiki / W.INDEX_NAME).write_text(
                "# Jarvis Wiki\n\n- [[Allotment Society]] - the allotment society\n",
                encoding="utf-8")
        self._env = os.environ.get("JARVIS_OBSIDIAN_VAULT")
        os.environ["JARVIS_OBSIDIAN_VAULT"] = str(self.dir)

    def add_seed_list(self):
        """seed-list.txt added to the wiki earlier and unchanged since;
        planting-dates.md added earlier and edited since."""
        sha = W._sha((self.wiki / W.SOURCES_DIR / "seed-list.txt").read_bytes())
        (self.wiki / W.CACHE_NAME).write_text(json.dumps(
            {"version": 1, "sources": {
                "seed-list.txt": {"sha256": sha, "added": "2026-09-20", "pages": []},
                "planting-dates.md": {"sha256": "0" * 64, "added": "2026-09-21",
                                      "pages": []}}}), encoding="utf-8")
        (self.wiki / W.LOG_NAME).write_text(
            "## [2026-09-20] ingest | seed-list.txt\n\n- created [[Allotment Society]]\n",
            encoding="utf-8")

    def close(self):
        if self._env is None:
            os.environ.pop("JARVIS_OBSIDIAN_VAULT", None)
        else:
            os.environ["JARVIS_OBSIDIAN_VAULT"] = self._env
        shutil.rmtree(self.dir, ignore_errors=True)


def _fix(obj, vault: Vault):
    """The made-up vault's real folder, shown as SHOWN_VAULT."""
    real = os.path.realpath(str(vault.dir))
    text = json.dumps(obj)
    text = text.replace(json.dumps(real)[1:-1], SHOWN_VAULT)
    out = json.loads(text)
    if isinstance(out, dict) and isinstance(out.get("folder"), str):
        out["folder"] = out["folder"].replace("\\", "/")
    return out


def _off_why() -> str:
    import gen_second_card_cases as G
    with G.World(G.SMI["one_card"]):
        return W._off_why()


def cases() -> dict:
    off = _off_why()
    saved = (W.time, W.secrets, W._today, W._audit, W._off_why)
    W.time = types.SimpleNamespace(time=lambda: NOW, strftime=lambda f: "20260924-120000")
    W.secrets = types.SimpleNamespace(token_hex=lambda n: "0" * (2 * n))
    W._today = lambda: DAY
    W._audit = lambda what, detail: None
    # Every "off" answer is the second card's words for a one-card PC, never
    # whatever this machine's own nvidia-smi says.
    W._off_why = lambda: off
    out = {}
    try:
        def run(name, fn, *, wiki=True, seeded=True):
            W._reset_for_tests()
            v = Vault(wiki=wiki)
            try:
                if wiki and seeded:
                    v.add_seed_list()
                out[name] = _fix(fn(v), v)
            finally:
                v.close()
                W._reset_for_tests()

        ready = lambda: LANE  # noqa: E731
        none = lambda: None  # noqa: E731
        # GET /api/wiki
        run("status_off", lambda v: {"status": 200, "body": W.status(lane_for=none,
                                                                     why=lambda: off)})
        run("status_ready", lambda v: {"status": 200, "body": W.status(lane_for=ready)})
        run("status_no_wiki_folder", lambda v: {"status": 200, "body": W.status(lane_for=ready)},
            wiki=False)

        def running(v):
            W.ingest("spring-meeting.md", lane_for=ready, call=fake_call,
                     spawn=lambda fn: None)
            return {"status": 200, "body": W.status(lane_for=ready)}
        run("status_running", running)

        # POST /api/wiki/ingest
        def started(v):
            code, body = W.ingest("spring-meeting.md", lane_for=ready, call=fake_call,
                                  spawn=lambda fn: None)
            return {"status": code, "body": body}
        run("ingest_started", started)
        run("ingest_off", lambda v: dict(zip(("status", "body"), W.ingest(
            "spring-meeting.md", lane_for=none))))
        run("ingest_in_wiki", lambda v: dict(zip(("status", "body"), W.ingest(
            "seed-list.txt", lane_for=ready))))
        run("ingest_too_big", lambda v: dict(zip(("status", "body"), W.ingest(
            "old-minutes.md", lane_for=ready))))
        run("ingest_unreadable", lambda v: dict(zip(("status", "body"), W.ingest(
            "plot-map.pdf", lane_for=ready))))

        def busy(v):
            W.ingest("spring-meeting.md", lane_for=ready, call=fake_call, spawn=lambda fn: None)
            code, body = W.ingest("seed-list.txt", lane_for=ready, call=fake_call,
                                  spawn=lambda fn: None)
            return {"status": code, "body": body}
        run("ingest_busy", busy, seeded=False)

        # GET /api/wiki/ingest?id= - one job, in each state it can be in.
        def job(gate):
            def fn(v):
                code, body = W.ingest("spring-meeting.md", lane_for=ready, call=fake_call,
                                      gate_check=gate, spawn=lambda f: f())
                code, body = W.ingest_status(body["id"])
                return {"status": code, "body": body}
            return fn

        def job_reading(v):
            _, body = W.ingest("spring-meeting.md", lane_for=ready, call=fake_call,
                               spawn=lambda f: None)
            return dict(zip(("status", "body"), W.ingest_status(body["id"])))
        run("job_reading", job_reading)

        seen = {}

        def gate_snapshot(action, detail, prompt):
            jid = next(iter(W._jobs))
            seen["waiting"] = W.ingest_status(jid)
            return Verdict(False, "denied")

        def job_waiting(v):
            job(gate_snapshot)(v)
            return dict(zip(("status", "body"), seen["waiting"]))
        run("job_waiting", job_waiting)
        run("job_done", job(lambda a, d, p: Verdict(True, "approved")))
        run("job_denied", job(lambda a, d, p: Verdict(False, "denied")))

        def job_failed(v):
            # The source changes while its card is up, so the write is refused.
            def gate(a, d, p):
                (v.wiki / W.SOURCES_DIR / "spring-meeting.md").write_text("edited\n",
                                                                         encoding="utf-8")
                return Verdict(True, "approved")
            return job(gate)(v)
        run("job_failed", job_failed)

        def model_refused(v):
            def bad(lane, body):
                return {"message": {"content": "not json"}, "done_reason": "stop"}
            _, body = W.ingest("spring-meeting.md", lane_for=ready, call=bad,
                               spawn=lambda f: f())
            return dict(zip(("status", "body"), W.ingest_status(body["id"])))
        run("job_model_refused", model_refused)
        run("job_unknown", lambda v: dict(zip(("status", "body"), W.ingest_status("wiki_nope"))))
    finally:
        W.time, W.secrets, W._today, W._audit, W._off_why = saved
        W._reset_for_tests()
    return out


def render() -> str:
    body = {
        "_about": ("Real answers of backend/jarvis_wiki.py's status() (GET /api/wiki), "
                   "ingest() (POST /api/wiki/ingest) and ingest_status() (GET "
                   "/api/wiki/ingest?id=), one per named case, each {status, body}, made by "
                   "tools/gen_wiki_cases.py against a real folder. The model and the "
                   "approval gate are stand-ins; the clock and job ids are fixed; the "
                   "made-up vault is shown as /home/owner/Vault. Do not edit by hand: "
                   "re-run the tool."),
        "cases": cases(),
    }
    return json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        have = FIXTURE.read_text(encoding="utf-8") if FIXTURE.is_file() else ""
        if have.replace("\r\n", "\n") != text:
            print(f"{FIXTURE.relative_to(ROOT)} is out of date: run "
                  f"python3 tools/gen_wiki_cases.py")
            return 1
        print("wiki-cases.json matches the producer.")
        return 0
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {FIXTURE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
