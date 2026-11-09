"""test_notes_smart_create.py - ONE sentence, four facts: title, body, pin, date.

    python -B backend/test_notes_smart_create.py

WHY THIS SUITE EXISTS (the owner's own report, 2026-11-09). The owner asked,
in one sentence:

    "create a new note called Workout Log, pin it, and add using todays date
     that i used the punching bag"

and Jarvis made a note whose TITLE was the whole sentence and whose body was
empty (measured on this tree before the change: the note's file name was
`Workout Log, pin it, and add using todays date that i used the punching
bag.md`). The grammar in `jarvis_quick.py` took every word after "called" as
the name. This suite pins the fix, on a temporary vault, with a fake gate - no
model, no network, no owner's file, no real card:

1. THE OWNER'S SENTENCE. It creates ONE note, `Workout Log.md`, card-free,
   whose body is exactly "i used the punching bag" and whose front matter is
   `pinned: true` and `date: <today>`. The reply names the file, says it can
   be undone, and says it is pinned and dated.
2. THE FOUR FACTS ARE READ SEPARATELY. An explicit title ("called/titled/
   named"), a body after it ("with ...", "saying ...", "add ...", "that ...",
   or the words after the title's comma), a pin ("pin it" / "and pin it"),
   and a date (today / todays date / yesterday / tomorrow / an explicit date),
   in either order.
3. THE OLD RULES STILL HOLD, byte for byte. A body-only sentence ("write a
   note for me about X") is still a body-only note with its title drawn from
   the words; "... called Shopping with milk and eggs" still has exactly
   "milk and eggs" as its body; "a note called Salt and Pepper" keeps its
   "and"; and "went to the gym YESTERDAY" keeps "yesterday" in the body
   instead of turning it into a date property.
4. THE PERMISSION MODEL IS UNCHANGED. A NEW note from chat is card-free and
   collision-refused (the file is never overwritten) and its undo removes it.
   Pinning or unpinning an EXISTING note is an EDIT: exactly ONE
   `edit_vault_note` card, the File Guardian copy, one Undo - and pinning
   twice asks no second card. While the lists are hidden, the create is still
   card-free and names no title, and the pin/unpin edit is refused with NO
   card and NO title.
5. BOTH APPS GET THE SAME RESULT. The desktop and the phone both POST
   `/api/chat`, whose fast path is `answer_turn` -> `answer` -> this grammar;
   this suite drives the phone's own body shape and the desktop's through
   `answer_turn` and checks the same note, the same pin and the same date.
6. THE RECORDS AGREE. `jarvis_quick.py` and `jarvis_notes_edit.py` have
   byte-identical published twins, and `docs/JARVIS-API.md` documents the new
   reading and the unchanged permission model.
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
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
# The live backend's copy of jarvis_quick.py is OLDER than this branch's until
# the deploy pass, and `_where.require_shipped` would refuse to run for that
# reason alone. This suite is about the repository's own code, so the ambient
# install is ignored exactly as test_notes_write.py ignores it.
os.environ.pop("JARVIS_BACKEND", None)
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_notes_edit.py", "jarvis_quick.py")

_TMP = Path(tempfile.gettempdir()) / ("jarvis-notes-smart-" + secrets.token_hex(6))
_TMP.mkdir(parents=True, exist_ok=True)
VAULT = _TMP / "vault"
(VAULT / ".obsidian").mkdir(parents=True, exist_ok=True)
CONF = _TMP / "config"
CONF.mkdir(exist_ok=True)
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONF)
os.environ["JARVIS_RECEIPTS_DB"] = str(_TMP / "receipts.db")
os.environ["JARVIS_OBSIDIAN_VAULT"] = str(VAULT)
# Hermetic: a mutating fast-path answer writes the change journal, and that
# journal's memory module may reach for its embedding model. Offline is what
# keeps this suite at "no network", the same rule every suite here follows;
# the journal's own failure is swallowed by jarvis_quick, as it is on a PC
# with no model downloaded.
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

try:
    import jarvis_receipts as RC
except Exception:                                           # noqa: BLE001
    RC = None

#: A fixed clock: 2026-11-09, 10:30 local time. Every date assertion below is
#: read from THIS instant, so "today"/"yesterday"/"tomorrow" are fixed facts
#: and not whatever day the suite happens to run on.
NOW = time.mktime(time.strptime("2026-11-09 10:30:00", "%Y-%m-%d %H:%M:%S"))
TODAY = "2026-11-09"
YESTERDAY = "2026-11-08"
TOMORROW = "2026-11-10"

FAILED, PASSED, SKIPPED = [], [], []


def skip(name: str, why: str) -> None:
    SKIPPED.append(name)
    print(f"skip  {name}: {why}")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if not cond else ""))


def reset_vault() -> None:
    for child in list(VAULT.iterdir()):
        if child.name == ".obsidian":
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
    E._reset_for_tests()


def write_note(rel: str, text: str) -> Path:
    p = VAULT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def read(rel: str) -> str:
    return (VAULT / rel).read_text(encoding="utf-8")


def ask(text: str):
    return Q.answer(text, sched=Stub(), now=NOW, peer="127.0.0.1", local=True)


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


OWNER_SENTENCE = ("create a new note called Workout Log, pin it, and add using "
                  "todays date that i used the punching bag")

#: What the owner's sentence must write, byte for byte.
OWNER_NOTE = ("---\n"
              "pinned: true\n"
              "date: " + TODAY + "\n"
              "---\n"
              "i used the punching bag\n")


# --------------------------------------------------------------------------
# 1. THE OWNER'S SENTENCE
# --------------------------------------------------------------------------
def t_the_owner_sentence_is_four_facts():
    reset_vault()
    gate = Gate()
    set_gate(gate)
    got = ask(OWNER_SENTENCE)
    check("owner: the sentence is answered by the fast path, not the model",
          got is not None and got.intent == "note_created",
          got.intent if got else "model")
    files = sorted(p.name for p in VAULT.glob("*.md"))
    check("owner: exactly ONE note is made, named Workout Log.md",
          files == ["Workout Log.md"], files)
    check("owner: the TITLE is not the whole sentence",
          "pin it" not in "".join(files) and "punching" not in "".join(files),
          files)
    if not (VAULT / "Workout Log.md").is_file():
        return
    check("owner: the note is pinned, dated today, and holds the body",
          read("Workout Log.md") == OWNER_NOTE, repr(read("Workout Log.md")))
    check("owner: NO card was asked (a NEW note stays card-free)",
          gate.calls == [], gate.calls)
    check("owner: the reply names the file and says it can be undone",
          "Workout Log.md" in got.reply and "You can undo it" in got.reply,
          got.reply)
    check("owner: the reply says pinned and dated",
          "pinned" in got.reply and TODAY in got.reply, got.reply)


def t_the_owner_note_can_be_undone():
    """The create recorded ONE undo receipt BEFORE the file existed."""
    reset_vault()
    set_gate(Gate())
    ask(OWNER_SENTENCE)
    if RC is None:
        skip("owner: undo removes the created note", "jarvis_receipts is not on this tree")
        return
    rows = RC.recent(50)
    mine = [r for r in rows if "Workout Log.md" in str(r.get("summary") or "")]
    if not mine:
        check("owner: the create recorded an undo receipt", False, rows)
        return
    check("owner: the create recorded an undo receipt",
          str(mine[0].get("tool_name") or "") == "notes_create", mine[0])
    RC.undo(str(mine[0].get("receipt_id") or ""))
    check("owner: one undo removes exactly the created note",
          not (VAULT / "Workout Log.md").exists())


# --------------------------------------------------------------------------
# 2. THE OLD RULES STAY (the control the brief asks for)
# --------------------------------------------------------------------------
def t_no_title_is_still_a_body_only_note():
    reset_vault()
    gate = Gate()
    set_gate(gate)
    got = ask("write a note for me about the gym trip")
    check("control: a body-only sentence still creates a note",
          got is not None and got.intent == "note_created",
          got.intent if got else "model")
    made = sorted(p.name for p in VAULT.glob("*.md"))
    check("control: its title is drawn from the words, as before",
          made == ["the gym trip.md"], made)
    check("control: its body is exactly the words, with NO front matter",
          made and read(made[0]) == "the gym trip",
          repr(read(made[0])) if made else "missing")
    check("control: NO card, as before", gate.calls == [], gate.calls)
    reset_vault()
    got = ask("create a note called Shopping with milk and eggs")
    check("control: 'called X with Y' is still title X and body Y",
          got is not None and got.intent == "note_created"
          and (VAULT / "Shopping.md").is_file()
          and read("Shopping.md") == "milk and eggs",
          repr(read("Shopping.md")) if (VAULT / "Shopping.md").is_file() else "missing")
    # The old named grammar is still there, and it agrees about this shape.
    m = Q._NOTE_CREATE_NAMED.fullmatch(Q.normalise("create a note called Shopping with milk and eggs"))
    check("control: the older named grammar still reads the same title and body",
          m is not None and m.group("name").strip() == "shopping"
          and (m.group("text") or "").strip() == "milk and eggs",
          m.groupdict() if m else "no match")


def t_title_and_body_keep_their_words():
    reset_vault()
    set_gate(Gate())
    got = ask("make a new note called Gym with went to the gym yesterday")
    check("control: 'yesterday' in the BODY stays in the body (no date property)",
          got is not None and got.intent == "note_created"
          and read("Gym.md") == "went to the gym yesterday",
          repr(read("Gym.md")) if (VAULT / "Gym.md").is_file() else "missing")
    got = ask("create a note called Salt and Pepper")
    made = sorted(p.name for p in VAULT.glob("*.md"))
    check("control: a title's own 'and' does not split it",
          got is not None and "Salt and Pepper.md" in made, made)
    got = ask("create a note called Notes on Physics with chapter one")
    check("control: a title's own 'on' does not split it",
          got is not None and (VAULT / "Notes on Physics.md").is_file()
          and read("Notes on Physics.md") == "chapter one",
          sorted(p.name for p in VAULT.glob("*.md")))


# --------------------------------------------------------------------------
# 3. PIN + ADD IN ONE SENTENCE
# --------------------------------------------------------------------------
def t_pin_and_add_in_one_sentence():
    reset_vault()
    gate = Gate()
    set_gate(gate)
    got = ask("create a note called Workout Log and add squats, pin it")
    check("pin+add: one sentence creates the note and the body",
          got is not None and got.intent == "note_created"
          and (VAULT / "Workout Log.md").is_file(),
          got.intent if got else "model")
    check("pin+add: the pin clause is not part of the body",
          read("Workout Log.md") == "---\npinned: true\n---\nsquats\n",
          repr(read("Workout Log.md")))
    check("pin+add: NO card (a NEW note stays card-free)",
          gate.calls == [], gate.calls)
    reset_vault()
    got = ask("create a note called Workout Log and add squats and pin it")
    check("pin+add: 'and pin it' at the end is read the same way",
          got is not None and read("Workout Log.md").endswith("squats\n")
          and "pinned: true" in read("Workout Log.md"),
          repr(read("Workout Log.md")))
    reset_vault()
    got = ask("write a note for me about the gym trip, pin it")
    check("pin+add: a body-only create can be pinned too",
          got is not None and got.intent == "note_created"
          and (VAULT / "the gym trip.md").is_file()
          and "pinned: true" in read("the gym trip.md"),
          repr(read("the gym trip.md")) if (VAULT / "the gym trip.md").is_file() else "missing")
    reset_vault()
    got = ask("write a note for me about how to pin it")
    check("pin+add: an ordinary topic keeps its words ('how to pin it')",
          got is not None and (VAULT / "how to pin it.md").is_file()
          and "pinned:" not in read("how to pin it.md"),
          repr(read("how to pin it.md")) if (VAULT / "how to pin it.md").is_file() else "missing")


# --------------------------------------------------------------------------
# 4. DATE WORDS BECOME THE NOTE'S DATE
# --------------------------------------------------------------------------
def t_date_words_become_the_notes_date():
    cases = (
        ("create a note called Gym using todays date with went to the gym", TODAY),
        ("create a note called Gym using today's date with went to the gym", TODAY),
        ("create a note called Gym dated yesterday with went to the gym", YESTERDAY),
        ("create a note called Gym using tomorrow with i will run", TOMORROW),
        ("create a note called Gym dated 2026-11-03 with went to the gym", "2026-11-03"),
        ("create a note called Gym dated 3 November with went to the gym", "2026-11-03"),
        ("create a note called Gym dated November 3rd with went to the gym", "2026-11-03"),
        ("create a note called Gym with went to the gym on 12/11/2026", "2026-12-11"),
    )
    for said, day in cases:
        reset_vault()
        gate = Gate()
        set_gate(gate)
        got = ask(said)
        text = read("Gym.md") if (VAULT / "Gym.md").is_file() else ""
        check(f"date: {said!r} writes date: {day}",
              got is not None and got.intent == "note_created"
              and ("date: " + day) in text,
              text or (got.intent if got else "model"))
        check("date: ... the date is the note's property, not body words",
              "date: " + day in text and "yesterday" not in text
              and "tomorrow" not in text and "todays" not in text, text)
        check("date: ... and NO card was asked", gate.calls == [], gate.calls)


def t_explicit_date_this_year_not_next():
    """A note records what a date WAS: no year means this year."""
    reset_vault()
    set_gate(Gate())
    ask("create a note called Gym dated 3 November with went to the gym")
    text = read("Gym.md") if (VAULT / "Gym.md").is_file() else ""
    check("date: '3 November' on 9 November is THIS year's 3 November",
          "date: 2026-11-03" in text, text)


# --------------------------------------------------------------------------
# 5. PIN / UNPIN AN EXISTING NOTE: ONE CARD, UNCHANGED PERMISSIONS
# --------------------------------------------------------------------------
def t_pin_and_unpin_an_existing_note_is_one_card():
    reset_vault()
    set_gate(Gate())
    ask("create a note called Workout Log and add squats")
    before = read("Workout Log.md")
    check("pin existing: the plain note starts with no front matter",
          before == "squats", repr(before))
    gate = Gate()
    set_gate(gate)
    got = ask("pin my Workout Log note")
    check("pin existing: the sentence rides the customize door",
          got is not None and got.intent == "note_customized",
          got.intent if got else "model")
    check("pin existing: exactly ONE card was asked",
          len(gate.calls) == 1, gate.calls)
    check("pin existing: the card's action is the existing edit_vault_note",
          gate.calls and gate.calls[0][0] == "edit_vault_note", gate.calls)
    check("pin existing: the note gained pinned: true and kept its body",
          "pinned: true" in read("Workout Log.md")
          and read("Workout Log.md").endswith("squats"),
          repr(read("Workout Log.md")))
    check("pin existing: the reply says it can be undone",
          got is not None and "You can undo it" in got.reply,
          got.reply if got else "")
    # Pinning twice is pinning once: no second card, nothing changed.
    gate2 = Gate()
    set_gate(gate2)
    got = ask("pin my Workout Log note")
    check("pin existing: pinning again asks NO card and changes nothing",
          got is not None and gate2.calls == [] and "pinned: true" in read("Workout Log.md"),
          f"{got.intent if got else 'model'} {gate2.calls}")
    # Unpin: one more card, and the note is byte-for-byte what it was.
    gate3 = Gate()
    set_gate(gate3)
    got = ask("unpin my Workout Log note")
    check("unpin existing: exactly ONE card was asked",
          got is not None and len(gate3.calls) == 1, gate3.calls)
    check("unpin existing: the property is gone and the note is as it was",
          read("Workout Log.md") == "squats", repr(read("Workout Log.md")))
    gate4 = Gate()
    set_gate(gate4)
    got = ask("unpin my Workout Log note")
    check("unpin existing: unpinning a note that is not pinned asks NO card",
          got is not None and gate4.calls == [], f"{got.intent if got else 'model'}")


def t_hidden_lists_and_the_permission_model():
    reset_vault()
    gate = Gate()
    set_gate(gate)
    old = Q._calendar_hidden
    try:
        Q._calendar_hidden = lambda: (True, "Words hidden.")
        got = ask(OWNER_SENTENCE)
        check("hidden: a NEW note is still created card-free",
              got is not None and got.intent == "note_created"
              and gate.calls == [], got.intent if got else "model")
        check("hidden: the reply names no title and no date",
              got is not None and "Workout Log" not in got.reply
              and TODAY not in got.reply, got.reply if got else "")
        check("hidden: the file is really written, pinned and dated",
              (VAULT / "Workout Log.md").is_file()
              and "pinned: true" in read("Workout Log.md"),
              sorted(p.name for p in VAULT.glob("*.md")))
        hidden_gate = Gate()
        set_gate(hidden_gate)
        got = ask("pin my Workout Log note")
        check("hidden: pinning an existing note is refused with NO card",
              got is not None and got.intent == "note_write_hidden"
              and hidden_gate.calls == [], got.intent if got else "model")
        check("hidden: ... and the refusal names no title",
              got is not None and "Workout Log" not in got.reply,
              got.reply if got else "")
        got = ask("unpin my Workout Log note")
        check("hidden: unpinning is refused the same way",
              got is not None and got.intent == "note_write_hidden"
              and hidden_gate.calls == [], got.intent if got else "model")
    finally:
        Q._calendar_hidden = old


# --------------------------------------------------------------------------
# 6. COLLISION AND ONE PATH
# --------------------------------------------------------------------------
def t_collision_is_refused_and_nothing_is_overwritten():
    reset_vault()
    set_gate(Gate())
    ask(OWNER_SENTENCE)
    first = read("Workout Log.md")
    gate = Gate()
    set_gate(gate)
    got = ask(OWNER_SENTENCE)
    check("collision: the same sentence twice is refused in words",
          got is not None and "already a note at Workout Log.md" in got.reply,
          got.reply if got else "model")
    check("collision: the first note is byte-for-byte untouched",
          read("Workout Log.md") == first, repr(read("Workout Log.md")))
    check("collision: NO card was asked and nothing was created",
          gate.calls == [] and sorted(p.name for p in VAULT.glob("*.md")) == ["Workout Log.md"],
          gate.calls)


def t_no_bulk_no_second_file():
    reset_vault()
    gate = Gate()
    set_gate(gate)
    got = ask("create notes called Workout Log and Gym")
    check("bulk: a request for several notes is not quietly done to the first",
          got is None or got.intent != "note_created"
          or not list(VAULT.glob("*.md")),
          f"{got.intent if got else 'model'} {sorted(p.name for p in VAULT.glob('*.md'))}")


# --------------------------------------------------------------------------
# 7. BOTH APPS (backend-side parity)
# --------------------------------------------------------------------------
def _chat_body(sentence: str, surface: str) -> dict:
    """The shape both apps POST to /api/chat (phone: ChatHistory.requestBody)."""
    return {"messages": [{"role": "user", "content": sentence,
                          "provenance": "typed"}],
            "has_image": False, "stream": True, "auto": True,
            "device": surface}


def t_both_apps_get_the_same_result():
    """The phone and the desktop both POST /api/chat; the same grammar answers."""
    reset_vault()
    set_gate(Gate())
    phone = Q.answer_turn(_chat_body(OWNER_SENTENCE, "phone"), now=NOW,
                          client_surface="phone")
    check("parity: the phone's own body shape creates the same note",
          phone is not None and phone.intent == "note_created"
          and (VAULT / "Workout Log.md").is_file(),
          phone.intent if phone else "model")
    check("parity: ... with the same pin and date",
          (VAULT / "Workout Log.md").read_text(encoding="utf-8") == OWNER_NOTE,
          repr(read("Workout Log.md")))
    check("parity: ... and the same reply facts",
          phone is not None and "pinned" in phone.reply and TODAY in phone.reply,
          phone.reply if phone else "")
    # The phone's Notes plate reads the vault through these two routes; the
    # note (with its pin and date) is what both apps' editors then show. The
    # PIN is a note property and neither app draws a pin control yet - that is
    # said plainly in docs/JARVIS-API.md 170.11.
    code, listing = E.handle_list("")
    paths = [str(r.get("path") or "") for r in (listing.get("notes") or [])]
    check("parity: /api/notes/list (both apps' Notes plate) lists the note",
          code == 200 and "Workout Log.md" in paths, paths)
    code, one = E.handle_read("path=" + urllib.parse.quote("Workout Log.md", safe=""))
    check("parity: /api/notes/read returns the pinned, dated note text",
          code == 200 and one.get("text") == OWNER_NOTE, one)
    # A second, different note through the desktop's body, so both surfaces
    # really go through the same answer: no second call can collide.
    reset_vault()
    set_gate(Gate())
    desktop = Q.answer_turn(
        _chat_body("create a note called Gym dated yesterday with went to the gym",
                   "desktop"), now=NOW, client_surface="desktop")
    check("parity: the desktop's body shape creates its note too",
          desktop is not None and desktop.intent == "note_created"
          and (VAULT / "Gym.md").is_file(),
          desktop.intent if desktop else "model")
    check("parity: ... with the same date reading",
          "date: " + YESTERDAY in read("Gym.md"), repr(read("Gym.md")))


# --------------------------------------------------------------------------
# 8. RECORDS
# --------------------------------------------------------------------------
def _same_text(a: Path, b: Path) -> bool:
    try:
        return (a.read_bytes().replace(b"\r\n", b"\n")
                == b.read_bytes().replace(b"\r\n", b"\n"))
    except OSError:
        return False


def t_twins_and_docs_agree():
    for name in ("jarvis_notes_edit.py", "jarvis_quick.py"):
        check(f"records: {name} has a byte-identical published twin",
              _same_text(HERE / name, REPO / "jarvis-backend" / name),
              f"{HERE/name} vs {REPO/'jarvis-backend'/name}")
    api = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    check("docs: JARVIS-API.md documents the smart create reading",
          "Smart note creation" in api or "smart note creation" in api.lower(),
          "section heading not found")
    for needle in ("pinned: true", "date:"):
        check(f"docs: ... it names {needle!r}", needle in api)
    check("docs: ... it names the three explicit title words",
          all(w in api for w in ("`called`", "`titled`", "`named`")),
          "one of called/titled/named is missing")
    check("docs: ... it says the permission model is unchanged",
          "card-free" in api and "edit_vault_note" in api)


# --------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------
TESTS = [
    t_the_owner_sentence_is_four_facts,
    t_the_owner_note_can_be_undone,
    t_no_title_is_still_a_body_only_note,
    t_title_and_body_keep_their_words,
    t_pin_and_add_in_one_sentence,
    t_date_words_become_the_notes_date,
    t_explicit_date_this_year_not_next,
    t_pin_and_unpin_an_existing_note_is_one_card,
    t_hidden_lists_and_the_permission_model,
    t_collision_is_refused_and_nothing_is_overwritten,
    t_no_bulk_no_second_file,
    t_both_apps_get_the_same_result,
    t_twins_and_docs_agree,
]


def main():
    print("=" * 74)
    print("jarvis_quick + jarvis_notes_edit - smart note creation (2026-11-09)")
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
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
