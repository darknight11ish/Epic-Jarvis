"""test_chat_log.py - chat history on the PC: encrypted, fail closed, and the
patch that feeds it.

    python3 backend/test_chat_log.py

Runs anywhere: the database is in a temporary folder, the key comes from a
stand-in provider (or a stand-in Credential Manager), the approval gate is a
stand-in, and chat-history.patch is checked on the whole patch stack's
stand-in for jarvis_hud.py and jarvis_gate.py (backend/_stack.py). Needs the
`cryptography` package for everything except the fail-closed checks.
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_chat_log.py", "jarvis_agent.py")
import jarvis_chat_log as H  # noqa: E402

PASSED, FAILED = [], []
KEY = bytes(range(32))
SENTENCE = "my sister's birthday is on the ninth of March"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class Clock:
    def __init__(self, t=1_790_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class World:
    """One temporary history: its folder, clock and log."""

    def __init__(self, key=KEY, crypto=True, provider=None):
        H._reset_for_tests()
        self.dir = Path(tempfile.mkdtemp(prefix="jarvis-history-"))
        self.clock = Clock()
        self.log = H.ChatLog(self.dir / "chat-history.db", self.dir / "chat-history.json",
                             provider or (lambda: key), clock=self.clock, crypto=crypto)
        H.use(self.log)

    def raw(self) -> bytes:
        """Every byte of every file this history wrote."""
        return b"".join(p.read_bytes() for p in sorted(self.dir.iterdir()) if p.is_file())

    def done(self):
        H.use(None)
        shutil.rmtree(self.dir, ignore_errors=True)


def req(text, *, cid="conv-000001", device="phone", prov="typed", history=(), **extra):
    msg = {"role": "user", "content": text}
    if prov is not None:
        msg["provenance"] = prov
    body = {"messages": list(history) + [msg], "conversation_id": cid, "device": device}
    body.update(extra)
    return body


def local(answer="Noted.", tools=(), finish="stop", gone=False):
    return {"finish_reason": finish, "client_gone": gone, "rounds": 1 + bool(tools),
            "answer": answer, "tools_ran": list(tools)}


# ---------------------------------------------------------------- the module

def t_round_trip_and_no_plain_text_on_disk():
    w = World()
    try:
        out = w.log.record_turn(req(SENTENCE), lane="qwen3:8b", turn=local("I will remember that."))
        check("a local turn is recorded, answer kept", out.get("recorded") and out["answer_kept"], out)
        conv = w.log.get("conv-000001")
        check("it reads back: the words, then the answer",
              [(t["role"], t["text"]) for t in conv["turns"]]
              == [("user", SENTENCE), ("assistant", "I will remember that.")], conv)
        check("the title is the first user line", conv["title"] == SENTENCE, conv["title"])
        raw = w.raw()
        check("the database holds no plain text: not the sentence",
              SENTENCE.encode() not in raw and b"ninth of March" not in raw)
        check("... not the answer", b"remember that" not in raw)
        check("... and the key is not in the file either", KEY not in raw
              and base64.b64encode(KEY) not in raw)
        st = w.log.status()
        check("status: on, recording, encrypted, nothing waiting",
              st == {"enabled": True, "recording": True, "why_not": "", "waiting": False,
                     "keep_days": 0, "encrypted": True}, st)
    finally:
        w.done()


def t_rows_cannot_be_moved_between_conversations():
    w = World()
    try:
        w.log.record_turn(req("first secret", cid="conv-aaaaaa"), turn=local("a"))
        w.log.record_turn(req("second secret", cid="conv-bbbbbb"), turn=local("b"))
        import sqlite3
        c = sqlite3.connect(str(w.log.db_path))
        blob = c.execute("SELECT text FROM turns WHERE conversation_id='conv-aaaaaa' AND idx=0"
                         ).fetchone()[0]
        c.execute("UPDATE turns SET text=? WHERE conversation_id='conv-bbbbbb' AND idx=0", (blob,))
        c.commit()
        c.close()
        got = w.log.get("conv-bbbbbb")["turns"][0]["text"]
        check("a row copied into another conversation does not open there",
              got != "first secret" and "could not be opened" in got, got)
    finally:
        w.done()


def t_fail_closed_without_a_key():
    def no_key():
        raise H.KeyUnavailable("there is no Windows Credential Manager on this system")
    w = World(provider=no_key)
    try:
        out = w.log.record_turn(req(SENTENCE), turn=local("x"))
        check("no key: nothing recorded", out["recorded"] is False, out)
        check("no key: not a byte of the sentence anywhere", SENTENCE.encode() not in w.raw())
        st = w.log.status()
        check("no key: status says recording false, and why, in words",
              st["recording"] is False and st["enabled"] is True
              and "Credential Manager" in st["why_not"], st)
        code, body = H.handle_get("/api/history", "")
        check("no key: the list says why rather than failing",
              code == 200 and body["conversations"] == [] and body["why_not"], body)
    finally:
        w.done()


def t_fail_closed_without_cryptography():
    w = World(crypto=False)
    try:
        out = w.log.record_turn(req(SENTENCE), turn=local("x"))
        st = w.log.status()
        check("no cryptography package: nothing recorded", out["recorded"] is False, out)
        check("... and no plain-text fallback on disk", SENTENCE.encode() not in w.raw())
        check("... status names the package and how to install it",
              st["recording"] is False and "cryptography" in st["why_not"]
              and "requirements.txt" in st["why_not"], st)
    finally:
        w.done()


def t_a_replaced_key_is_refused_not_mixed():
    w = World()
    try:
        w.log.record_turn(req("kept under the first key"), turn=local("ok"))
        other = H.ChatLog(w.log.db_path, w.log.settings_path, lambda: bytes(32), clock=w.clock)
        out = other.record_turn(req("under a second key"), turn=local("ok"))
        st = other.status()
        check("a key that does not open the kept history: nothing new recorded",
              out["recorded"] is False, out)
        check("... and status says so, and how to start again",
              "does not open" in st["why_not"] and "delete" in st["why_not"], st)
    finally:
        w.done()


def t_credential_manager_key():
    class Store:
        def __init__(self, value=None, echo=True):
            self.value, self.echo, self.writes = value, echo, 0

        def read(self):
            return self.value

        def write(self, text):
            self.writes += 1
            if self.echo:
                self.value = text

    s = Store()
    key = H.CredentialKey(store_factory=lambda: s)()
    check("first use: a 32-byte key is made, saved once and read back",
          len(key) == 32 and s.writes == 1 and base64.b64decode(s.value) == key)
    check("next use: the same key, nothing written", H.CredentialKey(store_factory=lambda: s)()
          == key and s.writes == 1)
    for name, store in (("a key that does not read back", Store(echo=False)),
                        ("a stored key of the wrong length",
                         Store(base64.b64encode(b"short").decode()))):
        try:
            H.CredentialKey(store_factory=lambda st=store: st)()
            check(f"{name} is refused", False)
        except H.KeyUnavailable as exc:
            check(f"{name} is refused, in words", "key" in str(exc), str(exc))
    check("the key's name in Credential Manager",
          H.KEY_TARGET == "Jarvis Backend/chat history key"
          and H.CredentialKey().target == H.KEY_TARGET)
    try:
        import jarvis_token_store  # noqa: F401
        real = H.CredentialKey()
        try:
            real()
            check("off Windows the real store is not there", sys.platform == "win32")
        except H.KeyUnavailable as exc:
            check("off Windows: KeyUnavailable in words, not a crash",
                  "Credential Manager" in str(exc), str(exc))
    except ImportError:
        check("SKIP - jarvis_token_store not importable", True)


def t_only_the_newest_user_turn():
    w = World()
    try:
        history = [{"role": "user", "content": "old question one", "provenance": "typed"},
                   {"role": "assistant", "content": "old answer one"},
                   {"role": "system", "content": "context the app added"},
                   {"role": "user", "content": "old question two", "provenance": "voice"},
                   {"role": "assistant", "content": "old answer two"}]
        w.log.record_turn(req("the live question", history=history), turn=local("live answer"))
        turns = w.log.get("conv-000001")["turns"]
        check("only the newest user message and its answer are recorded",
              [t["text"] for t in turns] == ["the live question", "live answer"], turns)
        w.log.record_turn(req("next one", history=history + [
            {"role": "user", "content": "the live question", "provenance": "typed"},
            {"role": "assistant", "content": "live answer"}]), turn=local("next answer"))
        turns = w.log.get("conv-000001")["turns"]
        check("re-sent history is never recorded twice; turn numbers run on",
              [t["text"] for t in turns]
              == ["the live question", "live answer", "next one", "next answer"], turns)
    finally:
        w.done()


def t_shared_text_goes_with_its_typed_message():
    w = World()
    try:
        shared = {"role": "user", "content": "a long article from the browser",
                  "provenance": "shared"}
        w.log.record_turn(req("summarise this", history=[shared]), turn=local("Summary."))
        turns = w.log.get("conv-000001")["turns"]
        check("phone Share: the shared message and the typed one are both kept",
              [(t["text"], t.get("provenance")) for t in turns]
              == [("a long article from the browser", "shared"), ("summarise this", "typed"),
                  ("Summary.", None)], turns)
        w.log.record_turn(req("and in one line?", history=[
            shared, {"role": "user", "content": "summarise this", "provenance": "typed"},
            {"role": "assistant", "content": "Summary."}]), turn=local("One line."))
        texts = [t["text"] for t in w.log.get("conv-000001")["turns"]]
        check("next turn: the shared text is not picked up again",
              texts.count("a long article from the browser") == 1, texts)
    finally:
        w.done()


def t_provenance_is_checked_and_unknown_by_default():
    w = World()
    try:
        cases = [("typed", "typed"), ("pasted", "pasted"), ("clipboard", "clipboard"),
                 ("shared", "shared"), ("made-up", "unknown"), (None, "unknown"),
                 ("voice_unverified", "unknown"), (42, "unknown")]
        for i, (sent, want) in enumerate(cases):
            w.log.record_turn(req(f"words {i}", cid=f"conv-prov{i:02d}", prov=sent), turn=None)
            got = w.log.get(f"conv-prov{i:02d}")["turns"][0]["provenance"]
            check(f"provenance {sent!r} is recorded as {want!r}", got == want, got)
        pic = {"role": "user", "provenance": "typed", "content": [
            {"type": "text", "text": "what is this plant?"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJDREVGR0g="}}]}
        w.log.record_turn({"messages": [pic], "conversation_id": "conv-picture",
                           "device": "phone"}, turn=local("A fern."))
        t = w.log.get("conv-picture")["turns"][0]
        check("a picture turn: the words only, as picture_caption",
              t["text"] == "what is this plant?" and t["provenance"] == "picture_caption", t)
        check("... the picture itself is not stored", b"QUJDREVGR0g" not in w.raw())
    finally:
        w.done()


def t_voice_is_voice_only_when_the_pc_heard_it():
    w = World()
    try:
        w.log.note_transcript("turn the lights off", strictness="strict", model="3dspeaker",
                              mode="owner", source="wake_word")
        w.log.record_turn(req("turn the lights off", cid="conv-voice01", prov="voice"), turn=None)
        w.log.record_turn(req("something else", cid="conv-voice02", prov="voice"), turn=None)
        check("a transcript the PC's speech route made: recorded as voice",
              w.log.get("conv-voice01")["turns"][0]["provenance"] == "voice")
        check("claimed voice the PC never heard: voice_unverified",
              w.log.get("conv-voice02")["turns"][0]["provenance"] == "voice_unverified")
        import sqlite3
        c = sqlite3.connect(str(w.log.db_path))
        facts = c.execute("SELECT voice_check FROM turns WHERE conversation_id='conv-voice01'"
                          ).fetchone()[0]
        c.close()
        check("the voice check's facts are kept with the turn, with how the clip started",
              json.loads(facts) == {"strictness": "strict", "model": "3dspeaker",
                                    "mode": "owner", "source": "wake_word"}, facts)
        live = w.log.live_turn("conv-voice01", "turn the lights off")
        check("...and the live-turn registry has the source too (for automatic learning)",
              live and live["voice_check"]["source"] == "wake_word", live)
        # A speech route that did not say how the clip started: "" (which
        # automatic learning treats as hands-free).
        w.log.note_transcript("lights on please", strictness="very_strict", model="m",
                              mode="owner")
        w.log.record_turn(req("lights on please", cid="conv-voice04", prov="voice"), turn=None)
        live = w.log.live_turn("conv-voice04", "lights on please")
        check("no source said: kept as \"\"", live and live["voice_check"]["source"] == "", live)
        check("only a hash of the transcript is held in memory",
              all(len(h) == 64 for h in w.log._heard) and "turn the lights off"
              not in repr(w.log._heard))
        w.clock.t += H.VOICE_WINDOW + 1
        w.log.record_turn(req("turn the lights off", cid="conv-voice03", prov="voice"), turn=None)
        check("after ten minutes the same words are voice_unverified",
              w.log.get("conv-voice03")["turns"][0]["provenance"] == "voice_unverified")
        code, body = H.handle_get("/api/history", "")
        marks = {c["id"]: c["has_voice"] for c in body["conversations"]}
        check("has_voice marks the conversations with voice", all(marks.values()), marks)
    finally:
        w.done()


def t_answers_kept_only_from_the_local_loop():
    w = World()
    try:
        w.log.record_turn(req("to the cloud", cid="conv-cloud1"), lane="cloud-lane", turn=None)
        w.log.record_turn(req("the app left", cid="conv-gone01"), turn=local("half", gone=True))
        w.log.record_turn(req("ollama failed", cid="conv-fail01"), turn=local("", finish=None))
        for cid, what in (("conv-cloud1", "a cloud answer"), ("conv-gone01", "an answer nobody got"),
                          ("conv-fail01", "a failed answer")):
            turns = w.log.get(cid)["turns"]
            check(f"{what}: the user turn only, answer_kept false",
                  len(turns) == 1 and turns[0]["answer_kept"] is False, turns)
    finally:
        w.done()


def t_taint_from_a_turn_on():
    w = World()
    try:
        w.log.record_turn(req("hello"), turn=local("hi"))
        check("no tool yet: not tainted", w.log.get("conv-000001")["tainted"] is False
              and w.log.tainted_from("conv-000001") is None)
        w.log.record_turn(req("check my email"), turn=local("You have 2.", tools=["email_check"]))
        w.log.record_turn(req("thanks"), turn=local("You're welcome."))
        conv = w.log.get("conv-000001")
        check("a turn where a tool ran is marked read_outside",
              [t.get("read_outside") for t in conv["turns"] if t["role"] == "user"]
              == [False, True, False], conv["turns"])
        check("the conversation is tainted from that turn on",
              conv["tainted"] is True and w.log.tainted_from("conv-000001") == 2,
              w.log.tainted_from("conv-000001"))
        code, body = H.handle_get("/api/history", "")
        check("the list says tainted", body["conversations"][0]["tainted"] is True)
    finally:
        w.done()


def t_off_records_nothing():
    w = World()
    try:
        w.log.set_enabled(False)
        out = w.log.record_turn(req(SENTENCE), turn=local("x"))
        check("history off: nothing recorded", out["recorded"] is False
              and SENTENCE.encode() not in w.raw(), out)
        st = w.log.status()
        check("history off: status says so", st["enabled"] is False and st["recording"] is False
              and st["why_not"] == "Chat history is off.", st)
        (w.dir / "chat-history.json").write_text("{nope", encoding="utf-8")
        st = w.log.status()
        check("a damaged settings file: off, and why",
              st["enabled"] is False and "damaged" in st["why_not"], st)
    finally:
        w.done()


def t_paging_skips_nothing_in_the_same_second():
    """Three conversations updated within one second, one per page: every
    one of them is reached by "Load older" (the audit's case: page 2 came
    back empty and two conversations were never shown)."""
    w = World()
    try:
        for i, frac in enumerate((0.2, 0.5, 0.9)):
            w.clock.t = 1000 + frac
            w.log.record_turn(req(f"q {i}", cid=f"conv-same{i:02d}"), turn=local("a"))
        seen, before = [], None
        for _ in range(6):
            q = "limit=1" + (f"&before={before}" if before is not None else "")
            code, body = H.handle_get("/api/history", q)
            rows = body["conversations"]
            if not rows:
                break
            seen += [r["id"] for r in rows]
            before = body["conversations"][-1]["updated"]
        check("all three are reached, none skipped, none twice", sorted(seen) ==
              ["conv-same00", "conv-same01", "conv-same02"], seen)
        code, body = H.handle_get("/api/history", "limit=1")
        check("a page never splits a second: all three come on the first page",
              len(body["conversations"]) == 3, body)
    finally:
        w.done()


def t_list_paging_and_conversation_routes():
    w = World()
    try:
        for i in range(5):
            w.clock.t += 60
            w.log.record_turn(req(f"question {i}\nsecond line", cid=f"conv-page{i:02d}",
                                  device=("desktop", "hud", "phone", "watch", "phone")[i]),
                              turn=local(f"answer {i}"))
        code, body = H.handle_get("/api/history", "limit=2")
        ids = [c["id"] for c in body["conversations"]]
        check("newest first, limit honoured", code == 200 and ids == ["conv-page04", "conv-page03"],
              ids)
        first = body["conversations"][0]
        check("a list row: title (first line), when, turns, device",
              first["title"] == "question 4" and first["turns"] == 2
              and first["device"] == "phone" and first["started"] <= first["updated"], first)
        code, body = H.handle_get("/api/history", f"limit=2&before={body['conversations'][-1]['updated']}")
        check("before= pages on to older ones",
              [c["id"] for c in body["conversations"]] == ["conv-page02", "conv-page01"], body)
        code, body = H.handle_get("/api/history", "limit=all&before=soon")
        check("a bad limit or before is ignored, not an error",
              code == 200 and len(body["conversations"]) == 5, code)
        code, body = H.handle_get("/api/history", "limit=100000")
        check("limit is capped", code == 200 and len(body["conversations"]) == 5)
        check("a device name that is not one of the three is 'unknown'",
              w.log.get("conv-page03") and H.handle_get("/api/history", "")[1]["conversations"][1]
              ["device"] == "unknown")
        code, body = H.handle_get("/api/history/conversation", "id=conv-page01")
        check("one conversation", code == 200 and body["turns"][1]["text"] == "answer 1", body)
        check("user turns carry provenance and read_outside; answers do not",
              set(body["turns"][0]) >= {"role", "text", "at", "provenance", "read_outside"}
              and set(body["turns"][1]) == {"role", "text", "at"}, body["turns"])
        code, _ = H.handle_get("/api/history/conversation", "id=conv-nothere")
        check("an unknown conversation: 404", code == 404)
        code, _ = H.handle_get("/api/history/conversation", "id=../../etc")
        check("a malformed id: 400", code == 400)
    finally:
        w.done()


def t_untagged_requests_are_grouped():
    w = World()
    try:
        w.log.record_turn({"messages": [{"role": "user", "content": "from an old app"}]},
                          turn=local("hi"))
        w.log.record_turn({"messages": [{"role": "user", "content": "again"}],
                           "conversation_id": "bad id!", "device": "phone"}, turn=local("hi"))
        rows = H.handle_get("/api/history", "")[1]["conversations"]
        check("no conversation id: kept per app and per day, not lost",
              sorted(r["id"][:15] for r in rows) == ["untagged-phone-", "untagged-unknow"], rows)
    finally:
        w.done()


def t_delete_one_and_no_delete_all():
    w = World()
    try:
        w.log.record_turn(req(SENTENCE, cid="conv-delete1"), turn=local("ok"))
        w.log.record_turn(req("keep me", cid="conv-keep001"), turn=local("ok"))
        import sqlite3
        c = sqlite3.connect(str(w.log.db_path))
        blob = bytes(c.execute("SELECT text FROM turns WHERE conversation_id='conv-delete1'"
                               " AND idx=0").fetchone()[0])
        c.close()
        code, out = H.handle_post("/api/history/delete", {"id": "conv-delete1"})
        check("delete one: 200 ok", code == 200 and out == {"ok": True}, out)
        check("it is gone; the other stays", w.log.get("conv-delete1") is None
              and w.log.get("conv-keep001") is not None)
        check("its bytes are not left in the file's free pages", blob not in w.raw())
        code, _ = H.handle_post("/api/history/delete", {"id": "conv-delete1"})
        check("deleting it again: 404", code == 404)
        for bad in ({"ids": ["conv-keep001"]}, {"id": ["conv-keep001"]}, {"all": True}, {},
                    {"id": "conv-keep001", "also": "x"}):
            code, _ = H.handle_post("/api/history/delete", bad)
            check(f"no bulk or odd delete ({bad!r}): 400", code == 400)
        check("nothing else was deleted", w.log.get("conv-keep001") is not None)
    finally:
        w.done()


def t_keep_days_sweep():
    w = World()
    try:
        w.log.record_turn(req("very old", cid="conv-old0001"), turn=local("x"))
        w.clock.t += 40 * 86400
        w.log.record_turn(req("recent", cid="conv-new0001"), turn=local("x"))
        code, out = H.request_settings({"keep_days": 30}, log=w.log)
        check("keep_days 30: 200, and the reply says one was deleted",
              code == 200 and out["deleted"] == 1 and out["keep_days"] == 30
              and "1 conversation was deleted" in out["message"], out)
        check("the old conversation is gone, the recent one stays",
              w.log.get("conv-old0001") is None and w.log.get("conv-new0001") is not None)
        w.clock.t += 31 * 86400
        w.log.list()
        check("once a day, the sweep runs again by itself", w.log.get("conv-new0001") is None)
        for bad in (7, "30", True, None, -1):
            code, _ = H.request_settings({"keep_days": bad}, log=w.log)
            check(f"keep_days {bad!r}: 400", code == 400)
        code, out = H.request_settings({"keep_days": 0}, log=w.log)
        check("keep_days 0 (keep until deleted)", code == 200 and out["keep_days"] == 0
              and "until you delete" in out["message"], out)
        fresh = H.ChatLog(w.log.db_path, w.log.settings_path, lambda: KEY, clock=w.clock)
        H.request_settings({"keep_days": 90}, log=w.log)
        fresh.record_turn(req("x", cid="conv-start01"), turn=None)
        w.clock.t += 100 * 86400
        again = H.ChatLog(w.log.db_path, w.log.settings_path, lambda: KEY, clock=w.clock)
        again.list()
        check("on start (first use), expired conversations are deleted",
              again.get("conv-start01") is None)
    finally:
        w.done()


# ------------------------------------------------------ the switch and card

class V:
    def __init__(self, outcome, tier="ask"):
        self.outcome, self.tier = outcome, tier
        self.allowed = outcome == "approved"
        self.reason = outcome


class Card:
    def __init__(self, world, verdict=None, tier="ask"):
        self.w, self.verdict, self.tier = world, verdict or V("approved"), tier
        self.cards, self.later = [], []

    def gate(self, action, detail, prompt):
        self.cards.append((action, detail, prompt))
        return self.verdict

    def req(self, body):
        return H.request_settings(body, gate=self.gate, tier_of=lambda a: self.tier,
                                  spawn=self.later.append, log=self.w.log)

    def run(self):
        for fn in list(self.later):
            fn()
        self.later.clear()


def t_off_is_instant_on_asks():
    w = World()
    try:
        c = Card(w)
        code, out = c.req({"enabled": False})
        check("OFF: 200 at once, no card, the owner's words",
              code == 200 and not c.later and out["enabled"] is False
              and out["message"] == H.OFF_TEXT, out)
        code, out = c.req({"enabled": True})
        check("ON: 202 waiting, nothing changed yet",
              code == 202 and out["waiting"] is True and out["enabled"] is False
              and w.log.settings()["enabled"] is False, out)
        check("status shows the waiting card", w.log.status()["waiting"] is True)
        c.run()
        action, detail, prompt = c.cards[0]
        check("the card: history_enable, stays on this PC, the agreed words",
              action == "history_enable" and detail["leaves_this_pc"] is False
              and "Turn chat history back on?" in prompt and "encrypted" in prompt
              and "Nothing leaves this PC." in prompt, c.cards)
        check("approved: history is on", w.log.settings()["enabled"] is True
              and H.state()["last"]["outcome"] == "enabled")
        code, out = c.req({"enabled": True})
        check("ON while already on: 200, no second card", code == 200 and not c.later, out)
    finally:
        w.done()


def t_no_yes_changes_nothing():
    for outcome in ("denied", "timed_out", "refused"):
        w = World()
        try:
            w.log.set_enabled(False)
            c = Card(w, V(outcome))
            c.req({"enabled": True})
            c.run()
            check(f"{outcome}: history stays off", w.log.settings()["enabled"] is False
                  and H.state()["last"]["outcome"] == outcome, H.state())
        finally:
            w.done()
    w = World()
    try:
        w.log.set_enabled(False)
        c = Card(w, V("approved", tier="auto"))
        c.req({"enabled": True})
        c.run()
        check("a gate that answered at tier auto is not a person saying yes",
              w.log.settings()["enabled"] is False and H.state()["last"]["outcome"] == "refused")
    finally:
        w.done()


def t_the_toml_cannot_make_it_automatic():
    for tier in ("auto", "notify", "never", "unreadable (KeyError)"):
        w = World()
        try:
            w.log.set_enabled(False)
            c = Card(w, tier=tier)
            code, out = c.req({"enabled": True})
            check(f"tier {tier!r}: 503, no card, still off",
                  code == 503 and not c.later and w.log.settings()["enabled"] is False
                  and "must be 'ask'" in out["error"], out)
        finally:
            w.done()
    toml = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check('the shipped settings file has history_enable = "ask"',
          '\nhistory_enable            = "ask"\n' in toml)


def t_off_while_waiting_withdraws_it():
    w = World()
    try:
        w.log.set_enabled(False)
        c = Card(w)
        c.req({"enabled": True})
        code, out = c.req({"enabled": False})
        c.run()
        check("turned off while the card waited: the approval does not turn it on",
              code == 200 and w.log.settings()["enabled"] is False
              and H.state()["last"]["outcome"] == "withdrawn", H.state())
    finally:
        w.done()


def t_off_pressed_while_an_approved_card_writes_wins():
    """Red team R5 (2026-09-24): OFF landing between the approved card's
    "was it withdrawn?" check and its set_enabled(True) was answered "off" -
    and then the card turned chat history back on."""
    import threading as _th
    w = World()
    try:
        w.log.set_enabled(False)
        entered, release = _th.Event(), _th.Event()
        real = w.log.set_enabled

        def slow(on):
            if on:
                entered.set()
                release.wait(2)
            return real(on)

        w.log.set_enabled = slow
        c = Card(w)
        c.req({"enabled": True})
        card = _th.Thread(target=c.run)
        card.start()
        entered.wait(2)
        off = []
        t = _th.Thread(target=lambda: off.append(c.req({"enabled": False})))
        t.start()
        t.join(0.3)
        early = bool(off)
        release.set()
        card.join(2)
        t.join(2)
        check("OFF waits for the card's write, then chat history is OFF",
              off and off[0][0] == 200 and w.log.settings()["enabled"] is False and not early,
              (off, w.log.settings(), early))
    finally:
        w.done()


def t_audit_fixes_2026_09_24():
    """The chat history audit's findings, each reproduced before the fix."""
    # 1. Two requests on first use: one key, the one Credential Manager kept.
    import threading as _th
    import time as _time

    class SlowStore:
        def __init__(self):
            self.value, self.lock = None, _th.Lock()

        def read(self):
            _time.sleep(0.05)
            return self.value

        def write(self, text):
            self.value = text

    store = SlowStore()
    d = Path(tempfile.mkdtemp(prefix="jarvis-history-race-"))
    try:
        log = H.ChatLog(d / "h.db", d / "h.json", H.CredentialKey(store_factory=lambda: store))
        errs = []

        def use():
            try:
                log._cipher()
            except Exception as exc:
                errs.append(exc)
        ts = [_th.Thread(target=use) for _ in range(2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        again = H.ChatLog(d / "h.db", d / "h.json", H.CredentialKey(store_factory=lambda: store))
        check("two requests on first use: no error, and after a restart the history opens",
              not errs and again._recording()[0] is not None, (errs, again._recording()[1]))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    # 2. ON, OFF, ON: a fresh card, and OFF shows nothing waiting.
    w = World()
    try:
        w.log.set_enabled(False)
        c = Card(w)
        c.req({"enabled": True})
        c.req({"enabled": False})
        check("after OFF nothing is shown as waiting", H.state()["waiting"] is False)
        code, out = c.req({"enabled": True})
        check("a second ON raises its own card", code == 202 and len(c.later) == 2
              and "already waiting" not in out["message"], out)
        c.later[1]()
        c.later[0]()
        check("the new card turns history on; the old one changes nothing shown",
              w.log.settings()["enabled"] is True and H.state()["last"]["outcome"] == "enabled",
              H.state())
    finally:
        w.done()
    # 3. Words sent with a picture keep a less-trusted tag.
    w = World()
    try:
        pic = [{"type": "text", "text": "what is this email"},
               {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}}]
        for i, prov in enumerate(("pasted", "clipboard", "shared", None, "typed", "voice")):
            body = req("x", cid=f"conv-pic{i:03d}", prov=prov)
            body["messages"][-1]["content"] = pic
            w.log.record_turn(body)
        got = [w.log.get(f"conv-pic{i:03d}")["turns"][0]["provenance"] for i in range(6)]
        check("pasted/clipboard/shared keep their tag, missing is unknown, typed/voice -> caption",
              got == ["pasted", "clipboard", "shared", "unknown", "picture_caption",
                      "picture_caption"], got)
    finally:
        w.done()
    # 4. One real transcript verifies ONE voice turn.
    w = World()
    try:
        w.log.note_transcript("turn the lights off", strictness="very_strict",
                              model="m", mode="owner")
        w.log.record_turn(req("turn the lights off", cid="conv-voice01", prov="voice"))
        w.log.record_turn(req("turn the lights off", cid="conv-voice02", prov="voice",
                              device="hud"))
        a = w.log.get("conv-voice01")["turns"][0]["provenance"]
        b = w.log.get("conv-voice02")["turns"][0]["provenance"]
        check("the first claim is voice, a second claim of the same words is not",
              (a, b) == ("voice", "voice_unverified"), (a, b))
    finally:
        w.done()
    # 5. An id with a trailing newline is not a conversation id.
    check("a trailing newline is refused", H._CID.fullmatch("abcdefgh\n") is None
          and H._CID.fullmatch("abcdefgh") is not None)


def t_one_card_at_a_time_and_bad_input():
    w = World()
    try:
        w.log.set_enabled(False)
        c = Card(w)
        c.req({"enabled": True})
        code, out = c.req({"enabled": True})
        check("a second ON while one waits: no second card",
              code == 202 and len(c.later) == 1 and "already waiting" in out["message"], out)
        for bad in ({"enabled": "yes"}, {"enabled": 1}, {"enabled": None}, {},
                    {"enabled": False, "keep_days": 30}, {"delete_all": True}, [], "on"):
            code, _ = c.req(bad)
            check(f"{bad!r}: 400", code == 400)
    finally:
        w.done()


# ------------------------------------------------- run_local_turn's new fields

def t_run_local_turn_says_what_it_answered_and_ran():
    import jarvis_agent as AG
    real_rec, real_pub = AG._record_chain, AG._publish_step
    real_calc = AG.TOOLS["calculator"].execute
    AG._record_chain = lambda steps: None
    AG._publish_step = lambda step: None
    AG.TOOLS["calculator"].execute = lambda args, state, **kw: {"ok": True, "value": 4}

    def allow(*_a, **_k):
        return types.SimpleNamespace(allowed=True, reason="approved", outcome="approved",
                                     tier="auto")

    def scripted(responses):
        it = iter(responses)
        return lambda url, payload: next(it)

    try:
        plain = AG.run_local_turn(
            [{"role": "user", "content": "hello"}], "m", ollama_url="http://127.0.0.1:1",
            stream_out=lambda b: None, gate_check=allow, context_length=4096,
            post=scripted([{"choices": [{"message": {"role": "assistant", "content": "hi there"},
                                         "finish_reason": "stop"}]}]))
        check("run_local_turn returns the answer it sent, and no tools",
              plain.get("answer") == "hi there" and plain.get("tools_ran") == [], plain)
        tool = AG.run_local_turn(
            [{"role": "user", "content": "what is 2+2"}], "m", ollama_url="http://127.0.0.1:1",
            stream_out=lambda b: None, gate_check=allow, context_length=4096,
            post=scripted([
                {"choices": [{"message": {"role": "assistant", "tool_calls": [
                    {"id": "1", "function": {"name": "calculator",
                                             "arguments": json.dumps({"expression": "2+2"})}}]}}]},
                {"choices": [{"message": {"role": "assistant", "content": "It's 4."},
                              "finish_reason": "stop"}]}]))
        check("... and names a tool that ran", tool.get("tools_ran") == ["calculator"]
              and tool.get("answer") == "It's 4.", tool)
    finally:
        AG._record_chain, AG._publish_step = real_rec, real_pub
        AG.TOOLS["calculator"].execute = real_calc


# ------------------------------------------------------------- the patch

def _stack_texts():
    import _stack
    hud, log = _stack.stand_in("jarvis_hud.py")
    gate, glog = _stack.stand_in("jarvis_gate.py")
    return _stack, hud, log, gate, glog


def t_the_patch():
    """chat-history.patch, applied as apply-patches.ps1 applies the whole
    stack."""
    _stack, hud, log, gate, glog = _stack_texts()
    names = [str(p).replace("\\", "/").split("/")[-1] for p in _stack.order()]
    # After voice-flow.patch too: this patch adds its read routes straight
    # after voice-flow's /api/voice/moment block.
    check("chat-history.patch comes after learning-asks and voice-flow in apply-patches.ps1's order",
          "chat-history.patch" in names
          and names.index("chat-history.patch") > names.index("learning-asks.patch")
          and names.index("chat-history.patch") > names.index("voice-flow.patch"), names[-3:])
    check("the whole stack builds", hud is not None and gate is not None,
          "\n".join((log or []) + (glog or []))[-500:])
    if hud is None or gate is None:
        return
    check("every chat-history hunk found its context in the stack (none made up)",
          not any("chat-history" in l for l in log + glog), [l for l in log + glog
                                                               if "chat-history" in l])

    # The helper: lifted and run.
    lines = hud.splitlines()
    fields = next(l for l in lines if l.startswith("_CHAT_CLIENT_FIELDS = "))
    ns: dict = {}
    exec(fields + "\n" + _stack.function_text(hud, "_chat_client_fields_off"), ns)
    off = ns["_chat_client_fields_off"]
    msgs = [{"role": "user", "content": "hi", "provenance": "voice", "origin": "owner"},
            {"role": "assistant", "content": "yo"}, "odd"]
    got = off(msgs)
    check("provenance comes off every message; origin and content stay",
          got == [{"role": "user", "content": "hi", "origin": "owner"},
                  {"role": "assistant", "content": "yo"}, "odd"], got)
    check("... on a copy: the request as it arrived is untouched",
          msgs[0]["provenance"] == "voice")

    # _open(): the lines between building the request and sending it, run.
    frag = _stack.fragment_with(hud, 'body = dict(payload); body["model"] = lane')
    a = next(i for i, l in enumerate(frag) if 'body = dict(payload); body["model"] = lane' in l)
    b = next(i for i, l in enumerate(frag) if "return urllib.request.urlopen(" in l)
    snippet = textwrap.dedent("\n".join(frag[a:b]))
    for lane, where in (("qwen3:8b", "local"), ("cloud-lane", "cloud")):
        env = dict(ns, lane=lane, local_model="qwen3:8b",
                   payload={"model": "x", "stream": True, "conversation_id": "conv-000001",
                            "device": "phone",
                            "messages": [{"role": "user", "content": "q1", "provenance": "typed"},
                                         {"role": "assistant", "content": "a1"},
                                         {"role": "user", "content": "q2",
                                          "provenance": "voice"}]})
        exec(snippet, env)
        sent = json.dumps(env["body"])
        check(f"_open, {where} lane: no provenance, conversation_id or device is sent",
              "provenance" not in sent and "conversation_id" not in sent
              and "device" not in sent, sent)
        check(f"_open, {where} lane: the payload shared by every hop is not changed",
              env["payload"]["messages"][2].get("provenance") == "voice")
    check("... and a cloud lane still gets the newest question only (cloud-one-turn)",
          env["body"]["messages"] == [{"role": "user", "content": "q2"}], env["body"])

    # Before the local answering loop.
    frag = "\n".join(_stack.fragment_with(hud, "lane = decision.lane") or [])
    check("messages are cleaned before the local loop, and the turn's clock starts",
          "        messages = _chat_client_fields_off(messages)\n"
          "        _history = {\"turn\": None, \"at\": time.time()}" in frag
          and frag.index("_chat_client_fields_off(messages)") < frag.index("_degrade_hops ="))
    frag = "\n".join(_stack.fragment_with(hud, "_turn = jarvis_agent.run_local_turn(") or [])
    check("the local loop's result is kept for the record",
          '_turn = _turn or {}\n' in frag and '_history["turn"] = _turn' in frag
          and frag.index("_turn = _turn or {}") < frag.index('_history["turn"] = _turn')
          < frag.index("except (BrokenPipeError"))

    # The `finally`: run, with stand-ins for everything it touches.
    frag = _stack.fragment_with(hud, "jarvis_chat_log.record_turn(")
    a = next(i for i, l in enumerate(frag) if l.strip() == '_activity("idle")')
    b = max(i for i, l in enumerate(frag) if l.strip() == "pass") + 1
    snippet = textwrap.dedent("\n".join(frag[a:b]))
    body = {"messages": [{"role": "user", "content": "hi", "provenance": "typed",
                          "origin": "owner"}], "conversation_id": "conv-000001",
            "device": "phone"}
    for broken in (False, True):
        offered, recorded = [], []
        stub = types.ModuleType("jarvis_chat_log")

        def rec(b, **kw):
            if broken:
                raise RuntimeError("disk full")
            recorded.append((b, kw))
        stub.record_turn = rec
        real = sys.modules.get("jarvis_chat_log")
        sys.modules["jarvis_chat_log"] = stub
        try:
            env = {"_activity": lambda *a: None, "MEMORY": True, "jarvis_side_memory": False,
                   "LEARNER": types.SimpleNamespace(
                       offer=lambda m, origin="unknown", **kw: offered.append((m, origin))),
                   "body": body, "route_header": {"lane": "qwen3:8b"}, "lane": "qwen3:8b",
                   "_history": {"turn": {"answer": "hello"}, "at": 5.0}}
            try:
                exec(snippet, env)
                raised = None
            except Exception as exc:
                raised = exc
        finally:
            if real is None:
                sys.modules.pop("jarvis_chat_log", None)
            else:
                sys.modules["jarvis_chat_log"] = real
        if broken:
            check("a history that fails is never the reason a turn fails", raised is None,
                  repr(raised))
            continue
        check("the learner still gets the ORIGINAL messages (origin and provenance on them)",
              offered == [(body["messages"], "owner")], offered)
        check("the record gets the request as it arrived, the lane, the turn and its start",
              recorded == [(body, {"lane": "qwen3:8b", "turn": {"answer": "hello"}, "at": 5.0})],
              recorded)
    # auto-learn.patch (later in the order) moves the learner AFTER the
    # record: record_turn also writes the live-turn registry that automatic
    # learning checks each turn against. Each is still in its own try.
    check("record_turn and the learner are each in their own try, the record first",
          "\n".join(frag).index("record_turn(") < "\n".join(frag).index("LEARNER.offer("))

    # The routes.
    get_i = hud.find('if path in ("/api/history", "/api/history/conversation"):')
    post_i = hud.find('if route in ("/api/history/delete", "/api/history/settings"):')
    check("GET /api/history and /api/history/conversation are routed", get_i >= 0)
    check("POST /api/history/delete and /api/history/settings are routed", post_i >= 0)
    for name, at, call in (("GET", get_i, "jarvis_chat_log.handle_get("),
                           ("POST", post_i, "jarvis_chat_log.handle_post(route, body)")):
        block = hud[hud.rfind("\n", 0, at) + 1:hud.find("\n\n", at)]
        try:
            compile("def f(self, path, route):\n" + block, "<patched block>", "exec")
            check(f"the {name} route block compiles", True)
        except SyntaxError as exc:
            check(f"the {name} route block compiles", False, str(exc))
        check(f"{name}: token and origin first, a missing module is a 503 in words",
              block.index("_origin_ok(self)") < block.index("_token_ok(self)")
              < block.index("import jarvis_chat_log")
              and "return self._send(503, _NO_CHAT_LOG)" in block and call in block, block)
    check("the 503 says what is missing and how to fix it",
          "chat history is not installed on this PC" in hud
          and "apply-patches.ps1 does this" in hud)

    # jarvis_gate.py: the approval notice's words.
    risk = next((l for l in gate.splitlines() if l.strip().startswith('"history_enable":')), "")
    check("jarvis_gate.py: history_enable is local and reversible in the notice table",
          risk.strip().startswith('"history_enable": ("yes", "local",'), risk)


def t_the_patch_applies_forwards_and_backwards():
    git = shutil.which("git")
    if not git:
        return check("SKIP - git is not installed", True)
    import _stack
    order = _stack.order()
    before = order[:order.index("chat-history.patch")]
    upto = order[:order.index("chat-history.patch") + 1]
    d = Path(tempfile.mkdtemp(prefix="jarvis-history-patch-"))
    try:
        for target in ("jarvis_hud.py", "jarvis_gate.py"):
            text, log = _stack.stand_in(target, before)
            check(f"{target}: the stack before chat-history.patch builds", text is not None)
            if text is None:
                return
            (d / target).write_text(text, encoding="utf-8", newline="\n")
        (d / "p.patch").write_bytes((HERE / "chat-history.patch").read_bytes()
                                    .replace(b"\r\n", b"\n"))
        for extra in (["--check"], [], ["--check", "--reverse"], ["--reverse"], []):
            r = subprocess.run([git, "apply", *extra, "p.patch"], cwd=d, capture_output=True,
                               text=True)
            check(f"git apply {' '.join(extra) or '(forwards)'} chat-history.patch",
                  r.returncode == 0, r.stderr.strip())
        full, _ = _stack.stand_in("jarvis_gate.py", upto)
        check("forwards gives the stack's own text",
              (d / "jarvis_gate.py").read_text(encoding="utf-8") == full)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def t_listed_where_it_must_be():
    import _where
    ps1 = (HERE.parent / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("shipped by apply-patches.ps1 and in _where.SHIPPED",
          "'jarvis_chat_log.py'" in ps1 and "jarvis_chat_log.py" in _where.SHIPPED)
    reqs = (HERE / "requirements.txt").read_text(encoding="utf-8")
    check("cryptography is in requirements.txt", "\ncryptography " in reqs)
    go = (HERE / "gate-outcome.patch").read_text(encoding="utf-8")
    check("a no on the history card proposes no memory (gate-outcome.patch)",
          '+    "history_enable",' in go)


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
