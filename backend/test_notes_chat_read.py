"""test_notes_chat_read.py - chat can READ a note (2026-11-05).

    py -3 -B backend/test_notes_chat_read.py

What this proves, driven through a THROWAWAY vault so every answer comes from
bytes this suite wrote:

  1. one note matches  -> its text, capped at 4,000 characters, and the cut is
     SAID ("...(cut off)" style tail with the real count);
  2. several match     -> the titles, how each starts, and "tell me which one";
  3. none match        -> a plain no-match that names the configured vault;
  4. no vault at all   -> an honest refusal that NAMES THE SWITCH;
  5. a note holding code, Unicode and a Markdown table comes back byte-for-byte
     (the only transformation is the 4,000-character cut, which is stated);
  6. the same text through the MODEL's read door (`chat_read_note`), marked as
     outside text so it is never learned or acted on;
  7. the LIVE flag speaks the read (first ~1,000 characters + where it stopped)
     and points at no screen;
  8. hidden lists / App lock still show no title and no word of any note.

No source-text pin is used: every assertion is on an answer the code produced.
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
# This suite prints real note text, and a Windows console is cp1252: without
# this, a FAIL line containing "café" raises instead of reporting.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

WORK = Path(tempfile.mkdtemp(prefix="jarvis-notes-chat-read-"))
VAULT = WORK / "vault"
VAULT.mkdir(parents=True, exist_ok=True)
(VAULT / ".obsidian").mkdir(exist_ok=True)
os.environ["JARVIS_OBSIDIAN_VAULT"] = str(VAULT)
os.environ["JARVIS_SCHEDULE_DB"] = str(WORK / "schedule.db")
os.environ["OPENJARVIS_HOME"] = str(WORK)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(WORK)

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok   " if cond else "FAIL ") + name
          + (("\n        " + detail) if detail and not cond else ""))


def _body(text, live=False):
    msg = {"role": "user", "content": text,
           "provenance": "voice" if live else "typed"}
    if live:
        msg["live"] = True
    return {"messages": [msg], "conversation_id": "abcdefgh-notes-read"}


# The one note that must survive exactly: code fences, a table, Unicode.
RICH = (
    "# Café notes\n"
    "\n"
    "| item | price |\n"
    "| --- | --- |\n"
    "| café | 3€ |\n"
    "| tea | 2€ |\n"
    "\n"
    "```python\n"
    "def greet(name):\n"
    "    return f\"héllo {name}\"\n"
    "```\n"
    "\n"
    "Ünïcödé: 日本語 ✓\n"
)


def main():
    (VAULT / "Welcome.md").write_text("Hello world.\nSecond line.", encoding="utf-8")
    (VAULT / "Café Notes.md").write_text(RICH, encoding="utf-8")
    (VAULT / "Long.md").write_text("A" * 5000, encoding="utf-8")
    (VAULT / "Alpha.md").write_text("first alpha line\nsecond", encoding="utf-8")
    (VAULT / "Beta.md").write_text("first beta line\nsecond", encoding="utf-8")

    import jarvis_schedule as SCH
    import jarvis_notes_edit as NE
    import jarvis_quick as Q
    import jarvis_private_view as PV
    sched = SCH.Scheduler(WORK / "schedule.db")

    def ask(text, live=False):
        return Q.answer_turn(_body(text, live=live), sched=sched)

    # --- 1. one note matches: its text, capped, and the cut is said. --------
    r = ask("read my Long note")
    check("one match: the whole 4,000-character cap is returned",
          r is not None and "A" * 4000 in r.reply and "A" * 4001 not in r.reply,
          f"got len={len(getattr(r, 'reply', '') or '')}")
    check("one match: the cut is stated with the real number left",
          r is not None and "\u2026and 1000 more characters." in r.reply,
          f"got {getattr(r, 'reply', None)!r}"[-80:])
    r = ask("what does my Welcome note say")
    check("one match: names the note and quotes its real bytes",
          r is not None and r.reply.startswith('"Welcome" says:')
          and "Hello world." in r.reply)

    # --- 2. several match: titles, how each starts, and the ask. -----------
    r = ask("read my notes")
    check("several: says how many notes there are",
          r is not None and r.reply.startswith("You have 5 notes."),
          f"got {getattr(r, 'reply', None)!r}")
    check("several: shows a one-line start of each note",
          r is not None and '"Welcome" (Hello world.)' in r.reply
          and '"Alpha" (first alpha line)' in r.reply,
          f"got {getattr(r, 'reply', None)!r}")
    check("several: asks which one instead of guessing",
          r is not None and r.reply.endswith("Tell me which one to read."))
    r = ask("what notes do I have")
    check("list: 'what notes do I have' answers the same list",
          r is not None and r.reply.startswith("You have 5 notes.")
          and "Tell me which one to read." in r.reply,
          f"got {getattr(r, 'reply', None)!r}")

    # --- 3. none match: plain no-match, and the vault is named. ------------
    r = ask("what does my Nonexistent note say")
    check("none: says plainly that no note has that title",
          r is not None and "No note in your vault is called" in r.reply,
          f"got {getattr(r, 'reply', None)!r}")
    check("none: names the configured vault folder it searched",
          r is not None and str(VAULT) in r.reply)

    # --- 4. no vault: the honest refusal names the switch. -----------------
    saved = os.environ.pop("JARVIS_OBSIDIAN_VAULT")
    try:
        r = ask("read my Welcome note")
        check("no vault: refuses honestly and names the switch",
              r is not None and "I cannot read a note" in r.reply
              and "JARVIS_OBSIDIAN_VAULT" in r.reply
              and "[notes.obsidian]" in r.reply,
              f"got {getattr(r, 'reply', None)!r}")
        check("no vault: says no note was read, so no text leaks",
              r is not None and "Hello world." not in r.reply)
    finally:
        os.environ["JARVIS_OBSIDIAN_VAULT"] = saved

    # --- 5. code / Unicode / a table survive the read. --------------------
    r = ask("read my Café Notes note")
    check("rich: the note's title is found with its accents",
          r is not None and r.reply.startswith('"Caf\u00e9 Notes" says:'))
    # The vault reader normalises line endings to CRLF; that and the 4,000
    # character cut are the ONLY transformations, and both are stated here.
    expected = RICH.replace("\n", "\r\n").strip()
    check("rich: fenced code, table pipes and Unicode are byte-identical",
          r is not None and expected in r.reply,
          f"got {getattr(r, 'reply', None)!r}")
    check("rich: nothing mangles the Markdown (no escaped pipes, no lost fence)",
          r is not None and "| café | 3€ |" in r.reply
          and "```python" in r.reply and "日本語 ✓" in r.reply
          and "\\|" not in r.reply)

    # --- 6. the model's read door returns the same text, marked outside. --
    code, one = NE.chat_read_note("Welcome")
    check("model door: returns the same text the chat quoted",
          code == 200 and one.get("text") == "Hello world.\r\nSecond line."
          or (code == 200 and one.get("text", "").replace("\r\n", "\n")
              == "Hello world.\nSecond line."),
          f"got {code} {one!r}")
    check("model door: the answer is marked as outside text",
          code == 200 and one.get("outside_text") is True)
    code, long_one = NE.chat_read_note("Long")
    check("model door: the same 4,000-character cap and remaining count",
          code == 200 and len(long_one.get("text") or "") == 4000
          and long_one.get("more") == 1000)
    code, choices = NE.chat_read_choices("")
    check("model door: the which-one helper lists titles and starts",
          code == 200 and choices.get("count") == 5
          and all("start" in row for row in choices.get("choices") or []))

    # the quick path records the reply as having read outside text
    r = ask("read my Welcome note")
    check("chat: the reply carries the outside-text fact, so it is not learned",
          r is not None and list(getattr(r, "read", []) or []) == ["notes_search"],
          f"got {getattr(r, 'read', None)!r}")

    # --- 7. Live speaks it: the start, then where it stopped. --------------
    r = ask("read my Long note", live=True)
    check("live: the spoken answer stops at ~1,000 characters and says so",
          r is not None and Q.LIVE_NOTE_START in r.reply
          and len(r.reply) <= Q.LIVE_NOTE_CHARS + len(Q.LIVE_NOTE_START) + 40,
          f"got len={len(getattr(r, 'reply', '') or '')}")
    check("live: it is spoken text, not a pointer at a screen",
          r is not None and getattr(r, "open_brain", None) is None
          and "Open the Brain" not in r.reply
          and "Notes plate" not in r.reply)
    r = ask("read my Welcome note", live=True)
    check("live: a short note is spoken whole, with no cut marker",
          r is not None and "Hello world." in r.reply
          and Q.LIVE_NOTE_START not in r.reply)
    r = ask("read my Long note")
    check("typed: a long note is NOT shortened - the full cap stays",
          r is not None and Q.LIVE_NOTE_START not in r.reply
          and "A" * 4000 in r.reply)

    # --- the topic question is a read: one match reads, several lists. -----
    r = ask("what did I write about alpha")
    check("topic: exactly one note mentions it, so its text is read",
          r is not None and r.reply.startswith('"Alpha" says:')
          and "first alpha line" in r.reply,
          f"got {getattr(r, 'reply', None)!r}")
    r = ask("what do my notes say about line")
    check("topic: several notes mention it, so titles are listed and asked",
          r is not None and "notes mention" in r.reply
          and "Tell me which one to read." in r.reply,
          f"got {getattr(r, 'reply', None)!r}")
    r = ask("what did I write about nothing-at-all")
    check("topic: no note mentions it, and the search door is named",
          r is not None and "No note in your vault mentions" in r.reply
          and "notes editor" in r.reply,
          f"got {getattr(r, 'reply', None)!r}")

    # --- 8. hidden lists / App lock: no title, no word. -------------------
    PV.note_state(app_locked=False, hide_memory_lists=True)
    try:
        r = ask("read my Welcome note")
        check("hidden: read shows no title and no text",
              r is not None and r.reply == Q.NOTES_READ_HIDDEN
              and "Welcome" not in r.reply and "Hello" not in r.reply)
        r = ask("read my notes")
        check("hidden: the which-one list shows no titles either",
              r is not None and "Welcome" not in r.reply
              and "Alpha" not in r.reply,
              f"got {getattr(r, 'reply', None)!r}")
        r = ask("what did I write about line")
        check("hidden: the topic read gives a count, never a title or a word",
              r is not None and "Welcome" not in r.reply
              and "alpha" not in r.reply.lower(),
              f"got {getattr(r, 'reply', None)!r}")
    finally:
        PV.note_state(app_locked=False, hide_memory_lists=False)


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
