"""The two mechanical guards against blind / stacked approvals.

    python3 test_approval_guards.py

WHAT THEY ANSWER (the owner's incident, 2026-10-20). One "approve all" click
approved three backup restores, two imports and a device-key registration,
because repeated requests had STACKED identical cards in `/api/pending` and
muscle memory walked the queue. The review the owner accepted (ruling 8.2 of
`FOR-GEMINI-COMPREHENSIVE-REVIEW-2026-10-20-LATE`) asks for two MECHANICAL
guards, not advice:

  1. PENDING-CARD DEDUPLICATION - a request whose action and target are
     IDENTICAL to a card that is still waiting reuses that card's id instead
     of stacking a second one. It never merges different actions or targets,
     never suppresses a card (the waiting one is still drawn), never
     auto-approves, and never reuses a card that was already answered.
  2. STATE-REPLACING CARDS ARE MARKED - `restore_backup`,
     `register_approval_key`, `memory_forget_range`, and the voice-training
     clear (a `change_own_config` card, marked by its own module) carry
     `replaces: true` on every waiting row, so both apps can draw a plain
     "REPLACES CURRENT DATA" heading and ask a second, explicit confirmation.
     Every other card is unchanged.

Both guards are proved here BEHAVIOURALLY, against the same published gate the
owner's PC runs (`jarvis-backend/jarvis_gate.py`, the post-stack copy;
`backend/gate-touches.patch` is the carrier this repository applies to his
file). Nothing here raises a card on his PC, starts a model, or answers one:
the queue is a scratch SQLite file, the tier table is passed in, and the
decisions are made by this suite's own fake "human", through the real
`jarvis_gate.decide()`.

The last check in each section is a BITE: the guard is removed (in memory
only) and the behaviour must degrade exactly as the old code did. A suite that
cannot fail when the guard is gone proves nothing.

Runs in repo mode (JARVIS_BACKEND unset), from the repository root:

    py -3 backend/test_approval_guards.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BASE = REPO / "jarvis-backend"

# A SCRATCH home, before anything is imported: jarvis_gate reads its database
# path at import time. The owner's own ~/.openjarvis is never touched.
SCRATCH = Path(tempfile.mkdtemp(prefix="jarvis-approval-guards-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_CONFIG_DIR"] = str(SCRATCH)
# The gate reads this at import; the shipped 900 seconds is never in play.
os.environ.setdefault("JARVIS_APPROVAL_TIMEOUT", "2.0")
# No push, said explicitly rather than relied on: this suite must not post a
# card anywhere, and an owner with ntfy configured would otherwise get one.
os.environ["JARVIS_NTFY_TOPIC"] = ""
os.environ["JARVIS_NTFY_SERVER"] = ""

# The published copy of the gate, first on the path; backend/rebuilt/ second,
# for the library modules the shipped tier table is read by. Bytecode writing
# is off for the imports and the path is put back afterwards - the same rule
# and the same reason as test_gate_touches.py's header.
_SAVED_PATH = list(sys.path)
_SAVED_DONT_WRITE_BYTECODE = sys.dont_write_bytecode
sys.dont_write_bytecode = True
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(HERE / "rebuilt"))

import jarvis_gate as G  # noqa: E402
import jarvis_card_words as W  # noqa: E402

sys.path[:] = _SAVED_PATH
sys.dont_write_bytecode = _SAVED_DONT_WRITE_BYTECODE

FAILED, PASSED, SKIPPED = [], [], []

#: A tier table passed straight into check()/replaces_for() so this suite never
#: needs the owner's jarvis-framework.toml. Every action used here is "ask",
#: the tier a card is raised at.
TIERS = {"autonomy": {"tiers": {
    "send_email": "ask",
    "delete_file": "ask",
    "restore_backup": "ask",
    "register_approval_key": "ask",
    "memory_forget_range": "ask",
    "change_own_config": "ask",
    "write_note": "auto",
}}}

#: Read from the environment the gate read it from, so the two agree.
TIMEOUT = float(os.environ["JARVIS_APPROVAL_TIMEOUT"])


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


def _reset():
    """An empty queue and no latch: every test starts from the same place."""
    G._init()
    with closing(G._connect()) as c:
        c.execute("DELETE FROM approvals")
        c.execute("DELETE FROM taint")
    G.clear_taint()


def _pending(action=None):
    rows = G.pending()
    return [r for r in rows if action is None or r.get("action") == action]


def _wait_for_row(action, deadline=5.0):
    end = time.time() + deadline
    while time.time() < end:
        rows = _pending(action)
        if rows:
            return rows[0]
        time.sleep(0.02)
    return None


def _approve(rid, action):
    """Answer "approve" the way this PC's own approval route does.

    The gate refuses an approval it never stamped (`owner-check.patch`), so a
    test that clicked Approve by calling decide() alone would be testing the
    refusal path. The stamp is what POST /api/approve on the PC leaves behind;
    here the suite is the PC, and `jarvis_owner_check` is the same module the
    gate imports.
    """
    try:
        import jarvis_owner_check
        jarvis_owner_check.stamp(rid, action)
    except Exception:                               # pragma: no cover
        pass
    return G.decide(rid, True, by="suite")


def _in_thread(action, detail, prompt, box, key, barrier=None):
    def run():
        try:
            if barrier is not None:
                barrier.wait(5)
            box[key] = G.check(action, detail, prompt=prompt, timeout=TIMEOUT,
                               framework=TIERS)
        except Exception as exc:                    # pragma: no cover
            box[key + "_error"] = exc

    t = threading.Thread(target=run, name=f"guard-{key}", daemon=True)
    t.start()
    return t


# =============================================================== guard 1: one
# ================================================== card per identical request

def t_two_identical_requests_share_one_pending_card():
    """Two clicks that raise the same request: ONE card, and one decision."""
    _reset()
    action = "send_email"
    detail = {"to": "same@example.com", "subject": "Status", "body": "All good."}
    prompt = "Send this email?"
    box = {}
    first = _in_thread(action, dict(detail), prompt, box, "a")
    row = _wait_for_row(action)
    check("the first request really raised a card", row is not None,
          repr([r.get("action") for r in G.pending()]))
    if row is None:
        first.join(1)
        return
    second = _in_thread(action, dict(detail), prompt, box, "b")
    time.sleep(0.3)                                 # let the second look

    rows = _pending(action)
    check("two identical requests leave ONE pending card, not two",
          len(rows) == 1, f"rows={[r['id'] for r in rows]} first={row['id']}")
    check("... the one card is still WAITING (nothing was auto-approved)",
          first.is_alive(), f"first_alive={first.is_alive()}")
    check("... and it is the card the first request raised",
          bool(rows) and rows[0]["id"] == row["id"],
          f"rows={[r['id'] for r in rows]} first={row['id']}")
    check("... an ORDINARY card is not marked as replacing anything",
          rows and rows[0].get("replaces") is False,
          repr(rows[0].get("replaces") if rows else None))
    check("... the duplicate was answered at once and runs NOTHING "
          "(one card is one action, so the stack cannot run three restores)",
          not second.is_alive() and box.get("b") is not None
          and not box["b"].allowed, repr(box.get("b")))
    check("... and it names the waiting card, so its caller knows where the "
          "decision is made",
          box.get("b") is not None and box["b"].request_id == row["id"],
          repr(getattr(box.get("b"), "request_id", None)))
    check("... saying plainly that the same request is already waiting",
          box.get("b") is not None and "already waiting" in box["b"].reason,
          repr(getattr(box.get("b"), "reason", None)))

    _approve(row["id"], row["action"])
    first.join(5)
    second.join(5)
    check("the one decision lets the WAITING request through",
          box.get("a") is not None and box["a"].allowed, repr(box.get("a")))
    check("... and the duplicate never ran: one card, one action",
          box.get("b") is not None and not box["b"].allowed, repr(box.get("b")))
    check("... and the queue is empty afterwards: no second card was ever made",
          _pending(action) == [], repr(_pending(action)))


def t_different_targets_are_never_merged():
    """The same action at a DIFFERENT target is a different request."""
    _reset()
    action = "send_email"
    box = {}
    a = _in_thread(action, {"to": "one@example.com", "subject": "A", "body": "x"},
                   "Send this email?", box, "a")
    row_a = _wait_for_row(action)
    b = _in_thread(action, {"to": "two@example.com", "subject": "A", "body": "x"},
                   "Send this email?", box, "b")
    row_b = None
    end = time.time() + 3
    while time.time() < end and row_b is None:
        rows = _pending(action)
        if len(rows) >= 2:
            row_b = rows[-1]
            break
        time.sleep(0.02)
    check("a different recipient is a different card",
          row_a is not None and row_b is not None and row_a["id"] != row_b["id"],
          repr([r["id"] for r in _pending(action)]))
    for r in _pending(action):
        G.decide(r["id"], False, by="suite")
    a.join(5)
    b.join(5)
    check("... and denying them denies both separately (neither was a reuse)",
          box.get("a") is not None and box.get("b") is not None
          and not box["a"].allowed and not box["b"].allowed, repr(box))


def t_different_actions_are_never_merged():
    """The same words and detail under two actions: two cards, no reuse."""
    _reset()
    detail = {"path": "C:/x/notes.txt"}
    box = {}
    a = _in_thread("delete_file", dict(detail), "Delete a file?", box, "a")
    row_a = _wait_for_row("delete_file")
    b = _in_thread("restore_backup", {"text": "Restore from the backup?"},
                   "Restore from the backup?", box, "b")
    row_b = _wait_for_row("restore_backup")
    check("two different actions are two different cards",
          row_a is not None and row_b is not None and row_a["id"] != row_b["id"],
          repr([(r["action"], r["id"]) for r in G.pending()]))
    for r in G.pending():
        G.decide(r["id"], False, by="suite")
    a.join(5)
    b.join(5)
    check("... and each had to be answered on its own",
          not box.get("a").allowed and not box.get("b").allowed, repr(box))


def t_approving_one_card_does_not_approve_another_action():
    """Guard 1 may never turn one approval into two answers."""
    _reset()
    box = {}
    a = _in_thread("send_email", {"to": "x@example.com", "subject": "S", "body": "b"},
                   "Send this email?", box, "a")
    row_a = _wait_for_row("send_email")
    b = _in_thread("delete_file", {"path": "C:/x/notes.txt"},
                   "Delete this file?", box, "b")
    row_b = _wait_for_row("delete_file")
    check("both cards are waiting before either is answered",
          row_a is not None and row_b is not None and a.is_alive() and b.is_alive(),
          repr([(r["action"], r["id"]) for r in G.pending()]))
    _approve(row_a["id"], row_a["action"])
    a.join(5)
    b.join(6)
    check("approving the email approves the email", box.get("a") is not None
          and box["a"].allowed, repr(box.get("a")))
    check("... and the delete card is still NOT approved",
          box.get("b") is not None and not box["b"].allowed, repr(box.get("b")))
    if _pending("delete_file"):
        for r in _pending("delete_file"):
            G.decide(r["id"], False, by="suite")


def t_an_answered_card_is_never_reused():
    """A card that was decided is an answer, not a slot to refill."""
    _reset()
    first = _in_thread("send_email", {"to": "again@example.com"},
                       "Send this email?", {}, "a")
    row = _wait_for_row("send_email")
    check("the first card was raised", row is not None, repr(row))
    if row is None:
        first.join(1)
        return
    G.decide(row["id"], False, by="suite")
    first.join(5)
    check("... and denied, which is a decision a person made",
          not first.is_alive() and G.history(1)[0]["state"] == "denied",
          repr(G.history(1)[:1]))
    second = _in_thread("send_email", {"to": "again@example.com"},
                        "Send this email?", {}, "b")
    fresh = _wait_for_row("send_email")
    check("the same request afterwards raises a NEW card with a NEW id",
          fresh is not None and fresh["id"] != row["id"],
          f"old={row['id']} new={fresh['id'] if fresh else None}")
    if fresh:
        G.decide(fresh["id"], False, by="suite")
    second.join(5)


def t_concurrent_identical_requests_still_share_one_card():
    """The check-then-insert is one transaction: a race cannot stack two."""
    _reset()
    action = "send_email"
    detail = {"to": "race@example.com", "subject": "R", "body": "b"}
    barrier = threading.Barrier(4)
    box = {}
    threads = [_in_thread(action, dict(detail), "Send it?", box, f"t{i}", barrier)
               for i in range(4)]
    row = _wait_for_row(action, deadline=5.0)
    time.sleep(0.4)
    rows = _pending(action)
    check("four requests at the same instant leave ONE pending card",
          len(rows) == 1, f"rows={[r['id'] for r in rows]}")
    if rows:
        _approve(rows[0]["id"], rows[0]["action"])
    for t in threads:
        t.join(6)
    verdicts = [box.get(f"t{i}") for i in range(4)]
    ids = {getattr(v, "request_id", None) for v in verdicts}
    check("... and every one of them names that one card",
          len(ids) == 1 and bool(rows) and ids == {rows[0]["id"]},
          f"ids={ids} row={rows[0]['id'] if rows else None}")
    check("... exactly ONE of them ran: the card was answered once",
          sum(1 for v in verdicts if getattr(v, "allowed", False)) == 1,
          repr([(getattr(v, "allowed", None), getattr(v, "outcome", None))
                for v in verdicts]))


def t_the_dedup_guard_is_the_thing_that_merges_them():
    """BITE: with the lookup removed, the old stacking comes straight back."""
    _reset()
    action = "send_email"
    detail = {"to": "bite@example.com"}
    real = G._pending_card_id
    box = {}
    try:
        G._pending_card_id = lambda c, a, d, p: None       # the guard, gone
        a = _in_thread(action, dict(detail), "Send it?", box, "a")
        _wait_for_row(action)
        b = _in_thread(action, dict(detail), "Send it?", box, "b")
        end = time.time() + 3
        rows = []
        while time.time() < end:
            rows = _pending(action)
            if len(rows) >= 2:
                break
            time.sleep(0.02)
        check("without the lookup, two identical requests stack two cards "
              "(so this suite can fail when the guard is reverted)",
              len(rows) >= 2, f"rows={[r['id'] for r in rows]}")
    finally:
        G._pending_card_id = real
        for r in _pending(action):
            G.decide(r["id"], False, by="suite")
    a.join(5)
    b.join(5)
    check("... and with the guard restored the published copy is what ran",
          G._pending_card_id is real, repr(G._pending_card_id))



# ------------------------------------------------- long details and the digest
#
# THE HOLE THIS CLOSES (2026-10-21 pre-merge audit, F-680-2). An approvals row
# kept only the first 4000 characters of `json.dumps(detail)`, and the dedupe
# re-hashed that STORED text. A request whose detail is longer than 4000
# characters (an email body, a path list) was therefore never recognised as
# identical: two cards stacked, and approving the stack ran the action twice -
# guard 1's own incident for that input. The row now carries the target digest
# computed from the WHOLE request at insert time, and the dedupe compares that
# first; a row from before the column has NULL there and keeps the old, parse-
# based comparison (a second card when it cannot be read, never a wrong merge).


def _long_detail(fill="x", n=6000):
    return {"to": "long@example.com", "subject": "A long one", "body": fill * n}


def _json_length(detail):
    return len(json.dumps(detail))


def _deny_all(action):
    for r in _pending(action):
        G.decide(r["id"], False, by="suite")


def t_an_identical_long_detail_raises_ONE_card():
    """F-680-2: a >4000-character detail still dedupes; one card, one id."""
    _reset()
    action = "send_email"
    detail = _long_detail()
    check("(set-up) the probe's detail really is longer than the stored 4000",
          _json_length(detail) > 4000, _json_length(detail))
    box = {}
    a = _in_thread(action, dict(detail), "Send the long one?", box, "a")
    row = _wait_for_row(action)
    check("the first long request raised a card", row is not None,
          repr([r["id"] for r in _pending(action)]))
    if row is None:
        a.join(2)
        _deny_all(action)
        return
    b = _in_thread(action, dict(detail), "Send the long one?", box, "b")
    end = time.time() + 4
    verdict_b = None
    while time.time() < end and verdict_b is None:
        verdict_b = box.get("b")
        time.sleep(0.02)
    rows = _pending(action)
    check("two identical >4000-character requests leave ONE pending card",
          len(rows) == 1, f"rows={[r['id'] for r in rows]}")
    check("... and the second request names that waiting card, not a new one",
          verdict_b is not None
          and getattr(verdict_b, "request_id", None) == rows[0]["id"],
          repr(getattr(verdict_b, "request_id", None)))
    _deny_all(action)
    a.join(5)
    b.join(5)


def t_two_DIFFERENT_long_details_are_two_cards():
    """A different long body is a DIFFERENT action target: two cards."""
    _reset()
    action = "send_email"
    first, second = _long_detail("x"), _long_detail("y")
    box = {}
    a = _in_thread(action, dict(first), "Send the long one?", box, "a")
    row_a = _wait_for_row(action)
    b = _in_thread(action, dict(second), "Send the long one?", box, "b")
    row_b = None
    end = time.time() + 4
    while time.time() < end and row_b is None:
        rows = _pending(action)
        if len(rows) >= 2:
            other = [r for r in rows if r["id"] != (row_a or {}).get("id")]
            row_b = other[0] if other else None
            break
        time.sleep(0.02)
    check("two DIFFERENT >4000-character details are two cards, never merged",
          row_a is not None and row_b is not None and row_a["id"] != row_b["id"],
          repr([r["id"] for r in _pending(action)]))
    _deny_all(action)
    a.join(5)
    b.join(5)


def t_the_3999_vs_4000_boundary_is_safe():
    """Both sides of the stored-text cut dedupe with themselves."""
    _reset()
    action = "send_email"
    base = {"to": "edge@example.com", "subject": "Boundary", "body": ""}
    found = {}
    body = ""
    while len(body) <= 5000 and len(found) < 2:
        detail = dict(base)
        detail["body"] = body
        n = _json_length(detail)
        if n in (3999, 4000) and n not in found:
            found[n] = detail
        body += "x"
    check("(set-up) one probe detail is 3999 characters and one is 4000",
          set(found) == {3999, 4000}, sorted(found))
    for label in (3999, 4000):
        if label not in found:
            continue
        _reset()
        detail = found[label]
        box = {}
        a = _in_thread(action, dict(detail), "Send?", box, "a")
        row = _wait_for_row(action)
        b = _in_thread(action, dict(detail), "Send?", box, "b")
        time.sleep(0.35)
        rows = _pending(action)
        check(f"... the same detail at {label} characters leaves ONE card",
              row is not None and len(rows) == 1,
              f"rows={[r['id'] for r in rows]}")
        _deny_all(action)
        a.join(5)
        b.join(5)


def t_concurrent_identical_long_requests_share_one_card():
    """The check-then-insert transaction still holds for a long target."""
    _reset()
    action = "send_email"
    detail = _long_detail()
    barrier = threading.Barrier(4)
    box = {}
    threads = [_in_thread(action, dict(detail), "Send the long one?", box,
                          f"t{i}", barrier) for i in range(4)]
    row = _wait_for_row(action, deadline=5.0)
    time.sleep(0.4)
    rows = _pending(action)
    check("four identical long requests at once leave ONE pending card",
          len(rows) == 1, f"rows={[r['id'] for r in rows]}")
    _deny_all(action)
    for t in threads:
        t.join(6)
    ids = {getattr(box.get(f"t{i}"), "request_id", None) for i in range(4)}
    check("... and all four name that one card",
          len(ids) == 1 and bool(rows) and ids == {rows[0]["id"]},
          f"ids={ids} row={rows[0]['id'] if rows else None}")


def t_an_old_row_without_a_digest_is_merged_only_by_its_parseable_detail():
    """Old rows (NULL digest) fall back to the old comparison, never guessed."""
    _reset()
    action = "send_email"
    short = {"to": "old@example.com"}
    with closing(G._connect()) as c:
        c.execute("BEGIN IMMEDIATE")
        c.execute(
            "INSERT INTO approvals (id,action,tier,detail,prompt,state,created,"
            "raised,target_digest) VALUES (?,?,?,?,?,'pending',?,?,NULL)",
            ("oldshort", action, "ask", json.dumps(short), "Send it?",
             time.time() - 1, None))
        long_raw = json.dumps({"to": "old@example.com", "body": "z" * 6000})
        c.execute(
            "INSERT INTO approvals (id,action,tier,detail,prompt,state,created,"
            "raised,target_digest) VALUES (?,?,?,?,?,'pending',?,?,NULL)",
            ("oldlong", action, "ask", long_raw[:4000], "Send it?",
             time.time() - 1, None))
        c.execute("COMMIT")
    with closing(G._connect()) as c:
        c.execute("BEGIN IMMEDIATE")
        got = G._pending_card_id(c, action, dict(short), "Send it?")
        c.execute("COMMIT")
    check("an OLD row with a parseable detail still dedupes (NULL-digest fallback)",
          got == "oldshort", repr(got))
    box = {}
    a = _in_thread(action, {"to": "old@example.com", "body": "z" * 6000},
                   "Send it?", box, "a")
    end = time.time() + 4
    fresh = None
    while time.time() < end and fresh is None:
        rows = [r for r in _pending(action) if r["id"] not in ("oldshort", "oldlong")]
        if rows:
            fresh = rows[0]
        time.sleep(0.02)
    check("... and an UNREADABLE old row is skipped: the long request gets its "
          "own card (a second card, never a wrong merge)",
          fresh is not None, repr([r["id"] for r in _pending(action)]))
    _deny_all(action)
    a.join(5)


def t_the_digest_column_migrates_idempotently_and_keeps_old_rows():
    """The schema change is forward-only: an old DB gains the column, twice."""
    _reset()
    real_path, real_inited = G.DB_PATH, G._inited
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-gate-migrate-"))
    old_db = tmp / "approvals.db"
    try:
        import sqlite3
        c = sqlite3.connect(str(old_db))
        c.execute("""CREATE TABLE approvals (
            id TEXT PRIMARY KEY, action TEXT NOT NULL, tier TEXT NOT NULL,
            detail TEXT, prompt TEXT, state TEXT NOT NULL, created REAL NOT NULL,
            decided REAL, decided_by TEXT)""")
        c.execute(
            "INSERT INTO approvals (id,action,tier,detail,prompt,state,created)"
            " VALUES ('oldrow','send_email','ask',?, 'Send it?','pending',?)",
            (json.dumps({"to": "x@example.com"}), time.time()))
        c.commit()
        c.close()
        G.DB_PATH = old_db
        G._inited = False
        G._init()
        with closing(G._connect()) as c:
            cols = [r[1] for r in c.execute("PRAGMA table_info(approvals)")]
            rows = c.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]
        check("the migration adds target_digest to an old database",
              "target_digest" in cols, cols)
        check("... and keeps the rows that were already there", rows == 1, rows)
        G._init()                                    # idempotent second init
        with closing(G._connect()) as c:
            c.execute("BEGIN IMMEDIATE")
            got = G._pending_card_id(c, "send_email", {"to": "x@example.com"},
                                     "Send it?")
            c.execute("COMMIT")
        check("... and the migrated old row still dedupes through its detail",
              got == "oldrow", repr(got))
    finally:
        G.DB_PATH, G._inited = real_path, real_inited
        G._init()
        shutil.rmtree(tmp, ignore_errors=True)


def t_the_long_detail_guard_is_the_thing_that_merges_them():
    """BITE: with the lookup removed, two long identical cards stack."""
    _reset()
    action = "send_email"
    detail = _long_detail()
    real = G._pending_card_id
    box = {}
    try:
        G._pending_card_id = lambda c, a, d, p: None    # the lookup, gone
        a = _in_thread(action, dict(detail), "Send?", box, "a")
        _wait_for_row(action)
        b = _in_thread(action, dict(detail), "Send?", box, "b")
        end = time.time() + 4
        rows = []
        while time.time() < end:
            rows = _pending(action)
            if len(rows) >= 2:
                break
            time.sleep(0.02)
        check("without the lookup, the long-detail requests stack two cards "
              "(so this suite can fail when the fix is reverted)",
              len(rows) >= 2, f"rows={[r['id'] for r in rows]}")
    finally:
        G._pending_card_id = real
        _deny_all(action)
        a.join(5)
        b.join(5)


def t_requests_differing_only_in_their_target_are_never_merged():
    """A different vault path, source file or byte count is a DIFFERENT card.

    Guard 1 merges only requests that would DO the same thing. A restore whose
    backup path differs, an import whose source file differs, or a write whose
    requested bytes differ each change what approving does, so each is its own
    card - the memoised answer to "one click approved three restores" must not
    become "one click restored the wrong backup".
    """
    pairs = (
        # (action, detail that is otherwise identical, the one key changed,
        #  two different values of it - the review's own "vault path")
        ("restore_backup",
         {"text": "Restore from this backup?", "to": "jarvis-backup-2026-10-01.jbak"},
         {"to": ("jarvis-backup-2026-10-01.jbak", "jarvis-backup-2026-10-02.jbak")}),
        # ... its "source file"
        ("browser_form_submit",
         {"text": "Submit this form?", "source": "C:/notes/one.html"},
         {"source": ("C:/notes/one.html", "C:/notes/two.html")}),
        # ... and its "requested bytes"
        ("send_email",
         {"to": "same@example.com", "subject": "Status", "body": "All good."},
         {"body": ("All good.", "All good!")}),
    )
    for action, base, changed in pairs:
        _reset()
        key, (first_value, second_value) = next(iter(changed.items()))
        first = dict(base)
        first[key] = first_value
        second = dict(base)
        second[key] = second_value
        box = {}
        a = _in_thread(action, dict(first), "Same card?", box, "a")
        row_a = _wait_for_row(action)
        b = _in_thread(action, dict(second), "Same card?", box, "b")
        row_b = None
        end = time.time() + 3
        while time.time() < end and row_b is None:
            rows = _pending(action)
            if len(rows) >= 2:
                row_b = [r for r in rows if r["id"] != (row_a or {}).get("id")]
                row_b = row_b[0] if row_b else None
                break
            time.sleep(0.02)
        check(f"{action}: a different `{key}` is a separate card",
              row_a is not None and row_b is not None and row_a["id"] != row_b["id"],
              repr([r["id"] for r in _pending(action)]))
        if not row_a or not row_b:
            for r in _pending(action):
                G.decide(r["id"], False, by="suite")
            a.join(5)
            b.join(5)
            continue
        # Denying ONE must answer only that one; the other keeps waiting.
        G.decide(row_a["id"], False, by="suite")
        a.join(5)
        check(f"... answering one of the two {action} requests leaves the other "
              f"waiting", not box.get("a").allowed and _pending(action)
              and _pending(action)[0]["id"] == row_b["id"],
              repr([r["id"] for r in _pending(action)]))
        G.decide(row_b["id"], False, by="suite")
        b.join(5)


def t_an_APPROVED_card_is_never_reused_either():
    """The other answer: a card a person said YES to is spent, not a hole."""
    _reset()
    detail = {"to": "approved-once@example.com"}
    first = _in_thread("send_email", dict(detail), "Send it?", {}, "a")
    row = _wait_for_row("send_email")
    check("the card was raised", row is not None, repr(row))
    if row is None:
        first.join(1)
        return
    _approve(row["id"], row["action"])
    first.join(5)
    check("... and approved", first is not None and not first.is_alive(),
          repr(G.history(1)[:1]))
    again = _in_thread("send_email", dict(detail), "Send it?", {}, "b")
    fresh = _wait_for_row("send_email")
    check("the same request after an approval raises a NEW card (an answered "
          "card is an answer, not a slot to refill)",
          fresh is not None and fresh["id"] != row["id"],
          f"old={row['id']} new={fresh['id'] if fresh else None}")
    if fresh:
        G.decide(fresh["id"], False, by="suite")
    again.join(5)


# ============================================== guard 2: cards that REPLACE

#: Every action the owner extended the two-press guard to (2026-10-21: "Extend
#: the two-press guard to them"), plus the three from review ruling 8.2. The
#: names are the ones the CODE uses in this gate's `_RISK` table, resolved
#: against the modules that raise the cards - the audit's wording and the
#: real action names do not all match, and a guard keyed on a name no module
#: sends would never fire.
EXTENDED_REPLACES = (
    "restore_backup", "register_approval_key", "memory_forget_range",
    "delete_file", "delete_joplin_note", "delete_logseq_page",
    "edit_joplin_note", "edit_logseq_page", "modify_own_code",
    "app_merge_change",
)

#: Review ruling 8.1: each action maps to exactly ONE warning category, and
#: the heading drawn is that category's heading - a card may never claim a
#: deletion when a recoverable copy is kept, nor promise a kept copy when the
#: action keeps none. These are the words both apps render (one source:
#: `jarvis_card_words`).
REPLACE_CATEGORIES = {
    "delete_file": "deletes_data",
    "delete_joplin_note": "deletes_data",
    "delete_logseq_page": "deletes_data",
    "memory_forget_range": "deletes_data",
    "edit_joplin_note": "overwrites_note",
    "edit_logseq_page": "overwrites_note",
    "restore_backup": "replaces_code_or_state",
    "register_approval_key": "replaces_code_or_state",
    "modify_own_code": "replaces_code_or_state",
    "app_merge_change": "replaces_code_or_state",
}

#: The claim each note must make, checked as a substring: a kept copy is named
#: ONLY where the gate's own `_RISK` why says one is really kept (a backup of
#: the CURRENT data first, the app's git history, removal in Settings), and
#: the note edits/deletions say plainly that nothing is kept.
REPLACE_CLAIMS = {
    "delete_file": "no undo",
    "delete_joplin_note": "no undo",
    "delete_logseq_page": "no undo",
    "memory_forget_range": "Undo",
    "edit_joplin_note": "keeps no copy",
    "edit_logseq_page": "keeps no copy",
    "restore_backup": "backed up first",
    "register_approval_key": "remove the device in Settings",
    "modify_own_code": "backup is the only way back",
    "app_merge_change": "older version stays in the app's git history",
}


def t_state_replacing_actions_are_marked():
    """The owner's extended set carries the flag; ordinary ones do not.

    Every name below is `reversible "no"` or `"hard"` in the gate's own
    `_RISK` table (the two reasons the owner gave for wanting the second
    press), and the fake-Cancel risk is answered by the rule itself: pressing
    once sends NOTHING, so a cancelled/abandoned card cannot have decided
    anything (`test_approval_guards`'s dedup and gate tests hold the sending
    path; this one holds the marking).
    """
    for action in EXTENDED_REPLACES:
        check(f"`{action}` is marked as replacing/removing what is there",
              G.replaces_for(action, {"text": "card"}) is True, action)
    check("the marked set is exactly the owner-approved actions - no action "
          "name twice, none forgotten",
          set(G._REPLACES_ACTIONS) == set(EXTENDED_REPLACES)
          and len(G._REPLACES_ACTIONS) == len(set(EXTENDED_REPLACES)),
          sorted(G._REPLACES_ACTIONS))
    check("a `change_own_config` card is ordinary unless it marks itself",
          G.replaces_for("change_own_config", {"what": "turn on a voice"}) is False,
          "change_own_config")
    check("the marker is data, not prose: a card SAYING 'replaces data' is not "
          "marked by its words",
          G.replaces_for("change_own_config",
                         {"text": "This REPLACES CURRENT DATA, honestly"}) is False)
    check("a card whose own module marks it does replace",
          G.replaces_for("change_own_config", {"replaces": True}) is True)
    for ordinary in ("send_email", "read_web_page", "switch_model",
                     "tidy_inbox", "draft_email"):
        check(f"an ordinary action (`{ordinary}`) is never marked",
              G.replaces_for(ordinary, {"to": "x@example.com"}) is False, ordinary)
    check("a missing action/None is not marked",
          G.replaces_for("", None) is False)


def t_the_voice_training_clear_marks_its_own_card():
    """The one state-replacing card with a generic action: its module marks it.

    The clear card is raised as `change_own_config` (the voice print decides
    who Jarvis obeys), the same action the voice settings beside it use - so
    an action name alone could not tell them apart, and the marker is what
    does. Read from the shipped module, never typed in here.
    """
    sys.dont_write_bytecode = True
    try:
        saved = list(sys.path)
        sys.path.insert(0, str(HERE))
        sys.path.insert(0, str(HERE / "rebuilt"))
        try:
            import jarvis_voice_enroll as E
        except Exception as exc:                 # pragma: no cover
            skip(f"jarvis_voice_enroll is not importable here "
                 f"({type(exc).__name__}: {exc})")
            return
        finally:
            sys.path[:] = saved
    finally:
        sys.dont_write_bytecode = _SAVED_DONT_WRITE_BYTECODE
    card_detail = E.clear_card_detail({
        "files": 3, "prints": 1, "verifiers": 1, "adaptation": 1,
        "text": "Clear the saved voice training?",
    })
    check("the voice-training clear marks its own card detail",
          card_detail.get("replaces") is True, repr(card_detail))
    check("... so the gate marks that waiting card as replacing data",
          G.replaces_for(E.ACTION, card_detail) is True,
          f"action={E.ACTION!r}")
    check("... while an ordinary voice-settings card on the same action is not",
          G.replaces_for(E.ACTION, {"what": "choose the voice to speak in"}) is False)
    check("... and the text a person reads is unchanged by the marker",
          card_detail.get("text") == "Clear the saved voice training?",
          repr(card_detail.get("text")))


def _seed(action, detail, card_id, prompt="card"):
    """Write a pending row straight into the scratch queue."""
    G._init()
    with closing(G._connect()) as c:
        c.execute(
            "INSERT INTO approvals (id,action,tier,detail,prompt,state,created,raised)"
            " VALUES (?,?,?,?,?,'pending',?,NULL)",
            (card_id, action, "ask", json.dumps(detail)[:4000], prompt, time.time()))


def t_the_three_labels_are_accurate_per_action():
    """Review ruling 8.1: three labels, each true for every action under it.

    The heading and note are drawn by BOTH apps from this one payload, so the
    pairing is checked here: every marked action has exactly one category, the
    category's own heading is what the card will say, and the note's recovery
    claim matches what the action really does (see `REPLACE_CLAIMS`, taken from
    the gate's `_RISK` why). Reverting a wording - or giving an edit the
    "keeps no copy" claim of a deletion, or promising a backup for an action
    that keeps none - fails this test, which is what "the tests bite" means
    for words.
    """
    check("every marked action has exactly one category",
          sorted(G._REPLACES_KINDS) == sorted(EXTENDED_REPLACES),
          sorted(G._REPLACES_KINDS))
    check("the categories are only the three ruling 8.1 names",
          set(G._REPLACES_KINDS.values()) == set(REPLACE_CATEGORIES.values()),
          sorted(set(G._REPLACES_KINDS.values())))
    headings = {}
    for action, category in sorted(REPLACE_CATEGORIES.items()):
        check(f"`{action}` maps to `{category}`",
              G.replaces_kind_for(action, {"text": "card"}) == category,
              G.replaces_kind_for(action, {"text": "card"}))
        words = G.replaces_words_for(action, {"text": "card"})
        headings.setdefault(category, set()).add(words.get("heading"))
        check(f"`{action}` draws the `{category}` heading, not another one",
              words.get("heading") == W.REPLACE_HEADINGS[category],
              words.get("heading"))
        check(f"`{action}` says what it really does",
              REPLACE_CLAIMS[action] in (words.get("note") or ""),
              words.get("note"))
        check(f"`{action}`'s words are the card_words module's own (one source)",
              words.get("note") == W.REPLACE_NOTES[action], words.get("note"))
    check("each category has exactly ONE heading (no drift per action)",
          all(len(v) == 1 for v in headings.values()),
          {k: sorted(v) for k, v in headings.items()})
    check("an ordinary action has no category and no warning words",
          G.replaces_kind_for("send_email", {"to": "x@example.com"}) is None
          and G.replaces_words_for("send_email", {"to": "x@example.com"}) == {},
          "send_email")
    marked = G.replaces_words_for("change_own_config", {"replaces": True})
    check("a detail-marked card draws the DELETES label",
          marked.get("kind") == "deletes_data"
          and marked.get("heading") == W.REPLACE_HEADINGS["deletes_data"],
          marked)
    check("... and its note is the category's honest fallback",
          marked.get("note") == W.REPLACE_GENERIC_NOTES["deletes_data"], marked)


def t_pending_rows_carry_the_flag_to_both_apps():
    """The wire shape both apps read: `replaces` on EVERY waiting row."""
    _reset()
    for index, action in enumerate(EXTENDED_REPLACES):
        _seed(action, {"text": "a card for " + action}, "seed-" + str(index))
    _seed("send_email", {"to": "x@example.com"}, "seed-email")
    _seed("change_own_config", {"replaces": True, "text": "Clear?"}, "seed-voice")
    rows = {r["id"]: r for r in G.pending()}
    for index, action in enumerate(EXTENDED_REPLACES):
        got = rows.get("seed-" + str(index), {}).get("replaces")
        check(f"`{action}` reaches both apps marked", got is True, repr(got))
    check("... the voice-training clear card does too",
          rows.get("seed-voice", {}).get("replaces") is True,
          repr(rows.get("seed-voice", {}).get("replaces")))
    check("... and an ordinary card says False, not 'missing' (so a client "
          "cannot read an absent field as 'unknown, allow once')",
          rows.get("seed-email", {}).get("replaces") is False,
          repr(rows.get("seed-email", {}).get("replaces")))
    check("... the flag is a JSON boolean, the shape both apps serialise",
          isinstance(rows.get("seed-0", {}).get("replaces"), bool),
          repr(type(rows.get("seed-0", {}).get("replaces"))))
    check("... the label words ride on the row too (ruling 8.1): kind, heading, note",
          rows.get("seed-0", {}).get("replaces_kind") == "replaces_code_or_state"
          and rows.get("seed-0", {}).get("replaces_heading")
          == W.REPLACE_HEADINGS["replaces_code_or_state"]
          and rows.get("seed-0", {}).get("replaces_note")
          == W.REPLACE_NOTES["restore_backup"],
          repr(rows.get("seed-0", {}))[-300:])
    check("... a note-edit card carries the OVERWRITES label, not DELETES",
          rows.get("seed-6", {}).get("replaces_kind") == "overwrites_note"
          and "DELETES" not in (rows.get("seed-6", {}).get("replaces_heading") or ""),
          repr(rows.get("seed-6", {}).get("replaces_heading")))
    check("... a delete card carries DELETES, not the note-edit label",
          rows.get("seed-3", {}).get("replaces_kind") == "deletes_data"
          and "DELETES" in (rows.get("seed-3", {}).get("replaces_heading") or ""),
          repr(rows.get("seed-3", {}).get("replaces_heading")))
    check("... an ordinary card carries no label words at all",
          rows.get("seed-email", {}).get("replaces_kind") is None
          and rows.get("seed-email", {}).get("replaces_heading") == ""
          and rows.get("seed-email", {}).get("replaces_note") == "",
          repr(rows.get("seed-email", {})))


def t_the_replaces_guard_is_what_marks_the_cards():
    """BITE: with the action table emptied, a restore loses its flag."""
    _reset()
    _seed("restore_backup", {"text": "Restore from backup?"}, "bite-restore")
    marked = {r["id"]: r for r in G.pending()}.get("bite-restore", {}).get("replaces")
    real = G._REPLACES_ACTIONS
    try:
        G._REPLACES_ACTIONS = frozenset()              # the guard, gone
        unmarked = {r["id"]: r for r in G.pending()}.get(
            "bite-restore", {}).get("replaces")
    finally:
        G._REPLACES_ACTIONS = real
    check("a restore card is marked while the table names it", marked is True,
          repr(marked))
    check("... and NOT marked the moment the table is emptied (so this suite "
          "can fail when the guard is reverted)", unmarked is False,
          repr(unmarked))
    check("... and the restored table marks it again",
          G.replaces_for("restore_backup", {}) is True)


# ==================================== the patch carrier (PROTECTED file rule)

def t_the_carrier_patch_and_the_published_gate_agree():
    """`jarvis_gate.py` is not in `backend/` whole: it is patch-carried.

    The published copy is the state the whole stack leaves and
    `backend/gate-touches.patch` is what carries the change to the owner's own
    file. This rehearses the carrier the way the patcher does - take the change
    back OUT of the published gate (which is the text the owner's own file
    holds), then apply it forwards - and proves the result is the published
    file again, byte for byte. A patch without its published copy (or the
    other way round) cannot pass this.

    `test_gate_touches.py` owns the hunk-level proof (that the four changed
    lines are the ones this change is about); what is checked HERE is that the
    change under test and the file the apps' PC will run are the same thing.
    """
    git = shutil.which("git")
    if not git:
        skip("git is not installed, so the carrier patch cannot be rehearsed here")
        return
    work = Path(tempfile.mkdtemp(prefix="jarvis-approval-guards-patch-"))
    try:
        shutil.copyfile(BASE / "jarvis_gate.py", work / "jarvis_gate.py")
        shutil.copyfile(HERE / "gate-touches.patch", work / "p.patch")
        check("the carrier patch is a real change, not an empty one",
              (work / "p.patch").stat().st_size > 1000,
              (work / "p.patch").stat().st_size)
        back = subprocess.run([git, "apply", "-R", "p.patch"], cwd=work,
                              capture_output=True, text=True)
        check("the patch reverses out of the published gate (the text the "
              "patcher recognises on the owner's PC)", back.returncode == 0,
              back.stderr.strip()[-300:])
        if back.returncode != 0:
            return
        fwd = subprocess.run([git, "apply", "p.patch"], cwd=work,
                             capture_output=True, text=True)
        check("... and applies forwards again", fwd.returncode == 0,
              fwd.stderr.strip()[-300:])
        if fwd.returncode != 0:
            return
        def _norm(path):
            return path.read_text(encoding="utf-8").replace("\r\n", "\n")
        check("... giving back the published gate byte for byte, line endings "
              "aside: the patch and the copy the tests run ARE the same change",
              _norm(work / "jarvis_gate.py") == _norm(BASE / "jarvis_gate.py"))
        check("... and the patch touches jarvis_gate.py and nothing else",
              [line[6:].strip() for line in
               (work / "p.patch").read_text(encoding="utf-8").splitlines()
               if line.startswith("+++ b/")] == ["jarvis_gate.py"])
    finally:
        shutil.rmtree(work, ignore_errors=True)

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
