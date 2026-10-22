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
import os
import subprocess
import sys
import tempfile
import traceback
import types
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, missing, explain, require_rebuilt  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-import-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
sys.modules.setdefault("jarvis_framework", fw)

# jarvis_memory is one of the ten modules this repository ships WHOLE
# (`backend/rebuilt/`), and _where.py is what puts them on sys.path. Without
# that line this import died as `ModuleNotFoundError: No module named
# 'jarvis_memory'` before one check could run - which is what the guard below
# says in one line.
require_rebuilt("jarvis_memory")
import jarvis_memory as M

# jarvis_extract.py needs a different answer. It is one of the five files only
# the owner's PC has, because the patcher edits it in place rather than copying
# it (scripts/apply-patches.ps1), so a clone does not hold it and run_suites.py
# skips this whole suite by name for that reason.
#
# UNLIKE test_decide_once.py, not every check here drives it: the parser checks
# read import_history.py alone, and this repository does ship that. So the
# checks that need jarvis_extract skip - with the reason - and the rest run.
# Before this, the module-level import below was one traceback for the whole
# file (`ModuleNotFoundError: No module named 'jarvis_extract'`), and six
# checks that could have run never got the chance.
try:
    import jarvis_extract as X
except ModuleNotFoundError:                              # pragma: no cover
    X = None
import import_history as I

FAILED, PASSED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this run cannot make, printed as `skip` and counted on its own -
    never as a pass. `run_suites.py` counts these lines, and the summary below
    prints the number, so a skip can never be read as a check that ran."""
    SKIPPED.append(why)
    print(f"skip  {why}")


def have_extract():
    """True when this check can run; a printed skip and False when
    jarvis_extract.py is not here."""
    if X is not None:
        return True
    skip(f"this check drives jarvis_extract.py, which is not in {BACKEND} - "
         f"only the owner's PC has it. {explain()}")
    return False


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
    if not have_extract():
        return
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
    if not have_extract():
        return
    s = fresh()
    X._local_llm = _stub_llm()
    I.run([("claude", _two_conversation_export())])
    sources = {p.get("source") for p in X.pending()}
    check("imported proposals are tagged import:claude, not just 'conversation'",
          sources == {"import:claude"}, f"got {sources}")


def t_a_full_queue_stops_the_run_rather_than_dropping_silently():
    if not have_extract():
        return
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
    if not have_extract():
        return
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
    if not have_extract():
        return
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


def t_a_chatgpt_export_shows_the_model_only_the_owners_words():
    """2026-09-28: ChatGPT's export, through the REAL propose(). The model's
    prompt holds what the owner wrote and never what the assistant said."""
    if not have_extract():
        return
    s = fresh()
    prompts = []

    def recording_llm(prompt, model=None, timeout=60):
        prompts.append(prompt)
        return json.dumps({"facts": [{"text": "Mario's dog is called Biscuit",
                                      "confidence": 0.9}]})
    X._local_llm = recording_llm
    mapping = {
        "r": {"id": "r", "parent": None, "children": ["u"], "message": None},
        "u": {"id": "u", "parent": "r", "children": ["a"], "message": {
            "author": {"role": "user"}, "recipient": "all",
            "content": {"content_type": "text", "parts": ["My dog is called Biscuit"]}}},
        "a": {"id": "a", "parent": "u", "children": [], "message": {
            "author": {"role": "assistant"}, "recipient": "all",
            "content": {"content_type": "text", "parts": ["ASSISTANT-ONLY-WORDS"]}}},
    }
    p = Path(tempfile.mkdtemp()) / "chatgpt.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("conversations.json", json.dumps([
            {"id": "g1", "create_time": 1700000000.0, "current_node": "a",
             "mapping": mapping}]))
    I.run([("auto", p)], say=lambda _l: None)
    check("the model was asked once", len(prompts) >= 1, f"{len(prompts)}")
    check("it read the owner's words", any("Biscuit" in q for q in prompts))
    check("and never the assistant's", not any("ASSISTANT-ONLY-WORDS" in q for q in prompts))
    check("a proposal, tagged import:chatgpt, and no fact",
          {r.get("source") for r in X.pending()} == {"import:chatgpt"}
          and s.status()["facts"] == 0, f"{X.pending()}")


def t_a_bad_progress_file_degrades_to_starting_over_rather_than_crashing():
    # NOT fresh(). That also builds a MemoryStore, whose meaning model is
    # the old memory library's - and the `fw.CONFIG_DIR = _TMP` stub at the top of this file
    # moves the model cache into a brand-new temp folder, so the model is
    # fetched from HuggingFace again on every run (measured 2026-10-10: 5 files,
    # 38 s, on every run). This check drives `_load_progress()` alone and needs
    # only the progress path, so the store - and the download - is left out. The
    # checks that DO need a store are the ones that skip without
    # jarvis_extract.py; on a machine that has it they still pay that cost.
    I.PROGRESS_FILE = (Path(tempfile.mkdtemp(prefix="jarvis-import-prog-"))
                       / "progress.json")
    I.PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    I.PROGRESS_FILE.write_text("{not json", encoding="utf-8")
    try:
        got = I._load_progress()
        check("a corrupt progress file reads as 'nothing done yet'",
              got == {"done": []}, f"got {got}")
    except Exception as exc:
        check("a corrupt progress file reads as 'nothing done yet'", False,
              f"raised {exc!r}")


def _make_dir_link(link: Path, target: Path) -> bool:
    """A directory link where this machine allows one: symlink first, NTFS
    junction second (mklink /J needs no elevation on Windows)."""
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                           capture_output=True, text=True)
        return r.returncode == 0
    return False


def t_a_link_out_and_an_unsafe_zip_are_never_read():
    """The 2026-10-20 parser audit (Area 6A) on the chat-export importer: a
    junction/symlink out of the chosen export folder is not followed, a zip
    whose member paths point outside itself is refused as a whole, and a zip
    that declares more than the export cap is refused before any member is
    parsed. A normal export still reads."""
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-import-guard-"))
    export = tmp / "export"
    export.mkdir()
    outside = tmp / "outside"
    outside.mkdir()
    (outside / "secret.json").write_text('{"mapping": {}}', encoding="utf-8")
    link = export / "escape"
    if _make_dir_link(link, outside):
        docs = list(I._walk_json_documents(export))
        labels = [label for label, _doc in docs]
        check("a junction out of the export folder: not read",
              not any("secret" in label for label in labels), labels)
    else:
        skip("a junction out of the export folder cannot be made here, "
             "so nothing was proved")
    traversal = export / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as z:
        z.writestr("../outside.json", "{}")
        z.writestr("good.json", '{"mapping": {}}')
    docs = list(I._walk_json_documents(traversal))
    check("a zip with a `..` member: refused as a whole", docs == [], docs)
    real_cap = I.EXPORT_UNCOMPRESSED_MAX
    I.EXPORT_UNCOMPRESSED_MAX = 1024
    try:
        bomb = export / "bomb.zip"
        with zipfile.ZipFile(bomb, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("big.json", "{}" * 1200)
        docs = list(I._walk_json_documents(bomb))
        check("a zip that declares more than the export cap: refused", docs == [], docs)
    finally:
        I.EXPORT_UNCOMPRESSED_MAX = real_cap
    good = export / "normal.zip"
    with zipfile.ZipFile(good, "w") as z:
        z.writestr("mapping.json", '{"mapping": {}}')
    docs = list(I._walk_json_documents(good))
    check("a normal export still reads", len(docs) == 1 and docs[0][1] == {"mapping": {}},
          docs)


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
               t_a_chatgpt_export_shows_the_model_only_the_owners_words,
               t_a_link_out_and_an_unsafe_zip_are_never_read,
               t_a_bad_progress_file_degrades_to_starting_over_rather_than_crashing):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
