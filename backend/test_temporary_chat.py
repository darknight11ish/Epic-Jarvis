"""test_temporary_chat.py - a temporary chat, and "Used in this answer".

    python3 backend/test_temporary_chat.py

The owner's decisions of 2026-09-25 (docs/JARVIS-API.md sections 4, 6, 18
and 19):

  * TEMPORARY CHAT. A /api/chat request with `"temporary": true` recalls no
    facts (no pinned list either), learns nothing (no background learning,
    no proposal, no "Remember:"), and is not kept in the chat history - the
    live-turn registry gets a hash under the provenance "temporary", never
    the words. X-Jarvis-Route says `"temporary": true` (and `remember_off`
    for a "Remember:"), and /api/version's capabilities.temporary_chat says
    whether the running server has it. Everything else is unchanged, and an
    ordinary request is exactly what it was.
  * USED IN THIS ANSWER. GET /api/memory/used?ids=12,15 gives the words of
    the facts an answer used (the header carries ids only): current or not,
    pinned or not, never an erased fact's words; token and origin like every
    memory read; 400 for anything but 1 to 100 ids.

Proved against the whole patch stack's stand-in for jarvis_hud.py
(backend/_stack.py) - its lines lifted and run - and real SQLite files in a
temporary folder. Every check here fails on the code before this change: the
patch, used_view() and the chat log's TEMPORARY_CHAT did not exist.

No pytest, no network, no model.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("rebuilt/jarvis_memory.py", "jarvis_chat_log.py", "jarvis_auto_learn.py",
                "rebuilt/jarvis_events.py")

try:
    import jarvis_memory as M
except ImportError:
    sys.path.append(str(REPO / "backend" / "rebuilt"))
    import jarvis_memory as M
import jarvis_auto_learn as A  # noqa: E402
import jarvis_chat_log as H  # noqa: E402

import _stack  # noqa: E402

PASSED, FAILED = [], []
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-temporary-"))
CID = "conv-temporary-1"
VEG = "Owner is vegetarian"
LEEDS = "Owner lives in Leeds and cooks on a gas hob"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def fresh(name: str):
    d = _TMP / name
    d.mkdir(parents=True, exist_ok=True)
    st = M.MemoryStore(path=d / "memory.db", embedder=M.HashEmbedder())
    M._store = st
    return st


_HUD = None


def hud():
    global _HUD
    if _HUD is None:
        _HUD, log = _stack.stand_in("jarvis_hud.py")
        check("the whole jarvis_hud.py stack builds, temporary-chat.patch included",
              _HUD is not None and "def _temporary_chat(body)" in _HUD,
              "\n".join(log or [])[-400:])
        check("every temporary-chat hunk found its context in the stack (none made up)",
              not any("temporary-chat" in line for line in log or []), log)
    return _HUD


def _fragment(src, start, stop, *, after=0):
    i = src.index(start, after)
    i = src.rfind("\n", 0, i) + 1
    j = src.index(stop, i)
    j = src.rfind("\n", 0, j) + 1
    return textwrap.dedent(src[i:j])


def helpers(src) -> dict:
    """The patch's module-level helpers, lifted and run."""
    ns: dict = {}
    fields = next(line for line in src.splitlines() if line.startswith("_CHAT_CLIENT_FIELDS = "))
    note_at = src.index("_TEMPORARY_NOTE = (")
    note = src[note_at:src.index("\n\n", note_at)]
    code = "\n".join([fields, _stack.function_text(src, "_chat_client_fields_off"),
                      _stack.function_text(src, "_temporary_chat"), note,
                      _stack.function_text(src, "_temporary_remember")])
    exec(compile(code, "<temporary-chat helpers>", "exec"), ns)
    return ns


# ------------------------------------------------------------ the read route

def t_ids_are_read_strictly():
    P = M.parse_used_ids
    check("12,15 -> [12, 15]", P("12,15") == [12, 15])
    check("the header's own spelling, mem:12, is read as 12", P("mem:12, mem:3") == [12, 3])
    check("each id once, in the order given", P("5,3,5,3") == [5, 3])
    for bad in ("", " ", "fact:3", "12,abc", "-1", "0", "1.5", "12,,15", "1e3", None, "١٢"):
        check(f"{bad!r} is refused as a whole", P(bad) is None, P(bad))
    check("100 ids are fine, 101 are not",
          P(",".join(str(i) for i in range(1, 101))) is not None
          and P(",".join(str(i) for i in range(1, 102))) is None)


def t_the_view_says_what_each_fact_is():
    st = fresh("view")
    veg, leeds = st.add(VEG), st.add("Owner lives in Harrogate")
    york = st.add("Owner lives in York", supersedes=leeds)
    gone = st.add("Owner's PIN is 4455")
    later = st.add("Owner rents a flat until next year", valid_from=time.time() - 10)
    st.pin(veg)
    st.erase(gone)
    st.retire(later, valid_to=time.time() + 86400 * 90)     # ends in the future
    out = M.used_view([york, leeds, veg, gone, 424242, later], st)
    by = {f["id"]: f for f in out["facts"]}
    check("in the order asked, a missing id listed apart",
          [f["id"] for f in out["facts"]] == [york, leeds, veg, gone, later]
          and out["missing"] == [424242], out)
    check("a current fact: its words, current",
          by[york]["text"] == "Owner lives in York" and by[york]["current"]
          and not by[york]["pinned"], by[york])
    check("a retired fact an answer about the past used: its words, not current, when it ended",
          by[leeds]["text"] == "Owner lives in Harrogate" and not by[leeds]["current"]
          and by[leeds]["valid_to"], by[leeds])
    check("a pinned fact is marked pinned", by[veg]["pinned"] and by[veg]["current"], by[veg])
    check("an erased fact: no words - not even the marker - and when it was erased",
          by[gone]["text"] == "" and by[gone]["erased_at"] and not by[gone]["current"]
          and "4455" not in json.dumps(out) and "[erased]" not in json.dumps(out), by[gone])
    check("a fact that ends in the future is still current (valid_to > now)",
          by[later]["current"], by[later])


def t_handle_used_get():
    st = fresh("handle")
    fid = st.add(VEG)
    code, body = M.handle_used_get(f"ids={fid}")
    check("200 with the words", code == 200 and body["facts"][0]["text"] == VEG, (code, body))
    for q in ("", "ids=", "ids=fact:2", "ids=a,b", "x=1",
              "ids=" + ",".join(str(i) for i in range(1, 102))):
        code, body = M.handle_used_get(q)
        check(f"400 for {q[:30]!r}", code == 400 and "ids" in body["error"], (code, body))
    code, body = M.handle_used_get("ids=424242")
    check("an unknown id is not an error: 200, listed as missing",
          code == 200 and body == {"facts": [], "missing": [424242]}, (code, body))


class _Handler:
    def __init__(self, path):
        self.path = path
        self.sent = None

    def _send(self, code, body):
        self.sent = (code, body)
        return self.sent


def _get_route(src):
    return _fragment(src, '        if path == "/api/memory/used":',
                     '        if path == "/api/memory/profile":')


def _call(block, url, *, origin=True, token=True, memory=True, module=None):
    ns = {"_origin_ok": lambda s: origin, "_token_ok": lambda s: token, "MEMORY": memory,
          "json": json, "jarvis_memory": module or M}
    exec(compile("def handle(self, path):\n" + textwrap.indent(block, "    "),
                 "<memory/used route>", "exec"), ns)
    h = _Handler(url)
    ns["handle"](h, url.split("?", 1)[0])
    return h.sent


def t_the_route():
    src = hud()
    if src is None:
        return
    block = _get_route(src)
    st = fresh("route")
    fid = st.add(VEG)
    url = f"/api/memory/used?ids={fid}"
    check("another site's page is refused (403), nothing read",
          _call(block, url, origin=False)[0] == 403)
    check("no or a wrong token (401)", _call(block, url, token=False)[0] == 401)
    check("memory not running (503)", _call(block, url, memory=False)[0] == 503)
    code, body = _call(block, url)
    check("200: the fact's own words", code == 200 and body["facts"][0]["text"] == VEG,
          (code, body))
    check("a bad id list is a 400 in words", _call(block, "/api/memory/used?ids=x")[0] == 400)
    old = types.SimpleNamespace(store=M.store)
    code, body = _call(block, url, module=old)
    check("an older jarvis_memory.py: 501 in words, nothing pretended",
          code == 501 and "jarvis_memory.py" in body["error"], (code, body))
    check("the route sits above \"Always keep in mind\"'s GET",
          src.index('if path == "/api/memory/used":') < src.index('if path == "/api/memory/profile":'))


# ------------------------------------------------------------ the chat turn

class _Store:
    """A store that says whether it was asked anything."""

    def __init__(self, st):
        self.st = st
        self.asked = []

    def search(self, *a, **k):
        self.asked.append("search")
        return self.st.search(*a, **k)

    def profile(self):
        self.asked.append("profile")
        return self.st.profile()

    def __getattr__(self, name):
        return getattr(self.st, name)


def _turn(src, st, query, body):
    """The chat turn's recall and header, as the stack writes them: search
    (past-recall, memory-profile, temporary-chat), chosen_facts, the FACTS
    block, the placement, and X-Jarvis-Route."""
    at = src.index("# past-recall.patch: a question about the past")
    search = _fragment(src, "# past-recall.patch: a question about the past", "if hits:")
    chosen = _fragment(src, "if hits:", "except Exception:", after=at)
    recall = _fragment(src, "injected = len(chosen_facts)", "# Late, not first", after=at)
    place = _fragment(src, "                # temporary-chat.patch: in a temporary chat NOTHING",
                      "# Memory is now in the transcript")
    header = _fragment(src, "# temporary-chat.patch: say so in X-Jarvis-Route",
                       "if use_tools:")
    spy = _Store(st)
    mem = types.SimpleNamespace(store=lambda: spy, with_profile=M.with_profile)
    real_past = sys.modules.get("jarvis_past")
    ns = dict(helpers(src), jarvis_memory=mem, query=query, MEMORY_K=5, time=time, body=body,
              messages=[{"role": "user", "content": query}])
    ns["_dated_fact"] = lambda f: "- " + str(f.get("text", ""))
    try:
        exec(compile(search, "<stacked search>", "exec"), ns)
    finally:
        if real_past is not None:
            sys.modules["jarvis_past"] = real_past
    ns["chosen_facts"] = []
    exec(compile(chosen, "<stacked chosen_facts>", "exec"), ns)
    ns["facts"] = ns.get("facts") or []
    if not ns["chosen_facts"]:
        # What the older word matcher over the jsonl might have found: the
        # placement must drop even that in a temporary chat.
        ns["chosen_facts"] = ns["facts"] = [{"text": "Owner's old jsonl fact", "id": 999,
                                              "created": None}]
    exec(compile(recall, "<stacked recall>", "exec"), ns)
    exec(compile(place, "<stacked placement>", "exec"), ns)
    rh = {"injected_facts": ns["injected"], "injected_ids": list(ns["injected_ids"]),
          "memory_side": "hud" if ns["injected"] else "none", "inject_memory": True,
          "reason": "", "lane": "qwen3:8b"}
    feedback = types.ModuleType("jarvis_feedback")
    feedback.record_turn = lambda ids: "0" * 32
    real_fb = sys.modules.get("jarvis_feedback")
    sys.modules["jarvis_feedback"] = feedback
    try:
        exec(compile("first_error = None\n" + header, "<stacked header>", "exec"),
             dict(ns, route_header=rh))
    finally:
        if real_fb is None:
            sys.modules.pop("jarvis_feedback", None)
        else:
            sys.modules["jarvis_feedback"] = real_fb
    return ns, rh, spy


def t_a_temporary_chat_recalls_nothing():
    src = hud()
    if src is None:
        return
    st = fresh("turn")
    veg = st.add(VEG)
    st.add(LEEDS)
    st.pin(veg)
    q = "What should I cook tonight on the hob?"
    ns, rh, spy = _turn(src, st, q, {"temporary": True, "messages": [
        {"role": "user", "content": q}]})
    sent = json.dumps(ns["messages"])
    check("no search and no pinned list were even read", spy.asked == [], spy.asked)
    check("no fact reaches the model - not the pinned one, not a searched one, "
          "not an old word-list one",
          VEG not in sent and "gas hob" not in sent and "jsonl fact" not in sent
          and "---FACTS---" not in sent, sent)
    check("the model is told it is a temporary chat, in the recalled block's place, "
          "just before the question",
          ns["messages"][0] == {"role": "system", "content": ns["_TEMPORARY_NOTE"]}
          and ns["messages"][1]["content"] == q
          and "Remember is off in a temporary chat" in ns["_TEMPORARY_NOTE"], ns["messages"])
    check("X-Jarvis-Route says temporary, and counts no fact used",
          rh["temporary"] is True and rh["injected_facts"] == 0 and rh["injected_ids"] == []
          and rh["memory_side"] == "none" and rh["inject_memory"] is False, rh)
    check("... and nothing sensitive", rh.get("injected_sensitive") == 0, rh)
    check("no remember_off on an ordinary question", "remember_off" not in rh, rh)

    ns2, rh2, _ = _turn(src, st, q, {"messages": [{"role": "user", "content": q}]})
    sent2 = json.dumps(ns2["messages"])
    check("an ordinary chat is unchanged: the pinned fact and the searched one go in",
          VEG in sent2 and "gas hob" in sent2 and "---FACTS---" in sent2, sent2)
    check("... and its header has no temporary mark and counts the facts",
          "temporary" not in rh2 and rh2["injected_facts"] == 2, rh2)
    ns3, rh3, _ = _turn(src, st, q, {"temporary": "yes", "messages": []})
    check("only JSON true turns it on (\"yes\" is an ordinary chat)",
          "temporary" not in rh3 and VEG in json.dumps(ns3["messages"]), rh3)


def t_remember_is_off():
    src = hud()
    if src is None:
        return
    st = fresh("remember")
    q = "Remember: my locker code is 4312"
    _, rh, _ = _turn(src, st, q, {"temporary": True,
                                   "messages": [{"role": "user", "content": q}]})
    check("a \"Remember:\" in a temporary chat: the header says remember_off",
          rh.get("remember_off") is True and rh["temporary"] is True, rh)
    ns = helpers(src)
    check("the same test as jarvis_intake's (\"remember -\", \"Remember,\")",
          ns["_temporary_remember"]({"messages": [{"role": "user", "content": "remember - x"}]})
          and not ns["_temporary_remember"]({"messages": [
              {"role": "user", "content": "Remember: x"},
              {"role": "user", "content": "what do you remember?"}]}))
    real = sys.modules.get("jarvis_intake")
    sys.modules["jarvis_intake"] = None                     # the import fails
    try:
        check("without jarvis_intake.py: still caught",
              ns["_temporary_remember"]({"messages": [{"role": "user", "content": "Remember: x"}]}))
    finally:
        if real is None:
            sys.modules.pop("jarvis_intake", None)
        else:
            sys.modules["jarvis_intake"] = real


def t_the_flag_never_reaches_a_model():
    src = hud()
    if src is None:
        return
    ns = helpers(src)
    got = ns["_chat_client_fields_off"]([{"role": "user", "content": "hi", "temporary": True}])
    check("\"temporary\" is one of the apps' bookkeeping fields, taken off every message",
          "temporary" in ns["_CHAT_CLIENT_FIELDS"] and got == [{"role": "user", "content": "hi"}])
    frag = _stack.fragment_with(src, 'body = dict(payload); body["model"] = lane')
    a = next(i for i, line in enumerate(frag) if 'body = dict(payload); body["model"] = lane' in line)
    b = next(i for i, line in enumerate(frag) if "return urllib.request.urlopen(" in line)
    env = dict(ns, lane="qwen3:8b", local_model="qwen3:8b",
               payload={"model": "x", "temporary": True,
                        "messages": [{"role": "user", "content": "q"}]})
    exec(textwrap.dedent("\n".join(frag[a:b])), env)
    check("nor off the request the relay sends", "temporary" not in json.dumps(env["body"]),
          env["body"])


def _finally(src):
    frag = _stack.fragment_with(src, "jarvis_chat_log.record_turn(")
    a = next(i for i, line in enumerate(frag) if line.strip() == '_activity("idle")')
    b = max(i for i, line in enumerate(frag) if line.strip() == "pass") + 1
    return textwrap.dedent("\n".join(frag[a:b]))


def _run_finally(snippet, body, stub):
    offered, recorded = [], []
    if stub is not None:
        stub.record_turn = lambda b, **kw: recorded.append(b)
    real = sys.modules.get("jarvis_chat_log")
    sys.modules["jarvis_chat_log"] = stub
    try:
        # games-temporary.patch: the snippet now calls _temporary_chat(body)
        # instead of reading body.get("temporary") directly (so a detected
        # game is kept out of history and learning too, not only a chat the
        # app itself marked temporary) - the real module always has that
        # name in scope; this isolated fragment needs it added to `env`,
        # same as MEMORY or LEARNER above. Plain flag semantics here on
        # purpose: game detection itself is test_games_temp_chat.py's job.
        env = {"_activity": lambda *a: None, "MEMORY": True, "jarvis_side_memory": False,
               "LEARNER": types.SimpleNamespace(
                   offer=lambda m, origin="unknown", **kw: offered.append(m)),
               "_temporary_chat": lambda b: isinstance(b, dict) and b.get("temporary") is True,
               "body": body, "route_header": {"lane": "qwen3:8b"}, "lane": "qwen3:8b",
               "_history": {"turn": {"answer": "hi"}, "at": 1.0}}
        exec(snippet, env)
    finally:
        if real is None:
            sys.modules.pop("jarvis_chat_log", None)
        else:
            sys.modules["jarvis_chat_log"] = real
    return offered, recorded


def t_nothing_is_learned_or_kept():
    src = hud()
    if src is None:
        return
    snippet = _finally(src)
    msg = [{"role": "user", "content": "Remember: I am vegetarian", "provenance": "typed"}]
    knows = types.ModuleType("jarvis_chat_log")
    knows.TEMPORARY_CHAT = True
    offered, recorded = _run_finally(snippet, {"messages": msg, "temporary": True,
                                               "conversation_id": CID}, knows)
    check("a temporary chat is never offered to the learner - not even a \"Remember:\"",
          offered == [], offered)
    check("the chat log still sees it (for the registry's hash), and keeps nothing - below",
          len(recorded) == 1 and recorded[0]["temporary"] is True, recorded)
    older = types.ModuleType("jarvis_chat_log")
    offered, recorded = _run_finally(snippet, {"messages": msg, "temporary": True,
                                               "conversation_id": CID}, older)
    check("an older jarvis_chat_log.py (which would keep it) is not called at all",
          recorded == [] and offered == [], (recorded, offered))
    offered, recorded = _run_finally(snippet, {"messages": msg, "conversation_id": CID}, older)
    check("an ordinary chat: recorded and offered to the learner, as before",
          len(recorded) == 1 and offered == [msg], (recorded, offered))


def t_the_chat_log_keeps_nothing():
    d = Path(tempfile.mkdtemp(prefix="jarvis-temporary-log-", dir=_TMP))
    H._reset_for_tests()
    log = H.ChatLog(d / "chat-history.db", d / "chat-history.json", lambda: bytes(range(32)))
    H.use(log)
    try:
        words = "my sister's new number is 07700 900123"
        body = {"messages": [{"role": "user", "content": words, "provenance": "typed"}],
                "conversation_id": CID, "device": "phone", "temporary": True}
        out = log.record_turn(body, lane="qwen3:8b",
                              turn={"finish_reason": "stop", "answer": "Noted.",
                                    "tools_ran": ["email_check"]})
        check("a temporary chat is not recorded, and says why",
              out == {"recorded": False, "why": H.TEMPORARY_WHY}, out)
        check("the history lists nothing", log.list()["conversations"] == [], log.list())
        raw = b"".join(p.read_bytes() for p in d.iterdir() if p.is_file())
        check("not one byte of the words is on disk", words.encode() not in raw
              and b"07700" not in raw)
        entry = log.live_turn(CID, words)
        check("the registry holds a hash under the provenance \"temporary\" - never the words",
              entry is not None and entry["provenance"] == "temporary"
              and words not in json.dumps(entry), entry)
        check("a tool that read outside text still marks the conversation (the note-write card)",
              log.conversation_tainted(CID))
        check("automatic learning makes a card of it, with the reason in words",
              A.check_provenance(entry) == "said in a temporary chat, which Jarvis never learns from")
        normal = dict(body)
        normal.pop("temporary")
        normal["conversation_id"] = "conv-ordinary-1"
        got = log.record_turn(normal, lane="qwen3:8b",
                              turn={"finish_reason": "stop", "answer": "Noted."})
        check("an ordinary chat is recorded as before", got.get("recorded") is True, got)
    finally:
        H.use(None)
        shutil.rmtree(d, ignore_errors=True)


def t_the_capability():
    try:
        import jarvis_events as E
    except ImportError:
        sys.path.append(str(REPO / "backend" / "rebuilt"))
        import jarvis_events as E
    check("an older server (no _temporary_chat) reports temporary_chat false",
          E._capability_probe()["temporary_chat"] is False)
    fake = types.ModuleType("jarvis_hud")
    fake._temporary_chat = lambda body: True
    real = sys.modules.get("jarvis_hud")
    sys.modules["jarvis_hud"] = fake
    try:
        check("the patched server reports temporary_chat true",
              E._capability_probe()["temporary_chat"] is True)
    finally:
        if real is None:
            sys.modules.pop("jarvis_hud", None)
        else:
            sys.modules["jarvis_hud"] = real


def t_listed_and_applies():
    import _where
    names = [str(p).replace("\\", "/").split("/")[-1] for p in _stack.order()]
    check("temporary-chat.patch is in apply-patches.ps1's order, after memory-profile",
          "temporary-chat.patch" in names
          and names.index("temporary-chat.patch") > names.index("memory-profile.patch"),
          names[-3:])
    check("the modules that do the work are shipped whole",
          "rebuilt/jarvis_memory.py" in _where.SHIPPED and "jarvis_chat_log.py" in _where.SHIPPED)
    git = shutil.which("git")
    if not git:
        return check("SKIP - git is not installed", True)
    order = _stack.order()
    at = order.index("temporary-chat.patch")
    text, _ = _stack.stand_in("jarvis_hud.py", order[:at])
    check("jarvis_hud.py: the stack before temporary-chat.patch builds", text is not None)
    if text is None:
        return
    d = Path(tempfile.mkdtemp(prefix="jarvis-temporary-patch-", dir=_TMP))
    (d / "jarvis_hud.py").write_text(text, encoding="utf-8", newline="\n")
    (d / "p.patch").write_bytes((HERE / "temporary-chat.patch").read_bytes()
                                .replace(b"\r\n", b"\n"))
    for extra in (["--check"], [], ["--check", "--reverse"], ["--reverse"], []):
        r = subprocess.run([git, "apply", *extra, "p.patch"], cwd=d, capture_output=True,
                           text=True)
        check(f"git apply {' '.join(extra) or '(forwards)'} temporary-chat.patch",
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
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
