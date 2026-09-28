"""test_brain_reads.py - the Brain upgrades' two reads (2026-09-28).

    python3 backend/test_brain_reads.py

docs/JARVIS-API.md section 71. What is proved here, against real SQLite
files in a temporary folder and a stand-in key:

"Search what was said in old chats" (jarvis_chat_log.ChatLog.search):
  * it finds words said INSIDE a conversation, not only in its title - in
    the owner's words and Jarvis's - case ignored, every word required;
  * the snippet comes back in parts, each hit marked, and the parts put
    together are exactly a piece of the kept words;
  * NOTHING IS WRITTEN: every byte of every file in the history folder, and
    the list of files, is the same after a search as before it - so there is
    no index and no record of what was searched for; and the search words
    are never in any file, never audited;
  * a temporary chat was never kept, so it is never found;
  * with history OFF, what is still kept is still found (as the list still
    lists it), and searching keeps nothing new;
  * a key that does not open the history: nothing found, and why;
  * too short, too long, limit and `more`.

"History of this fact" (jarvis_memory.fact_history_view):
  * a reworded fact's versions come back oldest first, whichever version is
    asked about, `this` on the one asked about;
  * a correction kept as older news is part of the history;
  * AN ERASED VERSION NEVER COMES WITH ITS WORDS - not the words, not the
    "[erased]" marker - and the later wording stays;
  * the route: one whole-number id, 400 / 404 in words.

The routes module (jarvis_brain_reads.py) and brain-reads.patch:
  * install() answers only its two paths, after the token and origin
    checks, and passes everything else on;
  * the patch is last in apply-patches.ps1, applies to the whole stack's
    stand-in, and the module is shipped;
  * neither route is something the AI model can call.

No pytest, no network, no model. Needs the `cryptography` package for the
search half, as test_chat_log.py does.
"""
from __future__ import annotations

import json
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_chat_log.py", "rebuilt/jarvis_memory.py", "jarvis_brain_reads.py")

import jarvis_chat_log as H  # noqa: E402
try:
    import jarvis_memory as M
except ImportError:
    sys.path.append(str(REPO / "backend" / "rebuilt"))
    import jarvis_memory as M
import jarvis_brain_reads as B  # noqa: E402

PASSED, FAILED = [], []
KEY = bytes(range(32))
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-brain-reads-"))


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


# ------------------------------------------------------------- chat history

class Clock:
    def __init__(self, t=1_790_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class World:
    """One temporary history: its folder, clock and log."""

    def __init__(self, name, key=KEY, provider=None):
        H._reset_for_tests()
        self.dir = _TMP / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.clock = Clock()
        self.log = H.ChatLog(self.dir / "chat-history.db", self.dir / "chat-history.json",
                             provider or (lambda: key), clock=self.clock)
        H.use(self.log)

    def say(self, text, *, cid, answer=None, temporary=False, prov="typed"):
        self.clock.t += 60
        body = {"messages": [{"role": "user", "content": text, "provenance": prov}],
                "conversation_id": cid, "device": "phone"}
        if temporary:
            body["temporary"] = True
        turn = None
        if answer is not None:
            turn = {"finish_reason": "stop", "client_gone": False, "rounds": 1,
                    "answer": answer, "tools_ran": []}
        return self.log.record_turn(body, lane="local", turn=turn)

    def files(self) -> dict:
        """Every file in the history folder, name -> bytes."""
        return {p.name: p.read_bytes() for p in sorted(self.dir.iterdir()) if p.is_file()}

    def done(self):
        H.use(None)


def seeded(name):
    w = World(name)
    w.say("Can you remind me what the dentist said about my back tooth?",
          cid="conv-dentist-01", answer="You said the dentist wants to see you on Tuesday.")
    w.say("And what time was that appointment?", cid="conv-dentist-01",
          answer="Half past nine, at the surgery on Mill Road.")
    w.say("Plan a birthday dinner for my sister", cid="conv-birthday-1",
          answer="How about the Italian place she liked? I can note the date.")
    w.say("What is the weather like tomorrow", cid="conv-weather-01",
          answer="Dry and bright, around fourteen degrees.")
    return w


def joined(snippet) -> str:
    return "".join(p["text"] for p in snippet["parts"])


def t_search_finds_words_inside_a_chat():
    w = seeded("finds")
    try:
        out = w.log.search("mill road")
        ids = [c["id"] for c in out["conversations"]]
        check("a phrase said only in Jarvis's answer, deep in a chat, is found",
              ids == ["conv-dentist-01"], ids)
        c = out["conversations"][0]
        check("the row carries the list's own fields",
              {"id", "title", "started", "updated", "turns", "device", "has_voice", "tainted"}
              <= set(c), sorted(c))
        check("the title is the chat's own title, not the snippet",
              c["title"].startswith("Can you remind me what the dentist"), c["title"])
        hits = [p["text"] for p in c["snippet"]["parts"] if p["hit"]]
        check("each search word is marked in the snippet, in the words as kept",
              hits == ["Mill", "Road"], hits)
        check("the snippet says whose words it is", c["snippet"]["role"] == "assistant",
              c["snippet"])
        check("the parts put together are a piece of what was kept",
              joined(c["snippet"]) in "Half past nine, at the surgery on Mill Road.",
              joined(c["snippet"]))
        out = w.log.search("DENTIST tuesday")
        check("every word is required, in any message, case ignored",
              [x["id"] for x in out["conversations"]] == ["conv-dentist-01"], out)
        check("hits counts the messages that hold a search word",
              out["conversations"][0]["hits"] == 2, out["conversations"][0]["hits"])
        out = w.log.search("dentist birthday")
        check("words spread over two different chats match neither",
              out["conversations"] == [], out["conversations"])
        out = w.log.search("sister")
        check("the owner's own words are searched too",
              [x["id"] for x in out["conversations"]] == ["conv-birthday-1"], out)
    finally:
        w.done()


def t_search_writes_nothing_and_keeps_no_record():
    w = seeded("writes")
    audits = []
    real_audit = H._audit
    H._audit = lambda event, detail: audits.append((event, detail))
    try:
        before = w.files()
        for q in ("dentist", "Zyxwvut quokka", "mill road", "x", "weather tomorrow"):
            w.log.search(q)
            H.search(q)
            H.handle_get(H.SEARCH_PATH, "q=" + q.replace(" ", "+"))
        after = w.files()
        check("the same files, byte for byte, after searching (no index, no cache)",
              before == after, sorted(set(after) ^ set(before)))
        blob = b"".join(after.values()).lower()
        check("a searched-for word is in no file", b"quokka" not in blob and b"zyxwvut" not in blob)
        check("a search is not audited", audits == [], audits)
    finally:
        H._audit = real_audit
        w.done()


def t_temporary_chats_are_never_found():
    w = World("temporary")
    try:
        r = w.say("my secret plan involves pineapples", cid="conv-temp-001", temporary=True,
                  answer="Pineapples it is.")
        check("the temporary chat was not kept", r.get("recorded") is False, r)
        w.say("an ordinary chat about apples", cid="conv-normal-1")
        out = w.log.search("pineapples")
        check("so it is never found", out["conversations"] == [], out)
        check("while an ordinary chat is", [c["id"] for c in w.log.search("apples")["conversations"]]
              == ["conv-normal-1"])
    finally:
        w.done()


def t_history_off_still_searches_what_is_kept():
    w = seeded("off")
    try:
        w.log.set_enabled(False)
        before = w.files()
        out = w.log.search("dentist")
        check("with history off, what is still kept is still found (as the list lists it)",
              [c["id"] for c in out["conversations"]] == ["conv-dentist-01"], out)
        check("and the answer says history is off", out["enabled"] is False, out)
        r = w.say("dentist again, this is new", cid="conv-dentist-02")
        check("a new turn is not kept while it is off", r.get("recorded") is False, r)
        check("so it is not found", [c["id"] for c in w.log.search("again")["conversations"]] == [])
        after = w.files()
        check("nothing was written by searching",
              {k: v for k, v in after.items() if k.endswith(".db")}
              == {k: v for k, v in before.items() if k.endswith(".db")})
    finally:
        w.done()


def t_a_key_that_does_not_open_it():
    w = seeded("badkey")
    try:
        other = H.ChatLog(w.dir / "chat-history.db", w.dir / "chat-history.json",
                          lambda: bytes(32), clock=w.clock)
        out = other.search("dentist")
        check("a key that does not open the history finds nothing", out["conversations"] == [], out)
        check("and says why, in words", "does not open" in out["why_not"], out["why_not"])

        def no_key():
            raise H.KeyUnavailable("Credential Manager could not be used")
        none = H.ChatLog(w.dir / "chat-history.db", w.dir / "chat-history.json", no_key,
                         clock=w.clock)
        out = none.search("dentist")
        check("no key: nothing, and why", out["conversations"] == []
              and "Credential Manager" in out["why_not"], out)
    finally:
        w.done()


def t_too_short_too_long_limit_and_more():
    w = World("limits")
    try:
        for i in range(7):
            w.say(f"shopping list number {i}: bread and milk", cid=f"conv-shop-{i:04d}")
        out = w.log.search("a")
        check("one letter is too short, in words", out["query_ok"] is False
              and out["why"] == H.SEARCH_TOO_SHORT and out["conversations"] == [], out)
        out = w.log.search("  ")
        check("blank is too short", out["query_ok"] is False)
        out = w.log.search(" ".join(f"word{i}" for i in range(9)))
        check("nine words is too long", out["query_ok"] is False and out["why"] == H.SEARCH_TOO_LONG)
        out = w.log.search("x" * 101)
        check("101 characters is too long", out["query_ok"] is False)
        out = w.log.search("bread", limit=3)
        check("limit is kept, newest first",
              [c["id"] for c in out["conversations"]] == ["conv-shop-0006", "conv-shop-0005",
                                                          "conv-shop-0004"], out["conversations"])
        check("and `more` says there were others", out["more"] is True)
        out = w.log.search("bread", limit=50)
        check("all seven when the limit allows, and no `more`",
              len(out["conversations"]) == 7 and out["more"] is False)
        check("a word shorter than two letters is skipped, not required",
              len(w.log.search("I bread")["conversations"]) == 7)
        code, body = H.handle_get(H.SEARCH_PATH, "q=bread&limit=2")
        check("the route answers 200 with the same shape",
              code == 200 and len(body["conversations"]) == 2 and body["more"] is True, (code, body))
        code, body = H.handle_get(H.SEARCH_PATH, "")
        check("no ?q= is a 200 with a sentence, not an error", code == 200
              and body["query_ok"] is False, (code, body))
    finally:
        w.done()


def t_snippet_parts_are_exact():
    rx = [__import__("re").compile("tea", __import__("re").IGNORECASE)]
    text = ("x " * 80) + "I like TEA with 🍋 lemon and tea cake " + ("y " * 120)
    snip = H._snippet(rx, "user", 5, text)
    whole = joined(snip)
    check("the parts are one piece of the words, in order", whole in text, whole)
    check("both matches are marked, as written", [p["text"] for p in snip["parts"] if p["hit"]]
          == ["TEA", "tea"], snip["parts"])
    check("cut at both ends, and it says so", snip["before"] and snip["after"], snip)
    check("never longer than the snippet size", len(whole) <= H.SNIPPET_CHARS, len(whole))
    check("no half word at the start", whole.startswith("x ") or whole.startswith("I "), whole[:10])


# ------------------------------------------------------------ fact history

class Emb(M.Embedder):
    name, dim, semantic = "brain-reads-test-v1", 8, True

    def embed(self, texts):
        return [[1.0 + ((hash(t) >> i) & 1) for i in range(self.dim)] for t in texts]


def store(name):
    d = _TMP / name
    d.mkdir(parents=True, exist_ok=True)
    st = M.MemoryStore(path=d / "memory.db", embedder=Emb())
    M._store = st
    return st


def t_fact_history_follows_rewordings():
    st = store("chain")
    a = st.add("Owner's dentist is Dr Patel on Mill Road", source="auto")
    st.add("Owner likes green tea", source="auto")
    b = st.add("Owner's dentist is Dr Patel on Station Road", source="edited", supersedes=a)
    c = st.add("Owner's dentist is Dr Okafor on Station Road", source="edited", supersedes=b)
    for asked in (a, b, c):
        v = M.fact_history_view(asked, st=st)
        ids = [x["id"] for x in v["versions"]]
        check(f"asked about #{asked}: all three versions, oldest first", ids == [a, b, c], ids)
        check(f"asked about #{asked}: `this` marks it and only it",
              [x["id"] for x in v["versions"] if x["this"]] == [asked])
    v = M.fact_history_view(c, st=st)
    check("only the newest is current", [x["current"] for x in v["versions"]] == [False, False, True])
    check("each older one names what replaced it",
          [x["retired_by"] for x in v["versions"]] == [b, c, None], v["versions"])
    check("the unrelated fact is not in it", all("tea" not in x["text"] for x in v["versions"]))
    check("the words of each version", v["versions"][0]["text"].endswith("Mill Road"))
    lone = st.add("Owner's cat is called Miso", source="auto")
    v = M.fact_history_view(lone, st=st)
    check("a fact never reworded has one version", v["count"] == 1 and v["versions"][0]["this"])
    check("no such fact is None", M.fact_history_view(99999, st=st) is None)


def t_fact_history_never_shows_erased_words():
    st = store("erased")
    secret = "Qwertylmnop"
    a = st.add(f"Owner's locker code is {secret} 1", source="auto")
    b = st.add(f"Owner's locker code is {secret} 2", source="edited", supersedes=a)
    c = st.add("Owner's locker is the one by the window", source="edited", supersedes=b)
    st.erase(b)          # erases b and, by default, the wording before it (a)
    v = M.fact_history_view(c, st=st)
    body = json.dumps(v)
    check("the erased versions are still in the history (dates kept)",
          [x["id"] for x in v["versions"]] == [a, b, c], v)
    check("an erased version comes with no words, not even the marker",
          all(x["text"] == "" and x["erased_at"] for x in v["versions"][:2]), v["versions"][:2])
    check("the erased words are nowhere in the answer",
          secret.lower() not in body.lower() and M.ERASED_TEXT not in body, body[:300])
    check("the later wording, never erased, keeps its words",
          v["versions"][2]["text"] == "Owner's locker is the one by the window")
    code, out = M.handle_fact_history_get(f"id={a}")
    check("through the route too", code == 200 and secret.lower() not in json.dumps(out).lower())


def t_fact_history_includes_older_news():
    st = store("older")
    new = st.add("Owner moved to Leeds in March 2026", source="auto")
    old = st.add("Owner moved to York in January 2026", source="auto", supersedes=new)
    check("the correction was kept as older news", st.last_older_news is True)
    v = M.fact_history_view(new, st=st)
    ids = [x["id"] for x in v["versions"]]
    check("it is part of the newer fact's history, first (true earlier)", ids == [old, new], ids)
    check("and the newer fact is still the current one",
          [x["current"] for x in v["versions"]] == [False, True])


def t_forgotten_is_marked():
    st = store("forgot")
    f = st.add("Owner plays the cello", source="auto")
    st.retire(f)
    v = M.fact_history_view(f, st=st)
    check("a forgotten fact says so", v["versions"][0]["forgotten"] is True
          and v["versions"][0]["current"] is False, v)


def t_fact_history_route():
    st = store("route")
    f = st.add("Owner's favourite colour is teal", source="auto")
    code, out = M.handle_fact_history_get(f"id={f}")
    check("200 with the versions", code == 200 and out["count"] == 1, (code, out))
    check("no meta, no conversation id in the answer",
          all(set(x) == {"id", "text", "this", "current", "forgotten", "erased_at", "created",
                         "valid_from", "valid_to", "retired_at", "retired_by", "source"}
              for x in out["versions"]), out)
    for bad in ("", "id=", "id=0", "id=-3", "id=abc", "id=1,2", "id=1.5"):
        code, out = M.handle_fact_history_get(bad)
        check(f"{bad!r} is a 400 in words", code == 400 and "fact id" in out["error"], (code, out))
    code, out = M.handle_fact_history_get("id=424242")
    check("no such fact is a 404 in words", code == 404 and "no such fact" in out["error"])


def t_conversation_facts():
    """"Facts this chat taught" (2026-09-28; JARVIS-API section 79): only the
    facts STILL IN USE whose own meta says that conversation - never a
    forgotten, erased or corrected one, never another chat's - and the route
    forgets nothing."""
    st = store("conv-facts")
    cid, other = "conv-teach-0001", "conv-other-0002"
    a = st.add("Owner's passport is in the top drawer", source="auto",
               meta={"auto": True, "conversation_id": cid})
    b = st.add("Owner likes green tea", source="auto",
               meta={"auto": True, "conversation_id": cid})
    gone = st.add("Owner's bike is red", source="auto",
                  meta={"auto": True, "conversation_id": cid})
    erased = st.add("Owner's locker code is Zyxwvut 9", source="auto",
                    meta={"auto": True, "conversation_id": cid})
    old = st.add("Owner works at Initech", source="auto",
                 meta={"auto": True, "conversation_id": cid})
    st.add("Owner works at Globex", source="edited", supersedes=old)
    st.add("Owner's cat is called Miso", source="auto",
           meta={"auto": True, "conversation_id": other})
    st.add("Owner is learning the harp", source="extracted", meta={"proposal_id": 3})
    lookalike = st.add("Owner plays chess", source="auto",
                       meta={"auto": True, "conversation_id": cid + "x"})
    st.retire(gone)
    st.erase(erased)
    before = [tuple(r) for r in _rows(st)]
    v = M.conversation_facts_view(cid, st=st)
    ids = [f["id"] for f in v["facts"]]
    check("only that chat's facts still in use, newest first", ids == [b, a], v)
    check("never a forgotten, erased or corrected one, or another chat's",
          gone not in ids and erased not in ids and old not in ids and lookalike not in ids)
    check("each is its id, words, when and source - no meta, no conversation id",
          all(set(f) == {"id", "text", "created", "source"} for f in v["facts"]), v)
    check("the erased words are nowhere in the answer", "Zyxwvut" not in json.dumps(v))
    code, out = M.handle_conversation_facts_get(f"conversation_id={cid}")
    check("the route: 200 with the list", code == 200 and out["count"] == 2, (code, out))
    for bad in ("", "conversation_id=", "conversation_id=short", "conversation_id=a%20b%20cdefgh",
                "conversation_id=" + "x" * 65):
        code, out = M.handle_conversation_facts_get(bad)
        check(f"{bad[:30]!r} is a 400 in words", code == 400 and "conversation id" in out["error"],
              (code, out))
    code, out = M.handle_conversation_facts_get("conversation_id=conv-nothing-99")
    check("a chat that taught nothing: an empty list", code == 200 and out["facts"] == [])
    check("reading it changes nothing", [tuple(r) for r in _rows(st)] == before)
    code, out = B.handle_get(B.CONVERSATION_FACTS_PATH, f"conversation_id={cid}")
    check("jarvis_brain_reads answers it", code == 200 and out["count"] == 2, (code, out))


def _rows(st):
    from contextlib import closing
    with closing(st._connect()) as c:
        return c.execute("SELECT * FROM facts ORDER BY id").fetchall()


# ------------------------------------------------------ routes and the patch

class FakeHandler:
    def __init__(self, path):
        self.path = path
        self.sent = None

    def do_GET(self):
        self.sent = ("original", self.path)

    def _send(self, code, body):
        self.sent = (code, body)


def t_install_answers_only_its_paths():
    class Hd(FakeHandler):
        pass
    line = B.install(Hd, origin_ok=lambda s: True, token_ok=lambda s: True)
    check("install returns a banner line", "Search old chats" in line, line)
    check("installing twice does not wrap twice",
          "already on" in B.install(Hd, origin_ok=lambda s: True, token_ok=lambda s: True))
    h = Hd("/api/history")
    h.do_GET()
    check("another path goes to the original", h.sent == ("original", "/api/history"), h.sent)
    st = store("install")
    f = st.add("Owner's bike is red", source="auto")
    h = Hd(f"/api/memory/fact-history?id={f}")
    h.do_GET()
    check("fact history is answered here", h.sent[0] == 200 and h.sent[1]["count"] == 1, h.sent)

    class Locked(FakeHandler):
        pass
    B.install(Locked, origin_ok=lambda s: True, token_ok=lambda s: False)
    h = Locked(f"/api/memory/fact-history?id={f}")
    h.do_GET()
    check("no token, no answer", h.sent[0] == 401, h.sent)

    class Foreign(FakeHandler):
        pass
    B.install(Foreign, origin_ok=lambda s: False, token_ok=lambda s: True)
    h = Foreign("/api/history/search?q=dentist")
    h.do_GET()
    check("another origin, no answer", h.sent[0] == 403, h.sent)


def t_an_older_module_says_update():
    real = getattr(M, "handle_fact_history_get")
    try:
        delattr(M, "handle_fact_history_get")
        code, out = B.handle_get(B.FACT_HISTORY_PATH, "id=1")
        check("an older jarvis_memory.py: 501 and a sentence", code == 501
              and "apply-patches.ps1" in out["error"], (code, out))
    finally:
        M.handle_fact_history_get = real
    real = getattr(M, "handle_conversation_facts_get")
    try:
        delattr(M, "handle_conversation_facts_get")
        code, out = B.handle_get(B.CONVERSATION_FACTS_PATH, "conversation_id=conv-abcdefgh")
        check("an older jarvis_memory.py: a chat's facts is a 501 and a sentence",
              code == 501 and "apply-patches.ps1" in out["error"], (code, out))
    finally:
        M.handle_conversation_facts_get = real


def t_not_a_tool_the_model_can_call():
    agent = (HERE / "jarvis_agent.py").read_text(encoding="utf-8")
    for needle in ("history/search", "fact-history", "jarvis_brain_reads", ".search(",
                   "fact_history", "conversation-facts", "conversation_facts"):
        if needle == ".search(":
            # jarvis_agent may search memory for recall; what must not be
            # there is the chat log's search.
            check("jarvis_agent.py never calls the chat log's search",
                  "jarvis_chat_log.search" not in agent and "_log().search" not in agent)
            continue
        check(f"jarvis_agent.py never mentions {needle}", needle not in agent)


def t_patch_and_shipping():
    import _stack
    import _where
    order = _stack.order()
    check("brain-reads.patch is last in apply-patches.ps1", order[-1] == "brain-reads.patch",
          order[-3:])
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("jarvis_brain_reads.py is shipped by the script and in _where.SHIPPED",
          "'jarvis_brain_reads.py'" in ps1 and "jarvis_brain_reads.py" in _where.SHIPPED)
    text, log = _stack.stand_in("jarvis_hud.py")
    check("the whole stack, this patch included, builds", text is not None, log[-3:])
    if text:
        at = text.find("import jarvis_brain_reads")
        sock = text.find("_loopback_companion(bind, HUD_PORT, Handler)", at)
        check("the install sits after sources' and right before the main socket",
              text.rfind("import jarvis_sources", 0, at) != -1 and 0 < sock - at < 1200,
              (at, sock))
        check("with the server's own token and origin checks",
              "jarvis_brain_reads.install(Handler, origin_ok=_origin_ok," in text)
        check("its own pre-image was already there (no gap for this patch)",
              not any(line.startswith("brain-reads.patch") for line in log), log)


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
