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
8. THE OWNER'S TWO 2026-11-18 SENTENCES, verbatim. "Can you make a note for me
   called Mood Log and have this be one of my favorite notes?" creates exactly
   `Mood Log.md` with `favorite: true` (the name is never the sentence's tail).
   "Can you add to the mood log and make a note for today and put today's date
   and say that I'm feeling okay, kind of tired, played a little too much
   poker, didn't know when to call it quits, disappointed, but y" finds the
   existing Mood Log case-insensitively, adds a dated entry under TODAY from
   the clock, and keeps every comma and clause of the owner's words as content.
   A name that is genuinely absent still fails with the same "nothing was
   written" sentence and creates nothing. Both readers cut a name at ONE named
   boundary list (`_NOTE_NAME_BOUNDARIES`), which is what each sentence needed.
   The other direction is pinned too: "and" is not a boundary by itself
   ("Salt and Pepper" keeps it; "Poker and Mood and pin it" names "Poker and
   Mood" and pins it; "add to my Notes and Ideas that ..." appends to that
   note), and "It is favourited." is said only when `favorite: true` is really
   in the file, never on a refused create.
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
#: THE OWNER'S TWO MEASURED SENTENCES (2026-11-18), verbatim. The second is
#: quoted as far as the report carries it - the live conversation was cut at
#: "but y" - so that is the fixture. The first created a file named with the
#: whole tail of the sentence and set no favourite; the second answered "I
#: could not find a note called \"mood log and make a note for today and put
#: today's date and say\"" and wrote nothing.
OWNER_MOOD_SENTENCE = (
    "Can you make a note for me called Mood Log and have this be one of my "
    "favorite notes?")
OWNER_MOOD_APPEND = (
    "Can you add to the mood log and make a note for today and put today's date "
    "and say that I'm feeling okay, kind of tired, played a little too much "
    "poker, didn't know when to call it quits, disappointed, but y")
#: The owner's words that are CONTENT: every comma, and the "didn't know when
#: to call it quits, disappointed" clause, belong to the entry - they are not
#: further instructions and must be written unchanged.
MOOD_TEXT = (
    "I'm feeling okay, kind of tired, played a little too much poker, didn't "
    "know when to call it quits, disappointed, but y")
#: An existing Mood Log, as the owner's vault would hold it: yesterday's one
#: entry. The append must add TODAY's heading below it and keep every byte.
MOOD_NOTE = """# Mood Log

## 2026-11-15

- A good day.
"""
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


def t_an_append_to_a_named_note_needs_no_my_or_the():
    """The owner names the note directly, so the article is optional (2026-11-17).

    MEASURED ON THE LIVE INSTALL (SOURCE-COMMIT 02332ecc514c): "add to Field Test
    Groceries that I bought milk" produced no fast-path intent, fell to the 30B
    model for 66 s and answered "I can't directly add to Field Test Groceries,
    as I don't have the capability to edit or update that specific list".
    Nothing was written. The grammar required `my|the` before the name; the same
    sentence with "my" ("add to my Field Test Groceries that ...") already
    matched, so the miss was the article and nothing else.

    What must NOT change is the guard that keeps a non-note sentence out: the
    sentence says "note", or the name resolves to a note that exists, and a
    named list keeps its own door. Every control below is asserted at the same
    fast-path door, so a widened grammar that swallows one of them fails here.
    """
    reset_vault()
    _write("Private & Shared/Field Test Groceries.md", "# Field Test Groceries\n")
    _write("Private & Shared/Groceries.md", "# Groceries\n")
    before_workout = read_bytes(WORKOUT_REL)
    gate = Gate()
    set_gate(gate)
    got = ask("add to Field Test Groceries that I bought milk")
    check("append-natural: 'add to <Note> that ...' is the append path",
          got is not None and got.intent == "note_appended",
          got.intent if got else "model")
    said = read("Private & Shared/Field Test Groceries.md")
    check("append-natural: the words land in THAT note, under today's heading",
          "## " + TODAY in said and "- I bought milk" in said, repr(said))
    check("append-natural: exactly ONE edit_vault_note card, naming that note",
          len(gate.calls) == 1 and gate.calls[0][0] == "edit_vault_note"
          and gate.calls[0][1].get("path") == "Private & Shared/Field Test Groceries.md",
          gate.calls)
    check("append-natural: the workout log keeps every byte",
          read_bytes(WORKOUT_REL) == before_workout, "workout log changed")

    # The controls, read at the fast-path door: each keeps the intent it had
    # before the article became optional.
    def intent_of(sentence):
        found = Q.match(sentence, NOW)
        return getattr(found, "name", None), (found.f if found else {})

    name, fields = intent_of("add to my workout log that I ran 5k")
    check("append-natural: 'add to my <note> that ...' is unchanged",
          name == "note_append" and fields.get("name") == "workout log"
          and fields.get("text") == "I ran 5k" and fields.get("dated") == TODAY,
          (name, fields))
    name, fields = intent_of("add milk to my groceries note")
    check("append-natural: 'add X to my <note>' is unchanged",
          name == "note_append" and fields == {"name": "groceries", "text": "milk"},
          (name, fields))
    name, fields = intent_of("add this to my notes")
    check("append-natural: 'add this to my notes' is unchanged",
          name == "note_append" and fields.get("name") == "notes", (name, fields))
    name, _fields = intent_of("append to the shopping list: eggs")
    check("append-natural: a named LIST keeps its own door",
          name != "note_append", name)
    for sentence in ("add to the timer that I need five minutes",
                     "add to my focus session that I need quiet",
                     "add to the shopping list that I need eggs",
                     "delete my note called Groceries",
                     "add a calendar event at 3",
                     "add a to-do called milk"):
        name, _fields = intent_of(sentence)
        check(f"append-natural: {sentence!r} never becomes a note append",
              name != "note_append", name)


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
# 11. THE OWNER'S TWO 2026-11-18 SENTENCES
# --------------------------------------------------------------------------
def t_the_owner_names_a_note_and_favourites_it_in_one_sentence():
    """"Can you make a note for me called Mood Log and have this be one of my
    favorite notes?" - the owner's own sentence, verbatim.

    MEASURED BEFORE THE FIX (2026-11-18): the reply said "Created Mood Log and
    have this be one of my favorite notes.md ...", so the NAME was the whole
    tail of the sentence and no favourite was set. The name did not stop at
    "and have this ..." because `_NOTE_NAME_BOUNDARIES` had no rule for it, and
    the favourite was said as a description ("have this be one of my favorite
    notes") rather than the "favourite it" verb the reader knew.

    Now the name ends at the first boundary and the description sets the SAME
    separate `favorite` front-matter property the store already writes for
    "favourite it" - no new field, no new route, no card.
    """
    reset_vault(alias_note=False, collision=False)
    before = rel_files()
    gate = Gate()
    set_gate(gate)
    got = ask(OWNER_MOOD_SENTENCE)
    check("owner-2026-11-18 create: the sentence is the create fast path",
          got is not None and got.intent == "note_created",
          got.intent if got else "model")
    new = sorted(rel_files() - before)
    check("owner-2026-11-18 create: exactly ONE note is made", len(new) == 1, new)
    if len(new) != 1:
        return
    check("owner-2026-11-18 create: the note is named exactly Mood Log",
          new[0] == "Mood Log.md", new)
    check("owner-2026-11-18 create: the NAME never carries the rest of the sentence",
          "have this" not in new[0] and "favorite" not in new[0], new)
    made = read(new[0])
    check("owner-2026-11-18 create: the note's own front matter says favorite: true",
          "favorite: true" in made, repr(made))
    check("owner-2026-11-18 create: the reply names the file AND says it is favourited",
          "Mood Log.md" in got.reply and "favourited" in got.reply, got.reply)
    check("owner-2026-11-18 create: NO card was asked (a NEW note stays card-free)",
          gate.calls == [], gate.calls)
    parsed = Q.match(OWNER_MOOD_SENTENCE, NOW)
    check("owner-2026-11-18 create: parsed title 'Mood Log', favourite True, no body",
          parsed is not None and parsed.name == "note_create"
          and parsed.f.get("name") == "Mood Log"
          and parsed.f.get("favorite") is True
          and parsed.f.get("text") == "",
          (getattr(parsed, "name", None), getattr(parsed, "f", None)))
    # The favourite said as a description, in the nearest ways of saying it:
    # each names the note Mood Log and sets the same property, and none of them
    # leaks into the name.
    for phrase in ("and have this be one of my favorite notes",
                   "and make this one of my favourites",
                   "and make it a favorite"):
        parsed_desc = Q.match("make a note called Mood Log " + phrase, NOW)
        check(f"owner-2026-11-18 create: {phrase!r} names Mood Log, favourited",
              parsed_desc is not None and parsed_desc.name == "note_create"
              and parsed_desc.f.get("name") == "Mood Log"
              and parsed_desc.f.get("favorite") is True,
              (getattr(parsed_desc, "name", None),
               getattr(parsed_desc, "f", None)))


def t_the_owner_appends_to_the_existing_mood_log():
    """The owner's second sentence, verbatim (quoted to "but y", where the live
    conversation was cut).

    MEASURED BEFORE THE FIX (2026-11-18): "I could not find a note called
    \"mood log and make a note for today and put today's date and say\" in your
    Obsidian vault. Nothing was written ...". The append matcher's name ran
    through two instructions and stopped at the "that"; no clause boundary cut
    it at "and make a note for today".

    Now the name stops at "and make", "mood log" resolves to Mood Log.md
    case-insensitively, the dated entry uses TODAY from the turn's clock, and
    the owner's words - every comma, and the "didn't know when to call it
    quits, disappointed" clause - are the entry's body, never instructions.
    """
    reset_vault(alias_note=False, collision=False)
    _write("Mood Log.md", MOOD_NOTE)
    E._reset_for_tests()
    before_bytes = read_bytes("Mood Log.md")
    files_before = rel_files()
    gate = Gate()
    set_gate(gate)
    got = ask(OWNER_MOOD_APPEND)
    check("owner-2026-11-18 append: the sentence is the append fast path",
          got is not None and got.intent == "note_appended",
          got.intent if got else "model")
    check("owner-2026-11-18 append: no second note was created (append, not create)",
          rel_files() == files_before, sorted(rel_files()))
    after = read_bytes("Mood Log.md")
    check("owner-2026-11-18 append: every old byte is still there, in order",
          after.startswith(before_bytes), "old bytes are not a prefix")
    check("owner-2026-11-18 append: ONE new '## TODAY' heading, newest last",
          after.count(b"## " + TODAY.encode()) == 1
          and after.rfind(b"## 2026-11-15") < after.rfind(b"## " + TODAY.encode()),
          repr(after))
    check("owner-2026-11-18 append: the owner's words are the entry, commas and all",
          ("- " + MOOD_TEXT).encode() in after, repr(after[-260:]))
    check("owner-2026-11-18 append: the instructions are NOT the entry's words",
          b"make a note for today" not in after
          and b"put today's date" not in after, repr(after[-260:]))
    check("owner-2026-11-18 append: exactly ONE edit_vault_note card, naming Mood Log.md",
          len(gate.calls) == 1 and gate.calls[0][0] == "edit_vault_note"
          and gate.calls[0][1].get("path") == "Mood Log.md", gate.calls)
    check("owner-2026-11-18 append: the reply names the file and the heading",
          got is not None and "Mood Log.md" in got.reply
          and "## " + TODAY in got.reply, got.reply if got else "")
    parsed = Q.match(OWNER_MOOD_APPEND, NOW)
    check("owner-2026-11-18 append: parsed name 'mood log', words intact, dated TODAY",
          parsed is not None and parsed.name == "note_append"
          and parsed.f.get("name") == "mood log"
          and parsed.f.get("text") == MOOD_TEXT
          and parsed.f.get("dated") == TODAY,
          (getattr(parsed, "name", None), getattr(parsed, "f", None)))
    # The date is TODAY FROM THE CLOCK: the same sentence on another day files
    # under that day, so no word of the sentence is being read as a date.
    other = time.mktime(time.strptime("2026-12-24 09:00:00", "%Y-%m-%d %H:%M:%S"))
    parsed_other = Q.match(OWNER_MOOD_APPEND, other)
    check("owner-2026-11-18 append: the heading date comes from the CLOCK",
          parsed_other is not None and parsed_other.f.get("dated") == "2026-12-24",
          getattr(parsed_other, "f", None))


def t_a_genuinely_missing_note_still_fails_honestly():
    """The fix must NOT mean "create it whenever the search fails".

    The same shape as the owner's second sentence, with a name that is really
    not in the vault: it fails with the SAME "nothing was written" sentence,
    asks no card and writes no file - it does not create a second note.
    """
    reset_vault(alias_note=False, collision=False)
    _write("Mood Log.md", MOOD_NOTE)
    E._reset_for_tests()
    files_before = rel_files()
    before_bytes = read_bytes("Mood Log.md")
    gate = Gate()
    set_gate(gate)
    sentence = ("Can you add to the mood diary and make a note for today and put "
                "today's date and say that I'm feeling okay, kind of tired, "
                "disappointed, but y")
    got = ask(sentence)
    check("owner-2026-11-18 missing: a name that is not there is REFUSED",
          got is not None and got.intent == "note_append_refused",
          got.intent if got else "model")
    check("owner-2026-11-18 missing: the answer is the same honest sentence",
          got is not None
          and got.reply == Q.NOTE_NOT_FOUND_SAID.format(name="mood diary"),
          got.reply if got else "")
    check("owner-2026-11-18 missing: NOTHING was written and no card was asked",
          rel_files() == files_before and read_bytes("Mood Log.md") == before_bytes
          and gate.calls == [], (sorted(rel_files()), gate.calls))


def t_both_name_readers_share_one_boundary_list():
    """ONE list of boundaries, used by the create reader and the append cut.

    The owner's two sentences need two different boundaries ("and have this
    ..." for the create, "and make a note ..." for the append); both live in
    `_NOTE_NAME_BOUNDARIES`, and both readers cut at it, so the next person
    adds a boundary once instead of writing a second extractor.
    """
    probe = "mood log and make a note for today"
    check("owner-2026-11-18 one-list: the CREATE reader and the APPEND cut agree",
          Q._note_title_and_rest(probe)[0] == "mood log"
          and Q._note_append_name(probe) == "mood log",
          (Q._note_title_and_rest(probe), Q._note_append_name(probe)))
    check("owner-2026-11-18 one-list: the list is one named tuple of rules",
          isinstance(Q._NOTE_NAME_BOUNDARIES, tuple)
          and len(Q._NOTE_NAME_BOUNDARIES) >= 5,
          len(Q._NOTE_NAME_BOUNDARIES))
    # The rules the owner's two sentences depend on are both in that one list.
    for phrase in ("and have this be one of my favorite notes",
                   "and make a note for today"):
        check(f"owner-2026-11-18 one-list: {phrase!r} is a boundary",
              any(rx.search("mood log " + phrase) for rx in Q._NOTE_NAME_BOUNDARIES),
              phrase)


def t_an_and_inside_a_name_is_still_a_name():
    """A boundary is decided by what FOLLOWS the "and", never by "and" alone.

    A 2026-11-17 corpus measured these families as already passing, and the new
    "and make/create"/"and have this" rules must not eat a real note name.
    "Salt and Pepper" is quoted in the boundary list's own comment; the other
    two are the owner's families where a second, real instruction follows a
    name that itself contains "and".
    """
    # 1. A bare "and" inside a name stays in the name.
    reset_vault(alias_note=False, collision=False)
    set_gate(Gate())
    parsed = Q.match("make a note called Salt and Pepper", NOW)
    check("and-name: 'Salt and Pepper' keeps its and in the parsed name",
          parsed is not None and parsed.name == "note_create"
          and parsed.f.get("name") == "Salt and Pepper",
          (getattr(parsed, "name", None), getattr(parsed, "f", None)))
    got = ask("make a note called Salt and Pepper")
    check("and-name: ... and the file is named Salt and Pepper.md",
          got is not None and got.intent == "note_created"
          and "Salt and Pepper.md" in rel_files(), sorted(rel_files()))

    # 2. A name with "and", then a REAL instruction: cut at the instruction.
    reset_vault(alias_note=False, collision=False)
    set_gate(Gate())
    parsed = Q.match("make a note called Poker and Mood and pin it", NOW)
    check("and-name: 'Poker and Mood and pin it' names 'Poker and Mood', pinned",
          parsed is not None and parsed.name == "note_create"
          and parsed.f.get("name") == "Poker and Mood"
          and parsed.f.get("pinned") is True,
          (getattr(parsed, "name", None), getattr(parsed, "f", None)))
    got = ask("make a note called Poker and Mood and pin it")
    check("and-name: ... and the file is Poker and Mood.md with pinned: true",
          got is not None and got.intent == "note_created"
          and "Poker and Mood.md" in rel_files()
          and "pinned: true" in read("Poker and Mood.md"), sorted(rel_files()))

    # 3. An APPEND whose note's own name contains "and".
    reset_vault(alias_note=False, collision=False)
    _write("Notes and Ideas.md", "# Notes and Ideas\n")
    E._reset_for_tests()
    gate = Gate()
    set_gate(gate)
    parsed = Q.match("add to my Notes and Ideas that I should call the bank", NOW)
    check("and-name: the append's name is 'Notes and Ideas'",
          parsed is not None and parsed.name == "note_append"
          and parsed.f.get("name") == "Notes and Ideas"
          and parsed.f.get("text") == "I should call the bank",
          (getattr(parsed, "name", None), getattr(parsed, "f", None)))
    got = ask("add to my Notes and Ideas that I should call the bank")
    check("and-name: ... and it appends to that note with one card",
          got is not None and got.intent == "note_appended"
          and "I should call the bank" in read("Notes and Ideas.md")
          and len(gate.calls) == 1
          and gate.calls[0][1].get("path") == "Notes and Ideas.md",
          (getattr(got, "intent", None), gate.calls))


def t_the_favourite_claim_matches_the_written_property():
    """No claimed effect without the effect (the DEF-089 class).

    "It is favourited." may only be said when `favorite: true` is really in the
    new file, and a refused create must not claim it at all. The favourite is
    ONE property, and it is not `pinned`.
    """
    # 1. The created path: the claim and the bytes agree.
    reset_vault(alias_note=False, collision=False)
    set_gate(Gate())
    made = ask(OWNER_MOOD_SENTENCE)
    text = read("Mood Log.md")
    check("favourite honesty: the reply claims it AND the bytes carry it",
          made is not None and "It is favourited." in made.reply
          and text.count("favorite: true") == 1,
          (getattr(made, "reply", None), repr(text)))
    check("favourite honesty: no second property is invented (pin stays separate)",
          "pinned" not in text and "tags:" not in text, repr(text))

    # 2. A refused create (the note already exists) claims nothing and writes
    #    nothing - the same honesty the 2026-11-18 bug report demands.
    reset_vault(alias_note=False, collision=False)
    _write("Mood Log.md", MOOD_NOTE)
    E._reset_for_tests()
    before = read_bytes("Mood Log.md")
    set_gate(Gate())
    refused = ask(OWNER_MOOD_SENTENCE)
    check("favourite honesty: a refused create does not claim a favourite",
          refused is not None and refused.intent == "note_create_refused"
          and "favourit" not in refused.reply.lower(),
          (getattr(refused, "intent", None), getattr(refused, "reply", None)))
    check("favourite honesty: ... and the existing note is byte-unchanged",
          read_bytes("Mood Log.md") == before, "note changed")


# --------------------------------------------------------------------------
# 12. RECORDS
# --------------------------------------------------------------------------
def _same_text(a: Path, b: Path) -> bool:
    try:
        return a.read_bytes() == b.read_bytes()
    except OSError:
        return False


def t_there_is_no_daily_note_fallback():
    """A missing note is REFUSED; the words never go to today's daily note.

    The owner's measured bug was exactly this fallback: a name that could not be
    found was filed into `2026-11-15.md` instead. The resolver has no daily
    branch at all, and the append door refuses when the note is not there.
    """
    reset_vault(alias_note=False, collision=False)      # only the daily note
    import jarvis_notes as N
    got = N.resolve_note("my workout log")
    check("no-fallback: the resolver refuses a name that is not in the vault",
          got.get("ok") is False and got.get("code") == "not_found", got)
    check("no-fallback: ... and it has no path to the daily note",
          not str(got.get("path") or "").endswith(DAILY), got)
    gate = Gate()
    set_gate(gate)
    before = read(DAILY)
    got = ask("add to the workout log that I did light cardio")
    check("no-fallback: the chat path never files it into the daily note",
          got is None or got.intent not in ("note_made", "note_make_waiting"),
          got.intent if got else "model (no write)")
    check("no-fallback: ... and the fast path claims no daily-note write",
          Q.match("add to the workout log that I did light cardio", NOW) is None
          or Q.match("add to the workout log that I did light cardio", NOW).name
          != "note_make",
          getattr(Q.match("add to the workout log that I did light cardio", NOW),
                  "name", None))
    check("no-fallback: ... with no card asked", gate.calls == [], gate.calls)
    check("no-fallback: ... and the daily note is byte-for-byte unchanged",
          read(DAILY) == before and "## " not in read(DAILY), repr(read(DAILY)))
    check("no-fallback: no new note was made either", rel_files() == {DAILY},
          sorted(rel_files()))


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
    t_an_append_to_a_named_note_needs_no_my_or_the,
    t_append_to_an_older_day_stays_in_date_order,
    t_collision_asks_and_never_overwrites,
    t_nothing_is_written_outside_the_vault,
    t_one_card_and_no_whole_file_rewrite,
    t_the_daily_door_is_unchanged,
    t_hidden_lists_still_guard_the_same_writes,
    t_there_is_no_daily_note_fallback,
    t_both_apps_get_the_same_answer,
    t_the_owner_names_a_note_and_favourites_it_in_one_sentence,
    t_the_owner_appends_to_the_existing_mood_log,
    t_a_genuinely_missing_note_still_fails_honestly,
    t_both_name_readers_share_one_boundary_list,
    t_an_and_inside_a_name_is_still_a_name,
    t_the_favourite_claim_matches_the_written_property,
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
