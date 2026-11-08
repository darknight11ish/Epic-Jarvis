"""test_folders_chat.py - "Folders Jarvis may look in" through chat (Wave 8.2).

    python -B backend/test_folders_chat.py

The owner asked for total awareness and for changing almost everything by
chat / Jarvis Live (2026-11-07). The folder list was the one place his words
had no door: he could not add a folder from chat and could not ask which
folders were allowed. These checks pin both halves:

  - the LIST question ("which folders may you look in?") is answered from
    `jarvis_documents.folders()` with no model and no card, in an ordinary and
    a PRIVATE chat (a private chat must not hand a local read to the model);
  - the ADD sentence ("add my downloads folder to the folders jarvis may look
    in", "let jarvis look in ...", or an explicit path) resolves the everyday
    folder names and reaches jarvis_documents.request_add - the SAME function
    the PC route uses - so it is PC-only and raises the same ONE approval card;
    nothing is added until that card is approved;
  - a refusal from the real function is relayed verbatim (phone-only refusal,
    an already-listed folder, a bad path), never reworded into a claim;
  - near misses keep their own owners: "add milk to my shopping list" is the
    to-do list, "what folders are restricted?" is the protection answer, and
    "open downloads" is not this door.

Hermetic: its own temp OPENJARVIS_HOME / config / schedule db; the documents
module and the request function are injected, so no real folder is added, no
card is raised and the owner's own list is never read or written.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-folders-chat-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_SCHEDULE_DB"] = str(_TMP / "schedule.db")
_HOME = _TMP / "home"
_HOME.mkdir(parents=True, exist_ok=True)
os.environ["OPENJARVIS_HOME"] = str(_HOME)
os.environ["JARVIS_HOME"] = str(_HOME)

import jarvis_documents as D  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_schedule as S  # noqa: E402

PASSED, FAILED = [], []


def check(name: str, ok: bool, detail=None) -> None:
    if ok:
        PASSED.append(name)
        print(f"ok    {name}")
    else:
        FAILED.append(name)
        print(f"FAIL  {name}" + (f" | {detail!r}" if detail is not None else ""))


def _require_own_home() -> None:
    home = os.environ.get("OPENJARVIS_HOME") or ""
    try:
        same = bool(home) and Path(home).resolve() == _HOME.resolve()
    except OSError:
        same = False
    if not same:
        print("FAIL  the suite's OPENJARVIS_HOME is not its own temp folder")
        sys.exit(1)


def _ran(sentence: str, sched=None, **kw):
    sched = sched or S.get()
    intent = Q.match(sentence)
    if intent is None:
        return None
    return Q.run(intent, sched, time.time(), **kw)


def t_the_list_question_is_answered_from_the_module():
    sched = S.get()
    for sentence in ("which folders may you look in?",
                     "what folders can you look in",
                     "list your folders"):
        m = Q.match(sentence)
        check(f"{sentence!r} is the folder-list answer",
              m is not None and m.name == "folder_list", m)

    old = D.folders
    try:
        D.folders = lambda: []
        r = _ran("which folders may you look in?", sched)
        check("an empty list says so honestly and names where adding happens",
              r is not None and r.intent == "folder_list"
              and "no folders yet" in r.reply.lower()
              and "settings" in r.reply.lower(),
              None if r is None else r.reply[:180])
        D.folders = lambda: ["C:\\Users\\pcadmin\\Documents"]
        r = _ran("which folders may you look in?", sched)
        check("a real list is named, with the card rule",
              r is not None and "C:\\Users\\pcadmin\\Documents" in r.reply
              and "card" in r.reply.lower(),
              None if r is None else r.reply[:200])
    finally:
        D.folders = old

    # A private chat answers this local read itself, never the model.
    private = Q.answer("which folders may you look in?", private=True, sched=sched)
    check("a private chat answers the list from local code",
          private is not None and private.intent == "folder_list",
          None if private is None else (private.intent, private.reply[:120]))


def t_the_add_sentence_reaches_the_real_request_add():
    sched = S.get()
    downloads = os.path.expanduser("~/Downloads")
    for sentence, want in (
            ("add my downloads folder to the folders jarvis may look in", downloads),
            ("let jarvis look in my downloads folder", downloads),
            ("add C:/Users/pcadmin/Downloads to the folders jarvis may look in",
             "C:/Users/pcadmin/Downloads")):
        m = Q.match(sentence)
        check(f"{sentence!r} resolves the folder it means",
              m is not None and m.name == "folder_add"
              and m.f.get("path") == want, None if m is None else (m.name, m.f))

    seen = {}

    def fake_request_add(body, *, peer=None, local=None):
        seen["body"], seen["peer"], seen["local"] = body, peer, local
        return 202, {"ok": True, "waiting": True,
                     "message": "Waiting for your approval. Nothing is added unless "
                                "you approve the card."}

    old = D.request_add
    try:
        D.request_add = fake_request_add
        r = _ran("add my downloads folder to the folders jarvis may look in", sched,
                 peer="127.0.0.1", local=True)
        check("the chat door calls jarvis_documents.request_add with the real path",
              seen.get("body") == {"path": downloads} and seen.get("local") is True,
              seen)
        check("... and relays 'waiting for your approval', never 'it was added'",
              r is not None and r.intent == "folder_add"
              and "waiting for your approval" in r.reply.lower()
              and "nothing is added" in r.reply.lower(),
              None if r is None else r.reply[:200])

        D.request_add = lambda body, **kw: (403, {"ok": False, "error": D.PC_ONLY,
                                                  "pc_only": True})
        refused = _ran("add my downloads folder to the folders jarvis may look in",
                       sched, peer="100.75.21.228", local=False)
        check("a phone ask gets the PC-only refusal, relayed",
              refused is not None and D.PC_ONLY in refused.reply,
              None if refused is None else refused.reply[:200])

        D.request_add = lambda body, **kw: (200, {
            "ok": True, "changed": False,
            "message": "That folder is already on the list."})
        already = _ran("add my downloads folder to the folders jarvis may look in",
                       sched, local=True)
        check("an already-listed folder says so", already is not None
              and "already on the list" in already.reply.lower(),
              None if already is None else already.reply[:160])
    finally:
        D.request_add = old

    m = Q.match("add it somewhere to the folders jarvis may look in")
    r = Q.run(m, sched, time.time(), local=True) if m is not None else None
    check("an unresolvable folder asks which one instead of guessing",
          m is not None and (m.f or {}).get("ask") is True
          and r is not None and "which folder" in r.reply.lower(),
          None if m is None else (m.f, r and r.reply[:120]))


def t_the_read_and_the_action_are_marked_right():
    check("folder_list is a read-only intent (it must not clear 'cancel that')",
          "folder_list" in Q.READ_ONLY_INTENTS)
    check("folder_list is answered in a private chat from local code",
          "folder_list" in Q._PRIVATE_DETERMINISTIC_READS)
    check("folder_add is NOT read-only - it mutates the owner's list",
          "folder_add" not in Q.READ_ONLY_INTENTS)
    sched = S.get()
    private = Q.answer("add my downloads folder to the folders jarvis may look in",
                       private=True, sched=sched)
    check("a private chat refuses the add like every other mutation",
          private is not None and private.intent == "folder_add"
          and private.reply != "",
          None if private is None else (private.intent, private.reply[:140]))


def t_near_misses_keep_their_owners():
    for sentence, not_this in (
            ("add milk to my shopping list", "folder_add"),
            ("what folders are restricted?", "folder_list"),
            ("open downloads", "folder_add"),
            ("what folders do you have", "folder_add")):
        m = Q.match(sentence)
        check(f"{sentence!r} is not the folder door",
              m is None or m.name != not_this, m)
    m = Q.match("add milk to my shopping list")
    check("'add milk to my shopping list' is still the to-do list",
          m is not None and m.name == "todo_add", m)


def main() -> int:
    _require_own_home()
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:  # pragma: no cover
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, repr(exc))
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
