"""test_notes_read_search.py - the chat's read & search half of the Obsidian work.

    python3 backend/test_notes_read_search.py

THE OWNER'S DECISION (2026-10-31, clicked): all three Obsidian abilities -
read & search, write & change, organize & tidy. This is the first half's proof:
deterministic, read-only, no card, no model, no new route.

Every fact here is driven through a THROWAWAY VAULT this suite writes itself,
so the answers are proved to come from bytes actually read - never from a
constant. It also pins the two rules that make the feature safe:
  * hidden lists / App lock: no title and no word of a note, ever;
  * the vault root and its hidden folders: no path outside it, no `.obsidian`.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parent

WORK = Path(tempfile.mkdtemp(prefix="jarvis-notes-read-"))
VAULT = WORK / "vault"
VAULT.mkdir(parents=True, exist_ok=True)
os.environ["JARVIS_OBSIDIAN_VAULT"] = str(VAULT)
os.environ["JARVIS_SCHEDULE_DB"] = str(WORK / "schedule.db")
os.environ["OPENJARVIS_HOME"] = str(WORK)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(WORK)

(WORK / "outside.md").write_text("outside needle-outside-secret", encoding="utf-8")
(WORK / ".obsidian").mkdir(exist_ok=True)
(VAULT / ".obsidian").mkdir(exist_ok=True)
(VAULT / ".obsidian" / "hidden.md").write_text("needle-hidden-word", encoding="utf-8")
(VAULT / "Welcome.md").write_text("Hello world.\nSecond line.", encoding="utf-8")
(VAULT / "Shopping.md").write_text("milk and eggs", encoding="utf-8")
(VAULT / "Long.md").write_text("A" * 5000, encoding="utf-8")
(VAULT / "Linked.md").write_text("about [Welcome](Welcome.md)", encoding="utf-8")
big = VAULT / "Huge.md"
with open(big, "wb") as f:
    f.write(b"B" * (2 * 1024 * 1024 + 1))

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok   " if cond else "FAIL ") + name
          + (("\n        " + detail) if detail and not cond else ""))


def _body(text):
    return {"messages": [{"role": "user", "content": text, "provenance": "typed"}],
            "conversation_id": "abcdefgh-notes"}


def main():
    import jarvis_schedule as SCH
    import jarvis_notes_edit as NE
    import jarvis_quick as Q
    import jarvis_private_view as PV
    sched = SCH.Scheduler(WORK / "schedule.db")

    def ask(text):
        return Q.answer_turn(_body(text), sched=sched)

    # --- 1. read one note: exact bytes, named title, bounded tail. ----------
    welcome = (VAULT / "Welcome.md").read_bytes().decode("utf-8")
    r = ask("what does my Welcome note say?")
    check("read: answers from the real bytes and names the note",
          r is not None and r.reply.startswith('"Welcome" says:')
          and welcome in r.reply,
          f"got {getattr(r, 'reply', None)!r}")
    r = ask("read my note Shopping")
    check("read: 'read my note <title>' reads the same note",
          r is not None and "milk and eggs" in r.reply, f"got {getattr(r, 'reply', None)!r}")
    r = ask("what is in my Long note?")
    check("read: bounded to 4000 chars and says how much is left",
          r is not None and "A" * 4000 in r.reply
          and "\u2026and 1000 more characters." in r.reply
          and "A" * 4001 not in r.reply,
          f"got len={len(getattr(r, 'reply', '') or '')}")
    r = ask("read my notes")
    check("read: many notes is refused in plain words",
          r is not None and r.reply == Q.NOTES_ONE_AT_A_TIME,
          f"got {getattr(r, 'reply', None)!r}")
    r = ask("what does my Nonexistent note say?")
    check("read: a missing note is an honest no-match, not a guess",
          r is not None and "could not find a note called" in r.reply,
          f"got {getattr(r, 'reply', None)!r}")

    # --- 2. hidden lists / App lock: no word, no title. -----------------------
    PV.note_state(app_locked=False, hide_memory_lists=True)
    try:
        r = ask("what does my Welcome note say?")
        check("hidden: read shows no title and no text",
              r is not None and r.reply == Q.NOTES_READ_HIDDEN
              and "Welcome" not in r.reply and "Hello" not in r.reply)
        r = ask("find my notes about milk")
        check("hidden: search gives counts only, never a title",
              r is not None and "1 note(s) match" in r.reply
              and "Shopping" not in r.reply and Q.NOTES_SEARCH_HIDDEN in r.reply,
              f"got {getattr(r, 'reply', None)!r}")
        r = ask("open my Welcome note")
        check("hidden: open shows no title either",
              r is not None and r.reply == Q.NOTES_READ_HIDDEN)
    finally:
        PV.note_state(app_locked=False, hide_memory_lists=False)

    # --- 3. search: title matches first, then bounded content, no bodies. ---
    r = ask("find my notes about milk")
    check("search: a content match is reported by title, without the body",
          r is not None and "Shopping" in r.reply and "milk and eggs" not in r.reply,
          f"got {getattr(r, 'reply', None)!r}")
    r = ask("search my notes for Hello")
    check("search: content matching works on another note too",
          r is not None and "Welcome" in r.reply)
    r = ask("which notes mention nonexistent-word")
    check("search: no match says so, and where the real search lives",
          r is not None and "No notes in your vault match" in r.reply
          and "notes editor" in r.reply,
          f"got {getattr(r, 'reply', None)!r}")
    r = ask("search my notes for needle-hidden-word")
    check("search: a dot-folder note is never read",
          r is not None and "No notes in your vault match" in r.reply)
    r = ask("search my notes for needle-outside-secret")
    check("search: a file outside the vault is never read",
          r is not None and "No notes in your vault match" in r.reply)

    # --- 4. open one note: the existing Brain/Notes door, one line where. ---
    r = ask("open my Welcome note")
    check("open: names the note and the existing Brain/Notes door",
          r is not None and "Welcome" in r.reply and "Brain" in r.reply
          and "Notes" in r.reply,
          f"got {getattr(r, 'reply', None)!r}")
    check("open: the existing open_brain route field is set",
          r is not None and getattr(r, "open_brain", None) == "brain",
          f"got {getattr(r, 'open_brain', None)!r}")

    # --- 5. the module refuses paths it must never read. --------------------
    for query, why in (
        ("?path=../outside.md", "a climbing path"),
        ("?path=C:/Windows/win.ini", "an absolute path"),
        ("?path=.obsidian/hidden.md", "a dot-folder path"),
    ):
        code, body = NE.handle_read(query)
        check(f"refuse: {why} is not read", code in (400, 403),
              f"got {code} {body}")
    code, found = NE.chat_read_note("Huge")
    check("refuse: a note over the 2 MiB cap is refused in words",
          code == 413 and bool(found.get("said")), f"got {code} {found}")
    code, found = NE.chat_find_notes("Welcome")
    check("reader: title matching comes from the one list reader",
          code == 200 and [n["title"] for n in found["matches"]] == ["Welcome"])

    # --- 6. over-capture: ordinary chat keeps the model's path. -------------
    note_marks = ('\" says:', "note(s) match", "No notes in your vault match",
                  "could not find a note", Q.NOTES_ONE_AT_A_TIME)
    for text in ("read my email", "read my mind", "what is the weather",
                 "open my email", "find my emails about milk"):
        got = ask(text)
        reply = getattr(got, "reply", None) or ""
        check(f"over-capture: {text!r} is not answered by the notes door",
              all(mark not in reply for mark in note_marks),
              f"got {reply!r}")

    # --- 7. the twin is byte-identical. ------------------------------------
    for name in ("jarvis_notes_edit.py", "jarvis_quick.py"):
        a = (REPO / "backend" / name).read_bytes()
        b = (REPO / "jarvis-backend" / name).read_bytes()
        check(f"twin: {name} is identical in both copies", a == b)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        FAILED.append("the suite itself raised")
    print()
    if FAILED:
        print(f"{len(PASSED)} passed, {len(FAILED)} FAILED")
        for name in FAILED:
            print(f"  FAIL {name}")
        sys.exit(1)
    print(f"{len(PASSED)} passed, 0 failed")
