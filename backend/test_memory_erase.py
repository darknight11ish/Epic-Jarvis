"""test_memory_erase.py - "Erase the words" wipes a fact's words for good.

    python3 backend/test_memory_erase.py

The owner's decision of 2026-09-24 (CLAUDE.md): Forget hides a fact and keeps
its history; "Erase the words" wipes its text for good, and its search
entry, and keeps only the dates, so the history shows that something was
erased. rebuilt/jarvis_memory.py (MemoryStore.erase, handle_erase) does the
work; memory-erase.patch routes POST /api/memory/erase to it.

What is proved here, against real SQLite files in a temp folder:

  * a current fact and an already-forgotten one can both be erased; the row,
    its id and its dates stay, the text is the marker, `erased_at` is set;
  * it is found by no word and no meaning afterwards (facts_fts, facts_vec);
  * the words are gone from the FILE - memory.db and memory.db-wal read as
    raw bytes - not only from the query results;
  * every copy of the words in the review queue goes too;
  * the route: token and origin like forget, one integer id and nothing
    else, 404 in its own words, and a reply that never carries the words;
  * no event on the bus (forget sends none either) and an audit line with
    the id only.

No pytest, no network, no model.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import textwrap
import time
import traceback
import types
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("rebuilt/jarvis_memory.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-erase-"))
try:
    import jarvis_memory as M
except ImportError:
    sys.path.append(str(REPO / "backend" / "rebuilt"))
    import jarvis_memory as M

PASSED, FAILED = [], []

#: A word no other fact, file header or SQLite page will ever hold, so
#: finding it in the raw bytes can only mean the erased words survived.
SECRET = "Zorblaxine"
WORDS = f"The owner is allergic to {SECRET} and keeps the pills in the blue drawer"
HASH = "c0ffee" * 10 + "abcd"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class Emb(M.Embedder):
    """Semantic, so the vector path is really taken when sqlite-vec is here."""
    name, dim, semantic = "erase-test-v1", 8, True

    def embed(self, texts):
        return [[1.0 + ((hash(t) >> i) & 1) for i in range(self.dim)] for t in texts]


def fresh(name: str):
    d = _TMP / name
    d.mkdir(parents=True, exist_ok=True)
    st = M.MemoryStore(path=d / "memory.db", embedder=Emb())
    M._store = st
    return st


def filler(st, n=25):
    for i in range(n):
        st.add(f"filler fact number {i} about tea and biscuits")


def add_secret(st, **kw):
    meta = {"auto": True, "proposal_source": "conversation", "device": "phone",
            "provenance": "typed", "conversation_id": "conv-7f3a", "message_hash": HASH,
            "tainted": False, "saved_at": 1790000000.0, "confidence": 0.9, "proposal_id": 3,
            "note": f"said about {SECRET}"}
    return st.add(WORDS, source="auto", meta=meta, **kw)


def raw_hits(st, needle: str) -> dict:
    """How often `needle` (any case) is in memory.db and memory.db-wal."""
    out = {}
    for suffix in ("", "-wal"):
        p = Path(str(st.path) + suffix)
        data = p.read_bytes().lower() if p.exists() else b""
        out["memory.db" + suffix] = data.count(needle.lower().encode("utf-8"))
    return out


def fts_ids(st, word):
    with closing(st._connect()) as c:
        return [r[0] for r in c.execute(
            "SELECT rowid FROM facts_fts WHERE facts_fts MATCH ?", (f'"{word}"',))]


def fts_ok(st):
    with closing(st._connect()) as c:
        try:
            c.execute("INSERT INTO facts_fts(facts_fts) VALUES('integrity-check')")
            return True
        except sqlite3.Error as exc:
            return str(exc)


def proposals(st):
    """The review queue, as memory-safety, memory-intake and the owner's
    jarvis_extract leave it (the same stand-in schema test_auto_learn uses)."""
    with closing(st._connect()) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS proposals (
            id INTEGER PRIMARY KEY, text TEXT NOT NULL, replaces TEXT,
            confidence REAL, source TEXT, created REAL,
            state TEXT NOT NULL DEFAULT 'pending', decided REAL, fact_id INTEGER,
            replaces_id INTEGER, replaces_text TEXT, kept_both REAL)""")


def queue(st, text, **kw):
    cols = ["text", "created"] + list(kw)
    with closing(st._connect()) as c:
        return c.execute(f"INSERT INTO proposals ({', '.join(cols)}) VALUES "
                         f"({', '.join('?' * len(cols))})",
                         [text, time.time()] + list(kw.values())).lastrowid


def prow(st, pid):
    with closing(st._connect()) as c:
        return dict(c.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone())


# ------------------------------------------------------------------ the store

def t_erase_a_current_fact():
    st = fresh("current")
    filler(st)
    fid = add_secret(st)
    before = st.get(fid)
    check("sanity: the word is found before erasing", fid in fts_ids(st, SECRET))
    out = st.erase(fid)
    after = st.get(fid)
    check("erase() answers with the id and when, never the words",
          out and out["id"] == fid and out["erased_at"] and SECRET not in json.dumps(out)
          and out["retired_now"] is True and out["already_erased"] is False, out)
    check("the row stays, with the marker for text",
          after is not None and after["text"] == M.ERASED_TEXT, after)
    check("erased_at is recorded", after["erased_at"] == out["erased_at"], after)
    check("it is retired as retire() stamps it: valid_to and retired_at now",
          after["valid_to"] == after["retired_at"] == out["erased_at"], after)
    check("created, valid_from, source and id are kept (the dates stay)",
          after["created"] == before["created"] and after["valid_from"] == before["valid_from"]
          and after["source"] == "auto", after)
    meta = json.loads(after["meta"])
    check("meta keeps dates, ids and where it came from",
          meta == {"auto": True, "proposal_source": "conversation", "device": "phone",
                   "provenance": "typed", "tainted": False, "saved_at": 1790000000.0,
                   "confidence": 0.9, "proposal_id": 3}, meta)
    check("meta loses the message hash, the conversation id and any other words",
          "message_hash" not in meta and "conversation_id" not in meta and "note" not in meta)
    check("no word search finds it any more", fts_ids(st, SECRET) == [] and
          fts_ids(st, "drawer") == [] and fts_ids(st, "erased") == [])
    check("search() does not return it, retired included",
          all(h["id"] != fid for h in st.search(f"allergic {SECRET} pills drawer", k=50,
                                                 include_retired=True)))
    check("it is not current, so it is never recalled",
          all(f["id"] != fid for f in st.current_facts()))
    check("the word index is still sound", fts_ok(st) is True, fts_ok(st))
    check("edit() refuses it (it is retired history now)", st.edit(fid, "new words") is False)
    past = [f for f in st.known_at(out["erased_at"] - 0.001) if f["id"] == fid]
    check("'what did Jarvis know then' still lists it - erased, never the words",
          len(past) == 1 and past[0]["text"] == M.ERASED_TEXT and past[0]["erased_at"], past)
    chain = st.timeline("filler fact number 3")
    check("the timeline rows carry erased_at (a column, so every reader sees it)",
          all("erased_at" in h for h in chain), chain[:1])


def t_erase_a_fact_already_forgotten():
    st = fresh("retired")
    filler(st)
    fid = add_secret(st)
    when = time.time() - 86400 * 30
    st.retire(fid, valid_to=when)
    was = st.get(fid)
    out = st.erase(fid)
    now = st.get(fid)
    check("a forgotten fact can be erased", out and now["text"] == M.ERASED_TEXT, now)
    check("its dates are the ones Forget gave it, untouched",
          now["valid_to"] == was["valid_to"] and now["retired_at"] == was["retired_at"]
          and out["retired_now"] is False, (was, now))
    check("its words are gone from search too", fts_ids(st, SECRET) == [])


def t_erase_a_lease():
    st = fresh("lease")
    fid = add_secret(st)
    with closing(st._connect()) as c:
        c.execute("UPDATE facts SET valid_to=? WHERE id=?", (time.time() + 86400 * 60, fid))
    check("sanity: a fact ending in two months is current", any(
        f["id"] == fid for f in st.current_facts()))
    out = st.erase(fid)
    check("an erased lease is retired now, not in two months",
          out["retired_now"] and all(f["id"] != fid for f in st.current_facts()), st.get(fid))


def t_erase_twice_and_unknown():
    st = fresh("twice")
    filler(st, 5)
    fid = add_secret(st)
    first = st.erase(fid)
    second = st.erase(fid)
    check("erasing again changes nothing: the first erased_at stays",
          second["already_erased"] is True and second["erased_at"] == first["erased_at"]
          and st.get(fid)["text"] == M.ERASED_TEXT, second)
    check("and leaves the word index sound", fts_ok(st) is True, fts_ok(st))
    check("no such fact: None", st.erase(987654) is None)


def t_the_vector_goes():
    st = fresh("vector")
    filler(st, 5)
    fid = add_secret(st)
    st.erase(fid)
    status = st.status()
    check("status counts it as erased, and not as waiting for a vector",
          status["erased"] == 1 and status["unembedded"] == (0 if st._vec_ok else 5), status)
    check("backfill never embeds the marker", st.backfill_embeddings() == 0
          and st.get(fid)["embedded"] == 0)
    if not st._vec_ok:
        return check("SKIP - sqlite-vec is not installed here, so there is no vector table "
                     "(the owner's PC has it; the DELETE is the same line edit() uses)", True)
    with closing(st._connect()) as c:
        n = c.execute("SELECT COUNT(*) FROM facts_vec WHERE fact_id=?", (fid,)).fetchone()[0]
    check("its meaning vector is deleted", n == 0, n)


def t_the_file_holds_no_words():
    """The point of the feature: not unreachable, GONE. Read the files."""
    st = fresh("bytes")
    filler(st, 40)
    proposals(st)
    fid = add_secret(st)
    # Long enough to spill onto an overflow page, the case secure_delete is for.
    long_id = st.add(f"{SECRET} " + "a long note about the drawer " * 200, source="remember")
    queue(st, WORDS, state="accepted", fact_id=fid, source="conversation")
    queue(st, "The owner is allergic to amoxicillin", state="pending", replaces_id=fid,
          replaces=WORDS, replaces_text=WORDS, source="conversation")
    filler(st, 40)
    hits = raw_hits(st, SECRET)
    check("sanity: before erasing, the word IS in the file (so the test can see it)",
          sum(hits.values()) > 0, hits)
    st.erase(fid)
    st.erase(long_id)
    hits = raw_hits(st, SECRET)
    check("after erasing, the word is in neither memory.db nor memory.db-wal",
          sum(hits.values()) == 0, hits)
    check("nor is its porter stem (what the word index stored)",
          sum(raw_hits(st, "zorblaxin").values()) == 0)
    check("nor the message hash the meta held", sum(raw_hits(st, HASH).values()) == 0)
    check("the other facts are all still there",
          len(st.current_facts()) == 80 and fts_ids(st, "biscuits"), st.status())
    # An open reader stops the log being truncated; erase() says so rather
    # than claiming the file is clean.
    st2 = fresh("bytes-reader")
    fid2 = add_secret(st2)
    reader = sqlite3.connect(st2.path, isolation_level=None)
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT COUNT(*) FROM facts").fetchone()
        out = st2.erase(fid2)
        check("a reader mid-read: erased, but file_clean is false and the reply says why",
              out["file_clean"] is False and M.handle_erase({"id": fid2})[1]["file_clean"] is False)
    finally:
        reader.execute("COMMIT")
        reader.close()
    out = M.handle_erase({"id": fid2})
    check("once the reader is done, erasing again cleans the file",
          out[1]["file_clean"] is True and sum(raw_hits(st2, SECRET).values()) == 0, out)


def t_copies_in_the_review_queue():
    st = fresh("queue")
    proposals(st)
    fid = add_secret(st)
    other = st.add("The owner likes Helix")
    became = queue(st, WORDS, state="accepted", fact_id=fid, source="conversation")
    correction = queue(st, "The owner is allergic to amoxicillin", state="pending",
                       replaces_id=fid, replaces="the allergy fact", replaces_text=WORDS,
                       source="conversation")
    retire_card = queue(st, "Stop using this fact? It was part of 5 answers you marked wrong.",
                        state="pending", replaces_id=fid, replaces=WORDS, replaces_text=WORDS,
                        source="feedback_retire")
    retired_by_card = queue(st, "Stop using this fact? It was part of 6 answers ...",
                            state="accepted", fact_id=fid, replaces_id=fid,
                            replaces_text=WORDS, source="feedback_retire")
    rejected = queue(st, WORDS.lower(), state="rejected", source="conversation")
    waiting = queue(st, "  " + WORDS + " ", state="pending", source="remember")
    unrelated = queue(st, "The owner likes Helix", state="accepted", fact_id=other)
    out = st.erase(fid)
    b, c_, r, rb, rj, w, u = (prow(st, p) for p in (became, correction, retire_card,
                                                    retired_by_card, rejected, waiting, unrelated))
    check("the card that became the fact: text erased", b["text"] == M.ERASED_TEXT, b)
    check("a correction that would replace it: its words for the old fact erased, the "
          "new fact's words kept, and it still waits for a decision",
          c_["replaces_text"] == M.ERASED_TEXT and c_["replaces"] == M.ERASED_TEXT
          and c_["text"].endswith("amoxicillin") and c_["state"] == "pending", c_)
    check("a 'retire this?' card still waiting about it: words erased and turned down "
          "(the fact is retired already)",
          r["replaces_text"] == M.ERASED_TEXT and r["state"] == "rejected" and r["decided"], r)
    check("a decided 'retire this?' card keeps its reason (it has no words of the fact)",
          rb["text"].startswith("Stop using") and rb["replaces_text"] == M.ERASED_TEXT, rb)
    check("a discarded card with the same words: erased",
          rj["text"] == M.ERASED_TEXT and rj["state"] == "rejected", rj)
    check("a waiting card with the same words: erased and turned down",
          w["text"] == M.ERASED_TEXT and w["state"] == "rejected", w)
    check("an unrelated card is untouched", u["text"] == "The owner likes Helix"
          and u["state"] == "accepted", u)
    check("erase() says how many copies it changed, never what they said",
          out["copies"] >= 6 and SECRET not in json.dumps(out), out)


def t_no_queue_table_is_fine():
    st = fresh("noqueue")
    fid = add_secret(st)
    out = st.erase(fid)
    check("a store with no review queue yet: erased, 0 copies", out["copies"] == 0
          and st.get(fid)["text"] == M.ERASED_TEXT, out)


def t_the_lists_show_it_as_erased():
    st = fresh("lists")
    filler(st, 3)
    fid = add_secret(st)
    st.erase(fid)
    # The /api/memory/facts and /api/memory/export routes are `SELECT *`
    # (memory-pane.patch, bitemporal.patch): the marker and the flag reach
    # both apps with no route change.
    with closing(st._connect()) as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM facts ORDER BY valid_from DESC")]
    row = next(r for r in rows if r["id"] == fid)
    check("the facts list row: marker text and erased_at, never the words",
          row["text"] == M.ERASED_TEXT and row["erased_at"] and SECRET not in json.dumps(rows))
    try:
        import jarvis_auto_learn as A
    except Exception as exc:
        return check(f"SKIP - jarvis_auto_learn.py not importable here ({type(exc).__name__})", True)
    fw = sys.modules.get("jarvis_framework")
    if fw is not None:
        fw.CONFIG_DIR = _TMP
    listed = A.list_auto(store=st)
    check("'Saved automatically' lists current facts only, so the erased one is gone",
          all(f["id"] != fid for f in listed["facts"]) and SECRET not in json.dumps(listed),
          listed)


def t_no_event_and_the_audit_line_has_the_id_only():
    st = fresh("events")
    fid = add_secret(st)
    published, audited = [], []
    ev = types.ModuleType("jarvis_events")
    ev.BUS = types.SimpleNamespace(publish=lambda kind, data: published.append((kind, data)),
                                   note=lambda *a, **k: published.append(a))
    real_ev = sys.modules.get("jarvis_events")
    sys.modules["jarvis_events"] = ev
    real_fw = M.fw
    M.fw = types.SimpleNamespace(audit_log=lambda e, d=None: audited.append((e, d)))
    try:
        st.erase(fid)
    finally:
        M.fw = real_fw
        if real_ev is not None:
            sys.modules["jarvis_events"] = real_ev
        else:
            sys.modules.pop("jarvis_events", None)
    check("nothing on the event bus - the same as Forget, which sends none",
          published == [], published)
    check("one audit line, the id only", audited == [("memory.erased", {"id": fid})], audited)


# ------------------------------------------------------------------ the route

def _route_block():
    import _stack
    text, log = _stack.stand_in("jarvis_hud.py")
    check("the whole jarvis_hud.py stack builds", text is not None, "\n".join(log or [])[-400:])
    if text is None:
        return None, None
    i = text.index('        if route == "/api/memory/erase":')
    j = text.index('        if route in ("/api/memory/forget"', i)
    return text, textwrap.dedent(text[i:j])


class _Handler:
    def __init__(self):
        self.sent = None

    def _send(self, code, body):
        self.sent = (code, body)
        return self.sent


def _call(block, raw, *, origin=True, token=True, memory=True, module=None):
    ns = {"_origin_ok": lambda s: origin, "_token_ok": lambda s: token, "MEMORY": memory,
          "_read_body": lambda s: raw, "json": json, "jarvis_memory": module or M}
    exec(compile("def handle(self, route):\n" + textwrap.indent(block, "    "),
                 "<memory-erase route>", "exec"), ns)
    h = _Handler()
    ns["handle"](h, "/api/memory/erase")
    return h.sent


def t_the_route():
    text, block = _route_block()
    if block is None:
        return
    check("the erase route sits right above forget's, with its own checks",
          text.index('if route == "/api/memory/erase":')
          < text.index('if route in ("/api/memory/forget"'))
    st = fresh("route")
    filler(st, 3)
    fid = add_secret(st)
    check("another site's page: 403, nothing erased",
          _call(block, b'{"id": %d}' % fid, origin=False)[0] == 403
          and st.get(fid)["text"] == WORDS)
    check("no or a wrong token: 401, nothing erased",
          _call(block, b'{"id": %d}' % fid, token=False)[0] == 401
          and st.get(fid)["text"] == WORDS)
    check("memory not running: 503", _call(block, b'{"id": 1}', memory=False)[0] == 503)
    for raw, why in ((b"not json", "not JSON"), (b"[1, 2]", "a list"),
                     (b'{"ids": [%d]}' % fid, "a list of ids"),
                     (b'{"id": "%d"}' % fid, "an id in quotes"), (b'{"id": true}', "true"),
                     (b'{"id": %d, "all": true}' % fid, "an extra key")):
        code, body = _call(block, raw)
        check(f"{why}: 400, nothing erased", code == 400 and st.get(fid)["text"] == WORDS,
              (code, body))
    code, body = _call(block, b'{"id": 99999}')
    check("no such fact: 404, saying so in a way the apps can tell from a missing route",
          code == 404 and body.get("reason") == "no_such_fact", (code, body))
    code, body = _call(block, b'{"id": %d}' % fid)
    check("one fact: 200, ok, erased",
          code == 200 and body["ok"] is True and body["id"] == fid
          and st.get(fid)["text"] == M.ERASED_TEXT, (code, body))
    check("the reply never carries the words (forget's reply has a 'was'; this has not)",
          "was" not in body and SECRET not in json.dumps(body), body)
    old = types.SimpleNamespace(store=M.store)          # a jarvis_memory.py from before
    code, body = _call(block, b'{"id": %d}' % fid, module=old)
    check("an older jarvis_memory.py with no erase: 501 in words, not a crash",
          code == 501 and "jarvis_memory.py" in body["error"], (code, body))


def t_listed_where_it_must_be():
    import _stack
    import _where
    names = [str(p).replace("\\", "/").split("/")[-1] for p in _stack.order()]
    check("memory-erase.patch is in apply-patches.ps1's order, after auto-learn",
          "memory-erase.patch" in names
          and names.index("memory-erase.patch") > names.index("auto-learn.patch"), names[-3:])
    check("the store that does the work is shipped whole",
          "rebuilt/jarvis_memory.py" in _where.SHIPPED)


def t_the_patch_applies_forwards_and_backwards():
    import shutil
    import subprocess
    import _stack
    git = shutil.which("git")
    if not git:
        return check("SKIP - git is not installed", True)
    order = _stack.order()
    at = order.index("memory-erase.patch")
    text, log = _stack.stand_in("jarvis_hud.py", order[:at])
    check("jarvis_hud.py: the stack before memory-erase.patch builds", text is not None)
    if text is None:
        return
    check("every hunk of it found its context (none made up)",
          not any("memory-erase" in line for line in _stack.stand_in("jarvis_hud.py")[1]))
    d = Path(tempfile.mkdtemp(prefix="jarvis-erase-patch-", dir=_TMP))
    (d / "jarvis_hud.py").write_text(text, encoding="utf-8", newline="\n")
    (d / "p.patch").write_bytes((HERE / "memory-erase.patch").read_bytes().replace(b"\r\n", b"\n"))
    for extra in (["--check"], [], ["--check", "--reverse"], ["--reverse"], []):
        r = subprocess.run([git, "apply", *extra, "p.patch"], cwd=d, capture_output=True,
                           text=True)
        check(f"git apply {' '.join(extra) or '(forwards)'} memory-erase.patch",
              r.returncode == 0, r.stderr.strip())
    full = _stack.stand_in("jarvis_hud.py", order[:at + 1])[0]
    check("forwards gives the stack's own text",
          (d / "jarvis_hud.py").read_text(encoding="utf-8") == full)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
