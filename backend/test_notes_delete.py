"""test_notes_delete.py - delete one note, or many, into the vault's trash.

    python -B backend/test_notes_delete.py

WHY THIS SUITE EXISTS (the owner's request, 2026-11-23, in their words): "i want
Jarvis to be able to delete obsidian notes , even multiple at a time. but it
will always require a card with fingerprint or windows hello confirmation", and
"it will list the names of the notes it wants to delete (from my request) in the
card and the conversation as well". Asked which shape a delete takes, they chose
the vault's own trash folder over "gone for good", and twenty notes as the most
in one go. This suite pins the four halves of that:

1. IT ALWAYS MEETS A PERSON. A delete is raised under its own gate action,
   `delete_vault_notes`, whose risk row says it cannot be undone by an app and
   stays on this PC - so `jarvis_owner_check` sends the PC to Windows Hello and
   the asking phone to its own signed approval. The action is NOT in
   `PC_ONLY_ACTIONS` (that would refuse the phone outright, and the owner asked
   for the phone's fingerprint too), it has written card words (a Windows Hello
   prompt cannot name an unlabelled action), and a denial answers the one batch
   rather than writing a standing rule.
2. THE CARD NAMES EVERY NOTE. One note or twenty, the card's own line lists all
   of them, and the job's answer carries the same names back to the conversation.
   While the lists are hidden the names stay out of BOTH - counts only.
3. NOTHING MOVES BEFORE THE CARD, AND THE BATCH IS ALL OR NOTHING. A denied
   card, a note that changed while the card waited, or a failure halfway through
   leaves every note exactly where it was (a note already moved is put back).
4. THE NOTES GO TO `.trash`, NOT INTO NOTHING. Each one keeps its relative path
   and every byte, `<vault>/.trash/<same path>`; a name already there gets
   " (2)", never an overwrite. Nothing is ever written over.

THE CHAT DOOR is `jarvis_quick`'s own: "delete my note Shopping", "delete notes
Shopping, Workout and Ideas", a name with "and" in it, a topic ("delete all
notes about the trip" - asks for names instead of guessing), and the sentences
that must NOT become a delete ("delete my 5pm reminder", "delete the timer",
"delete this line").

RUNS ANYWHERE: the vault, the settings folder and the receipts DB are temporary
folders; `jarvis_framework` and the gate's `check` are stand-ins; no model, no
network, no owner's file. The real `jarvis_gate` module is imported for its
TABLES only (never `check`), so the risk row is the shipped one.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_notes_edit.py", "jarvis_notes.py", "jarvis_quick.py",
                "jarvis_card_words.py")

# ── a temporary vault, and settings that are never the owner's ──────────────
_TMP = Path(tempfile.gettempdir()) / ("jarvis-notes-delete-" + secrets.token_hex(6))
_TMP.mkdir(parents=True, exist_ok=True)
VAULT = _TMP / "vault"
(VAULT / ".obsidian").mkdir(parents=True, exist_ok=True)
CONF = _TMP / "config"
CONF.mkdir(exist_ok=True)
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONF)
os.environ["JARVIS_RECEIPTS_DB"] = str(_TMP / "receipts.db")
os.environ["JARVIS_OBSIDIAN_VAULT"] = str(VAULT)
os.environ.pop("JARVIS_BACKEND", None)

FW = types.ModuleType("jarvis_framework")
FW.CONFIG_DIR = CONF
FW.LOG_DIR = _TMP / "log"
FW_STATE = {"notes": {"obsidian": {"vault_directory": str(VAULT)}}}
FW.load_framework = lambda: json.loads(json.dumps(FW_STATE))
FW.action_tier = lambda action: "ask"
FW.audit_log = lambda event, detail: AUDIT.append((event, detail))
AUDIT = []
sys.modules["jarvis_framework"] = FW

# The REAL gate, loaded from the published base before the stand-in replaces it
# in sys.modules: its tables are the safety claim this suite makes, so they must
# be the shipped ones, not a fixture. (`jarvis_gate.py` lives only in
# `jarvis-backend/`, the published base, so it is loaded by path.)
import importlib.util as _ilu  # noqa: E402

_gate_path = REPO / "jarvis-backend" / "jarvis_gate.py"
_spec = _ilu.spec_from_file_location("_shipped_gate", _gate_path)
REAL_GATE = _ilu.module_from_spec(_spec)
# dataclasses resolve their own module through sys.modules, so the module has to
# be registered under the temporary name while it is executed.
sys.modules["_shipped_gate"] = REAL_GATE
_spec.loader.exec_module(REAL_GATE)


class Verdict:
    """The gate's own answer shape: allowed, tier, outcome, reason."""

    def __init__(self, allowed: bool, tier: str, outcome: str, reason: str = ""):
        self.allowed = allowed
        self.tier = tier
        self.outcome = outcome
        self.reason = reason


GATE = {"allowed": True, "outcome": "approved", "tier": "ask", "calls": [],
        "cards": [], "entered": None, "release": None}


def gate_check(action, detail=None, prompt="", **kwargs):
    GATE["calls"].append(action)
    GATE["cards"].append((action, detail, prompt))
    entered, release = GATE.get("entered"), GATE.get("release")
    if entered is not None and release is not None:
        entered.set()
        release.wait(20)
    return Verdict(GATE["allowed"], GATE["tier"], GATE["outcome"])


GATE_MODULE = types.ModuleType("jarvis_gate")
GATE_MODULE.check = gate_check
GATE_MODULE.taint_active = lambda: False
GATE_MODULE.pending = lambda: []
sys.modules["jarvis_gate"] = GATE_MODULE

import jarvis_card_words as CW  # noqa: E402
import jarvis_notes as N  # noqa: E402
import jarvis_notes_edit as E  # noqa: E402
import jarvis_quick as Q  # noqa: E402

FAILED, PASSED = [], []


class Stub:
    """The scheduler stand-in `answer()` needs for bookkeeping only.

    Any method this suite did not think of answers an empty list: the point of
    the stub is that the note lane never reaches a real scheduler, and a missing
    method here must not look like a failure of the lane.
    """

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: []

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


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   A throw-away vault
# --------------------------------------------------------------------------
def put(rel: str, text: str = "the note's own words\n", *, where: Path = None) -> Path:
    full = (where or VAULT) / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    # write_bytes, not write_text: a byte-for-byte comparison must not depend on
    # Windows' newline translation.
    full.write_bytes(text.encode("utf-8"))
    return full


def here(rel: str) -> bool:
    return (VAULT / rel).is_file()


def trashed(rel: str) -> bool:
    return (VAULT / ".trash" / rel).is_file()


def read(rel: str) -> bytes:
    return (VAULT / rel).read_bytes()


def reset_all() -> None:
    for child in list(VAULT.iterdir()):
        if child.name == ".obsidian":
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
    E._reset_for_tests()
    AUDIT.clear()
    GATE.update(allowed=True, outcome="approved", tier="ask", calls=[], cards=[],
                entered=None, release=None)


def ask(text: str):
    return Q.answer(text, sched=Stub(), now=time.time(),
                    peer="127.0.0.1", local=True)


# --------------------------------------------------------------------------
# 1. It always meets a person
# --------------------------------------------------------------------------
def t_the_action_is_its_own_and_the_gate_knows_it():
    check("the delete is its own gate action, not the ordinary note edit",
          E.DELETE_ACTION == "delete_vault_notes" and E.DELETE_ACTION != E.ACTION,
          E.DELETE_ACTION)
    row = REAL_GATE.risk_for(E.DELETE_ACTION)
    check("... the gate classifies it (no unclassified fallback on the card)",
          row["classified"] is True, row)
    check("... it cannot be put back by an app", row["reversible"] == "no", row)
    check("... it stays on this PC", row["reach"] == "local", row)
    check("... so a swipe cannot approve it", row["swipe_ok"] is False, row)
    check("... its words are about the trash folder, not about bytes being lost",
          ".trash" in row["why"] and "Explorer" in row["why"], row["why"])
    check("... a denial answers that one batch, not a standing rule",
          E.DELETE_ACTION in REAL_GATE._NO_RULE_FROM_DENIAL)
    owner = (HERE / "jarvis_owner_check.py").read_text(encoding="utf-8")
    block = owner.split("PC_ONLY_ACTIONS = frozenset(", 1)[-1].split("})", 1)[0]
    check("... and the phone may still approve it: it is not PC-only",
          E.DELETE_ACTION not in block)
    check("... the card has written words a Windows Hello prompt can name",
          CW.has_written_title(E.DELETE_ACTION) is True)
    title = CW.title_for(E.DELETE_ACTION)
    check("... and the title says it deletes a note", "delete" in title.lower()
          and "note" in title.lower(), title)
    for word in ("Windows", "Hello", "fingerprint"):
        check(f"... the waiting answer names {word}",
              word in Q.NOTE_DELETE_WAITING_SAID, Q.NOTE_DELETE_WAITING_SAID)


# --------------------------------------------------------------------------
# 2. Nothing moves before the card; the card names every note
# --------------------------------------------------------------------------
def t_a_denied_card_deletes_nothing():
    reset_all()
    put("Shopping.md")
    before = read("Shopping.md")
    GATE.update(allowed=False, outcome="denied")
    code, out = E.handle_delete({"paths": ["Shopping.md"]}, gate_check=gate_check,
                               wait_s=5)
    check("a denied card answers 200 with a denied state",
          code == 200 and out.get("state") == "denied", (code, out))
    check("... in the module's own words",
          out.get("message") == "You said no, so no note was deleted.",
          out.get("message"))
    check("... the note is still there, byte for byte",
          here("Shopping.md") and read("Shopping.md") == before)
    check("... and no trash folder was made at all",
          not (VAULT / ".trash").exists())
    check("... the gate was asked once, under the delete action",
          GATE["calls"] == [E.DELETE_ACTION], GATE["calls"])


def t_the_card_names_every_note():
    reset_all()
    put("Shopping.md")
    put("Workout/Log.md")
    put("Ideas.md")
    GATE.update(allowed=False, outcome="denied")
    E.handle_delete({"paths": ["Shopping.md", "Workout/Log.md", "Ideas.md"]},
                    gate_check=gate_check, wait_s=5)
    action, detail, prompt = GATE["cards"][-1]
    for name in ("Shopping.md", "Workout/Log.md", "Ideas.md"):
        check(f"the card's own line names {name}", name in prompt, prompt)
    check("... it says how many, too", "3 notes" in prompt, prompt)
    check("... the detail carries every path",
          detail.get("paths") == ["Shopping.md", "Workout/Log.md", "Ideas.md"], detail)
    check("... and says there is no undo, and that it deletes",
          detail.get("undo") is False and detail.get("deletes") is True
          and detail.get("count") == 3, detail)
    check("... and says the notes go to the trash",
          detail.get("trash") is True, detail)


def t_hidden_lists_keep_the_names_out_of_the_card():
    reset_all()
    put("Secret.md")
    put("Other.md")
    real = E._hidden_lists
    E._hidden_lists = lambda: True
    try:
        GATE.update(allowed=False, outcome="denied")
        code, out = E.handle_delete({"paths": ["Secret.md", "Other.md"]},
                                    gate_check=gate_check, wait_s=5)
        action, detail, prompt = GATE["cards"][-1]
        check("while the lists are hidden the card names no note",
              "Secret.md" not in prompt and "Other.md" not in prompt, prompt)
        check("... it says the count instead", "2 notes" in prompt, prompt)
        check("... and the detail says the lists were hidden",
              detail.get("hidden_lists") is True and "paths" not in detail, detail)
        check("... the answer names none either",
              "Secret.md" not in str(out.get("message") or ""), out.get("message"))
    finally:
        E._hidden_lists = real


# --------------------------------------------------------------------------
# 3. The notes really move into .trash
# --------------------------------------------------------------------------
def t_an_approved_card_moves_the_notes_into_the_trash():
    reset_all()
    put("Shopping.md", "milk and eggs\n")
    put("Workout/Log.md", "squats\n")
    before = {"Shopping.md": read("Shopping.md"),
              "Workout/Log.md": read("Workout/Log.md")}
    code, out = E.handle_delete({"paths": ["Shopping.md", "Workout/Log.md"]},
                               gate_check=gate_check, wait_s=5)
    check("an approved card answers 200 with a saved state",
          code == 200 and out.get("state") == "saved", (code, out))
    check("... both notes left the vault",
          not here("Shopping.md") and not here("Workout/Log.md"))
    check("... and are in .trash at the same relative path",
          trashed("Shopping.md") and trashed("Workout/Log.md"))
    check("... with every byte kept",
          (VAULT / ".trash" / "Shopping.md").read_bytes() == before["Shopping.md"]
          and (VAULT / ".trash" / "Workout" / "Log.md").read_bytes()
          == before["Workout/Log.md"])
    said = str(out.get("message") or "")
    for name in ("Shopping.md", "Workout/Log.md"):
        check(f"the answer names {name}", name in said, said)
    check("... and says where they went", ".trash" in said, said)
    check("... the job's status carries the count and the names",
          out.get("count") == 2
          and out.get("paths") == ["Shopping.md", "Workout/Log.md"], out)
    check("... the audit log has the delete",
          any(kind.endswith("deleted") for kind, _d in AUDIT), AUDIT)


def t_a_name_already_in_the_trash_is_never_overwritten():
    reset_all()
    put("Shopping.md", "new words\n")
    put(".trash/Shopping.md", "older words\n")
    code, out = E.handle_delete({"paths": ["Shopping.md"]}, gate_check=gate_check,
                               wait_s=5)
    check("a note whose trash name is taken still deletes", code == 200
          and out.get("state") == "saved", (code, out))
    check("... the older copy is untouched",
          (VAULT / ".trash" / "Shopping.md").read_text(encoding="utf-8")
          == "older words\n")
    check("... and the new one got the next free name",
          (VAULT / ".trash" / "Shopping (2).md").read_text(encoding="utf-8")
          == "new words\n")


def t_two_notes_whose_trash_names_collide_get_separate_targets():
    """The audit's F1: both rows used to be handed the SAME free name, because
    the first move has not happened when the second target is chosen - the
    second `os.replace` then overwrote the first note while the reply said both
    moved. `.trash/Foo.md` existing is what pushes both rows onto `Foo (2)`."""
    reset_all()
    put("Foo.md", "first\n")
    put("Foo (2).md", "second\n")
    put(".trash/Foo.md", "older\n")
    code, out = E.handle_delete({"paths": ["Foo.md", "Foo (2).md"]},
                               gate_check=gate_check, wait_s=5)
    check("two notes whose trash names would collide both delete", code == 200
          and out.get("state") == "saved", (code, out))
    check("... the older copy is untouched",
          (VAULT / ".trash" / "Foo.md").read_text(encoding="utf-8") == "older\n")
    check("... the first note took the next free name",
          (VAULT / ".trash" / "Foo (2).md").read_text(encoding="utf-8") == "first\n")
    check("... and the second did not overwrite it",
          (VAULT / ".trash" / "Foo (2) (2).md").read_text(encoding="utf-8")
          == "second\n")


def t_a_failure_halfway_puts_the_moved_notes_back():
    reset_all()
    put("A.md", "first\n")
    put("sub/B.md", "second\n")
    # `sub` inside the trash is a FILE, so making room for B fails after A has
    # already moved - the one window the put-back exists for.
    (VAULT / ".trash").mkdir()
    (VAULT / ".trash" / "sub").write_text("not a folder\n", encoding="utf-8")
    code, out = E.handle_delete({"paths": ["A.md", "sub/B.md"]},
                               gate_check=gate_check, wait_s=5)
    check("a failed delete answers a failed state",
          code == 200 and out.get("state") == "failed", (code, out))
    check("... the note that had moved is back",
          here("A.md") and read("A.md") == b"first\n")
    check("... the note that never moved is still there", here("sub/B.md"))
    check("... and the answer says the notes were put back",
          "put back" in str(out.get("message") or ""), out.get("message"))


def t_a_note_that_changed_after_the_card_stops_the_batch():
    reset_all()
    put("A.md", "first\n")
    put("B.md", "second\n")
    GATE.update(entered=threading.Event(), release=threading.Event())
    got = {}

    def run():
        got["out"] = E.handle_delete({"paths": ["A.md", "B.md"]},
                                     gate_check=gate_check, wait_s=0.05)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    GATE["entered"].wait(5)
    put("B.md", "someone else's words\n")      # the card is on screen
    GATE["release"].set()
    thread.join(10)
    code, out = got.get("out", (0, {}))
    check("a note that changed while the card waited stops the batch",
          out.get("state") == "failed", (code, out))
    check("... in words that name the note",
          "B.md" in str(out.get("message") or ""), out.get("message"))
    check("... and NOTHING moved, not even the note that did not change",
          here("A.md") and here("B.md") and not (VAULT / ".trash" / "A.md").exists())


# --------------------------------------------------------------------------
# 4. Refusals happen before any card
# --------------------------------------------------------------------------
def t_refusals_before_any_card():
    reset_all()
    put("Shopping.md")
    put("Shopping.txt", "text note\n")
    put("Photo.png", "not a note\n")
    cases = [
        ("nothing named", {"paths": []}, 400),
        ("not a list at all", {"paths": 3}, 400),
        ("a hidden folder", {"paths": [".obsidian/x.md"]}, 400),
        ("a path outside the vault", {"paths": ["../outside.md"]}, 400),
        ("not a note file", {"paths": ["Photo.png"]}, 400),
        ("a note that is not there", {"paths": ["Gone.md"]}, 404),
        ("the same note twice", {"paths": ["Shopping.md", "Shopping.md"]}, 400),
    ]
    for name, body, want in cases:
        code, out = E.handle_delete(body, gate_check=gate_check, wait_s=0.05)
        check(f"{name} is refused with {want}, before any card",
              code == want, (code, out))
    check("... and the gate was never asked for any of them",
          GATE["calls"] == [], GATE["calls"])
    too_many = {"paths": [f"n{i}.md" for i in range(E.MAX_DELETE + 1)]}
    code, out = E.handle_delete(too_many, gate_check=gate_check, wait_s=0.05)
    check(f"more than {E.MAX_DELETE} notes is refused with 400 and the number",
          code == 400 and str(E.MAX_DELETE) in str(out.get("error") or ""),
          (code, out))
    check("... and that raised no card either", GATE["calls"] == [], GATE["calls"])


# --------------------------------------------------------------------------
# 5. The chat door
# --------------------------------------------------------------------------
def t_one_named_note_is_deleted_from_chat():
    reset_all()
    put("Shopping.md", "milk\n")
    got = ask("delete my note Shopping")
    check("'delete my note Shopping' is the note-delete intent",
          got is not None and got.intent in ("note_deleted", "note_delete_waiting"),
          got.intent if got else "the model")
    reply = got.reply if got else ""
    check("... the reply names the note", "Shopping.md" in reply, reply)
    check("... and says it moved", "Moved" in reply, reply)
    check("... the note really left the vault", not here("Shopping.md"))
    check("... and is in the trash", trashed("Shopping.md"))
    check("... under the delete action, once",
          GATE["calls"] == [E.DELETE_ACTION], GATE["calls"])


def t_several_named_notes_are_deleted_at_once():
    reset_all()
    for rel in ("Shopping.md", "Workout.md", "Ideas.md"):
        put(rel)
    got = ask("delete notes Shopping, Workout and Ideas")
    reply = got.reply if got else ""
    check("a list of three names is one delete",
          got is not None and got.intent in ("note_deleted", "note_delete_waiting"),
          got.intent if got else "the model")
    for rel in ("Shopping.md", "Workout.md", "Ideas.md"):
        check(f"... the reply names {rel}", rel in reply, reply)
        check(f"... and {rel} is gone", not here(rel))
        check(f"... and {rel} is in the trash", trashed(rel))
    check("... one card for the whole batch",
          GATE["calls"] == [E.DELETE_ACTION], GATE["calls"])


def t_a_name_with_and_in_it_is_one_note():
    reset_all()
    put("Salt and Pepper.md", "grinder\n")
    got = ask("delete my Salt and Pepper note")
    check("a note whose own name holds 'and' is read as ONE note",
          got is not None and got.intent in ("note_deleted", "note_delete_waiting"),
          got.intent if got else "the model")
    check("... and it is the one that was deleted",
          not here("Salt and Pepper.md") and trashed("Salt and Pepper.md"))


def t_an_ambiguous_or_missing_name_deletes_nothing():
    reset_all()
    put("A/Note.md")
    put("B/Note.md")
    got = ask("delete the Note note")
    reply = got.reply if got else ""
    check("an ambiguous name answers in words, never a guess",
          got is not None and got.intent == "note_delete_refused",
          got.intent if got else "the model")
    check("... it says how many notes matched", "matches 2 notes" in reply, reply)
    check("... it says nothing was deleted", "nothing was deleted" in reply, reply)
    check("... nothing was deleted", here("A/Note.md") and here("B/Note.md"))
    check("... and no card was raised", GATE["calls"] == [], GATE["calls"])
    reset_all()
    got = ask("delete my note Nosuchnote")
    reply = got.reply if got else ""
    check("a name that is not there answers in words",
          got is not None and got.intent == "note_delete_refused",
          got.intent if got else "the model")
    check("... saying no note by that name", "could not find a note" in reply, reply)
    check("... and nothing was deleted", "nothing was deleted" in reply, reply)
    check("... and no card was raised", GATE["calls"] == [], GATE["calls"])


def t_sentences_that_are_not_a_note_delete_stay_where_they_were():
    reset_all()
    for text in ("delete my 5pm reminder", "delete the timer",
                 "delete my alarm", "cancel my reminder"):
        got = ask(text)
        check(f"{text!r} is not a note delete",
              got is None or got.intent != "note_delete",
              got.intent if got else "the model")
    got = ask("delete this line")
    check("'delete this line' is the line refusal, not a note delete",
          got is not None and got.intent == "note_line_delete_refused",
          got.intent if got else "the model")
    check("... and its words say a line is still not deletable",
          "Deleting a line inside a note is not built"
          in (got.reply if got else ""), got.reply if got else "")


def t_a_topic_or_no_name_asks_for_names():
    reset_all()
    put("Trip 2026.md")
    got = ask("delete all notes about the trip")
    check("a topic is not guessed at: the lane asks for names",
          got is not None and got.intent == "note_delete_ask",
          got.intent if got else "the model")
    check("... in words that ask for the notes by name",
          "Name the notes" in (got.reply if got else ""),
          got.reply if got else "")
    check("... and nothing was deleted", here("Trip 2026.md"))
    check("... and no card was raised", GATE["calls"] == [], GATE["calls"])
    got = ask("delete a note")
    check("a delete with no name asks which notes",
          got is not None and got.intent == "note_delete_ask",
          got.intent if got else "the model")


def t_the_lane_caps_a_batch_at_the_module_limit():
    reset_all()
    names = [f"N{i:02d}" for i in range(1, E.MAX_DELETE + 2)]
    for name in names:
        put(name + ".md")
    got = ask("delete notes " + ", ".join(names))
    check(f"a sentence naming more than {E.MAX_DELETE} notes asks instead",
          got is not None and got.intent == "note_delete_ask",
          got.intent if got else "the model")
    check("... and says the limit", str(E.MAX_DELETE) in (got.reply if got else ""),
          got.reply if got else "")
    check("... and deleted none of them",
          all(here(n + ".md") for n in names))
    check("... and raised no card", GATE["calls"] == [], GATE["calls"])


def t_hidden_lists_refuse_from_chat_too():
    reset_all()
    put("Secret.md")
    real = Q._notes_write_hidden
    Q._notes_write_hidden = lambda: True
    try:
        got = ask("delete my note Secret")
        check("while the lists are hidden a delete is refused in words",
              got is not None and got.intent == "note_write_hidden",
              got.intent if got else "the model")
        check("... nothing was deleted", here("Secret.md"))
        check("... and no card was raised", GATE["calls"] == [], GATE["calls"])
    finally:
        Q._notes_write_hidden = real


# --------------------------------------------------------------------------
# 6. The wiring the two apps read
# --------------------------------------------------------------------------
def t_the_route_is_registered():
    check("the delete route is in POST_PATHS",
          E.DELETE_PATH == "/api/notes/delete" and E.DELETE_PATH in E.POST_PATHS,
          E.POST_PATHS)
    source = (HERE / "jarvis_notes_edit.py").read_text(encoding="utf-8")
    check("... and install() dispatches it",
          "route == DELETE_PATH" in source and "handle_delete(body)" in source)
    check("... the install line the plugin prints mentions delete",
          "delete up to twenty notes" in source)
    check("the change-status answer can carry the names and the count",
          '"count", "paths"' in source)


def t_the_lane_lists_its_new_answers():
    source = (HERE / "jarvis_quick.py").read_text(encoding="utf-8")
    for name in ("note_delete_ask", "note_delete_refused",
                 "note_line_delete_refused"):
        check(f"{name} is in the read-only intent list", f'"{name}"' in source)
    check("the delete's own answers are NOT listed as read-only",
          '"note_delete_waiting",' not in source and '"note_deleted",' not in source)


def main() -> int:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("t_") and callable(v)]
    for test in tests:
        print("\n" + test.__name__.replace("t_", "", 1).replace("_", " "))
        try:
            test()
        except Exception:                                   # noqa: BLE001
            import traceback
            traceback.print_exc()
            FAILED.append(test.__name__ + " (raised)")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print("  FAILED: " + name)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
