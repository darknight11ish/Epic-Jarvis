"""test_memory_fault.py - a broken learning check is ONE banner, not 200 cards.

    python3 backend/test_memory_fault.py

WHAT THIS FILE IS FOR (2026-11-09, the memory-card research's measured
finding). When one of automatic learning's three batch checks fails - a
damaged auto-learning.json, no local model, a cloud model name, a missing
jarvis_intake.py - after_pass used to write the SAME reason onto every
proposal in the pass, so one broken check looked like up to 200 facts waiting
for a decision. The approved replacement is one `memory-fault.json` record,
one banner in both apps, and one button, "Retry now"; the cards parked by
that fault are left out of the pending read while it is active.

What is proved here, one check at a time:

  (a) a batch check failure writes exactly ONE fault record, the cards carry
      that same reason, and the pending read's own filter leaves them out -
      including across a second pass, where the record is still one;
  (b) a genuine per-fact card still appears: a sensitive fact, and a card
      that happens to carry the fault's own reason but has a sensitive label;
  (c) "Retry now" clears the fault only when the check passes, and writes no
      memory and approves nothing;
  (d) a retry that still fails keeps the fault, counts the try and says why;
  (e) the fault record holds no fact's words - only the check's own sentence,
      a time and a count;
  plus the honesty case: a record that cannot be written hides nothing (the
  cards are shown instead, with no banner to explain a silence), and the
  owner's own "automatic learning is off" is never a fault.

Runs anywhere, no model, no network, no browser: real jarvis_auto_learn,
jarvis_intake, jarvis_chat_log and the rebuilt jarvis_memory. The pending read
itself is proved by cutting auto-learn.patch's own hunk out of the patch file,
applying it with `git apply` to the published base
(jarvis-backend/jarvis_extract.py) and calling the `pending()` that results -
nothing is typed twice and nothing is pinned by source text.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import traceback
import types
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-memory-fault-"))
fw = sys.modules.get("jarvis_framework")
if fw is None:
    fw = types.ModuleType("jarvis_framework")
    fw.CONFIG_DIR = _TMP
    fw.LOG_DIR = _TMP
    fw.load_framework = lambda: {}
    fw.audit_log = lambda *a, **k: None
    fw.action_tier = lambda action: "ask"
    sys.modules["jarvis_framework"] = fw

try:
    import jarvis_memory as M
except ImportError:
    sys.path.append(str(REPO / "backend" / "rebuilt"))
    import jarvis_memory as M
if str(REPO / "backend" / "rebuilt") not in sys.path:
    sys.path.append(str(REPO / "backend" / "rebuilt"))

require_shipped("jarvis_auto_learn.py", "jarvis_intake.py", "jarvis_chat_log.py",
                "jarvis_sensitive.py")
import jarvis_intake as I  # noqa: E402
import jarvis_chat_log as H  # noqa: E402
import jarvis_auto_learn as A  # noqa: E402
import jarvis_sensitive as SENS  # noqa: E402
os.environ.setdefault("JARVIS_TEST_UNSEALED_FIXTURES", "1")

# No local model runs here. The sensitive-topic check's second layer asks the
# learner's model; this stand-in answers "not sensitive" to everything, so the
# word and shape layers decide, exactly as the other memory suites do.
SENS.ASK_MODEL = lambda prompt: '{"sensitive": false, "category": "none"}'

PASSED, FAILED = [], []
KEY = bytes(range(32))
CID = "conv-fault-0001"
LOCAL = "http://127.0.0.1:11434"
AWAY = "http://10.0.0.5:11434"
MODEL = "qwen3:8b"
MODEL_AWAY = "the learning model is not on this PC"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class _Emb(M.Embedder):
    name, dim, semantic = "test-apart-v1", 8, False

    def embed(self, texts):
        return [[float((hash(t) >> i) & 1) for i in range(self.dim)] for t in texts]


def _init(c):
    c.execute("""CREATE TABLE IF NOT EXISTS proposals (
        id INTEGER PRIMARY KEY, text TEXT NOT NULL, replaces TEXT,
        confidence REAL, source TEXT, created REAL,
        state TEXT NOT NULL DEFAULT 'pending', decided REAL, fact_id INTEGER,
        replaces_id INTEGER, replaces_text TEXT)""")


class World:
    """A memory store, a chat history, and the learning pass's own store
    handles - the smallest world after_pass runs in."""

    def __init__(self):
        A._reset_for_tests()
        self.dir = Path(tempfile.mkdtemp(prefix="jarvis-mf-", dir=_TMP))
        fw.CONFIG_DIR = self.dir
        self.store = M.MemoryStore(path=self.dir / "memory.db", embedder=_Emb())
        M._store = self.store
        with closing(self.store._connect()) as c:
            _init(c)
        self.log = H.ChatLog(self.dir / "chat-history.db", self.dir / "chat-history.json",
                             lambda: KEY)
        H.use(self.log)
        self.events = []
        ev = types.ModuleType("jarvis_events")
        ev.BUS = types.SimpleNamespace(
            publish=lambda kind, data: self.events.append((kind, data)))
        sys.modules["jarvis_events"] = ev
        self.history = []

    def say(self, text, prov="typed", cid=CID, device="desktop"):
        msg = {"role": "user", "content": text}
        if prov is not None:
            msg["provenance"] = prov
        msgs = list(self.history) + [msg]
        body = {"messages": msgs, "conversation_id": cid, "device": device}
        H.record_turn(body, lane=MODEL,
                      turn={"finish_reason": "stop", "answer": "ok", "tools_ran": []})
        self.history = msgs + [{"role": "assistant", "content": "ok"}]
        return msgs

    def queue(self, text, source="conversation"):
        with closing(self.store._connect()) as c:
            cur = c.execute(
                "INSERT INTO proposals (text, replaces, confidence, source, created,"
                " replaces_id, replaces_text) VALUES (?,?,?,?,?,?,?)",
                (text, None, 0.9, source, time.time(), None, None))
            pid = cur.lastrowid
        return {"id": pid, "text": text, "replaces": None, "replaces_id": None,
                "confidence": 0.9, "state": "pending"}

    def learn(self, facts, *, ollama=LOCAL, model=MODEL, learning_on=True):
        """One learning pass over the turns said so far, with the checks'
        own handles - the non-loopback address is how a model fault is made."""
        turns = [m["content"] for m in self.history if m.get("role") == "user"]
        out = [self.queue(f) if isinstance(f, str) else self.queue(**f) for f in facts]
        return A.after_pass(out, [{"role": "user", "content": t} for t in turns],
                            conversation_id=CID, model=model, ollama=ollama,
                            learning_on=learning_on)

    def pending(self):
        st = M.store()
        with closing(st._connect()) as c:
            _init(c)
            rows = [dict(r) for r in c.execute(
                "SELECT id,text,replaces,replaces_id,replaces_text,confidence,source,created"
                " FROM proposals WHERE state='pending' ORDER BY created")]
        return I.annotate(rows)

    def state_of(self, pid):
        with closing(self.store._connect()) as c:
            row = c.execute("SELECT state FROM proposals WHERE id=?", (int(pid),)).fetchone()
        return row[0] if row else None

    def done(self):
        H.use(None)
        sys.modules.pop("jarvis_events", None)


def _patched_pending():
    """jarvis_extract.pending() as the shipped base plus the patch's own hunk
    leave it.

    THE POINT IS THAT NOTHING IS TYPED HERE. The hunk is cut out of
    backend/auto-learn.patch, applied with `git apply` to the published
    base (jarvis-backend/jarvis_extract.py), and the resulting top-level
    `def pending(` is lifted and called against the world's real store. So
    the check below is the read the apps really make, not a copy of it."""
    import shutil
    import subprocess
    patch = (HERE / "auto-learn.patch").read_text(encoding="utf-8")
    start = patch.index("@@ -509,")
    end = patch.index("@@ -608,", start)
    hunk = patch[start:end].rstrip("\n")
    d = Path(tempfile.mkdtemp(prefix="jarvis-mf-patch-", dir=_TMP))
    shutil.copyfile(REPO / "jarvis-backend" / "jarvis_extract.py",
                    d / "jarvis_extract.py")
    (d / "p.patch").write_text(
        "--- a/jarvis_extract.py\n+++ b/jarvis_extract.py\n" + hunk + "\n",
        encoding="utf-8", newline="\n")
    r = subprocess.run(["git", "apply", "--check", "p.patch"], cwd=d,
                       capture_output=True, text=True)
    if r.returncode == 0:
        assert subprocess.run(["git", "apply", "p.patch"], cwd=d).returncode == 0
        text = (d / "jarvis_extract.py").read_text(encoding="utf-8")
    else:
        # A base re-taken AFTER this patch already carries it; use it as it is
        # and let the function lift below fail if it is not really there.
        text = (REPO / "jarvis-backend" / "jarvis_extract.py").read_text(encoding="utf-8")
    # The filter the same patch appends, cut from the patch's own added lines
    # (never typed here), so `pending()` can be called as it ships.
    marker = "+def _intake_fault_visible("
    helper = []
    for line in patch[patch.index(marker):].split("\n"):
        if not line.startswith("+"):
            break
        helper.append(line[1:])
    assert helper, "auto-learn.patch appends no _intake_fault_visible()"
    text = text + "\n\n" + "\n".join(helper) + "\n"
    lines = text.splitlines()
    ns = {"M": M, "closing": closing, "_init": _init,
          "_intake_annotate": lambda rows: I.annotate(rows)}
    for name in ("pending", "_intake_fault_visible"):
        i = next(k for k, ln in enumerate(lines) if ln.startswith(f"def {name}("))
        body = [lines[i]]
        for line in lines[i + 1:]:
            if line and not line[0].isspace():
                break
            body.append(line)
        exec(compile("\n".join(body) + "\n",
                     f"<jarvis_extract.{name}: base + auto-learn.patch>", "exec"), ns)
    return ns["pending"]


def _record():
    p = A.fault_path()
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


# ======================================================= (a) one fault, one banner

def t_a_batch_check_failure_is_one_fault_and_hides_its_cards():
    w = World()
    try:
        w.say("The office fern is called Bartholomew")
        res = w.learn(["The office fern is called Bartholomew"], ollama=AWAY)
        rec = A.fault()
        check("(a) a batch check failure writes ONE fault record",
              A.fault_path().is_file() and rec["active"] is True, rec)
        check("(a) the fault is the check's own sentence, not a fact",
              rec["reason"] == MODEL_AWAY and rec["recorded"] is True, rec)
        check("(a) the banner's sentence is the PC's, and says it is the check",
              "could not check the facts" in rec["headline"]
              and "This is the check failing, not your facts" in rec["headline"],
              rec.get("headline"))
        check("(a) the count is the cards this fault parked (1 right now)",
              rec["count"] == 1, rec["count"])
        check("(a) the pass carded the proposal WITH that reason",
              list(res.get("cards", {}).values()) == [MODEL_AWAY]
              and not res.get("saved"), res)
        notes = A.card_notes([r["id"] for r in w.pending()])
        check("(a) the card's note says the same reason, so the read can find it",
              all(n["auto_reason"] == MODEL_AWAY for n in notes.values()), notes)
        rows = w.pending()
        check("(a) the SHIPPED pending read (base + the patch's hunk) leaves it out",
              _patched_pending()() == [], rows)
        check("(a) the same filter, called directly, leaves it out too",
              A.visible_pending(rows) == [], rows)
        check("(a) the proposal is STILL pending - hidden is not decided",
              all(w.state_of(r["id"]) == "pending" for r in rows), rows)
        # A second failing pass: ONE record still, the count is now the two
        # parked cards, and the first time it started is kept.
        since = A.fault()["since"]
        w.say("The kitchen kettle is red")
        w.learn(["The kitchen kettle is red"], ollama=AWAY)
        rec2 = A.fault()
        check("(a) a second failing pass still leaves exactly one record",
              isinstance(_record(), dict) and rec2["active"] is True
              and rec2["count"] == 2, rec2)
        check("(a) ... and keeps when it started", rec2["since"] == since,
              (since, rec2["since"]))
    finally:
        w.done()


def t_the_owner_turning_learning_off_is_not_a_fault():
    w = World()
    try:
        w.say("The office fern is called Bartholomew")
        A.set_auto(False)
        res = w.learn(["The office fern is called Bartholomew"])
        check("an owner's own off is NOT a fault and writes no banner",
              A.fault()["active"] is False and res.get("cards"), res)
        check("... and its cards keep no machine reason, as before",
              all(n["auto_reason"] == ""
                  for n in A.card_notes(list(res["cards"])).values()))
        check("... and every one of them is still shown",
              len(A.visible_pending(w.pending())) == 1)
        A.set_auto(True)
    finally:
        w.done()


# ================================================= (b) per-fact decisions stay

def t_a_genuine_per_fact_card_still_appears():
    w = World()
    try:
        w.say("I have diabetes")
        res = w.learn(["I have diabetes"])
        pid = list(res["cards"])[0]
        check("(b) a sensitive fact is a card with its own reason",
              res["cards"][pid] == "about health, a sensitive topic", res)
        note = A.card_notes([pid])[pid]
        check("(b) ... which is not the fault's reason (a decision, not machinery)",
              bool(note.get("auto_reason"))
              and note.get("auto_reason") != MODEL_AWAY, note)
        # Now a fault in the SAME conversation, from a second pass.
        w.say("The office fern is called Bartholomew")
        w.learn(["The office fern is called Bartholomew"], ollama=AWAY)
        check("(b) the fault is active", A.fault()["active"] is True)
        rows = A.visible_pending(w.pending())
        ids = [r["id"] for r in rows]
        check("(b) the sensitive card is STILL shown while a fault is active",
              pid in ids, ids)
        check("(b) the fault's own card is not",
              all(r["auto_reason"] != MODEL_AWAY for r in rows), rows)
        # The guard itself: a sensitive-labelled card that happens to carry
        # the fault's own reason is never hidden.
        other = w.queue("a card that only looks like the fault")
        with closing(w.store._connect()) as c:
            A._note_card(c, other["id"], MODEL_AWAY, sensitive="health")
            c.commit()
        kept = [r["id"] for r in A.visible_pending(w.pending())]
        check("(b) a sensitive card is never hidden, even with the fault's reason",
              other["id"] in kept, kept)
    finally:
        w.done()


# ==================================================== (c) retry clears, saves nothing

def t_retry_clears_only_when_the_check_passes_and_saves_nothing():
    w = World()
    try:
        w.say("The office fern is called Bartholomew")
        w.learn(["The office fern is called Bartholomew"], ollama=AWAY)
        pid = w.pending()[0]["id"]
        facts_before = len(w.store.current_facts())
        pending_before = [r["id"] for r in w.pending()]
        out = A.retry_fault(learning_on=True, model=MODEL, ollama=LOCAL)
        check("(c) a retry whose check now passes clears the fault",
              out["cleared"] is True and A.fault()["active"] is False, out)
        check("(c) the PC's own sentence says the check works now",
              "check works again" in out["outcome"], out.get("outcome"))
        check("(c) it saved no memory", len(w.store.current_facts()) == facts_before,
              (facts_before, len(w.store.current_facts())))
        check("(c) it approved/decided nothing: the proposal is still pending",
              w.state_of(pid) == "pending" and [r["id"] for r in w.pending()] == pending_before,
              (w.state_of(pid), pending_before))
        check("(c) a retry with no active fault is a no-op that says so",
              A.retry_fault(learning_on=True, model=MODEL, ollama=LOCAL)["outcome"]
              == A.RETRY_NOTHING)
    finally:
        w.done()


def t_a_damaged_settings_file_is_a_fault_and_a_retry_clears_it():
    w = World()
    try:
        A.settings_path().write_text("{not json", encoding="utf-8")
        w.say("The office fern is called Bartholomew")
        w.learn(["The office fern is called Bartholomew"])
        rec = A.fault()
        check("(c) a damaged auto-learning.json is a fault, not an owner's off",
              rec["active"] is True and "damaged" in rec["reason"], rec)
        check("(c) ... and its card is hidden while it is active",
              A.visible_pending(w.pending()) == [])
        A.settings_path().unlink()
        out = A.retry_fault(learning_on=True, model=MODEL, ollama=LOCAL)
        check("(c) the retry clears it once the settings file is whole again",
              out["cleared"] is True and A.fault()["active"] is False, out)
        check("(c) ... and the card comes back: hidden never meant decided",
              len(A.visible_pending(w.pending())) == 1)
    finally:
        w.done()


def t_a_retry_with_learning_off_says_there_is_no_check():
    w = World()
    try:
        fact = "The office fern is called Bartholomew"
        w.say(fact)
        w.learn([fact], ollama=AWAY)
        check("(c) a fault is active before the owner turns learning off",
              A.fault()["active"] is True)
        A.set_auto(False)
        out = A.retry_fault(learning_on=True, model=MODEL, ollama=LOCAL)
        check("(c) a retry while learning is off clears it and says there is no check",
              out["cleared"] is True and A.fault()["active"] is False
              and "no check to run" in out["outcome"], out)
        check("(c) ... and saved nothing", not w.store.current_facts())
        A.set_auto(True)
    finally:
        w.done()


# ==================================================== (d) a failed retry keeps it

def t_a_retry_that_still_fails_keeps_the_fault_and_says_why():
    w = World()
    try:
        w.say("The office fern is called Bartholomew")
        w.learn(["The office fern is called Bartholomew"], ollama=AWAY)
        facts_before = len(w.store.current_facts())
        out = A.retry_fault(learning_on=True, model=MODEL, ollama=AWAY)
        rec = A.fault()
        check("(d) a retry that still fails keeps the fault",
              rec["active"] is True and out["cleared"] is False, out)
        check("(d) ... counts the try and keeps the reason",
              rec["tries"] == 1 and rec["last_result"] == MODEL_AWAY, rec)
        check("(d) ... and says why, in the PC's words",
              "still fails" in out["outcome"] and MODEL_AWAY in out["outcome"],
              out.get("outcome"))
        check("(d) ... and still saved and approved nothing",
              len(w.store.current_facts()) == facts_before
              and all(w.state_of(r["id"]) == "pending" for r in w.pending()))
        check("(d) the banner's reason is unchanged", rec["reason"] == MODEL_AWAY)
    finally:
        w.done()


# ==================================================== (e) no fact words, ever

def t_the_fault_record_holds_no_facts_words():
    w = World()
    try:
        fact = "Bartholomew Pendergast keeps the brass key"
        w.say(fact)
        w.learn([fact], ollama=AWAY)
        raw = A.fault_path().read_text(encoding="utf-8")
        rec = json.loads(raw)
        check("(e) no word of the fact is in the fault record",
              "Bartholomew" not in raw and "Pendergast" not in raw and "brass" not in raw,
              raw)
        check("(e) the record is a fixed shape: reason, times and a count",
              set(rec) == {"version", "reason", "count", "at", "since", "tries",
                           "last_try_at", "last_result"}, sorted(rec))
        check("(e) the reason is one of the checks' own sentences",
              rec["reason"] == MODEL_AWAY, rec["reason"])
        check("(e) the pass itself did not save the fact", not w.store.current_facts())
        # And a retry that fails writes its reason only, never the fact again.
        A.retry_fault(learning_on=True, model=MODEL, ollama=AWAY)
        raw2 = A.fault_path().read_text(encoding="utf-8")
        check("(e) a failed retry adds no fact words either",
              "Pendergast" not in raw2 and "brass" not in raw2, raw2)
    finally:
        w.done()


# ============================================ honesty: a record that cannot be written

def t_a_record_that_cannot_be_written_hides_nothing():
    w = World()
    try:
        w.say("The office fern is called Bartholomew")
        # A file where the settings folder should be: mkdir/write cannot work.
        blocker = w.dir / "not-a-folder"
        blocker.write_text("x", encoding="utf-8")
        fw.CONFIG_DIR = blocker
        res = w.learn(["The office fern is called Bartholomew"], ollama=AWAY)
        check("a fault that cannot be recorded says so",
              (res.get("fault") or {}).get("written") is False, res.get("fault"))
        check("... and is NOT reported as an active fault",
              A.fault()["active"] is False, A.fault())
        rows = w.pending()
        check("... so the cards are shown: silence with no banner would be worse",
              len(A.visible_pending(rows)) == 1, rows)
    finally:
        fw.CONFIG_DIR = _TMP
        w.done()


# ==================================================== the routes

def t_the_fault_routes_read_and_retry():
    w = World()
    try:
        code, body = A.handle_get("/api/memory/fault")
        check("GET /api/memory/fault answers 200 with no fault before one",
              code == 200 and body["active"] is False, (code, body))
        w.say("The office fern is called Bartholomew")
        w.learn(["The office fern is called Bartholomew"], ollama=AWAY)
        code, body = A.handle_get("/api/memory/fault")
        check("GET /api/memory/fault is the banner both apps read",
              code == 200 and body["active"] is True
              and body["reason"] == MODEL_AWAY and body["headline"], (code, body))
        code, body = A.handle_post("/api/memory/fault/retry", {},
                                   learning_on=True, model=MODEL, ollama=AWAY)
        check("POST /api/memory/fault/retry still failing answers 200 and keeps it",
              code == 200 and body["cleared"] is False
              and body["fault"]["active"] is True, (code, body))
        code, body = A.handle_post("/api/memory/fault/retry", {},
                                   learning_on=True, model=MODEL, ollama=LOCAL)
        check("POST /api/memory/fault/retry passing answers 200 and clears it",
              code == 200 and body["cleared"] is True
              and body["fault"]["active"] is False, (code, body))
        check("an unknown memory route is still 404",
              A.handle_get("/api/memory/nope")[0] == 404
              and A.handle_post("/api/memory/nope", {})[0] == 404)
        check("the three switches still take their own routes",
              A.handle_post("/api/memory/learning/auto", {"enabled": False})[0] == 200)
    finally:
        w.done()


# ==================================================== main

def main():
    for fn in (t_a_batch_check_failure_is_one_fault_and_hides_its_cards,
               t_the_owner_turning_learning_off_is_not_a_fault,
               t_a_genuine_per_fact_card_still_appears,
               t_retry_clears_only_when_the_check_passes_and_saves_nothing,
               t_a_damaged_settings_file_is_a_fault_and_a_retry_clears_it,
               t_a_retry_with_learning_off_says_there_is_no_check,
               t_a_retry_that_still_fails_keeps_the_fault_and_says_why,
               t_the_fault_record_holds_no_facts_words,
               t_a_record_that_cannot_be_written_hides_nothing,
               t_the_fault_routes_read_and_retry):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:                                     # noqa: BLE001
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
