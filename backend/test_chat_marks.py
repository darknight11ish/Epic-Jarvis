"""test_chat_marks.py - "New section here": a divider the owner puts above one of
their messages in a long chat (the owner's decision of 2026-09-30;
docs/OVERNIGHT-TAGS-DESIGN.md section 5, docs/JARVIS-API.md section 106).

    python3 backend/test_chat_marks.py

The rules this pins:

  * VIEW-ONLY: a marker is a sealed list of turn numbers in its own table. It
    never changes a turn, never reaches the learner, memory or a model (the
    owner's answer, 2026-09-30: "only a divider");
  * offered from 10 turns; at most 20; a number must be an existing turn;
    adding twice or removing a missing one is fine (idempotent);
  * not on a crisis chat ("A difficult moment"), or a support, chatbot or
    comparison record (the same test as `forkable`);
  * sealed: the database file holds no readable turn-number list;
  * carried through every path that moves or copies a chat: take_out/put_back
    (Undo of "Forget a time frame"), fork (only the markers at or below `upto`,
    renumbered), delete (the row goes with the chat);
  * works while history is OFF (it marks an already-kept chat); 503 with no key.

Runs against the real jarvis_chat_log.ChatLog in a temporary folder with a test
key. No network, no model.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import traceback
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_chat_log.py")
import jarvis_chat_log as H  # noqa: E402

KEY = bytes(range(32))
PASSED, FAILED = [], []
SKIPPED = []
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-chat-marks-"))
_N = [0]


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass. (It used to be check("SKIP - ...", True) - a condition of
    the constant True, so it printed as a pass and was counted as one.)"""
    SKIPPED.append(why)
    print(f"skip  {why}")


class Clock:
    def __init__(self, t=1_790_000_000.0):
        self.t = float(t)

    def __call__(self):
        return self.t


def new_log(key=KEY):
    _N[0] += 1
    d = _TMP / f"h{_N[0]}"
    d.mkdir()
    clk = Clock()
    log = H.ChatLog(d / "chat-history.db", d / "chat-history.json", lambda: key, clock=clk)
    return log, clk


def turn(log, cid, words, *, answer="Sure.", crisis=False, live=False):
    m = {"role": "user", "content": words, "provenance": "typed"}
    if live:
        m["live"] = True
    t = {"answer": answer, "finish_reason": "stop"}
    if crisis:
        t["crisis"] = True
    return log.record_turn({"conversation_id": cid, "device": "desktop", "messages": [m]},
                           lane="test", turn=t)


def chat(log, cid, exchanges=6, **kw):
    """`exchanges` questions with answers = 2 * exchanges turns."""
    for i in range(exchanges):
        turn(log, cid, f"question number {i} about the garage door", **kw)
    return cid


def _no_crypto():
    if H.AESGCM is None:
        skip("the cryptography package is not installed")
        return True
    return False


def raw_marks(log):
    with closing(sqlite3.connect(str(log.db_path))) as c:
        return c.execute("SELECT conversation_id, v FROM marks").fetchall()


# ------------------------------------------------------------------ tests

def t_read_and_offer():
    if _no_crypto():
        return
    log, _ = new_log()
    chat(log, "conv-short-00001", exchanges=4)          # 8 turns
    got = log.get("conv-short-00001")
    check("a chat under 10 turns is not markable, with a plain reason",
          got["markable"] is False and got["mark_why"] == H.MARK_WHY_SHORT and got["marks"] == [],
          got)
    chat(log, "conv-long-000001", exchanges=5)          # 10 turns
    got = log.get("conv-long-000001")
    check("10 turns is markable, no marks yet, no reason",
          got["markable"] is True and got["mark_why"] == "" and got["marks"] == [], got)
    code, out = log.set_mark("conv-short-00001", 0, True)
    check("marking a short chat is refused 409 not_markable, mark_why in the answer",
          code == 409 and out["error"] == "not_markable" and out["mark_why"] == H.MARK_WHY_SHORT
          and out["message"] == H.MARK_WHY_SHORT, (code, out))


def t_add_remove_idempotent():
    if _no_crypto():
        return
    log, _ = new_log()
    cid = chat(log, "conv-marks-00001", exchanges=6)
    code, out = log.set_mark(cid, 4, True)
    check("add answers ok with the whole list",
          code == 200 and out == {"ok": True, "id": cid, "idx": 4, "on": True, "marks": [4]}, out)
    code, out = log.set_mark(cid, 2, True)
    check("the list is sorted", out["marks"] == [2, 4], out)
    code, out = log.set_mark(cid, 2, True)
    check("adding the same one again is fine and changes nothing",
          code == 200 and out["marks"] == [2, 4], out)
    check("the chat read carries the marks", log.get(cid)["marks"] == [2, 4])
    code, out = log.set_mark(cid, 2, False)
    check("remove works", code == 200 and out["marks"] == [4] and out["on"] is False, out)
    code, out = log.set_mark(cid, 2, False)
    check("removing a missing one is fine", code == 200 and out["marks"] == [4], out)
    code, out = log.set_mark(cid, 4, False)
    check("the last one removed leaves no row at all",
          code == 200 and out["marks"] == [] and raw_marks(log) == [], (out, raw_marks(log)))


def t_bad_input():
    if _no_crypto():
        return
    log, _ = new_log()
    cid = chat(log, "conv-marks-00002", exchanges=6)     # turns 0..11
    for label, idx in (("negative", -1), ("a fraction", 1.5), ("past the end", 12),
                       ("text", "3"), ("a bool", True), ("None", None)):
        code, out = log.set_mark(cid, idx, True)
        check(f"idx {label} is bad_request", code == 400 and out["error"] == "bad_request"
              and out["ok"] is False, (code, out))
    code, out = log.set_mark(cid, 3, "yes")
    check("on must be a real boolean", code == 400, out)
    code, out = log.set_mark("../etc/passwd", 3, True)
    check("a bad chat id is bad_request", code == 400, out)
    code, out = log.set_mark("conv-nothere-0001", 3, True)
    check("a chat that is gone is 404 not_found", code == 404 and out["error"] == "not_found", out)
    check("nothing was written by any of them", raw_marks(log) == [])


def t_limit_of_twenty():
    if _no_crypto():
        return
    log, _ = new_log()
    cid = chat(log, "conv-marks-00003", exchanges=15)    # 30 turns
    for i in range(20):
        code, out = log.set_mark(cid, i, True)
        assert code == 200, (i, out)
    code, out = log.set_mark(cid, 20, True)
    check("the 21st is refused too_many_marks (409) with the fixed sentence",
          code == 409 and out["error"] == "too_many_marks"
          and out["message"] == "You can have at most 20 section breaks in one chat.", (code, out))
    check("still twenty", len(log.get(cid)["marks"]) == 20)
    code, out = log.set_mark(cid, 5, True)
    check("re-adding one of the twenty is not the 21st", code == 200, out)
    code, out = log.set_mark(cid, 0, False)
    code, out = log.set_mark(cid, 20, True)
    check("after a removal there is room again", code == 200 and 20 in out["marks"], out)


def t_sealed_and_view_only():
    if _no_crypto():
        return
    log, _ = new_log()
    cid = chat(log, "conv-marks-00004", exchanges=6)
    with closing(sqlite3.connect(str(log.db_path))) as c:
        before = c.execute("SELECT * FROM turns ORDER BY conversation_id, idx").fetchall()
        conv_before = c.execute("SELECT * FROM conversations").fetchall()
    log.set_mark(cid, 7, True)
    log.set_mark(cid, 3, True)
    rows = raw_marks(log)
    check("one row for the chat", len(rows) == 1 and rows[0][0] == cid)
    blob = bytes(rows[0][1])
    check("the value is sealed: no readable turn-number list in it",
          b"[3, 7]" not in blob and b"3" != blob and b"[" not in blob[:1], blob)
    raw = log.db_path.read_bytes()
    check("...and none in the database file", b"[3, 7]" not in raw and b"[3,7]" not in raw)
    with closing(sqlite3.connect(str(log.db_path))) as c:
        after = c.execute("SELECT * FROM turns ORDER BY conversation_id, idx").fetchall()
        conv_after = c.execute("SELECT * FROM conversations").fetchall()
    check("no turn was touched (the turns table is byte for byte the same)", before == after)
    check("the conversation row is untouched too (same title, updated, tag)",
          conv_before == conv_after)
    # sealed under the marks AAD, not any other
    aead = log._cipher()
    try:
        log._open(aead, blob, log._aad(cid, "title"))
        wrong = True
    except Exception:
        wrong = False
    check("it opens only with its own AAD (id|marks), not the title's", not wrong)
    check("it opens with the right one",
          json.loads(log._open(aead, blob, log._aad(cid, "marks"))) == [3, 7])


def t_kinds_refused():
    if _no_crypto():
        return
    log, _ = new_log()
    chat(log, "conv-crisis-0001", exchanges=6, crisis=True)
    got = log.get("conv-crisis-0001")
    check("a crisis chat is not markable", got["markable"] is False
          and got["mark_why"] == H.MARK_WHY_CRISIS, got["mark_why"])
    code, out = log.set_mark("conv-crisis-0001", 2, True)
    check("...and marking it is 409 not_markable", code == 409 and out["error"] == "not_markable", out)
    rows = [{"provenance": "support_company", "text": f"line {i}", "at": 1_790_000_000 + i}
            for i in range(12)]
    log.record_support("conv-support-001", "Refund", rows)
    got = log.get("conv-support-001")
    check("a support record is not markable", got["markable"] is False
          and got["mark_why"] == H.MARK_WHY_KIND, got["mark_why"])
    log.record_chatbot("conv-chatbot-001", "Asked an AI", [
        {"provenance": "chatbot_reply", "text": f"line {i}", "at": 1_790_000_000 + i}
        for i in range(12)])
    log.record_chatbot("conv-compare-001", "Comparison", [
        {"provenance": "chatbot_reply", "text": f"line {i}", "at": 1_790_000_000 + i}
        for i in range(12)], kind="compare")
    for cid in ("conv-support-001", "conv-chatbot-001", "conv-compare-001"):
        code, out = log.set_mark(cid, 1, True)
        check(f"{cid}: 409 not_markable", code == 409 and out["error"] == "not_markable", (code, out))
    chat(log, "conv-live-000001", exchanges=6, live=True)
    got = log.get("conv-live-000001")
    check("a Live session is markable (the same test as fork)",
          got["kind"] == "live" and got["markable"] is True, got["kind"])
    check("markable agrees with forkable for every kind",
          all(log.get(c)["markable"] == log.get(c)["forkable"] for c in
              ("conv-live-000001", "conv-crisis-0001", "conv-support-001")))


def t_history_off_and_no_key():
    if _no_crypto():
        return
    log, _ = new_log()
    cid = chat(log, "conv-marks-00005", exchanges=6)
    log.set_enabled(False)
    code, out = log.set_mark(cid, 2, True)
    check("works while chat history is OFF (it records nothing new)",
          code == 200 and out["marks"] == [2], (code, out))
    nokey = H.ChatLog(log.db_path, log.settings_path, lambda: None, clock=Clock())
    code, out = nokey.set_mark(cid, 4, True)
    check("503 with no key, and the answer says nothing was saved",
          code == 503 and "not saved" in out["message"], (code, out))
    check("...and nothing was written", log.get(cid)["marks"] == [2])


def t_through_take_out_and_put_back():
    if _no_crypto():
        return
    log, _ = new_log()
    cid = chat(log, "conv-marks-00006", exchanges=6)
    log.set_mark(cid, 2, True)
    log.set_mark(cid, 5, True)
    held = log.take_out([cid])
    check("take_out removes the chat and its marks row", log.get(cid) is None
          and raw_marks(log) == [])
    check("the held chat carries the marks still sealed (no plain list)",
          isinstance(held[cid].get("marks"), bytes) and b"[2, 5]" not in held[cid]["marks"])
    out = log.put_back(held)
    check("put_back restores the chat", out["restored"] == [cid], out)
    check("...with its section breaks", log.get(cid)["marks"] == [2, 5], log.get(cid)["marks"])
    # joined: the owner went on with the chat after it was deleted
    cid2 = chat(log, "conv-marks-00007", exchanges=6)
    log.set_mark(cid2, 3, True)
    held = log.take_out([cid2])
    log._clock.t += 60
    for i in range(3):
        turn(log, cid2, f"new question {i} after the delete")
    # the new chat restarted at turn 0; give one of its turns a break
    fresh = log.get(cid2)
    check("the chat came back as a new, short one", len(fresh["turns"]) == 6)
    log.set_mark  # (too short to mark: 6 turns) -> the joined marks come only from the held ones
    out = log.put_back(held)
    joined = log.get(cid2)
    check("joined chat: restored, old messages first",
          out["restored"] == [cid2] and len(joined["turns"]) == 18, out)
    check("joined chat keeps the held section break", joined["marks"] == [3], joined["marks"])


def t_joined_marks_follow_their_messages():
    if _no_crypto():
        return
    log, _ = new_log()
    cid = chat(log, "conv-marks-00008", exchanges=5)     # 10 turns, break at 3
    log.set_mark(cid, 3, True)
    held = log.take_out([cid])
    log._clock.t += 60
    chat(log, cid, exchanges=6)                            # a new chat, 12 turns, numbers 0..11
    log.set_mark(cid, 4, True)                             # a break on ITS message 4
    out = log.put_back(held)
    joined = log.get(cid)
    n_held = 10
    check("joined: 10 held + 12 newer turns", out["restored"] == [cid] and len(joined["turns"]) == 22)
    check("the held break stays, the newer break moved to follow its message (4 -> 14)",
          joined["marks"] == [3, n_held + 4], joined["marks"])
    t14 = joined["turns"][14]["text"]
    check("...and 14 is really the message that had number 4",
          "number 2" in t14, t14)


def t_fork_carries_marks_up_to():
    if _no_crypto():
        return
    log, _ = new_log()
    cid = chat(log, "conv-marks-00009", exchanges=8)     # 16 turns
    for i in (2, 6, 9, 12):
        log.set_mark(cid, i, True)
    code, out = log.fork(cid, 8)
    check("fork works", code == 200, out)
    forked = log.get(out["id"])
    check("only the breaks at or below upto are carried", forked["marks"] == [2, 6], forked["marks"])
    check("the source keeps all of its own", log.get(cid)["marks"] == [2, 6, 9, 12])
    code, out2 = log.fork(cid, 6)
    check("a break exactly at upto is carried (it sits above that message)",
          log.get(out2["id"])["marks"] == [2, 6])
    code, out3 = log.fork(cid, 1)
    check("a fork before any break has none, and no row", log.get(out3["id"])["marks"] == []
          and all(r[0] != out3["id"] for r in raw_marks(log)))
    rows = dict(raw_marks(log))
    aead = log._cipher()
    check("the fork's row is sealed for the fork (AAD = new id|marks)",
          json.loads(log._open(aead, rows[out["id"]], log._aad(out["id"], "marks"))) == [2, 6])


def t_delete_removes_marks():
    if _no_crypto():
        return
    log, _ = new_log()
    cid = chat(log, "conv-marks-00010", exchanges=6)
    log.set_mark(cid, 2, True)
    check("there is a row", len(raw_marks(log)) == 1)
    check("delete removes the chat", log.delete(cid) is True)
    check("...and its marks row", raw_marks(log) == [])


def t_sweep_removes_marks():
    if _no_crypto():
        return
    log, clk = new_log()
    cid = chat(log, "conv-marks-00011", exchanges=6)
    log.set_mark(cid, 2, True)
    log._save_settings(keep_days=30)
    clk.t += 40 * 86400
    check("the keep-days sweep deleted the chat", log.sweep() == 1)
    check("...and its marks row", raw_marks(log) == [])


def t_routes():
    if _no_crypto():
        return
    log, _ = new_log()
    H.use(log)
    try:
        cid = chat(log, "conv-marks-00012", exchanges=6)
        code, out = H.handle_post("/api/history/mark", {"id": cid, "idx": 4, "on": True})
        check("POST /api/history/mark adds", code == 200 and out["marks"] == [4], (code, out))
        code, out = H.handle_get("/api/history/conversation", "id=" + cid)
        check("GET /api/history/conversation carries marks, markable, mark_why",
              code == 200 and out["marks"] == [4] and out["markable"] is True
              and out["mark_why"] == "", out.get("marks"))
        for bad in ({"id": cid, "idx": 4}, {"id": cid, "idx": 4, "on": True, "x": 1}, [], None):
            code, out = H.handle_post("/api/history/mark", bad)
            check(f"a body of the wrong shape is 400: {bad!r}", code == 400
                  and out["error"] == "bad_request", (code, out))
        code, out = H.handle_post("/api/history/mark", {"id": cid, "idx": 4, "on": False})
        check("POST removes", code == 200 and out["marks"] == [])
    finally:
        H.use(None)


def t_no_chat_words_in_audit_or_learner():
    if _no_crypto():
        return
    log, _ = new_log()
    cid = chat(log, "conv-marks-00013", exchanges=6)
    before = log.live_upto(cid)
    seen = []
    orig = H._audit
    H._audit = lambda e, d: seen.append((e, d))
    H.use(log)
    try:
        H.handle_post("/api/history/mark", {"id": cid, "idx": 4, "on": True})
    finally:
        H._audit = orig
        H.use(None)
    check("the audit line holds no chat id, no words and no turn number",
          seen == [("history.mark", {"on": True})], seen)
    check("the learner's registry is untouched", log.live_upto(cid) == before)


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("t_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
        except Exception:
            FAILED.append(name)
            print(f"FAIL {name} raised\n{traceback.format_exc()}")
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
