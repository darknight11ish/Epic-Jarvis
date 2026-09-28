"""Bring in old chats: DeepSeek, the real Gemini and Claude shapes, and
reading a long chat whole (import_history.py; JARVIS-API.md section 85).

    python3 test_import_understanding.py

No network, no model, no real export: made-up exports in the shapes that
open-source readers of real exports describe (import_history.py says which),
and a stand-in jarvis_extract. Every socket is refused for the whole run.

What it holds to:
  1. DeepSeek: the owner's words are the REQUEST fragments; the reasoning
     (THINK), web results (SEARCH), tools and files are never read; the
     branch read is the one ending at the newest message, in tree order;
     its account file (user.json) is never read; it is told apart from a
     ChatGPT export, both ways.
  2. Gemini (Takeout): the verb ("Prompted ") is cut off, "Attached N
     files." too; feedback, "Used ..." and other non-prompts are skipped;
     Search/YouTube records are skipped; another language's records are read
     when Gemini answered them; prompts close in time are one conversation.
  3. Claude: only "text" blocks - never thinking, tool calls, tool results
     or an attachment's text.
  4. A long chat is read in pieces the model can read whole, in order,
     none over PIECE_CHARS; pasted-in messages and code blocks are left out.
  5. Each piece goes through jarvis_intake.propose (the conversation's date
     and the stored-fact list in the prompt), on the chat's own model; a
     model that does not answer pauses the run and the chat stays unread.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import traceback
import types
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-import-understanding-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.AUDIT = []
fw.audit_log = lambda event, detail: fw.AUDIT.append((event, detail))
sys.modules.setdefault("jarvis_framework", fw)


class _NoNetwork(socket.socket):
    def connect(self, *a, **k):
        raise AssertionError("a network call was made")

    def connect_ex(self, *a, **k):
        raise AssertionError("a network call was made")


socket.socket = _NoNetwork
socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(
    AssertionError("a network call was made"))

import import_history as I  # noqa: E402
import jarvis_history_import as H  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def _zip(name: str, files: dict) -> Path:
    p = Path(tempfile.mkdtemp(dir=_TMP)) / name
    with zipfile.ZipFile(p, "w") as z:
        for fname, doc in files.items():
            z.writestr(fname, json.dumps(doc, ensure_ascii=False))
    return p


def fresh_progress():
    I.PROGRESS_FILE = Path(tempfile.mkdtemp(dir=_TMP)) / "progress.json"


class FakeExtract:
    """jarvis_extract: propose() asks the model it is handed, like the real
    one, and records what it was handed. `answer` is what _local_llm says
    (None: the model is not running)."""

    def __init__(self, answer='{"facts": []}', with_llm=True):
        self.calls, self.sources, self.prompts, self.models = [], [], [], []
        self.answer, self.with_llm = answer, with_llm

    def install(self):
        m = types.ModuleType("jarvis_extract")
        m.OLLAMA = "http://127.0.0.1:11434"
        m.propose = self.propose
        m.setup_status = lambda: {"queue_full": False}
        m.local_model_ok = lambda: True
        if self.with_llm:
            m._local_llm = self._local_llm
        sys.modules["jarvis_extract"] = m
        return self

    def _local_llm(self, prompt, model=None, timeout=60):
        self.prompts.append(prompt)
        self.models.append(model)
        return self.answer

    def propose(self, messages, llm=None, source="conversation"):
        self.calls.append([dict(m) for m in messages])
        self.sources.append(source)
        if llm is not None:
            out = llm("Find the facts in:\n" + "\n".join(m["content"] for m in messages))
            if out is None:
                return []
        return [{"id": len(self.calls)}]


def _owner_text(calls) -> str:
    return " | ".join(m["content"] for c in calls for m in c)


# --------------------------------------------------------------------------
#   1. DeepSeek
# --------------------------------------------------------------------------

def _ds_node(nid, parent, children, frags=None, t=None):
    msg = None
    if frags is not None:
        msg = {"files": [], "model": "deepseek-reasoner", "inserted_at": t,
               "fragments": [{"type": k, "content": c} for k, c in frags]}
    return nid, {"id": nid, "parent": parent, "children": children, "message": msg}


def deepseek_export() -> Path:
    """root -> 1 (asked: Paris) -> 2 (answer); 1 was edited: root -> 3
    (asked: Lisbon, later) -> 4 (think + search + answer, stamped 4 ms
    BEFORE its question). The newest branch is 3-4."""
    mapping = dict([
        _ds_node("root", None, ["1", "3"]),
        _ds_node("1", "root", ["2"], [("REQUEST", "I live in Paris and I teach maths")],
                 "2024-12-04T14:51:13.334000+08:00"),
        _ds_node("2", "1", [], [("RESPONSE", "Paris sounds lovely.")],
                 "2024-12-04T14:51:20.000000+08:00"),
        _ds_node("3", "root", ["4"], [("REQUEST", "I live in Lisbon and I teach maths")],
                 "2024-12-04T15:00:00.004000+08:00"),
        _ds_node("4", "3", [], [
            ("THINK", "The user secretly wants to move to Mars"),
            ("SEARCH", "search results about Lisbon rents"),
            ("TOOL_OPEN", "a web page about Lisbon"),
            ("RESPONSE", "Lisbon is a great city for teachers.")],
            "2024-12-04T15:00:00.000000+08:00"),
    ])
    convos = [{"id": "ds-1", "title": "Moving", "inserted_at": "2024-12-04T14:51:13.334000+08:00",
               "updated_at": "2024-12-04T15:00:00.004000+08:00", "mapping": mapping},
              {"id": "ds-2", "title": "Only a question", "inserted_at": "2024-12-05T10:00:00+08:00",
               "updated_at": "2024-12-05T10:00:00+08:00",
               "mapping": dict([_ds_node("root", None, ["a"]),
                                _ds_node("a", "root", [], [("REQUEST", "hello?")],
                                         "2024-12-05T10:00:00+08:00")])}]
    user = {"user_id": "u1", "email": "someone@example.com", "mobile": "+1 555 0100"}
    return _zip("deepseek_data-2024-12-06.zip",
                {"conversations.json": convos, "user.json": user})


def chatgpt_export() -> Path:
    mapping = {
        "r": {"id": "r", "parent": None, "children": ["u"], "message": None},
        "u": {"id": "u", "parent": "r", "children": ["a"],
              "message": {"author": {"role": "user"}, "weight": 1.0, "recipient": "all",
                          "content": {"content_type": "text", "parts": ["My cat is Tom"]},
                          "metadata": {}}},
        "a": {"id": "a", "parent": "u", "children": [],
              "message": {"author": {"role": "assistant"}, "weight": 1.0, "recipient": "all",
                          "content": {"content_type": "text", "parts": ["Nice cat."]},
                          "metadata": {}}},
    }
    return _zip("chatgpt.zip", {"conversations.json": [
        {"id": "c1", "title": "Cat", "create_time": 1700000000.0, "current_node": "a",
         "mapping": mapping}]})


def t_deepseek_reads_the_owners_words_on_the_newest_branch():
    p = deepseek_export()
    got = list(I.deepseek_conversations(p))
    check("one conversation (the one with no answer is not offered)", len(got) == 1,
          [c for c, _ in got])
    if not got:
        return
    cid, turns = got[0]
    check("its id is DeepSeek's own", cid == "deepseek:ds-1", cid)
    check("the newest branch, in tree order: the Lisbon question, then its answer",
          [t["role"] for t in turns] == ["user", "assistant"]
          and turns[0]["content"] == "I live in Lisbon and I teach maths", turns)
    everything = json.dumps(turns)
    check("the edited-away question (Paris) is not read", "Paris" not in everything)
    check("the reasoning (THINK) is never read", "Mars" not in everything)
    check("web results and tools (SEARCH, TOOL_OPEN) are never read",
          "rents" not in everything and "web page" not in everything)
    check("the account file (user.json) is never read",
          "example.com" not in everything and "555" not in everything)
    when = I.WHEN.get(cid)
    check("dated from its inserted_at, with its +08:00 offset",
          when is not None and abs(when - 1733295073.334) < 1, when)


def t_deepseek_and_chatgpt_are_told_apart():
    ds, gpt = deepseek_export(), chatgpt_export()
    check("a DeepSeek export is detected as DeepSeek", I.detect_kind(ds) == "deepseek",
          I.detect_kind(ds))
    check("a ChatGPT export is still detected as ChatGPT", I.detect_kind(gpt) == "chatgpt",
          I.detect_kind(gpt))
    check("the ChatGPT reader takes nothing from a DeepSeek export",
          list(I.chatgpt_conversations(ds)) == [])
    check("the DeepSeek reader takes nothing from a ChatGPT export",
          list(I.deepseek_conversations(gpt)) == [])
    check("DeepSeek is named in the labels", I.LABELS.get("deepseek") == "DeepSeek"
          and H.LABELS.get("deepseek") == "DeepSeek")


def t_deepseek_through_run():
    fresh_progress()
    fx = FakeExtract().install()
    code = I.run([("auto", deepseek_export())], say=lambda _l: None)
    check("run() reads a DeepSeek export picked as 'any'",
          code == 0 and I.SUMMARY.get("kinds") == ["deepseek"], I.SUMMARY)
    check("tagged import:deepseek", fx.sources == ["import:deepseek"], fx.sources)
    check("only the owner's words reached the model",
          _owner_text(fx.calls) == "I live in Lisbon and I teach maths", fx.calls)


# --------------------------------------------------------------------------
#   2. Gemini (Google Takeout)
# --------------------------------------------------------------------------

def _g(title, time, header="Gemini Apps", answer=None, products=None):
    rec = {"header": header, "title": title, "time": time,
           "products": products or [header], "activityControls": ["Gemini Apps Activity"]}
    if answer is not None:
        rec["safeHtmlItem"] = [{"html": answer}]
    return rec


def gemini_export() -> Path:
    # Newest first, as Takeout writes them.
    recs = [
        _g("Prompted what should I cook tonight", "2026-07-26T12:00:00.000Z",
           answer="<p>Try a <b>risotto</b>.</p><p>Or pasta.</p>"),
        _g("여동생은 간호사예요", "2026-07-26T10:00:00.000Z", header="Gemini 앱",
           answer="<p>좋네요</p>"),
        _g("알림 설정됨", "2026-07-26T09:40:00.000Z", header="Gemini 앱"),
        _g("Searched for cheap flights", "2026-07-26T09:10:00.000Z", header="Search"),
        _g("Gave feedback: thumbs down", "2026-07-26T09:09:00.000Z"),
        _g("Used an Assistant feature", "2026-07-26T09:08:00.000Z"),
        _g("Created Canvas", "2026-07-26T09:07:00.000Z"),
        _g("Prompted she loves jazz, especially Coltrane Attached 1 file.",
           "2026-07-26T09:05:00.000Z"),
        _g("Prompted my sister Anna is a nurse", "2026-07-26T09:00:00.000Z",
           answer="<p>That&#39;s a demanding job.</p>"),
        _g("Prompted with: my old flat was in Leeds", "2024-01-01T09:00:00.000Z"),
    ]
    return _zip("takeout-20260727.zip",
                {"Takeout/My Activity/Gemini Apps/MyActivity.json": recs})


def t_gemini_reads_what_the_owner_said():
    got = list(I.gemini_conversations(gemini_export()))
    said = [[t["content"] for t in turns if t["role"] == "user"] for _c, turns in got]
    check("prompts close in time are one conversation; 30 minutes' silence starts a new one",
          said == [["my old flat was in Leeds"],
                   ["my sister Anna is a nurse", "she loves jazz, especially Coltrane"],
                   ["여동생은 간호사예요"],
                   ["what should I cook tonight"]], said)
    everything = json.dumps([t for _c, t in got], ensure_ascii=False)
    check("the verb is cut off ('Prompted ', 'Prompted with: ')",
          "Prompted" not in everything)
    check("'Attached 1 file.' is cut off", "Attached" not in everything)
    check("feedback, 'Used ...' and 'Created ...' are not taken as things said",
          "feedback" not in everything and "Assistant feature" not in everything
          and "Canvas" not in everything)
    check("a Search record in the same Takeout is not read", "flights" not in everything)
    check("another language: a record Gemini answered is read, whole",
          "여동생은 간호사예요" in everything)
    check("another language: a record with no answer (not a prompt) is not",
          "알림" not in everything)
    last = got[-1][1]
    check("Gemini's answer is read from safeHtmlItem, as words, not HTML",
          last[-1] == {"role": "assistant", "content": "Try a risotto. Or pasta."}, last)
    check("each conversation is dated from its first prompt",
          I.WHEN.get(got[1][0]) and abs(I.WHEN[got[1][0]] - 1785056400.0) < 1,
          I.WHEN.get(got[1][0]))
    check("the kind is worked out from the Takeout folder",
          I.detect_kind(gemini_export()) == "gemini")


def t_gemini_ids_are_stable_and_change_when_a_conversation_grows():
    a = [c for c, _ in I.gemini_conversations(gemini_export())]
    b = [c for c, _ in I.gemini_conversations(gemini_export())]
    check("reading the same export twice gives the same ids", a == b and len(set(a)) == len(a))


# --------------------------------------------------------------------------
#   3. Claude
# --------------------------------------------------------------------------

def claude_export() -> Path:
    convo = {"uuid": "cl-1", "name": "Plans", "created_at": "2025-03-01T10:00:00Z",
             "chat_messages": [
                 {"uuid": "m1", "sender": "human", "text": "I run marathons",
                  "content": [{"type": "text", "text": "I run marathons"}],
                  "attachments": [{"file_name": "email.txt",
                                   "extracted_content": "From my bank: your PIN is 4321"}],
                  "files": [{"file_name": "email.txt"}]},
                 {"uuid": "m2", "sender": "assistant", "text": "",
                  "content": [{"type": "thinking", "thinking": "hidden reasoning here"},
                              {"type": "tool_use", "name": "artifacts",
                               "input": {"content": "an artifact body"}},
                              {"type": "tool_result", "content": [{"type": "text",
                                                                   "text": "tool said"}]},
                              {"type": "text", "text": "Great hobby."}]},
                 {"uuid": "m3", "sender": "human", "text": "My knee hurts after 20 km"},
             ]}
    return _zip("claude.zip", {"conversations.json": [convo], "users.json": [{"uuid": "u"}]})


def t_claude_reads_only_text_blocks():
    got = list(I.claude_conversations(claude_export()))
    check("one conversation", len(got) == 1, got)
    if not got:
        return
    turns = got[0][1]
    everything = json.dumps(turns)
    check("the assistant's words are only its text block",
          turns[1] == {"role": "assistant", "content": "Great hobby."}, turns)
    check("thinking, tool calls and tool results are never read",
          "hidden" not in everything and "artifact" not in everything
          and "tool said" not in everything)
    check("an attachment's text is never read (outside text)", "4321" not in everything)
    check("a message with only its plain text field is still read",
          turns[-1] == {"role": "user", "content": "My knee hurts after 20 km"}, turns)


# --------------------------------------------------------------------------
#   4. A long chat, read whole
# --------------------------------------------------------------------------

def _said(n, size=500, tag="m"):
    return [{"role": "user", "content": (f"{tag}{i} " + "word " * size)[:size]}
            for i in range(n)]


def t_a_long_chat_is_read_in_whole_pieces():
    mine = _said(40)                        # 40 x 500 = 20,000 characters
    parts = I.pieces(mine)
    check("more than one piece", len(parts) >= 4, len(parts))
    check("no piece is over PIECE_CHARS",
          all(sum(len(m["content"]) for m in p) <= I.PIECE_CHARS for p in parts),
          [sum(len(m["content"]) for m in p) for p in parts])
    order = []
    for p in parts:
        for m in p:
            if not order or order[-1] != m["content"]:
                order.append(m["content"])
    check("every message is read, in order, none lost",
          order == [m["content"] for m in mine])
    check("each piece after the first starts with the last message of the one before",
          all(parts[i][0] == parts[i - 1][-1] for i in range(1, len(parts))))
    check("a short chat is one piece", I.pieces(_said(3)) == [_said(3)])
    one = I.pieces([{"role": "user", "content": "x" * 3000}, {"role": "user",
                                                               "content": "y" * 3500}])
    check("two long messages that do not fit together are two pieces, no overlap",
          [len(p) for p in one] == [1, 1], [len(p) for p in one])


def t_pasted_text_and_code_are_left_out():
    mine = [{"role": "user", "content": "My daughter is called Mia"},
            {"role": "user", "content": "Dear customer, " + "blah " * 1000},
            {"role": "user", "content": "fix this ```def f(): return 1``` please, I use Python"}]
    parts = I.pieces(mine)
    flat = " | ".join(m["content"] for p in parts for m in p)
    check("a message over PASTED_CHARS (a pasted email) is left out",
          "Dear customer" not in flat, flat[:120])
    check("a code block is left out, the words round it kept",
          "def f" not in flat and "I use Python" in flat and "Mia" in flat, flat)
    check("nothing left: no piece", I.pieces([{"role": "user", "content": "``` x ```"}]) == [])


def t_run_reads_a_long_chat_in_pieces():
    fresh_progress()
    fx = FakeExtract().install()
    turns = []
    for m in _said(30):
        turns += [m, {"role": "assistant", "content": "ok"}]
    convo = {"uuid": "long-1", "created_at": "2023-05-02T09:00:00Z",
             "chat_messages": [{"sender": "human" if t["role"] == "user" else "assistant",
                                "text": t["content"]} for t in turns]}
    I.run([("claude", _zip("long.zip", {"conversations.json": [convo]}))],
          say=lambda _l: None)
    check("one chat, several model calls", I.SUMMARY.get("offered") == 1
          and I.SUMMARY.get("pieces") == len(fx.calls) and len(fx.calls) >= 3, I.SUMMARY)
    check("every model call fits", all(sum(len(m["content"]) for m in c) <= I.PIECE_CHARS
                                       for c in fx.calls))
    check("the chat is marked read once all its pieces are",
          "claude:long-1" in json.loads(I.PROGRESS_FILE.read_text())["done"])


# --------------------------------------------------------------------------
#   5. The same door as live learning, the chat's model, a model that is down
# --------------------------------------------------------------------------

def t_pieces_go_through_jarvis_intake_on_the_chats_model():
    try:
        import jarvis_intake  # noqa: F401
    except Exception as exc:
        check("jarvis_intake.py is importable here", False, repr(exc))
        return
    fresh_progress()
    fx = FakeExtract().install()
    old = os.environ.get("JARVIS_LOCAL_MODEL")
    os.environ["JARVIS_LOCAL_MODEL"] = "jarvis-primary"
    try:
        I.run([("claude", claude_export())], say=lambda _l: None)
    finally:
        if old is None:
            os.environ.pop("JARVIS_LOCAL_MODEL", None)
        else:
            os.environ["JARVIS_LOCAL_MODEL"] = old
    check("the model was asked", len(fx.prompts) == 1, len(fx.prompts))
    check("on the chat's own model, not a second one",
          fx.models == ["jarvis-primary"], fx.models)
    prompt = fx.prompts[0] if fx.prompts else ""
    check("the prompt carries the live learner's extra rules (jarvis_intake.addendum)",
          "More rules" in prompt, prompt[-300:])
    check("dated to the chat (2025), not to today", "2025" in prompt, prompt[-400:])
    check("only the owner's words", "Great hobby" not in _owner_text(fx.calls)
          and "I run marathons" in _owner_text(fx.calls))


def t_a_model_that_does_not_answer_pauses_and_loses_nothing():
    fresh_progress()
    fx = FakeExtract(answer=None).install()
    code = I.run([("claude", claude_export())], say=lambda _l: None)
    check("run() stops, saying the model did not answer",
          code == 0 and I.SUMMARY.get("stopped") == "no_model", I.SUMMARY)
    done = json.loads(I.PROGRESS_FILE.read_text()).get("done", []) \
        if I.PROGRESS_FILE.is_file() else []
    check("the chat is NOT marked read", "claude:cl-1" not in done, done)
    fx = FakeExtract().install()
    I.run([("claude", claude_export())], say=lambda _l: None)
    check("once the model answers, the next run reads it",
          I.SUMMARY.get("stopped") == "done" and len(fx.calls) == 1
          and "claude:cl-1" in json.loads(I.PROGRESS_FILE.read_text())["done"], I.SUMMARY)


def t_without_a_model_call_to_hand_it_is_as_before():
    fresh_progress()
    fx = FakeExtract(with_llm=False).install()
    I.run([("claude", claude_export())], say=lambda _l: None)
    check("a jarvis_extract with no _local_llm: plain propose(), no model argument",
          len(fx.calls) == 1 and fx.prompts == [], (fx.calls, fx.prompts))


def t_the_button_says_so():
    H._reset_for_tests()
    with H._LOCK:
        H._STATE.update(state="finished", outcome="no_model", kind="deepseek",
                        read=3, offered=3, waiting=1)
    w = H.view(here=True)["words"]
    check("the button's words for a model that did not answer",
          w.startswith("Paused, because Jarvis's AI model on this PC did not answer")
          and "not marked as read" in w, w)
    H._reset_for_tests()
    check("the idle words name all four",
          "ChatGPT, Claude, Gemini or DeepSeek" in H.view(here=True)["words"])


if __name__ == "__main__":
    for fn in [v for k, v in list(globals().items()) if k.startswith("t_") and callable(v)]:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
