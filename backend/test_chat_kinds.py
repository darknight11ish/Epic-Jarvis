"""test_chat_kinds.py - what kind of conversation each History row is, and
the other chat-history changes of the chat audit (2026-09-28).

    python3 backend/test_chat_kinds.py

The owner's decisions of 2026-09-28 (CLAUDE.md, "History marks Live
sessions" and "Chats, after the chat audit"; docs/studio-2026-09-28/
chat-audit-*.md):

  * History rows carry a kind - chat, live, support, chatbot, compare - and a
    project (empty until Projects step 4). ONE schema change, with a
    migration: a history kept before it is given both in place, support
    records becoming "support" and everything else "chat".
  * Chats with other AIs and comparisons are kept in History, encrypted,
    marked as outside text, never learned from, never read aloud - and
    read-only (no "Continue this chat").
  * Crisis chats are kept but titled "A difficult moment", never with the
    owner's words.
  * "Delete conversations older than" never removes a support chat's record
    by itself.

Everything runs against the real jarvis_chat_log.ChatLog in a temporary
folder, with a test key. No network, no model.
"""
from __future__ import annotations

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
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-chat-kinds-"))
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


def new_log(clock=None):
    _N[0] += 1
    d = _TMP / f"h{_N[0]}"
    d.mkdir()
    return H.ChatLog(d / "chat-history.db", d / "chat-history.json", lambda: KEY,
                     clock=clock or Clock())


def turn(log, cid, words, *, live=False, provenance="typed", answer="Sure.", crisis=False,
         extra=None, device="desktop"):
    msgs = list(extra or [])
    m = {"role": "user", "content": words, "provenance": provenance}
    if live:
        m["live"] = True
    msgs.append(m)
    t = {"answer": answer, "finish_reason": "stop"}
    if crisis:
        t["crisis"] = True
    return log.record_turn({"conversation_id": cid, "device": device, "messages": msgs},
                           lane="test", turn=t)


def t_kinds_on_new_rows():
    if H.AESGCM is None:
        return skip("the cryptography package is not installed")
    log = new_log()
    turn(log, "conv-plain-0001", "what is the weather")
    turn(log, "conv-live-00002", "tell me a joke", live=True, provenance="voice")
    rows = {c["id"]: c for c in log.list()["conversations"]}
    check("an ordinary chat is kind chat", rows["conv-plain-0001"]["kind"] == "chat", rows)
    check("a chat started in Jarvis Live is kind live",
          rows["conv-live-00002"]["kind"] == "live", rows)
    check("every row carries project, empty until Projects step 4",
          all(r["project"] is None for r in rows.values()), rows)
    check("every row carries tag_id, empty until the owner files it",
          all(r["tag_id"] is None for r in rows.values()), rows)
    got = log.list(kind="live")["conversations"]
    check("the list can be filtered to Live sessions only",
          [c["id"] for c in got] == ["conv-live-00002"], got)
    check("an unknown kind filter is ignored, not an error",
          len(log.list(kind="nonsense")["conversations"]) == 2)
    conv = log.get("conv-live-00002")
    check("an opened Live chat says its kind, and may be continued",
          conv["kind"] == "live" and conv["continuable"] is True and conv["continue_why"] == "",
          conv)
    check("an opened chat says when it started and last changed",
          conv["started"] > 0 and conv["updated"] >= conv["started"], conv)


def t_the_route_filters_by_kind():
    if H.AESGCM is None:
        return skip("the cryptography package is not installed")
    log = new_log()
    H.use(log)
    try:
        turn(log, "conv-plain-0003", "hello there")
        turn(log, "conv-live-00004", "hello live", live=True, provenance="voice")
        code, out = H.handle_get("/api/history", "kind=live")
        check("GET /api/history?kind=live answers the Live sessions only",
              code == 200 and [c["id"] for c in out["conversations"]] == ["conv-live-00004"]
              and out["kind"] == "live", out)
        code, out = H.handle_get("/api/history", "")
        check("...and without it, every kind", code == 200 and len(out["conversations"]) == 2
              and out["kind"] is None, out)
    finally:
        H.use(None)


def t_migration():
    if H.AESGCM is None:
        return skip("the cryptography package is not installed")
    log = new_log()
    turn(log, "conv-old-00005", "an old chat")
    log.record_support("sup-old-000006", "Support: refund",
                       [{"provenance": "support_company", "text": "We can refund"}])
    # Make it look like a history kept before the columns existed.
    with closing(sqlite3.connect(log.db_path)) as c:
        c.execute("CREATE TABLE old AS SELECT id, title, started, updated, device"
                  " FROM conversations")
        c.execute("DROP TABLE conversations")
        c.execute("ALTER TABLE old RENAME TO conversations")
        c.commit()
        cols = {r[1] for r in c.execute("PRAGMA table_info(conversations)")}
    check("(set-up) the old file has no kind or project", "kind" not in cols
          and "project" not in cols, cols)
    again = H.ChatLog(log.db_path, log.settings_path, lambda: KEY, clock=Clock())
    rows = {c["id"]: c for c in again.list()["conversations"]}
    check("migrated in place: the old chat is kind chat",
          rows["conv-old-00005"]["kind"] == "chat", rows)
    check("...the support record is kind support",
          rows["sup-old-000006"]["kind"] == "support", rows)
    check("...and the titles still open (no text was rewritten)",
          rows["conv-old-00005"]["title"] == "an old chat", rows)
    with closing(sqlite3.connect(log.db_path)) as c:
        cols = {r[1] for r in c.execute("PRAGMA table_info(conversations)")}
    check("the file now has kind, project and tag_id (chat tags, 2026-09-30)",
          {"kind", "project", "tag_id"} <= cols, cols)


def t_chatbot_and_compare_records():
    if H.AESGCM is None:
        return skip("the cryptography package is not installed")
    log = new_log()
    got = log.record_chatbot("chat_0123456789ab", "Gemini: best tent",
                             [{"provenance": "chatbot_note", "text": "Your goal: best tent"},
                              {"provenance": "chatbot_jarvis", "text": "Jarvis to Gemini: hi"},
                              {"provenance": "chatbot_reply", "text": "Gemini: the X2"},
                              {"provenance": "chatbot_summary", "text": "Summary: X2"},
                              {"provenance": "made_up", "text": "odd"}])
    check("a chatbot conversation is kept", got.get("recorded") and got["rows"] == 5, got)
    conv = log.get("chat_0123456789ab")
    check("kind chatbot, read-only, and says why",
          conv["kind"] == "chatbot" and conv["continuable"] is False
          and "can't be continued" in conv["continue_why"], conv)
    check("every row is role chatbot - never user, so the learner never reads it",
          {t["role"] for t in conv["turns"]} == {"chatbot"}, conv["turns"])
    check("every row is outside text, and the whole record is tainted",
          all(t["read_outside"] for t in conv["turns"]) and conv["tainted"], conv)
    check("an unknown author is a note", conv["turns"][-1]["provenance"] == "chatbot_note")
    raw = log.db_path.read_bytes()
    check("encrypted: no word of it is in the file in plain text",
          b"the X2" not in raw and b"best tent" not in raw)
    got = log.record_chatbot("cmp_0123456789ab", "Compared 2 AIs: tents",
                             [{"provenance": "chatbot_reply", "text": "Claude: the Y"}],
                             kind="compare")
    rows = {c["id"]: c for c in log.list()["conversations"]}
    check("a comparison is kind compare", rows["cmp_0123456789ab"]["kind"] == "compare", rows)
    check("a comparison cannot be continued either",
          log.get("cmp_0123456789ab")["continuable"] is False)
    got = log.record_chatbot("chat_0123456789ab", "Gemini", [{"provenance": "chatbot_reply",
                                                              "text": "again"}])
    check("the same id again replaces it (one record)",
          len(log.get("chat_0123456789ab")["turns"]) == 1)
    check("nothing about it is in the live-turn registry (never learned from)",
          log.live_turn("chat_0123456789ab", "again") is None)


def t_crisis_title():
    if H.AESGCM is None:
        return skip("the cryptography package is not installed")
    log = new_log()
    turn(log, "conv-crisis-007", "I feel like I can't go on", crisis=True)
    rows = {c["id"]: c for c in log.list()["conversations"]}
    check("a chat that starts with a crisis turn is titled \"A difficult moment\"",
          rows["conv-crisis-007"]["title"] == H.CRISIS_TITLE, rows)
    turn(log, "conv-later-0008", "help me plan dinner")
    turn(log, "conv-later-0008", "honestly everything is too much", crisis=True,
         extra=[{"role": "user", "content": "help me plan dinner", "provenance": "typed"},
                {"role": "assistant", "content": "Sure."}])
    rows = {c["id"]: c for c in log.list()["conversations"]}
    check("a crisis turn later in a chat re-titles it too, never the owner's words",
          rows["conv-later-0008"]["title"] == H.CRISIS_TITLE, rows)
    check("the chat itself is kept (the owner's decision: kept, titled)",
          len(log.get("conv-later-0008")["turns"]) == 4)
    try:
        import jarvis_wellbeing  # noqa: F401
        have_wb = True
    except Exception:
        have_wb = False
    if have_wb:
        turn(log, "conv-phrase-009", "I want to kill myself")
        rows = {c["id"]: c for c in log.list()["conversations"]}
        check("the crisis help line's own phrase check titles it too, without the loop's flag",
              rows["conv-phrase-009"]["title"] == H.CRISIS_TITLE, rows)


def t_a_crisis_chat_is_not_continued():
    """The second chat audit (2026-09-28): a chat titled "A difficult moment"
    is kept but not carried on - its words would go back to the model."""
    if H.AESGCM is None:
        return skip("the cryptography package is not installed")
    log = new_log()
    turn(log, "conv-crisis-101", "I feel like I can't go on", crisis=True)
    conv = log.get("conv-crisis-101")
    check("the chat is kept and titled neutrally", conv["title"] == H.CRISIS_TITLE
          and len(conv["turns"]) == 2, conv["title"])
    check("but it cannot be continued, with the PC's own plain reason",
          conv["continuable"] is False and conv["continue_why"] == H.CRISIS_CONTINUE_WHY
          and "start a new chat" in conv["continue_why"], conv)
    turn(log, "conv-plain-0102", "help me plan dinner")
    check("an ordinary chat still can", log.get("conv-plain-0102")["continuable"] is True)


def t_title_prefers_the_owners_words():
    if H.AESGCM is None:
        return skip("the cryptography package is not installed")
    log = new_log()
    turn(log, "conv-share-0010", "what does this say?", device="phone",
         extra=[{"role": "user", "content": "Dear customer, your parcel...",
                 "provenance": "shared"}])
    rows = {c["id"]: c for c in log.list()["conversations"]}
    check("a chat that began with shared text is titled with what the owner asked",
          rows["conv-share-0010"]["title"] == "what does this say?", rows)


def t_support_is_not_swept():
    if H.AESGCM is None:
        return skip("the cryptography package is not installed")
    clock = Clock()
    log = new_log(clock)
    turn(log, "conv-old-00011", "an old chat")
    log.record_support("sup-old-000012", "Support: refund",
                       [{"provenance": "support_company", "text": "We can refund",
                         "at": clock.t}])
    clock.t += 40 * 86400
    deleted = log.set_keep_days(30)
    ids = [c["id"] for c in log.list()["conversations"]]
    check("\"Delete conversations older than\" deletes the old chat",
          deleted == 1 and "conv-old-00011" not in ids, (deleted, ids))
    check("...but never a support chat's record", "sup-old-000012" in ids, ids)
    check("how many were kept back is known", log.support_past_keep() == 1)
    H.use(log)
    try:
        code, out = H.request_settings({"keep_days": 30}, log=log)
        check("the reply says a support record was kept, and how to remove it",
              code == 200 and out["support_kept"] == 1
              and "customer-support chat record was older than that and kept" in out["message"],
              out)
    finally:
        H.use(None)
    check("the same note is ready for both apps' confirm",
          "Customer-support chat records are not deleted by this" in H.SUPPORT_KEPT_NOTE)


def t_take_out_keeps_the_kind():
    if H.AESGCM is None:
        return skip("the cryptography package is not installed")
    log = new_log()
    turn(log, "conv-live-00013", "a live chat", live=True, provenance="voice")
    held = log.take_out(["conv-live-00013"])
    check("taken out", not log.list()["conversations"])
    log.put_back(held)
    rows = {c["id"]: c for c in log.list()["conversations"]}
    check("Undo puts it back as a Live session still",
          rows["conv-live-00013"]["kind"] == "live", rows)
    items = log.overlapping(0, 4e9)["items"]
    check("\"Forget a time frame\"'s list carries each chat's kind",
          items and items[0]["kind"] == "live", items)


def t_the_live_mark_is_the_first_message():
    if H.AESGCM is None:
        return skip("the cryptography package is not installed")
    log = new_log()
    turn(log, "conv-mixed-0014", "typed first")
    turn(log, "conv-mixed-0014", "then live", live=True, provenance="voice",
         extra=[{"role": "user", "content": "typed first", "provenance": "typed"},
                {"role": "assistant", "content": "Sure."}])
    rows = {c["id"]: c for c in log.list()["conversations"]}
    check("a kind is decided when the conversation starts, and kept",
          rows["conv-mixed-0014"]["kind"] == "chat", rows)


def t_search_rows_carry_the_kind():
    if H.AESGCM is None:
        return skip("the cryptography package is not installed")
    log = new_log()
    turn(log, "conv-live-00015", "pancakes recipe please", live=True, provenance="voice")
    got = log.search("pancakes")
    check("a search result carries its kind", got["conversations"]
          and got["conversations"][0]["kind"] == "live", got)


def t_chatbot_keeps_its_conversation():
    """jarvis_chatbot.keep_in_history and jarvis_chatbot_compare's: what they
    hand the history, with the writer replaced (the suites never touch the
    owner's real history - backend/_where.py)."""
    try:
        import jarvis_chatbot as CB
        import jarvis_chatbot_compare as CC
    except Exception as exc:
        return skip(f"the chatbot modules do not import ({type(exc).__name__})")
    kept = []
    d = CB.Deps(keep_history=lambda cid, title, rows, kind: kept.append(
        (cid, title, rows, kind)) or {"recorded": True})
    s = CB.Session(id="chat_aaaaaaaaaaaa", chatbot="gemini", goal="find the best tent\nmore",
                   limits=CB.Limits(6, 10), tier=None)
    got = CB.keep_in_history(s, d)
    check("nothing said: nothing kept", got.get("recorded") is False and not kept, got)
    s.transcript = [{"who": "jarvis", "n": 1, "text": "Which tent?", "at": 10.0},
                    {"who": "chatbot", "n": 1, "text": "The X2.", "at": 12.0,
                     "outside_text": True}]
    s.ended_words = "Finished."
    s.summary = {"answer": "It suggested the X2."}
    CB.keep_in_history(s, d)
    cid, title, rows, kind = kept[-1]
    check("kept under the conversation's own id, kind chatbot",
          cid == "chat_aaaaaaaaaaaa" and kind == "chatbot", kept[-1])
    check("titled with the chatbot's name and the goal's first line",
          title.endswith(": find the best tent"), title)
    provs = [r["provenance"] for r in rows]
    check("goal, message, reply, ending, summary - in that order",
          provs == ["chatbot_note", "chatbot_jarvis", "chatbot_reply", "chatbot_note",
                    "chatbot_summary"], provs)
    check("the default writer keeps nothing while a suite runs",
          CB._default_keep_history("chat_bbbbbbbbbbbb", "t", [], "chatbot").get("recorded")
          is False)
    m1 = CB.Session(id="chat_cccccccccccc", chatbot="gemini", goal="q", limits=CB.Limits(6, 10),
                    tier=None, compare="cmp_dddddddddddd")
    m1.transcript = [{"who": "chatbot", "n": 1, "text": "A", "at": 1.0}]
    m2 = CB.Session(id="chat_eeeeeeeeeeee", chatbot="gemini", goal="q", limits=CB.Limits(6, 10),
                    tier=None, compare="cmp_dddddddddddd")
    c = CC.Compare(id="cmp_dddddddddddd", goal="which tent", chatbots=("gemini", "gemini"),
                   limits=CB.Limits(6, 10), tier=None, members=[m1, m2])
    c.summary = {"answer": "They agree."}
    CC.keep_in_history(c, d)
    cid, title, rows, kind = kept[-1]
    check("a comparison is kept once, as kind compare, under its own id",
          cid == "cmp_dddddddddddd" and kind == "compare" and title.startswith("Compared 2 AIs"),
          kept[-1])
    check("...with each chatbot's part and the one summary",
          [r["provenance"] for r in rows][-1] == "chatbot_summary"
          and any("not asked" in r["text"] for r in rows), rows)


def t_both_apps_copy_is_current():
    """tools/gen_history_cases.py writes the words and worked examples both
    apps' tests read; a stale copy would let the two drift apart."""
    import subprocess
    gen = HERE.parent / "tools" / "gen_history_cases.py"
    r = subprocess.run([sys.executable, str(gen), "--check"], capture_output=True, text=True)
    check("both apps' copy of the History words and examples is current "
          "(python3 tools/gen_history_cases.py)", r.returncode == 0, r.stdout + r.stderr)


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
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
