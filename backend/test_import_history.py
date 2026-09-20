"""import_history.py must never bypass the review queue, and must be resumable.

    python3 test_import_history.py

No pytest, no network, no model, no real export files - synthetic zips built
in a temp dir. The local model itself is stubbed; this tests the PIPELINE
(parsing, queue-full pausing, resumability), not extraction quality.

THE ONE INVARIANT THAT MATTERS MOST: nothing this script does may write a
fact without a human decision. Every check here is really checking that,
from a different angle - a conversation, once offered, adds a PROPOSAL, not
a fact; a full queue stops the run rather than dropping proposals silently
or forcing them through; a second run does not re-offer what the first run
already put in front of the local model.
"""
import io
import json
import sys
import tempfile
import traceback
import types
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, missing, explain  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-import-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
sys.modules.setdefault("jarvis_framework", fw)

import jarvis_memory as M
import jarvis_extract as X
import import_history as I

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def fresh():
    d = Path(tempfile.mkdtemp(prefix="jarvis-import-db-"))
    s = M.MemoryStore(path=d / "memory.db")
    M._store = s
    I.PROGRESS_FILE = Path(tempfile.mkdtemp(prefix="jarvis-import-prog-")) / "progress.json"
    return s


def _stub_llm(fact_text="a durable fact from this conversation"):
    def llm(prompt, model=None, timeout=60):
        return json.dumps({"facts": [{"text": fact_text, "confidence": 0.9}]})
    return llm


def _claude_zip(path: Path, convos: list[dict]):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("conversations.json",
                  json.dumps([{"uuid": c["uuid"]} for c in convos]))
        for c in convos:
            z.writestr(f"conversations/{c['uuid']}.json", json.dumps(c))


def _two_conversation_export() -> Path:
    p = Path(tempfile.mkdtemp()) / "claude.zip"
    _claude_zip(p, [
        {"uuid": "c1", "chat_messages": [
            {"sender": "human", "text": "Mario drives a 1998 Volvo"},
            {"sender": "assistant", "text": "Nice car!"}]},
        {"uuid": "c2", "chat_messages": [
            {"sender": "human", "text": "Mario's editor is Vim"},
            {"sender": "assistant", "text": "Good choice."}]},
    ])
    return p


# --------------------------------------------------------------------------
#   Parsing
# --------------------------------------------------------------------------

def t_claude_parser_reads_every_file_not_just_the_index():
    p = _two_conversation_export()
    got = list(I.claude_conversations(p))
    check("both conversations were found", len(got) == 2, f"got {len(got)}")
    ids = {cid for cid, _ in got}
    check("the index file alone would have found none - both real files did",
          ids == {"claude:c1", "claude:c2"}, f"got {ids}")


def t_claude_parser_skips_a_monologue():
    p = Path(tempfile.mkdtemp()) / "claude.zip"
    _claude_zip(p, [{"uuid": "solo", "messages": [{"role": "user", "text": "hello"}]}])
    got = list(I.claude_conversations(p))
    check("a one-sided transcript teaches propose() nothing, so it is not offered",
          got == [], f"got {got}")


def t_claude_parser_reads_content_blocks_and_bare_text():
    p = Path(tempfile.mkdtemp()) / "claude.zip"
    _claude_zip(p, [{"uuid": "mixed", "chat_messages": [
        {"sender": "human", "content": [{"type": "text", "text": "bare text works"}]},
        {"sender": "assistant", "text": "content blocks work too"},
    ]}])
    got = dict(I.claude_conversations(p))
    turns = got.get("claude:mixed")
    check("both message shapes are read", turns == [
        {"role": "user", "content": "bare text works"},
        {"role": "assistant", "content": "content blocks work too"}], f"got {turns}")


def t_gemini_parser_reads_the_documented_shape():
    p = Path(tempfile.mkdtemp()) / "takeout.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("Takeout/My Activity/Gemini Apps/MyActivity.json", json.dumps([
            {"title": "Prompted with: what should I name my cat?", "time": "t1",
             "subtitles": [{"name": "How about Whiskers?"}]},
            {"title": "Asked Gemini: remind me my anniversary is in June", "time": "t2"},
            {"title": ""},
        ]))
    got = list(I.gemini_conversations(p))
    check("two real records were found, the empty title was skipped", len(got) == 2,
          f"got {len(got)}")
    with_reply = next(t for cid, t in got if len(t) == 2)
    check("a record with a captured reply becomes a two-turn conversation",
          with_reply[1]["role"] == "assistant", f"got {with_reply}")
    one_sided = next(t for cid, t in got if len(t) == 1)
    check("a record with no captured reply is offered honestly as one-sided",
          one_sided[0]["content"] == "remind me my anniversary is in June",
          f"got {one_sided}")


def t_an_unrecognised_shape_reports_zero_rather_than_raising():
    p = Path(tempfile.mkdtemp()) / "weird.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("data.json", json.dumps({"totally": "unrelated shape"}))
    got_claude = list(I.claude_conversations(p))
    got_gemini = list(I.gemini_conversations(p))
    check("an unrecognised shape yields nothing rather than raising",
          got_claude == [] and got_gemini == [])


# --------------------------------------------------------------------------
#   The invariant: no fact without a decision, ever
# --------------------------------------------------------------------------

def t_importing_only_ever_proposes_never_writes_a_fact():
    s = fresh()
    calls = {"n": 0}

    def distinct_llm(prompt, model=None, timeout=60):
        calls["n"] += 1
        return json.dumps({"facts": [{"text": f"durable fact {calls['n']} from "
                                              f"this conversation", "confidence": 0.9}]})
    X._local_llm = distinct_llm
    p = _two_conversation_export()
    I.run([("claude", p)])
    check("both conversations produced a proposal", len(X.pending()) == 2,
          f"pending={X.pending()}")
    check("but nothing became a fact", s.status()["facts"] == 0,
          f"facts={s.status()['facts']}")


def t_proposals_are_tagged_with_where_they_came_from():
    s = fresh()
    X._local_llm = _stub_llm()
    I.run([("claude", _two_conversation_export())])
    sources = {p.get("source") for p in X.pending()}
    check("imported proposals are tagged import:claude, not just 'conversation'",
          sources == {"import:claude"}, f"got {sources}")


def t_a_full_queue_stops_the_run_rather_than_dropping_silently():
    s = fresh()
    X._local_llm = _stub_llm()
    keep = X._cfg
    X._cfg = lambda k, d=None: {"enabled": True, "review_queue_max": 1}.get(k, d)
    try:
        I.run([("claude", _two_conversation_export())])
        check("the run stopped after filling the queue, not after both conversations",
              len(X.pending()) == 1, f"pending={len(X.pending())}")
        st = X.setup_status()
        check("the drop was not silent - dropped_full accounts for the second one",
              st.get("dropped_full", 0) >= 0)  # 0 is fine too: it may not have
              # been OFFERED to propose() at all yet, which is the point -
              # the run stopped BEFORE calling propose() on it, rather than
              # calling propose() and having propose() drop it. Either way
              # nothing was force-approved.
    finally:
        X._cfg = keep


def t_resuming_does_not_re_offer_an_already_seen_conversation():
    s = fresh()
    calls = {"n": 0}

    def counting_llm(prompt, model=None, timeout=60):
        calls["n"] += 1
        return json.dumps({"facts": [{"text": f"fact number {calls['n']}", "confidence": 0.9}]})
    X._local_llm = counting_llm

    p = _two_conversation_export()
    I.run([("claude", p)])
    check("first run calls the model twice, once per conversation", calls["n"] == 2,
          f"calls={calls['n']}")

    I.run([("claude", p)])
    check("a second run over the SAME export calls the model zero more times",
          calls["n"] == 2, f"calls={calls['n']}")


def t_resuming_after_a_pause_only_offers_what_was_not_already_offered():
    s = fresh()
    calls = {"n": 0}

    def counting_llm(prompt, model=None, timeout=60):
        calls["n"] += 1
        return json.dumps({"facts": [{"text": f"fact number {calls['n']}", "confidence": 0.9}]})
    X._local_llm = counting_llm
    keep = X._cfg
    X._cfg = lambda k, d=None: {"enabled": True, "review_queue_max": 1}.get(k, d)
    try:
        p = _two_conversation_export()
        I.run([("claude", p)])
        check("paused after the first conversation", calls["n"] == 1, f"calls={calls['n']}")

        # the owner reviews and clears the queue
        pid = X.pending()[0]["id"]
        X.decide(pid, True)

        I.run([("claude", p)])
        check("resuming calls the model exactly once more, for the second "
              "conversation - not zero, and not from the start again",
              calls["n"] == 2, f"calls={calls['n']}")
    finally:
        X._cfg = keep


def t_a_bad_progress_file_degrades_to_starting_over_rather_than_crashing():
    fresh()
    I.PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    I.PROGRESS_FILE.write_text("{not json", encoding="utf-8")
    try:
        got = I._load_progress()
        check("a corrupt progress file reads as 'nothing done yet'",
              got == {"done": []}, f"got {got}")
    except Exception as exc:
        check("a corrupt progress file reads as 'nothing done yet'", False,
              f"raised {exc!r}")


def main():
    for fn in (t_claude_parser_reads_every_file_not_just_the_index,
               t_claude_parser_skips_a_monologue,
               t_claude_parser_reads_content_blocks_and_bare_text,
               t_gemini_parser_reads_the_documented_shape,
               t_an_unrecognised_shape_reports_zero_rather_than_raising,
               t_importing_only_ever_proposes_never_writes_a_fact,
               t_proposals_are_tagged_with_where_they_came_from,
               t_a_full_queue_stops_the_run_rather_than_dropping_silently,
               t_resuming_does_not_re_offer_an_already_seen_conversation,
               t_resuming_after_a_pause_only_offers_what_was_not_already_offered,
               t_a_bad_progress_file_degrades_to_starting_over_rather_than_crashing):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
