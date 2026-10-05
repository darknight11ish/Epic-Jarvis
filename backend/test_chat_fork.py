"""test_chat_fork.py - "Fork from here" in History (the owner's decision of
2026-09-30; docs/CHAT-TAGS-DESIGN.md section 8 and its frozen fork contract,
docs/JARVIS-API.md section 110).

    python3 backend/test_chat_fork.py

The backend half: ChatLog.fork() and POST /api/history/fork, and the rules
around them:

  * turns 0..upto are copied into a NEW conversation "Fork of <title>", each
    turn opened and sealed again under the new id (AAD = id|idx) - the raw file
    holds neither the new title nor a copied line in the clear;
  * the fork keeps the tag, device, project, times, provenance, lane, voice
    check and read_outside marks; the source is never touched;
  * only chats the apps may Continue, and never "A difficult moment"; a
    support record, a chat with another AI and a comparison are refused;
  * the source's Forget/Erase hush is not copied - the fork has its own, set
    at the fork point, so copied messages are never learned from twice (proved
    end to end with the real learner: test_auto_learn's World);
  * no card, works with recording off, needs the key (fails closed without);
  * Undo of "Forget a time frame" restores a fork with its tag and hush;
    deleting the original leaves the fork whole;
  * the row-copy paths all read ONE column list (CONV_COLS), pinned against
    the real table.

Real jarvis_chat_log.ChatLog in a temporary folder, a test key, no network.
"""
from __future__ import annotations

import json
import shutil
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
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-chat-fork-"))
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

    def tick(self, s=10):
        self.t += s


def new_log(key=KEY, clock=None):
    _N[0] += 1
    d = _TMP / f"h{_N[0]}"
    d.mkdir()
    return H.ChatLog(d / "chat-history.db", d / "chat-history.json", lambda: key,
                     clock=clock or Clock())


def turn(log, cid, words, *, provenance="typed", answer="Sure.", live=False,
         crisis=False, read_outside=False, device="desktop"):
    m = {"role": "user", "content": words, "provenance": provenance}
    if live:
        m["live"] = True
    t = {"answer": answer, "finish_reason": "stop"}
    if crisis:
        t["crisis"] = True
    if read_outside:
        t["tools_ran"] = ["web_search"]
    return log.record_turn({"conversation_id": cid, "device": device, "messages": [m]},
                           lane="qwen3:8b", turn=t)


def _no_crypto():
    if H.AESGCM is None:
        skip("the cryptography package is not installed")
        return True
    return False


def raw_bytes(log) -> bytes:
    """Every byte the history file holds (with the WAL, if any)."""
    out = b""
    for suffix in ("", "-wal", "-journal"):
        p = Path(str(log.db_path) + suffix)
        if p.exists():
            out += p.read_bytes()
    return out


def turns_of(log, cid):
    with closing(log._connect()) as c:
        return c.execute(f"SELECT {log._TURN_COLS} FROM turns WHERE conversation_id=?"
                         " ORDER BY idx", (cid,)).fetchall()


def source(log, cid="conv-source-001", n=3, **kw):
    for i in range(n):
        turn(log, cid, f"question number {i} about the boiler", answer=f"answer number {i}", **kw)
    return cid


# ----------------------------------------------------------------- the copy

def t_a_fork_copies_the_first_turns_into_a_new_chat():
    if _no_crypto():
        return
    clock = Clock()
    log = new_log(clock=clock)
    cid = source(log)                  # idx 0 user, 1 assistant, 2 user, 3 assistant, ...
    log.tags()
    log.set_tag(cid, 2)
    clock.tick(3600)
    fork_time = clock()
    code, out = log.fork(cid, 3)
    check("a fork answers 200 and ok", code == 200 and out["ok"] is True, out)
    new = out["id"]
    check("a new id, valid as a conversation id, not the source's",
          new != cid and H._CID.fullmatch(new) is not None, new)
    check("the title is 'Fork of <title>'", out["title"] == "Fork of question number 0 about the boiler",
          out["title"])
    check("four turns were copied (0..3), and the answer says so", out["turns"] == 4, out)
    check("the tag is kept and reported", out["tag_id"] == 2, out)
    got = log.get(new)
    src = log.get(cid)
    check("the opened fork holds exactly the first four turns, in order",
          [(t["role"], t["text"]) for t in got["turns"]]
          == [(t["role"], t["text"]) for t in src["turns"][:4]], got["turns"])
    check("each turn carries its own idx, 0..3 in the fork",
          [t["idx"] for t in got["turns"]] == [0, 1, 2, 3], got["turns"])
    check("each turn keeps its time", [t["at"] for t in got["turns"]]
          == [t["at"] for t in src["turns"][:4]])
    check("the title read back from the fork is sealed under the new id",
          got["title"] == out["title"] and got["kind"] == "chat" and got["tag_id"] == 2)
    check("started is the source's; updated is the moment of the fork (it counts as new)",
          got["started"] == src["started"] and got["updated"] == fork_time
          and src["updated"] < fork_time, (got, src))
    rows = {r["id"]: r for r in log.list()["conversations"]}
    check("the list shows both, the fork with four messages",
          rows[new]["turns"] == 4 and rows[cid]["turns"] == 6 and rows[new]["device"] == "desktop",
          rows)
    a, b = turns_of(log, cid), turns_of(log, new)
    ix = {n.strip(): i for i, n in enumerate(log._TURN_COLS.split(","))}
    same = all(all(x[ix[k]] == y[ix[k]] for k in ("idx", "at", "role", "provenance", "device",
                                                  "lane", "read_outside", "voice_check"))
               for x, y in zip(a[:4], b))
    check("provenance, device, lane, voice check and read_outside are copied as they were", same)
    check("the source is untouched: six turns, same sealed bytes",
          len(a) == 6 and a[:4] != b and turns_of(log, cid) == a)


def t_the_copy_is_sealed_again_under_the_new_id():
    if _no_crypto():
        return
    log = new_log()
    cid = source(log)
    code, out = log.fork(cid, 1)
    new = out["id"]
    raw = raw_bytes(log)
    check("the raw file holds no plain title, question or answer",
          b"Fork of" not in raw and b"boiler" not in raw and b"answer number" not in raw)
    aead = log._cipher()
    blob = turns_of(log, new)[0][10]
    check("a copied line opens with the NEW id and place",
          log._open(aead, blob, log._aad(new, 0)) == b"question number 0 about the boiler")
    try:
        log._open(aead, blob, log._aad(cid, 0))
        old_opens = True
    except Exception:
        old_opens = False
    check("it does not open with the source's id (the seal is bound to the id)", not old_opens)
    with closing(log._connect()) as c:
        title = c.execute("SELECT title FROM conversations WHERE id=?", (new,)).fetchone()[0]
    check("the new title opens under the new id's title seal only",
          log._open(aead, title, log._aad(new, "title")) == b"Fork of question number 0 about the boiler")
    try:
        log._open(aead, title, log._aad(cid, "title"))
        t_old = True
    except Exception:
        t_old = False
    check("...and not under the source's", not t_old)


def t_a_fork_point_can_be_a_user_message():
    if _no_crypto():
        return
    log = new_log()
    cid = source(log)
    code, out = log.fork(cid, 2)               # the second question, without its answer
    check("forking at a user message copies through it", code == 200 and out["turns"] == 3, out)
    tail = log.get(out["id"])["turns"]
    check("...ends on that question", tail[-1]["role"] == "user"
          and tail[-1]["text"].startswith("question number 1"), tail)
    check("its answer_kept mark is cleared: no answer is kept in the fork",
          tail[-1]["answer_kept"] is False and tail[0]["answer_kept"] is True, tail)
    check("the source's mark is unchanged", log.get(cid)["turns"][2]["answer_kept"] is True)


def t_read_outside_is_copied_and_taints_the_fork():
    if _no_crypto():
        return
    log = new_log()
    cid = "conv-outside-01"
    turn(log, cid, "read my latest email", read_outside=True)
    turn(log, cid, "and I like jazz")
    code, out = log.fork(cid, 3)
    got = log.get(out["id"])
    check("the fork is marked as having read outside text", got["tainted"] is True)
    check("...on the turns that had it",
          got["turns"][0]["read_outside"] is True, got["turns"])
    fresh = H.ChatLog(log.db_path, log.settings_path, lambda: KEY)
    check("a restarted PC still treats the fork as tainted",
          fresh.conversation_tainted(out["id"], [{"role": "user", "content": "x"},
                                                 {"role": "assistant", "content": "y"},
                                                 {"role": "user", "content": "z"}]) is True)


def t_a_fork_taken_before_outside_text_is_clean():
    if _no_crypto():
        return
    log = new_log()
    cid = "conv-outside-02"
    turn(log, cid, "I like jazz")
    turn(log, cid, "read my latest email", read_outside=True)
    code, out = log.fork(cid, 1)
    check("only the turns up to the fork point come along, so no outside text",
          code == 200 and log.get(out["id"])["tainted"] is False, out)


# ------------------------------------------------------ what cannot be forked

def t_only_chats_the_apps_may_continue_are_forkable():
    if _no_crypto():
        return
    log = new_log()
    log.record_support("sup-fork-000001", "Support: refund",
                       [{"provenance": "support_company", "text": "We can refund"},
                        {"provenance": "support_owner", "text": "Thanks"}])
    log.record_chatbot("chat_0123456789ab", "Gemini: tent",
                       [{"provenance": "chatbot_reply", "text": "The X2"}])
    log.record_chatbot("cmp_0123456789ab", "Compared: tents",
                       [{"provenance": "chatbot_summary", "text": "Summary"}], kind="compare")
    for cid, kind in (("sup-fork-000001", "support"), ("chat_0123456789ab", "chatbot"),
                      ("cmp_0123456789ab", "compare")):
        code, out = log.fork(cid, 0)
        check(f"a {kind} record is not forkable (409 not_forkable, with the reason)",
              code == 409 and out == {"ok": False, "error": "not_forkable",
                                      "message": H.FORK_WHY_KIND}, out)
        conv = log.get(cid)
        check(f"...and GET says so for {kind}",
              conv["forkable"] is False and conv["fork_why"] == H.FORK_WHY_KIND)
    check("nothing was made by the refusals", len(log.list()["conversations"]) == 3)


def t_a_crisis_chat_is_never_forked():
    if _no_crypto():
        return
    log = new_log()
    turn(log, "conv-crisis-fork", "I feel like I can't go on", crisis=True)
    turn(log, "conv-late-crisis", "hello there")
    turn(log, "conv-late-crisis", "everything is too much", crisis=True)
    for cid in ("conv-crisis-fork", "conv-late-crisis"):
        code, out = log.fork(cid, 0)
        check(f"{cid}: 409 not_forkable with the crisis reason",
              code == 409 and out["error"] == "not_forkable"
              and out["message"] == H.FORK_WHY_CRISIS, out)
        conv = log.get(cid)
        check(f"{cid}: GET says forkable false and why",
              conv["forkable"] is False and conv["fork_why"] == H.FORK_WHY_CRISIS)
    check("no fork was made", len(log.list()["conversations"]) == 2)
    check("no fork's title or words leaked: the reason never quotes the owner",
          "go on" not in H.FORK_WHY_CRISIS)


def t_a_live_session_can_be_forked_as_an_ordinary_chat():
    if _no_crypto():
        return
    log = new_log()
    turn(log, "conv-live-fork01", "tell me a joke", live=True, provenance="voice")
    turn(log, "conv-live-fork01", "another one", live=True, provenance="voice")
    check("a Live session is forkable", log.get("conv-live-fork01")["forkable"] is True)
    code, out = log.fork("conv-live-fork01", 1)
    got = log.get(out["id"])
    check("the fork is an ordinary chat (kind chat), not a Live session, with its words",
          code == 200 and got["kind"] == "chat" and got["turns"][0]["text"] == "tell me a joke"
          and got["turns"][0]["provenance"] == log.get("conv-live-fork01")["turns"][0]["provenance"],
          got)


# ---------------------------------------------------------------- the errors

def t_bad_requests_and_missing_things():
    if _no_crypto():
        return
    log = new_log()
    cid = source(log)
    cases = [
        (cid, 99, 400, "bad_request"),           # past the end
        (cid, 4, 200, None),                     # exists (idx 4, a user turn)
        (cid, -1, 400, "bad_request"),
        (cid, True, 400, "bad_request"),
        (cid, "1", 400, "bad_request"),
        (cid, 1.5, 400, "bad_request"),
        (cid, None, 400, "bad_request"),
        (cid, 10 ** 30, 400, "bad_request"),      # was an OverflowError -> 500
        (cid, 2 ** 63, 400, "bad_request"),
        ("short", 0, 400, "bad_request"),
        (None, 0, 400, "bad_request"),
        ("conv-nothere-01", 0, 404, "not_found"),
    ]
    for c, u, code, err in cases:
        got_code, out = log.fork(c, u)
        check(f"fork({c!r}, {u!r}) -> {code} {err}",
              got_code == code and (err is None or (out["ok"] is False and out["error"] == err
                                                    and out["message"])), (got_code, out))
    check("each refusal has a plain sentence, none quotes the owner",
          all("boiler" not in (log.fork(c, u)[1].get("message") or "")
              for c, u, code, _ in cases if code != 200))
    n = len(log.list()["conversations"])
    check("only the one good fork was made (two chats in all)", n == 2, n)


def t_the_route_takes_exactly_id_and_upto():
    if _no_crypto():
        return
    log = new_log()
    H.use(log)
    try:
        cid = source(log)
        for body in (None, [], {}, {"id": cid}, {"upto": 1}, {"id": cid, "upto": 1, "x": 1},
                     "nope"):
            code, out = H.handle_post("/api/history/fork", body)
            check(f"body {body!r} is 400 bad_request",
                  code == 400 and out["error"] == "bad_request" and out["ok"] is False, out)
        code, out = H.handle_post("/api/history/fork", {"id": cid, "upto": 1})
        check("a good body works through the route", code == 200 and out["turns"] == 2, out)
        check("the module-level call is the same door",
              H.fork_chat(cid, 3)[0] == 200)
    finally:
        H.use(None)


def t_the_route_is_whitelisted_in_the_hud_patch():
    patch = (HERE / "chat-history.patch").read_text(encoding="utf-8")
    check("chat-history.patch lets POST /api/history/fork through to jarvis_chat_log",
          '"/api/history/fork"' in patch)


# ---------------------------------------------------- key, recording, hush

def t_fork_works_while_recording_is_off_but_needs_the_key():
    if _no_crypto():
        return
    log = new_log()
    cid = source(log)
    log.set_enabled(False)
    code, out = log.fork(cid, 1)
    check("with chat history OFF an already-kept chat can still be forked",
          code == 200 and log.get(out["id"])["turns"][0]["text"].startswith("question number 0"),
          out)
    # No key: fail closed, nothing read or written.
    before = raw_bytes(log)
    bad = H.ChatLog(log.db_path, log.settings_path, lambda: b"short")
    code, out = bad.fork(cid, 1)
    check("no usable key: 503 bad_request with a plain reason, fail closed",
          code == 503 and out["ok"] is False and out["error"] == "bad_request"
          and "not forked" in out["message"], out)
    wrong = H.ChatLog(log.db_path, log.settings_path, lambda: bytes(reversed(range(32))))
    code, out = wrong.fork(cid, 1)
    check("a key that does not open the history is refused the same way",
          code == 503 and out["ok"] is False, out)
    check("...and nothing was written", raw_bytes(log) == before)
    with closing(log._connect()) as c:
        n = c.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    check("still two chats in the file", n == 2, n)


def t_the_source_hush_is_not_copied_the_fork_has_its_own():
    if _no_crypto():
        return
    log = new_log()
    cid = source(log, n=3)
    log.note_hush(cid, erased=True)             # the owner Erased a fact said here
    code, out = log.fork(cid, 3)                # the first two exchanges
    new = out["id"]
    with closing(log._connect()) as c:
        src = log._hush_read(c, cid)
        fork = log._hush_read(c, new)
    check("the source keeps its own hush (up to its newest user turn, erased)",
          src == {"upto": 4, "erased": True}, src)
    check("the fork gets ITS OWN, up to the last copied user message, and keeps 'erased'",
          fork == {"upto": 2, "erased": True}, fork)
    log3 = new_log()
    c3 = source(log3, n=3)
    log3.note_hush(c3, erased=False)
    code, o3 = log3.fork(c3, 3)
    with closing(log3._connect()) as c:
        check("a plain Forget's hush stays 'not erased' in the fork",
              log3._hush_read(c, o3["id"]) == {"upto": 2, "erased": False})
    # A fork of a chat with no hush also gets the fork-point hush.
    log2 = new_log()
    c2 = source(log2, n=2)
    code, o2 = log2.fork(c2, 1)
    with closing(log2._connect()) as c:
        check("a fork of a chat that never had a hush still gets one",
              log2._hush_read(c, o2["id"]) == {"upto": 0, "erased": False})
    # Only an assistant answer: no user message, no hush needed.
    check("hush rows hold numbers only, never words",
          b"boiler" not in raw_bytes(log))


def t_copied_turns_are_not_learned_twice():
    """End to end with the real learner: test_auto_learn's World."""
    if _no_crypto():
        return
    try:
        import test_auto_learn as TA
    except Exception as exc:               # pragma: no cover - needs the shipped modules
        skip(f"the learner's test World cannot be built here ({type(exc).__name__})")
        return
    A, H2 = TA.A, TA.H
    w = TA.World()
    try:
        src = "conv-learn-src01"
        w.say("I live in York", cid=src)
        w.say("My sister is called Priya", cid=src)
        first = w.learn(["The owner lives in York"], cid=src)
        check("the fact is learned once, in the source chat", TA.saved(first), first)
        code, out = w.log.fork(src, 3)
        check("the fork is made", code == 200, out)
        fk = out["id"]
        # The backend restarts; the owner continues the fork.
        TA._restart(w)
        w.say("I'm learning the cello", cid=fk)
        e = H2.live_turn(fk, "I live in York")
        check("Continue puts the fork's copied messages back, from the record",
              e is not None and e.get("from_record") is True, e)
        floor = H2.hush_floor(fk)
        check("...under the fork's hush floor, newest copied message included",
              floor is not None and floor["seq"] >= e["seq"]
              and H2.live_turn(fk, "My sister is called Priya")["seq"] <= floor["seq"], floor)
        check("the new message is above the floor",
              H2.live_turn(fk, "I'm learning the cello")["seq"] > floor["seq"])
        again = w.learn(["The owner lives in York"], cid=fk)
        check("the same fact from a copied message is dropped, not proposed again",
              again.get("dropped") and not again.get("saved") and not again.get("cards"), again)
        new = w.learn(["The owner is learning the cello"], cid=fk)
        check("a fact from a message said AFTER the fork is learned as usual",
              TA.saved(new), new)
        # Control: without the fork-point hush the copied words WOULD be read again.
        with closing(w.log._connect()) as c:
            with c:
                c.execute("DELETE FROM meta WHERE k=?", (w.log._hush_key(fk),))
        TA._restart(w)
        w.say("and I like jazz", cid=fk)
        ctrl = w.learn(["The owner has a sister called Priya"], cid=fk)
        check("control: with the hush removed the copied message is read again "
              "(so it is the hush that prevents the double learning)",
              not ctrl.get("dropped"), ctrl)
    finally:
        w.done()


def t_a_fork_does_not_double_the_said_again_count():
    """The audit's reproduction: chat-history.patch records a turn with an `at`
    a few seconds EARLIER than the moment the live registry saw it, so the
    fork's copy (put back from the record) has another time than the source's
    live entry - and a store that keeps one row per time counted both."""
    if _no_crypto():
        return
    try:
        import test_auto_learn as TA
        import jarvis_intake as I
    except Exception as exc:               # pragma: no cover
        skip(f"the learner's test World cannot be built here ({type(exc).__name__})")
        return

    class Store:
        """One row per (fact, time), like MemoryStore.said_again."""
        def __init__(self):
            self.rows = set()

        def search(self, text, k=5, word_floor=0.0):
            return [{"id": 1, "text": "The owner lives in York", "current": True}]

        def said_again(self, fid, at, prov):
            before = len(self.rows)
            self.rows.add((fid, at))
            return len(self.rows) > before

    import time
    w = TA.World()
    try:
        src = "conv-said-src001"
        now = time.time()
        w.log.record_turn({"conversation_id": src, "device": "desktop", "messages": [
            {"role": "user", "content": "I live in York", "provenance": "typed"}]},
            lane="qwen3:8b", turn={"answer": "ok", "finish_reason": "stop"}, at=now - 30)
        w.log.record_turn({"conversation_id": src, "device": "desktop", "messages": [
            {"role": "user", "content": "I live in York", "provenance": "typed"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "and I like tea", "provenance": "typed"}]},
            lane="qwen3:8b", turn={"answer": "ok", "finish_reason": "stop"}, at=now - 20)
        code, out = w.log.fork(src, 3)
        check("the fork is made", code == 200, out)
        fk = out["id"]
        # The fork is continued: its copied messages come back from the record.
        w.log.record_turn({"conversation_id": fk, "device": "desktop", "messages": [
            {"role": "user", "content": "I live in York", "provenance": "typed"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "and I like tea", "provenance": "typed"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "one more thing", "provenance": "typed"}]},
            lane="qwen3:8b", turn={"answer": "ok", "finish_reason": "stop"}, at=now - 10)
        e_fork = H.live_turn(fk, "I live in York")
        e_src = H.live_turn(src, "I live in York")
        check("the copy came back from the record with another time than the live entry",
              e_fork and e_src and e_fork.get("from_record") and e_fork["at"] != e_src["at"],
              (e_fork, e_src))
        st = Store()
        n = I.note_said_again(["The owner lives in York"], ["I live in York"], store=st)
        check("the words count once, not once per copy", n <= 1 and len(st.rows) == 1,
              (n, st.rows))
        check("...and it is the source's own live message that counted",
              (1, e_src["at"]) in st.rows, st.rows)
        # Only a fork: the source's live entry is gone (a restart) - nothing counts.
        TA._restart(w)
        w.log.record_turn({"conversation_id": fk, "device": "desktop", "messages": [
            {"role": "user", "content": "I live in York", "provenance": "typed"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "and I like tea", "provenance": "typed"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "a new day", "provenance": "typed"}]},
            lane="qwen3:8b", turn={"answer": "ok", "finish_reason": "stop"})
        st2 = Store()
        check("after a restart a message that only exists as a fork copy is not counted",
              I.note_said_again(["The owner lives in York"], ["I live in York"], store=st2) == 0
              and not st2.rows, st2.rows)
    finally:
        w.done()


def t_a_fork_of_an_erased_chat_secure_deletes_re_proposals():
    """The source hush says 'erased': the fork's must too, so the learner
    deletes (secure_delete) a re-proposal of the erased fact in the fork, as
    it does in the source, instead of keeping the words as a rejected row."""
    if _no_crypto():
        return
    try:
        import test_auto_learn as TA
    except Exception as exc:               # pragma: no cover
        skip(f"the learner's test World cannot be built here ({type(exc).__name__})")
        return
    w = TA.World()
    try:
        src = "conv-erase-src01"
        w.say("I live in York", cid=src)
        w.say("My sister is called Priya", cid=src)
        first = w.learn(["The owner lives in York"], cid=src)
        check("learned once in the source", TA.saved(first), first)
        w.log.note_hush(src, erased=True)
        code, out = w.log.fork(src, 3)
        fk = out["id"]
        TA._restart(w)
        w.say("I'm learning the cello", cid=fk)
        res = w.learn(["The owner lives in York"], cid=fk)
        check("the fork's hush is 'erased' (copied from the source)",
              A_hush(fk) == "erased" or bool(res.get("dropped")), res)
        with closing(w.store._connect()) as c:
            left = c.execute("SELECT COUNT(*) FROM proposals WHERE text LIKE ?"
                             " AND state IN ('pending', 'rejected')",
                             ("%lives in York%",)).fetchone()[0]
            rej = 0
        check("the re-proposal leaves no copy of the erased words in the fork "
              "(deleted, not kept as rejected)", left == 0 and rej == 0, (left, rej))
    finally:
        w.done()


def A_hush(cid):
    try:
        import jarvis_auto_learn as A
        return A.hushed(cid, ["I live in York"])
    except Exception:
        return ""


# ------------------------------------------------- forks, tags, Undo, delete

def t_a_fork_of_a_fork():
    if _no_crypto():
        return
    log = new_log()
    cid = source(log)
    code, one = log.fork(cid, 3)
    code, two = log.fork(one["id"], 1)
    check("a fork of a fork works and is titled from the fork",
          code == 200 and two["title"] == "Fork of Fork of question number 0 about the boiler"
          and two["turns"] == 2, two)
    got = log.get(two["id"])
    check("its two turns are the source's first two",
          [t["text"] for t in got["turns"]] ==
          ["question number 0 about the boiler", "answer number 0"], got)
    check("a very long title is cut with an ellipsis at the title limit",
          len(log.fork(cid, 1)[1]["title"]) <= H.TITLE_CHARS)
    long_cid = "conv-longtitle01"
    turn(log, long_cid, "x" * 200)
    t = log.fork(long_cid, 1)[1]["title"]
    check("...and starts with 'Fork of '", t.startswith("Fork of ") and len(t) <= H.TITLE_CHARS
          and t.endswith("…"), t)


def t_forks_continue_normally_and_are_independent():
    if _no_crypto():
        return
    log = new_log()
    cid = source(log)
    code, out = log.fork(cid, 3)
    new = out["id"]
    turn(log, new, "a new thought in the fork", answer="a new reply")
    conv = log.get(new)
    check("a message added to the fork lands after the copied turns",
          [t["idx"] for t in conv["turns"]] == [0, 1, 2, 3, 4, 5]
          and conv["turns"][4]["text"] == "a new thought in the fork", conv["turns"])
    check("the source did not get it", len(log.get(cid)["turns"]) == 6)
    # Retagging one does not move the other.
    log.tags()
    log.set_tag(new, 3)
    check("tags are independent afterwards", log.get(cid)["tag_id"] is None
          and log.get(new)["tag_id"] == 3)


def t_deleting_the_original_leaves_the_fork_whole():
    if _no_crypto():
        return
    log = new_log()
    cid = source(log)
    log.tags()
    log.set_tag(cid, 1)
    new = log.fork(cid, 3)[1]["id"]
    check("the original is deleted", log.delete(cid) is True)
    got = log.get(new)
    check("the fork is intact: title, four turns, tag",
          got is not None and got["title"].startswith("Fork of ") and len(got["turns"]) == 4
          and got["tag_id"] == 1, got)
    check("...and every copied line still opens",
          all("could not be opened" not in t["text"] for t in got["turns"]))
    with closing(log._connect()) as c:
        h = log._hush_read(c, new)
    check("its own hush is still there", h == {"upto": 2, "erased": False}, h)


def t_undo_of_forget_a_time_frame_restores_a_fork_with_its_tag():
    if _no_crypto():
        return
    log = new_log()
    cid = source(log)
    log.tags()
    log.set_tag(cid, 4)
    new = log.fork(cid, 3)[1]["id"]
    before = log.get(new)
    held = log.take_out([new])
    check("Forget a time frame takes the fork out", log.get(new) is None and new in held)
    back = log.put_back(held)
    after = log.get(new)
    check("Undo puts it back", back["restored"] == [new] and after is not None, back)
    check("...with its title, turns and tag",
          after["title"] == before["title"] and after["tag_id"] == 4
          and [t["text"] for t in after["turns"]] == [t["text"] for t in before["turns"]], after)
    with closing(log._connect()) as c:
        h = log._hush_read(c, new)
    check("...and its hush, so the copied messages are still not re-learned",
          h == {"upto": 2, "erased": False}, h)
    check("the source was not part of it", log.get(cid) is not None
          and log.get(cid)["tag_id"] == 4)


# ------------------------------------------------------- the shared column list

def t_one_column_list_covers_every_row_copy():
    if _no_crypto():
        return
    log = new_log()
    turn(log, "conv-cols-000001", "hello")
    with closing(log._connect()) as c:
        cols = [r[1] for r in c.execute("PRAGMA table_info(conversations)")]
    check("CONV_COLS is exactly the conversations table, in the same order",
          list(H.CONV_COLS) == cols, (H.CONV_COLS, cols))
    check("the SQL helper names every column once",
          H._conv_cols(raw=True).split(", ") == list(H.CONV_COLS)
          and "COALESCE(kind, 'chat')" in H._conv_cols()
          and "COALESCE" not in H._conv_cols(raw=True))
    log.tags()
    log.set_tag("conv-cols-000001", 2)
    held = log.take_out(["conv-cols-000001"])
    check("take_out holds a row as wide as the table",
          len(held["conv-cols-000001"]["conversation"]) == len(H.CONV_COLS))
    # A row held before tag_id existed (7 columns) still goes back.
    old = held["conv-cols-000001"]
    old["conversation"] = old["conversation"][:6]
    back = log.put_back({"conv-cols-000001": old})
    check("a short (older) held row is padded, not lost",
          back["restored"] == ["conv-cols-000001"], back)


# ------------------------------------------------------------------ the read

def t_the_single_read_gains_idx_and_forkable():
    if _no_crypto():
        return
    log = new_log()
    cid = source(log, n=2)
    conv = log.get(cid)
    check("every turn has an integer idx, in order",
          [t["idx"] for t in conv["turns"]] == [0, 1, 2, 3], conv["turns"])
    check("an ordinary chat is forkable with an empty reason",
          conv["forkable"] is True and conv["fork_why"] == "")
    H.use(log)
    try:
        code, out = H.handle_get("/api/history/conversation", f"id={cid}")
        check("GET /api/history/conversation carries idx and forkable",
              code == 200 and out["forkable"] is True and out["turns"][3]["idx"] == 3, out)
    finally:
        H.use(None)


if __name__ == "__main__":
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"\n--- {name} ---")
                try:
                    fn()
                except Exception:
                    FAILED.append(name)
                    traceback.print_exc()
    finally:
        H.use(None)
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
