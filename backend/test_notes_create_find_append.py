"""test_notes_create_find_append.py - create, find by alias, append a dated entry.

    python -B backend/test_notes_create_find_append.py

WHY THIS SUITE EXISTS (the owner's own report, 2026-11-16). Three failures were
measured in the owner's vault:

1. "Make a new note for me that's called my workout log and pin it and remember
   that when I ask for adding to my workout log in the future, this is the one
   that it adds to." was answered "Filed in Obsidian, 2026-11-15.md." The TAIL
   of the sentence was appended to that day's daily note and no note named "my
   workout log" was made. The daily-note pattern `_NOTE_TEXT_SPACE` claimed the
   sentence because it saw "note" and took every word after it.
2. Nine days earlier the same kind of sentence produced a 0-byte file named
   `Workout Log, pin it, and add using todays date that i used the punching
   bag.md` - a create path taking the WHOLE SENTENCE as the file name.
3. "add to the workout log that today I did light cardio and angled push-ups"
   was answered "I'm not sure where your new note is yet ..." - no lookup.

The fix under test is create / find / append and nothing else (no heading or
frontmatter patching, no search index). It is pinned here on a temporary vault
with a fake gate - no model, no network, no owner's file, no real card:

1. CREATE FROM A SENTENCE. The owner's exact sentence creates ONE note, whose
   title is "my workout log" (never the sentence), filed BESIDE the existing
   workout notes, pinned, card-free, and the reply names the file. The daily
   note is untouched.
2. NEVER A SENTENCE AS A FILE NAME. The 2026-11-08 sentence creates
   `Workout Log.md` with its body, never the measured comma-laden file; a
   sentence handed to the create path directly is refused with no file.
3. FIND BY ALIAS, NO CONTEXT. `Private & Shared/Workout/Workout Log.md` holds
   `aliases: [workout log, my workout log]` in its own YAML frontmatter - the
   registry Obsidian reads natively - so "my workout log" resolves with no
   model and no earlier conversation, from chat read, chat append and the
   module's resolver. An alias beats a file-name lookalike; two matches ask.
4. APPEND UNDER A DATE. "add to the workout log that I did light cardio" adds
   a dated entry under `## YYYY-MM-DD`, creating the heading when missing,
   newest last, and the reply names the file AND the heading. A second entry
   the same day goes under the same single heading.
5. COLLISION ASKS. `Private & Shared/Workout.md` and the `Private & Shared/
   Workout/` folder both exist; a create that would hit either is refused
   before any card and nothing is overwritten.
6. THE VAULT BOUNDARY, ONE CARD, NO REWRITE. `..`, absolute and dot-folder
   paths are refused; an append asks exactly ONE `edit_vault_note` card and
   only ever ADDS bytes at one offset (a true append when the block is last).
7. THE RECORDS AGREE. The two changed modules have byte-identical published
   twins, and docs/JARVIS-API.md section 170.12 documents all of it.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import sys
import tempfile
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
# The live backend's copy is older than this branch's until the deploy pass, and
# `_where.require_shipped` would refuse for that reason alone. This suite is
# about the repository's own code, so the ambient install is ignored exactly as
# test_notes_smart_create.py ignores it.
os.environ.pop("JARVIS_BACKEND", None)
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_notes_edit.py", "jarvis_quick.py")

_TMP = Path(tempfile.gettempdir()) / ("jarvis-notes-cfa-" + secrets.token_hex(6))
_TMP.mkdir(parents=True, exist_ok=True)
VAULT = _TMP / "vault"
(VAULT / ".obsidian").mkdir(parents=True, exist_ok=True)
CONF = _TMP / "config"
CONF.mkdir(exist_ok=True)
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONF)
os.environ["JARVIS_RECEIPTS_DB"] = str(_TMP / "receipts.db")
os.environ["JARVIS_OBSIDIAN_VAULT"] = str(VAULT)
os.environ.setdefault("HF_HUB_OFFLINE", "1")

FW = types.ModuleType("jarvis_framework")
FW.CONFIG_DIR = CONF
FW.LOG_DIR = _TMP / "log"
FW_STATE = {"notes": {"obsidian": {"vault_directory": str(VAULT)}}}
FW.load_framework = lambda: json.loads(json.dumps(FW_STATE))
FW.action_tier = lambda action: "ask" if action == "edit_vault_note" else "auto"
AUDIT = []
FW.audit_log = lambda event, detail: AUDIT.append((event, detail))
sys.modules["jarvis_framework"] = FW

_GATE_MODULE = types.ModuleType("jarvis_gate")


class _Approved:
    allowed = True
    outcome = "approved"
    tier = "auto"
    reason = ""


_GATE_MODULE.check = lambda *a, **k: _Approved()
_GATE_MODULE.taint_active = lambda: False
sys.modules["jarvis_gate"] = _GATE_MODULE

import jarvis_notes_edit as E  # noqa: E402
import jarvis_quick as Q  # noqa: E402

#: A fixed clock: 2026-11-16, 10:30 local time. The dated append's heading is
#: read from THIS instant, so the suite does not depend on the day it runs.
NOW = time.mktime(time.strptime("2026-11-16 10:30:00", "%Y-%m-%d %H:%M:%S"))
TODAY = "2026-11-16"
WORKOUT_REL = "Private & Shared/Workout/Workout Log.md"

#: The owner's own note, as it stands in their vault, written with LF so a byte
#: comparison in this suite is not about Windows' line endings.
WORKOUT_NOTE = """---
aliases:
  - workout log
  - my workout log
pinned: true
---

# Workout Log

Day-by-day training entries, oldest first. New entries go at the bottom under the date
they were done, so "add to my workout log" always means appending here.

## 2026-11-15

- Light cardio.
- Angled push-ups.
"""

OWNER_SENTENCE = (
    "Make a new note for me that's called my workout log and pin it and remember "
    "that when I ask for adding to my workout log in the future, this is the one "
    "that it adds to.")
SENTENCE_AS_NAME = ("Workout Log, pin it, and add using todays date that i used "
                    "the punching bag")
CREATE_SENTENCE = ("create a new note called Workout Log, pin it, and add using "
                   "todays date that i used the punching bag")
DAILY = "2026-11-15.md"
DAILY_TEXT = "daily sentinel\n"

FAILED, PASSED, SKIPPED = [], [], []


def skip(name: str, why: str) -> None:
    SKIPPED.append(name)
    print(f"skip  {name}: {why}")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if not cond else ""))


def _write(rel: str, text: str) -> Path:
    p = VAULT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(str(p), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return p


def read(rel: str) -> str:
    return (VAULT / rel).read_text(encoding="utf-8")


def read_bytes(rel: str) -> bytes:
    return (VAULT / rel).read_bytes()


def rel_files() -> set:
    return {p.relative_to(VAULT).as_posix() for p in VAULT.rglob("*") if p.is_file()}


def reset_vault(alias_note: bool = True, collision: bool = True) -> None:
    for child in list(VAULT.iterdir()):
        if child.name == ".obsidian":
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
    E._reset_for_tests()
    if alias_note:
        _write(WORKOUT_REL, WORKOUT_NOTE)
        _write("Private & Shared/Workout/Push Up Variations.md", "# Push Up Variations\n")
        _write("Private & Shared/Workout/Workout Schedule.md", "# Workout Schedule\n")
        _write("Private & Shared/Workout/Lower Back Workouts.md", "# Lower Back\n")
    if collision:
        _write("Private & Shared/Workout.md", "# Workout\n")
    _write(DAILY, DAILY_TEXT)


class Verdict:
    def __init__(self, allowed, tier="ask", outcome="approved", reason=""):
        self.allowed = allowed
        self.tier = tier
        self.outcome = outcome
        self.reason = reason


class Gate:
    """A fake approval card: records every call, answers without a person."""

    def __init__(self, allowed=True, outcome="approved"):
        self.allowed = allowed
        self.outcome = outcome
        self.calls = []

    def __call__(self, action, detail, prompt):
        self.calls.append((action, dict(detail or {}), prompt))
        return Verdict(self.allowed, "ask", self.outcome)


def set_gate(gate) -> None:
    E._gate_check = gate                 # the module's own fail-closed wrapper


class Stub:
    def mark_command(self, text):
        pass

    def forget_set(self, conversation):
        pass

    def note_set(self, *a, **k):
        pass

    def last_set(self, *a, **k):
        return None

    def add_at(self, kind, at, text, source="quick", steps=None):
        return {"id": "stub-" + kind, "text": text, "due": at, "kind": kind}

    def add_todo(self, text, *a, **k):
        return {"id": "stub-todo", "text": text}

    def add_note(self, text, *a, **k):
        return {"id": "stub-note", "text": text}


def ask(text: str):
    return Q.answer(text, sched=Stub(), now=NOW, peer="127.0.0.1", local=True)


def _chat_body(sentence: str, surface: str) -> dict:
    """The shape both apps POST to /api/chat (phone: ChatHistory.requestBody)."""
    return {"messages": [{"role": "user", "content": sentence,
                          "provenance": "typed"}],
            "has_image": False, "stream": True, "auto": True,
            "device": surface}


def sha(rel: str) -> str:
    import hashlib
    return hashlib.sha256(read_bytes(rel)).hexdigest()


# --------------------------------------------------------------------------
# 1. CREATE FROM A SENTENCE WITH A TITLE
# --------------------------------------------------------------------------
def t_create_from_a_sentence_with_a_title():
    reset_vault()
    before = rel_files()
    gate = Gate()
    set_gate(gate)
    got = ask(OWNER_SENTENCE)
    check("create: the owner's sentence is answered by the fast path, not the model",
          got is not None and got.intent == "note_created",
          got.intent if got else "model")
    new = sorted(rel_files() - before)
    check("create: exactly ONE note is made", len(new) == 1, new)
    if len(new) != 1:
        return
    made = new[0]
    check("create: it is filed with the workout notes, not the vault root",
          made == "Private & Shared/Workout/my workout log.md", made)
    check("create: the TITLE is not the whole sentence",
          "," not in made and "pin it" not in made and "remember" not in made
          and "that it adds to" not in made, made)
    check("create: the reply names the file and says it can be undone",
          "Private & Shared/Workout/my workout log.md" in got.reply
          and "You can undo it" in got.reply, got.reply)
    check("create: the sentence's pin became the note's own property",
          "pinned: true" in read(made), repr(read(made)))
    check("create: the 'remember that ...' clause is not note text",
          "remember" not in read(made), repr(read(made)))
    check("create: NO card was asked (a NEW note stays card-free)",
          gate.calls == [], gate.calls)
    check("create: today's DAILY note was not touched",
          read(DAILY) == DAILY_TEXT, repr(read(DAILY)))
    check("create: the intent was note_create, never the daily note_make",
          (Q.match(OWNER_SENTENCE, NOW) or types.SimpleNamespace(name="")).name
          == "note_create",
          getattr(Q.match(OWNER_SENTENCE, NOW), "name", None))


def t_plain_create_is_one_sane_note():
    """'Make a new note called my workout log' - with and without the alias note."""
    reset_vault(alias_note=False, collision=False)
    set_gate(Gate())
    got = ask("Make a new note called my workout log")
    check("create: the plain sentence makes ONE note",
          got is not None and got.intent == "note_created" and
          rel_files() - {DAILY} == {"my workout log.md"},
          sorted(rel_files()))
    check("create: ... a sane title, not a sentence",
          "my workout log.md" in rel_files(), sorted(rel_files()))
    check("create: ... and the reply names where it went",
          got is not None and "my workout log.md" in got.reply, got.reply if got else "")
    # With the workout notes present, the same sentence is filed beside them.
    reset_vault()
    set_gate(Gate())
    got = ask("Make a new note called my workout log")
    check("create: with a matching note, the new note lands in ITS folder",
          got is not None and got.intent == "note_created"
          and "Private & Shared/Workout/my workout log.md" in rel_files(),
          sorted(rel_files()))
    check("create: ... and the existing Workout Log.md was NOT overwritten",
          read(WORKOUT_REL) == WORKOUT_NOTE, repr(read(WORKOUT_REL)))
    # A name that already names a FOLDER keeps its own path (never doubled).
    reset_vault()
    set_gate(Gate())
    got = ask("create a note called Gym/Log")
    check("create: a name that already has a folder keeps that folder",
          got is not None and got.intent == "note_created"
          and "Gym/Log.md" in rel_files(), sorted(rel_files()))


# --------------------------------------------------------------------------
# 2. THE SENTENCE IS NEVER A FILE NAME
# --------------------------------------------------------------------------
def t_the_sentence_is_never_a_filename():
    reset_vault(alias_note=False, collision=False)
    set_gate(Gate())
    got = ask(CREATE_SENTENCE)
    check("sentence: the 2026-11-08 sentence creates its real note",
          got is not None and got.intent == "note_created"
          and (VAULT / "Workout Log.md").is_file(), sorted(rel_files()))
    check("sentence: ... with its body and its date, as the four-facts reader says",
          "i used the punching bag" in read("Workout Log.md")
          and "date: " + TODAY in read("Workout Log.md"), repr(read("Workout Log.md")))
    bad = {p.name for p in VAULT.rglob("*.md")}
    check("sentence: the measured comma-laden file name was never made",
          SENTENCE_AS_NAME + ".md" not in bad, sorted(bad))
    check("sentence: no file name is a whole sentence (no comma, no 'pin it')",
          all("," not in name and "pin it" not in name for name in bad), sorted(bad))
    # Directly handing the create path a sentence name is refused, not filed.
    reset_vault(alias_note=False, collision=False)
    set_gate(Gate())
    out = Q._run_note_create({"name": SENTENCE_AS_NAME, "text": ""})
    check("sentence: the create path refuses a sentence name",
          out.intent == "note_create_refused", out.intent)
    check("sentence: ... says it is a sentence and asks for the name",
          "whole sentence" in out.reply and "nothing was created" in out.reply,
          out.reply)
    check("sentence: ... and writes NO file at all",
          rel_files() == {DAILY}, sorted(rel_files()))
    shaped = Q.match("create a note called " + "long words " * 30, NOW)
    check("sentence: a create-shaped sentence the reader declines asks for the name",
          shaped is not None and shaped.name == "note_create_ask",
          getattr(shaped, "name", None))
    check("sentence: ... and it never reaches the daily note",
          shaped is None or shaped.name != "note_make",
          getattr(shaped, "name", None))


# --------------------------------------------------------------------------
# 3. ALIAS RESOLUTION WITH NO OTHER CONTEXT
# --------------------------------------------------------------------------
def t_alias_resolution_with_no_other_context():
    reset_vault()
    for phrase in ("my workout log", "the workout log", "workout log",
                   "MY WORKOUT LOG", "workout log.md", "Workout Log"):
        row, why, matches = E.find_name(phrase)
        check(f"alias: {phrase!r} resolves to the note filed as Workout Log.md",
              row is not None and row.get("path") == WORKOUT_REL,
              (why, [r.get("path") for r in matches]))
    code, found = E.chat_find_notes("my workout log")
    check("alias: the chat finder resolves it too",
          code == 200 and len(found.get("matches") or []) == 1
          and found["matches"][0]["path"] == WORKOUT_REL, found)
    code, one = E.chat_read_note("my workout log")
    check("alias: the chat reader reads the alias note",
          code == 200 and one.get("title") == "Workout Log"
          and "Day-by-day" in one.get("text", ""), (code, one if code != 200 else ""))
    # A different conversation, through the apps' own /api/chat body.
    got = Q.answer_turn(_chat_body("read my workout log note", "phone"), now=NOW,
                        client_surface="phone")
    check("alias: a later conversation reads it with no model state",
          got is not None and got.intent == "note_read"
          and "Workout Log" in got.reply, got.intent if got else "model")
    # The resolver reads the note's own YAML, not a side file or an index: a
    # note that never claimed the name is not found by it.
    plain = _write("Private & Shared/No aliases.md", "# No aliases\n")
    check("alias: a note with no aliases is found by its own title",
          (E.find_name("no aliases")[0] or {}).get("path") ==
          "Private & Shared/No aliases.md", E.find_name("no aliases")[:2])
    check("alias: ... but it does not claim an alias it never had",
          (E.find_name("garden bucket")[0] is None), E.find_name("garden bucket")[:2])
    # A file-name lookalike must not steal the alias.
    _write("Private & Shared/Workout/Workout Log Backup.md", "# Backup\n")
    row, why, _m = E.find_name("my workout log")
    check("alias: an alias beats a file name that merely looks like it",
          row is not None and row.get("path") == WORKOUT_REL, (why, row))
    # Two notes claiming the same alias is an ambiguity, never a guess.
    _write("Private & Shared/Other log.md",
           "---\naliases:\n  - my workout log\n---\n\n# Other\n")
    row, why, matches = E.find_name("my workout log")
    check("alias: two notes with the same alias ask instead of guessing",
          row is None and why == "ambiguous" and len(matches) == 2,
          (why, [r.get("path") for r in matches]))
    code, asked = E.chat_read_note("my workout log")
    check("alias: ... and the chat read asks which note, never quotes one",
          code == 409 and not (asked.get("text") or ""), (code, asked))


# --------------------------------------------------------------------------
# 4. APPEND UNDER A NEW HEADING
# --------------------------------------------------------------------------
def t_append_under_a_new_heading():
    reset_vault()
    before = read_bytes(WORKOUT_REL)
    other = {"Private & Shared/Workout.md": sha("Private & Shared/Workout.md"),
             DAILY: sha(DAILY)}
    gate = Gate()
    set_gate(gate)
    got = ask("add to the workout log that I did light cardio")
    check("append-new: 'add to the workout log that ...' is the append path",
          got is not None and got.intent == "note_appended",
          got.intent if got else "model")
    after = read_bytes(WORKOUT_REL)
    check("append-new: the entry is under a new ## 2026-11-16 heading",
          b"## " + TODAY.encode() + b"\n\n- I did light cardio\n" in after, repr(after[-160:]))
    check("append-new: every old byte is still there, in the same order",
          after.startswith(before), "old bytes are not a prefix")
    check("append-new: the new day is LAST (newest last)",
          after.rfind(b"## 2026-11-15") < after.rfind(b"## " + TODAY.encode()), repr(after))
    headings = [ln for ln in read(WORKOUT_REL).splitlines() if ln.startswith("## ")]
    check("append-new: there is exactly one date heading for the day",
          headings == ["## 2026-11-15", "## 2026-11-16"], headings)
    check("append-new: the reply names the FILE and the HEADING it wrote",
          got is not None and WORKOUT_REL in got.reply
          and "## " + TODAY in got.reply, got.reply if got else "")
    check("append-new: exactly ONE edit_vault_note card was asked",
          len(gate.calls) == 1 and gate.calls[0][0] == "edit_vault_note"
          and gate.calls[0][1].get("path") == WORKOUT_REL, gate.calls)
    check("append-new: the daily note and the other notes are untouched",
          {k: sha(k) for k in other} == other,
          {k: sha(k) for k in other})


# --------------------------------------------------------------------------
# 5. APPEND UNDER AN EXISTING HEADING
# --------------------------------------------------------------------------
def t_append_under_an_existing_heading():
    reset_vault()
    set_gate(Gate())
    ask("add to the workout log that I did light cardio")
    mid = read_bytes(WORKOUT_REL)
    gate = Gate()
    set_gate(gate)
    got = ask("add to my workout log that I did a 20 minute walk")
    after = read_bytes(WORKOUT_REL)
    check("append-existing: a second entry the same day is saved",
          got is not None and got.intent == "note_appended", got.intent if got else "model")
    check("append-existing: there is still exactly one heading for the day",
          read(WORKOUT_REL).count("## " + TODAY) == 1, read(WORKOUT_REL))
    check("append-existing: the second entry is below the first (newest last)",
          after.find(b"- I did light cardio") < after.find(b"- I did a 20 minute walk"),
          repr(after[-200:]))
    check("append-existing: the earlier bytes are a prefix again",
          after.startswith(mid), "earlier bytes changed")
    check("append-existing: one card, and it names the heading",
          len(gate.calls) == 1 and "## " + TODAY in got.reply, gate.calls)


def t_append_to_an_older_day_stays_in_date_order():
    """A day with no heading keeps the file in date order, inserting one block."""
    reset_vault()
    set_gate(Gate())
    ask("add to the workout log that I did light cardio")
    before = read_bytes(WORKOUT_REL)
    expected, at, block, why = E._dated_entry(before, "Ran 5k", "2026-11-14")
    check("append-old: the dated reader builds one block and no error",
          expected is not None and not why and block, why)
    gate = Gate()
    set_gate(gate)
    code, out = E.handle_append({"path": WORKOUT_REL, "text": "Ran 5k",
                                 "expected_sha256": E._sha256(before),
                                 "dated": "2026-11-14"}, by="test", wait_s=0.5)
    after = read_bytes(WORKOUT_REL)
    headings = [ln for ln in read(WORKOUT_REL).splitlines() if ln.startswith("## ")]
    check("append-old: the older day's heading is created",
          code == 200 and out.get("state") == "saved" and "## 2026-11-14" in read(WORKOUT_REL),
          (code, out))
    check("append-old: the days stay newest last",
          headings == ["## 2026-11-14", "## 2026-11-15", "## 2026-11-16"], headings)
    check("append-old: the write is exactly the old bytes with ONE block inserted",
          after == before[:at] + block + before[at:], "insertion changed other bytes")
    check("append-old: one card for it",
          len(gate.calls) == 1 and gate.calls[0][0] == "edit_vault_note", gate.calls)


# --------------------------------------------------------------------------
# 6. A COLLISION ASKS
# --------------------------------------------------------------------------
def t_collision_asks_and_never_overwrites():
    reset_vault()
    before = {p.relative_to(VAULT).as_posix(): sha(p.relative_to(VAULT).as_posix())
              for p in VAULT.rglob("*.md")}
    gate = Gate()
    set_gate(gate)
    got = ask("create a note called Workout")
    check("collision: a name that already exists is refused, not overwritten",
          got is not None and got.intent == "note_create_refused",
          got.intent if got else "model")
    check("collision: ... the answer says there is already a note",
          "already a note" in got.reply, got.reply)
    check("collision: ... no card was asked and no file changed",
          gate.calls == [] and
          {p.relative_to(VAULT).as_posix(): sha(p.relative_to(VAULT).as_posix())
           for p in VAULT.rglob("*.md")} == before, gate.calls)
    # The existing note that the name actually points at is never rewritten.
    reset_vault()
    original = read(WORKOUT_REL)
    set_gate(Gate())
    got = ask("create a note called Workout Log")
    check("collision: creating the note that already exists refuses",
          got is not None and got.intent == "note_create_refused", got.intent if got else "")
    check("collision: ... and its bytes are untouched",
          read(WORKOUT_REL) == original, repr(read(WORKOUT_REL)))
    code, out = E.handle_create({"path": WORKOUT_REL, "text": "x"},
                                provenance="typed", client="hud")
    check("collision: the module's own create is a 409 on an existing path",
          code == 409 and out.get("state") == "exists", (code, out))


# --------------------------------------------------------------------------
# 7. NOTHING IS WRITTEN OUTSIDE THE VAULT
# --------------------------------------------------------------------------
def t_nothing_is_written_outside_the_vault():
    reset_vault()
    set_gate(Gate())
    outside = VAULT.parent / "escape.md"
    for rel in ("../escape.md", "notes/../../escape.md", "/abs.md", "C:/x.md",
                ".obsidian/x.md", "notes/.hidden.md"):
        code, out = E.handle_create({"path": rel, "text": "x"})
        check(f"boundary: create refuses {rel!r}",
              code == 400 and not outside.exists(), (code, out))
    before = read_bytes(WORKOUT_REL)
    code, out = E.handle_append({"path": "../escape.md", "text": "x",
                                 "expected_sha256": E._sha256(before)})
    check("boundary: append refuses a path that climbs out of the vault",
          code == 400 and not outside.exists(), (code, out))
    out2 = Q._run_note_create({"name": "../escape", "text": "x"})
    check("boundary: the chat create refuses a climbing name",
          out2.intent == "note_create_refused" and not outside.exists(), out2.intent)
    check("boundary: the note itself was never touched",
          read_bytes(WORKOUT_REL) == before, "note changed")


# --------------------------------------------------------------------------
# 8. ONE CARD PER WRITE, AND NO WHOLE-FILE REWRITE
# --------------------------------------------------------------------------
def t_one_card_and_no_whole_file_rewrite():
    reset_vault()
    before = read_bytes(WORKOUT_REL)
    gate = Gate()
    set_gate(gate)
    ask("add to the workout log that I did light cardio")
    after = read_bytes(WORKOUT_REL)
    check("card: one append asks exactly ONE edit_vault_note card",
          len(gate.calls) == 1 and gate.calls[0][0] == "edit_vault_note", gate.calls)
    check("card: the card names the note and what kind of change it is",
          gate.calls and gate.calls[0][1].get("path") == WORKOUT_REL
          and "dated entry" in str(gate.calls[0][1].get("action", "")), gate.calls)
    check("rewrite: the file only grew, by the one inserted block",
          len(after) > len(before) and after.startswith(before), "not an insertion")
    check("rewrite: no other note was written",
          read(DAILY) == DAILY_TEXT, repr(read(DAILY)))
    # A deny writes nothing and reports the module's own words.
    reset_vault()
    before = read_bytes(WORKOUT_REL)
    deny = Gate(allowed=False, outcome="denied")
    set_gate(deny)
    got = ask("add to the workout log that I did light cardio")
    check("card: a Deny writes nothing and says so",
          got is not None and got.intent == "note_append_refused"
          and read_bytes(WORKOUT_REL) == before, got.intent if got else "")
    check("card: ... with exactly one card asked", len(deny.calls) == 1, deny.calls)


# --------------------------------------------------------------------------
# 9. THE DAILY DOOR AND THE HIDDEN LISTS ARE UNCHANGED
# --------------------------------------------------------------------------
def t_the_daily_door_is_unchanged():
    reset_vault()
    # The words avoid "service": the cloud-provider matcher already claims
    # "make ... service" on main (an unrelated, pre-existing overlap), so this
    # check must not blame the note grammar for it.
    for sentence in ("make a note that the boiler is due",
                     "note this: the boiler service is due",
                     "add this to my daily note: the boiler service is due"):
        got = Q.match(sentence, NOW)
        check(f"daily: {sentence!r} is still the daily-note door",
              got is not None and got.name == "note_make",
              getattr(got, "name", None))
    got = Q.match("make a note that the boiler is due", NOW)
    check("daily: ... and its words are the words after 'note that'",
          got is not None and got.f.get("text") == "the boiler is due",
          getattr(got, "f", None))


def t_hidden_lists_still_guard_the_same_writes():
    reset_vault()
    old = Q._calendar_hidden
    Q._calendar_hidden = lambda: (True, "Words hidden.")
    try:
        gate = Gate()
        set_gate(gate)
        got = Q._run_note_append({"name": "workout log", "text": "x", "dated": TODAY})
        check("hidden: an append is refused with NO card",
              got.intent == "note_write_hidden" and gate.calls == [], got.intent)
        check("hidden: ... and the refusal names no title",
              "Workout" not in got.reply and "workout" not in got.reply, got.reply)
        got = ask("Make a new note called my workout log")
        check("hidden: a create is still card-free and writes the note",
              got.intent == "note_created" and gate.calls == [], got.intent)
        check("hidden: ... and it names no title",
              "workout" not in got.reply.lower(), got.reply)
    finally:
        Q._calendar_hidden = old


# --------------------------------------------------------------------------
# 10. BOTH APPS, THE SAME ANSWER
# --------------------------------------------------------------------------
def t_both_apps_get_the_same_answer():
    reset_vault()
    set_gate(Gate())
    phone = Q.answer_turn(_chat_body("add to the workout log that I did light cardio",
                                     "phone"), now=NOW, client_surface="phone")
    check("parity: the phone's own body shape appends the dated entry",
          phone is not None and phone.intent == "note_appended"
          and "## " + TODAY in read(WORKOUT_REL), phone.intent if phone else "model")
    reset_vault()
    set_gate(Gate())
    desk = Q.answer_turn(_chat_body("Make a new note called my workout log", "desktop"),
                         now=NOW, client_surface="desktop")
    check("parity: the desktop's own body shape creates the note",
          desk is not None and desk.intent == "note_created"
          and "Private & Shared/Workout/my workout log.md" in rel_files(),
          desk.intent if desk else "model")


# --------------------------------------------------------------------------
# 11. RECORDS
# --------------------------------------------------------------------------
def _same_text(a: Path, b: Path) -> bool:
    try:
        return a.read_bytes() == b.read_bytes()
    except OSError:
        return False


def t_twins_and_docs_agree():
    for name in ("jarvis_notes_edit.py", "jarvis_quick.py"):
        check(f"records: {name} has a byte-identical published twin",
              _same_text(HERE / name, REPO / "jarvis-backend" / name),
              f"{HERE/name} vs {REPO/'jarvis-backend'/name}")
    api = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    for needle in ("170.12", "aliases:", "newest last", "dated entry",
                   "no new route"):
        check(f"docs: JARVIS-API.md section 170.12 names {needle!r}",
              needle in api, "missing from JARVIS-API.md")


# --------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------
TESTS = [
    t_create_from_a_sentence_with_a_title,
    t_plain_create_is_one_sane_note,
    t_the_sentence_is_never_a_filename,
    t_alias_resolution_with_no_other_context,
    t_append_under_a_new_heading,
    t_append_under_an_existing_heading,
    t_append_to_an_older_day_stays_in_date_order,
    t_collision_asks_and_never_overwrites,
    t_nothing_is_written_outside_the_vault,
    t_one_card_and_no_whole_file_rewrite,
    t_the_daily_door_is_unchanged,
    t_hidden_lists_still_guard_the_same_writes,
    t_both_apps_get_the_same_answer,
    t_twins_and_docs_agree,
]


def main():
    print("=" * 74)
    print("jarvis_quick + jarvis_notes_edit - create, find by alias, dated append")
    print("=" * 74)
    for test in TESTS:
        print()
        print("--", test.__name__, "-" * max(0, 60 - len(test.__name__)))
        try:
            test()
        except Exception:                                   # noqa: BLE001
            FAILED.append(test.__name__ + " (exception)")
            import traceback
            traceback.print_exc()
    print()
    print("=" * 74)
    print(f"PASS {len(PASSED)}  FAIL {len(FAILED)}  SKIP {len(SKIPPED)}")
    for name in FAILED:
        print("  FAIL:", name)
    try:
        shutil.rmtree(_TMP, ignore_errors=True)
    except Exception:                                       # noqa: BLE001
        pass
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
