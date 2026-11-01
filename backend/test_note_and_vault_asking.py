"""test_note_and_vault_asking.py - "make a note" and "organize my notes" asked in chat.

    python -B backend/test_note_and_vault_asking.py

WHY THIS SUITE EXISTS (the owner's field test of 2026-10-31, live HUD):
"make a note: X" answered "I shall record the instruction" and wrote nothing
(the note tools are off in `[tools].enabled` and the fast path had no note
grammar); "organize my notes" and "organize my Obsidian vault with tags and
Maps of Content" were promises (the organizer exists and is off by default,
but had no chat door); and create/rename/delete plus Obsidian theme/CSS/
templates were invented (none of it is built). This suite pins the fixed
behaviour, on a temporary vault, with a fake gate - no model, no network, no
owner's file:

1. THE NOTE PATH USES THE EXISTING CAPTURE MODULE. Six owner shapes ("make a
   note: X", "make a note X", "note that X", "jot down X", "add a note: X",
   "add to my daily note: X", "add to today's note: X") each append the owner's
   exact words to `<vault>/<today>.md`, and the answer is the module's own
   sentence naming the file ("Filed in Obsidian, <file>."). No new tool and no
   new route: the FastPath calls `jarvis_note_capture.capture("obsidian", ...)`,
   which is the same plan/gate/run the note tools and the phone widget use.
2. THE GUARDIAN GOES FIRST. Appending to an EXISTING daily note calls
   `jarvis_notes.snapshot_vault_before_write` before the append; when that copy
   is refused the answer is the module's own refusal sentence and the file is
   byte-for-byte unchanged.
3. NOTHING IS WRITTEN WITHOUT THE GATE. A denied card files nothing and says
   the module's "You said no, so nothing was written." The file does not exist
   afterwards (or is unchanged).
4. THE ASK-AFTER-OUTSIDE-TEXT RULE IS PRESERVED. When the conversation is
   latched as having read outside text (`jarvis_gate.taint_active()`), the card
   is asked under `write_notes_after_outside_text` - the same action the agent
   uses - not under `append_obsidian_daily`; and a refusal still writes nothing.
5. THE ORGANIZER ANSWERS FROM ITS REAL STATE. Off: its own sentence ("The vault
   organizer is off. Turn it on first; it is off by default and turning it on
   is one approval card."), plus that the plan is a dry run and the one card.
   On: the module's own read-only plan description (scheme words and counts)
   and the writer's one-card / never-deletes rule. The vault tree is hashed
   before and after and must be identical: the plan is a genuine dry run.
6. THE SWITCH IS THE EXISTING ONE CARD. "turn on the vault organizer" raises
   ONE card through the module's own `handle_post` switch route (its
   `change_own_config` action); the answer says the switch stays off until the
   owner approves, and it really stays off until the fake gate says yes.
7. THE REFUSALS STAY HONEST, and the new WRITES are the wave-1 slice: rename
   and delete a note are still refused word for word (the notes editor's own
   limit), Obsidian theme/CSS/templates/customisation stays "not one of my
   features", and "create a new note called Shopping" now really creates ONE
   note through the notes-editor route (one edit_vault_note card, no overwrite,
   undo receipt) instead of promising.
8. NO OVER-CAPTURE: "remind me to call Sam at 5pm" stays a reminder, "organize
   my desk" is still the model's, "what does my Welcome note say?" is not a
   note write, and the two earlier lanes' fixes still hold ("what can I change
   in settings" is settings_help; "what can I edit in my notes?" is the
   catalogue's capability answer).

RUNS ANYWHERE: the vault, settings folder, guardian store and receipts DB are
temporary folders; `jarvis_framework` and `jarvis_gate` are stand-ins; nothing
touches the owner's PC and no model is called.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import secrets
import shutil
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_note_capture.py", "jarvis_vault_organizer.py",
                "jarvis_notes.py", "jarvis_quick.py")

# ── a temporary vault, and settings that are never the owner's ──────────────
_TMP = Path(tempfile.gettempdir()) / ("jarvis-note-asking-" + secrets.token_hex(6))
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

# ── a stub jarvis_framework, so nothing reads the owner's real settings ─────
FW = types.ModuleType("jarvis_framework")
FW.CONFIG_DIR = CONF
FW.LOG_DIR = _TMP / "log"
FW_STATE = {"notes": {"obsidian": {"vault_directory": str(VAULT)}},
            "vault_organizer": {"enabled": False}}
FW.load_framework = lambda: json.loads(json.dumps(FW_STATE))
FW.action_tier = lambda action: "ask" if action == "change_own_config" else "auto"
AUDIT = []
FW.audit_log = lambda event, detail: AUDIT.append((event, detail))
sys.modules["jarvis_framework"] = FW


class Verdict:
    """The gate's own answer shape: allowed, tier, outcome, reason."""

    def __init__(self, allowed: bool, tier: str, outcome: str, reason: str = ""):
        self.allowed = allowed
        self.tier = tier
        self.outcome = outcome
        self.reason = reason


GATE = {"tainted": False, "allowed": True, "outcome": "approved",
        "tier": "auto", "calls": [], "explode": False}


def gate_check(action, detail=None, prompt="", **kwargs):
    GATE["calls"].append(action)
    if GATE["explode"]:
        raise RuntimeError("gate exploded")
    if GATE["tainted"] and action != "write_notes_after_outside_text":
        # A real gate would not receive this from the quick path; failing here
        # proves the escalation is what made the call.
        return Verdict(False, "ask", "refused", "not escalated")
    return Verdict(GATE["allowed"], GATE["tier"], GATE["outcome"])


GATE_MODULE = types.ModuleType("jarvis_gate")
GATE_MODULE.check = gate_check
GATE_MODULE.taint_active = lambda: bool(GATE["tainted"])
sys.modules["jarvis_gate"] = GATE_MODULE

import jarvis_note_capture as NC  # noqa: E402
import jarvis_notes as N  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_vault_organizer as V  # noqa: E402

FAILED, PASSED = [], []
TODAY = dt.date.today()
TODAY_NOTE, _TODAY_WHY = NC.daily_note_path(VAULT, TODAY)
TODAY_NOTE = Path(TODAY_NOTE)


class Stub:
    """The scheduler stand-ins answer() uses for bookkeeping only."""

    def mark_command(self, text):
        pass

    def forget_set(self, conversation):
        pass

    def note_set(self, *a, **k):
        pass

    def last_set(self, *a, **k):
        return None

    def add_at(self, kind, at, text, source="quick"):
        return {"id": "stub-" + kind, "text": text, "due": at, "kind": kind}


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def reset_vault() -> None:
    for child in list(VAULT.iterdir()):
        if child.name == ".obsidian":
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


def reset_gate(*, tainted=False, allowed=True, outcome="approved",
               tier="auto") -> None:
    GATE.update(tainted=tainted, allowed=allowed, outcome=outcome, tier=tier,
                calls=[], explode=False)


def reset_all(*, organizer_on=False, tainted=False) -> None:
    reset_vault()
    reset_gate(tainted=tainted)
    V.reset_for_tests()
    try:
        V.state_path().unlink()
    except FileNotFoundError:
        pass
    if organizer_on:
        V.set_enabled(True)


def tree(root: Path) -> list:
    """Every file under `root` as (relative path, sha256) - the read-only check."""
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out.append((p.relative_to(root).as_posix(),
                        hashlib.sha256(p.read_bytes()).hexdigest()))
    return out


def ask(text: str):
    return Q.answer(text, sched=Stub(), now=time.time(),
                    peer="127.0.0.1", local=True)


def filed_message() -> str:
    rel = TODAY_NOTE.relative_to(VAULT).as_posix()
    return f"Filed in Obsidian, {rel}."


# --------------------------------------------------------------------------
# 1. The note path: the existing capture module, its own sentence, the file
# --------------------------------------------------------------------------
def t_the_owner_shapes_make_a_real_daily_note():
    shapes = {
        "make a note: call the plumber about the boiler":
            "call the plumber about the boiler",
        "make a note buy milk": "buy milk",
        "note that the meeting is in room B": "the meeting is in room B",
        "jot down ask Sam about the loan": "ask Sam about the loan",
        "add a note: pick up the parcel": "pick up the parcel",
        "add to my daily note: water the plants": "water the plants",
        "add to today's note: book the dentist": "book the dentist",
        "add to my obsidian daily note: renew the passport":
            "renew the passport",
    }
    for text, want_note in shapes.items():
        reset_all()
        got = ask(text)
        check(f"{text!r} is the note writer's answer",
              got is not None and got.intent == "note_made",
              got.intent if got else "the model")
        check(f"... and is the capture module's own words naming the file",
              got is not None and got.reply == filed_message(),
              (got.reply if got else "")[:200])
        check(f"... and today's daily note exists", TODAY_NOTE.is_file(),
              str(TODAY_NOTE))
        body = TODAY_NOTE.read_text(encoding="utf-8") if TODAY_NOTE.is_file() else ""
        check(f"... and holds the owner's exact words {want_note!r}",
              want_note in body, body[:220])
        check("... after the existing capture gate action",
              GATE["calls"] == ["append_obsidian_daily"], GATE["calls"])


def t_the_note_is_appended_never_overwritten():
    reset_all()
    TODAY_NOTE.write_text("Yesterday's thought.\n", encoding="utf-8")
    got = ask("make a note: a second thought")
    check("the append is the capture module's own answer",
          got is not None and got.intent == "note_made" and got.reply == filed_message(),
          got.reply if got else "the model")
    body = TODAY_NOTE.read_text(encoding="utf-8")
    check("the existing text is byte-for-byte intact",
          body.startswith("Yesterday's thought.\n"), body[:200])
    check("... and the new note is in the same file", "a second thought" in body)


# --------------------------------------------------------------------------
# 2. The File Guardian copy comes first
# --------------------------------------------------------------------------
def t_the_guardian_copy_is_attempted_before_the_append():
    reset_all()
    TODAY_NOTE.write_text("The original.\n", encoding="utf-8")
    seen = []
    original = N.snapshot_vault_before_write

    def spy(*a, **k):
        seen.append((a, k))
        return original(*a, **k)

    N.snapshot_vault_before_write = spy
    try:
        got = ask("note that a guardian test was asked for")
    finally:
        N.snapshot_vault_before_write = original
    check("the existing note was copied first", bool(seen), seen)
    check("... and the note was still appended",
          got is not None and got.intent == "note_made", got.intent if got else "the model")
    body = TODAY_NOTE.read_text(encoding="utf-8")
    check("... over the original text, not instead of it",
          body.startswith("The original.\n") and "a guardian test was asked for" in body,
          body[:220])


def t_a_refused_guardian_copy_writes_nothing_and_says_so():
    reset_all()
    TODAY_NOTE.write_text("The original.\n", encoding="utf-8")
    before = TODAY_NOTE.read_bytes()
    saved = N.snapshot_vault_before_write
    N.snapshot_vault_before_write = lambda *a, **k: {
        "ok": False, "error": "the guardian is full"}
    try:
        got = ask("make a note: should not be written")
    finally:
        N.snapshot_vault_before_write = saved
    check("the guardian's own refusal is the answer",
          got is not None and got.intent == "note_make_refused"
          and (got.reply or "").startswith(
              "Not filed: the current daily note could not be copied first"),
          (got.reply if got else "the model")[:240])
    check("... and the daily note is byte-for-byte unchanged",
          TODAY_NOTE.read_bytes() == before)
    check("... and no second file was made",
          [p.name for p in VAULT.iterdir() if p.is_file()] == [TODAY_NOTE.name],
          [p.name for p in VAULT.iterdir() if p.is_file()])


# --------------------------------------------------------------------------
# 3. Nothing is written without the gate
# --------------------------------------------------------------------------
def t_a_denied_card_writes_nothing_in_the_modules_words():
    reset_all()
    GATE.update(allowed=False, outcome="denied")
    got = ask("make a note: denied by the owner")
    check("the module's own denial sentence is the answer",
          got is not None and got.intent == "note_make_refused"
          and got.reply == "You said no, so nothing was written.",
          (got.reply if got else "the model")[:220])
    check("... and no daily note was made", not TODAY_NOTE.exists(),
          str(TODAY_NOTE))
    check("... and the gate was asked under the capture action",
          GATE["calls"] == ["append_obsidian_daily"], GATE["calls"])


# --------------------------------------------------------------------------
# 4. The ask-after-outside-text rule is preserved
# --------------------------------------------------------------------------
def t_outside_text_asks_under_the_agent_action():
    reset_all(tainted=True)
    GATE.update(allowed=False, outcome="denied")
    got = ask("note that this was read from outside")
    check("a tainted conversation asks, and files nothing on a denial",
          got is not None and got.intent == "note_make_refused",
          (got.reply if got else "the model")[:220])
    check("... under write_notes_after_outside_text, not the plain action",
          GATE["calls"] == ["write_notes_after_outside_text"], GATE["calls"])
    check("... and the daily note was never made", not TODAY_NOTE.exists(),
          str(TODAY_NOTE))
    reset_all(tainted=True)
    GATE.update(allowed=True, outcome="approved", tier="ask")
    got = ask("make a note: approved after outside text")
    check("an approved tainted note is still filed",
          got is not None and got.intent == "note_made", got.intent if got else "the model")
    check("... again under the outside-text action",
          GATE["calls"] == ["write_notes_after_outside_text"], GATE["calls"])


# --------------------------------------------------------------------------
# 5. The organizer: its real state, and a read-only plan when on
# --------------------------------------------------------------------------
def t_the_organizer_off_answer_quotes_its_state_and_changes_nothing():
    reset_all()
    before = tree(VAULT)
    got = ask("organize my notes")
    check("the organizer question is the fixed answer",
          got is not None and got.intent == "vault_organizer_plan",
          got.intent if got else "the model")
    reply = got.reply if got else ""
    check("... quoting its own off sentence, word for word",
          "The vault organizer is off. Turn it on first; it is off by default "
          "and turning it on is one approval card." in reply, reply[:400])
    check("... saying the plan is a dry run", "dry run" in reply
          and "changes nothing" in reply, reply[:400])
    check("... and no card was raised", GATE["calls"] == [], GATE["calls"])
    check("... and the vault is byte-for-byte unchanged", tree(VAULT) == before,
          (before, tree(VAULT)))


def t_the_organizer_on_preview_is_read_only_and_shows_counts():
    reset_all(organizer_on=True)
    (VAULT / "Alpha.md").write_text("# Alpha\n\nSome words about the boiler.\n",
                                    encoding="utf-8")
    (VAULT / "Beta.md").write_text("# Beta\n\nSome words about the garden.\n",
                                   encoding="utf-8")
    before = tree(VAULT)
    got = ask("organize my Obsidian vault with tags and Maps of Content")
    check("the organizer answer is still the fixed path",
          got is not None and got.intent == "vault_organizer_plan",
          got.intent if got else "the model")
    reply = got.reply if got else ""
    check("... naming the default scheme in its own words",
          "without moving a single file" in reply, reply[:400])
    check("... and the plan's own counts (2 notes read)", "2 note(s) read" in reply,
          reply[:400])
    check("... and that nothing has changed yet",
          "Nothing has been changed yet." in reply, reply[:400])
    check("... and the writer's one-card / never-deletes rule",
          "ONE approval card" in reply and "never deleted" in reply, reply[:400])
    check("... with no card raised by the preview", GATE["calls"] == [], GATE["calls"])
    check("... and the vault is byte-for-byte unchanged", tree(VAULT) == before,
          (before, tree(VAULT)))


def t_turning_it_on_raises_the_existing_one_card():
    reset_all()
    GATE.update(allowed=True, outcome="approved", tier="ask")
    got = ask("turn on the vault organizer")
    check("the turn-on answer says one card is waiting",
          got is not None and got.intent == "vault_organizer_on"
          and "One approval card is waiting" in (got.reply or ""),
          (got.reply if got else "the model")[:300])
    deadline = time.time() + 5.0
    while time.time() < deadline and not V.enabled():
        time.sleep(0.02)
    check("... the existing change_own_config card was asked, once",
          GATE["calls"] == ["change_own_config"], GATE["calls"])
    check("... and the switch is on only after the gate's yes", V.enabled(),
          V.switch_status())
    GATE["calls"].clear()
    again = ask("turn on the vault organizer")
    check("asking again when it is on changes nothing",
          again is not None and again.intent == "vault_organizer_on"
          and "already on" in (again.reply or "").lower(),
          (again.reply if again else "the model")[:220])
    check("... and raises no second card", GATE["calls"] == [], GATE["calls"])


# --------------------------------------------------------------------------
# 6. The invented capabilities get honest refusals
# --------------------------------------------------------------------------
def t_rename_and_delete_are_refused_in_plain_words():
    reset_all()
    before = tree(VAULT)
    for text in ("rename my note Welcome to Home",
                 "delete my note Welcome",
                 "remove the shopping note"):
        got = ask(text)
        check(f"{text!r} is the notes-editor refusal",
              got is not None and got.intent == "note_change_refused",
              got.intent if got else "the model")
        reply = got.reply if got else ""
        check("... saying what the notes editor does not do",
              "does not create, rename or delete notes" in reply, reply[:300])
        check("... and that nothing was changed", "Nothing was changed." in reply,
              reply[:300])
    check("no card was raised and nothing was written",
          GATE["calls"] == [] and tree(VAULT) == before,
          (GATE["calls"], tree(VAULT)))
    check("... and no daily note was made", not TODAY_NOTE.exists(),
          str(TODAY_NOTE))


def t_create_is_now_a_real_write_and_never_overwrites():
    """Wave 1: 'create a new note called X' makes ONE note, one card, no clobber."""
    reset_all()
    GATE.update(allowed=True, outcome="approved")
    got = ask("create a new note called Shopping")
    check("'create a new note called Shopping' is the create path",
          got is not None and got.intent == "note_created",
          got.intent if got else "the model")
    created = VAULT / "Shopping.md"
    check("... and the note really exists", created.is_file(), str(created))
    reply = got.reply if got else ""
    check("... in the module's own words, naming the file and undo",
          reply.lower().startswith("created shopping.md")
          and "you can undo it" in reply.lower(), reply[:300])
    check("... after ONE edit_vault_note card",
          GATE["calls"] == ["edit_vault_note"], GATE["calls"])
    # a second create of the same note is refused and never overwrites
    created.write_text("keep me\n", encoding="utf-8")
    GATE.update(calls=[])
    before = created.read_bytes()
    got = ask("create a new note called Shopping")
    check("a create over an existing note is refused",
          got is not None and got.intent == "note_create_refused",
          got.intent if got else "the model")
    check("... in plain words, and nothing was overwritten",
          "already a note" in (got.reply or "") and created.read_bytes() == before,
          (got.reply if got else "")[:300])
    check("... and it asked NO card", GATE["calls"] == [], GATE["calls"])


def t_obsidian_themes_css_and_templates_are_not_features():
    reset_all()
    before = tree(VAULT)
    for text in ("customize my Obsidian theme",
                 "can you customize my obsidian theme?",
                 "change my Obsidian CSS",
                 "make a template for my Obsidian notes"):
        got = ask(text)
        check(f"{text!r} is an honest refusal",
              got is not None and got.intent == "obsidian_style_refused",
              got.intent if got else "the model")
        reply = got.reply if got else ""
        check("... saying it is not one of my features",
              "That is not one of my features on this PC." in reply, reply[:260])
        check("... and naming the thing Jarvis does not change",
              "theme" in reply.lower() or "templates" in reply.lower(), reply[:260])
        check("... and pointing at the whole list",
              "Everything Jarvis can do" in reply, reply[:260])
    check("no card and no write for the style refusals",
          GATE["calls"] == [] and tree(VAULT) == before,
          (GATE["calls"], tree(VAULT)))


# --------------------------------------------------------------------------
# 7. No over-capture, and the earlier lanes still hold
# --------------------------------------------------------------------------
def t_no_over_capture_of_reminders_desks_or_reading():
    reset_all()
    got = ask("remind me to call Sam at 5pm")
    check("'remind me to call Sam at 5pm' stays a reminder",
          got is not None and got.intent == "reminder_set",
          got.intent if got else "the model")
    got = ask("remind me in 10 minutes to make a note about milk")
    check("'remind me ... to make a note' stays a reminder, not a note write",
          got is not None and got.intent == "reminder_set",
          got.intent if got else "the model")
    got = ask("organize my desk")
    check("'organize my desk' is still the model's", got is None,
          (got.intent if got else "")[:120])
    got = ask("what does my Welcome note say?")
    check("a note-reading question is the honest door, not a write or a claim",
          got is not None and got.intent == "note_read_honest",
          got.intent if got else "the model")
    got = ask("what can I change in settings")
    check("the settings-help lane still wins for its own phrase",
          got is not None and got.intent == "settings_help",
          got.intent if got else "the model")
    got = ask("what can you do with the calendar?")
    check("the note lane does not capture a capability question",
          got is None or got.intent != "note_make",
          got.intent if got else "the model")


# --------------------------------------------------------------------------
# 8. Registration: read-only vs acting, and no new tool
# --------------------------------------------------------------------------
def t_the_read_only_intents_are_registered_the_repo_way():
    for name in ("vault_organizer_plan", "note_change_refused",
                 "obsidian_style_refused", "note_make_refused"):
        check(f"{name!r} is a read-only answer", name in Q.READ_ONLY_INTENTS)
    for name in ("note_made", "note_make_waiting", "vault_organizer_on"):
        check(f"{name!r} is NOT read-only", name not in Q.READ_ONLY_INTENTS)
    check("a note write is dispatched as its own acting intent",
          Q.match("make a note: x") is not None
          and Q.match("make a note: x").name == "note_make")
    try:
        import jarvis_agent as AG
        tools = set(getattr(AG, "TOOLS", {}) or {})
        check("the note write adds no new agent tool",
              not any(name.startswith("note_") or "organize" in name
                      for name in tools), sorted(tools))
    except Exception:                       # noqa: BLE001 - module absent
        pass


def t_note_reading_questions_say_the_real_door_and_never_claim_a_read():
    """The audit's "I have located your notes" with no tool run: never again."""
    reset_all()
    before = tree(VAULT)
    for phrase in ("what does my Welcome note say?",
                   "find my notes about vault",
                   "search my notes for the boiler",
                   "read my Welcome note"):
        got = ask(phrase)
        check(f"{phrase!r} is the honest note-reading answer",
              got is not None and got.intent == "note_read_honest",
              got.intent if got else "the model")
        reply = got.reply if got else ""
        check("... saying chat does not read note text today",
              "Chat does not read note text today." in reply, reply[:260])
        check("... naming the real door, the Notes plate",
              "Notes plate" in reply and "Brain window" in reply, reply[:300])
        check("... never claiming it located or read the note",
              "located" not in reply.lower() and "I read" not in reply,
              reply[:260])
    check("no card was raised and the vault is unchanged",
          GATE["calls"] == [] and tree(VAULT) == before,
          (GATE["calls"], tree(VAULT)))
    # The merge must not have moved the working neighbours: the catalogue's
    # capability answer, settings help and "open my notes" keep their lanes.
    got = ask("what can you do with my notes?")
    check("'what can you do with my notes?' keeps the catalogue answer",
          got is not None and got.intent == "feature_capabilities",
          got.intent if got else "the model")
    got = ask("what can I change in settings")
    check("the settings-help phrase keeps its own answer",
          got is not None and got.intent == "settings_help",
          got.intent if got else "the model")
    got = ask("open my notes")
    check("'open my notes' still opens the Brain's Notes plate",
          got is not None and got.intent == "open_app",
          got.intent if got else "the model")


def main() -> int:
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                print(f"FAIL  {name} raised")
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
