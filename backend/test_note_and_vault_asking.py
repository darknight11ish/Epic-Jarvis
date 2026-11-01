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
        "tier": "auto", "calls": [], "cards": [], "explode": False,
        "gate_pending": []}


def gate_check(action, detail=None, prompt="", **kwargs):
    GATE["calls"].append(action)
    GATE["cards"].append((action, detail, prompt))
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
GATE_MODULE.pending = lambda: list(GATE.get("gate_pending") or [])
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
                calls=[], cards=[], explode=False, gate_pending=[])


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


def t_a_stale_switch_card_is_cleared_and_a_fresh_one_is_raised():
    """THE LIVE BUG (2026-10-31): the in-memory marker outlived the real card.

    Plant a marker as a raise leaves it, let the gate's pending list say the
    card is still there (status must stay waiting), then simulate its timeout /
    dismissal (the gate's list no longer has it). The status must say not
    waiting, and the next "turn on" must raise a FRESH card and turn on.
    """
    reset_all()
    # RAISE the card for real, but never let the fake gate's decide run (the
    # live window was dismissed / timed out without an answer).
    GATE.update(allowed=True, outcome="approved", tier="ask", calls=[],
                gate_pending=[])
    code, raised = V.request_enabled(True, gate=gate_check,
                                     tier_of=lambda action: "ask",
                                     spawn=lambda fn: None)
    check("the card is really raised and marked waiting",
          code == 202 and raised.get("waiting") is True, (code, raised))
    # While the gate lists the switch card, the marker must stay waiting.
    GATE["gate_pending"] = [{"id": "gate-card-1", "action": V.SWITCH_ACTION,
                             "prompt": V.SWITCH_CARD,
                             "detail": {"setting": "vault_organizer_enabled"}}]
    live = V.switch_status()
    check("a card the gate still lists keeps the marker waiting",
          live.get("waiting") is True and live.get("pending", {}).get("id") == raised.get("pending_id"),
          live)
    # The gate's own expiry bounds it even while a row lingers with no time left.
    GATE["gate_pending"] = [{"id": "gate-card-1", "action": V.SWITCH_ACTION,
                             "prompt": V.SWITCH_CARD,
                             "detail": {"setting": "vault_organizer_enabled"},
                             "expires_in": 0}]
    expired = V.switch_status()
    check("... and a matching card with no time left is not waited for",
          expired.get("waiting") is False, expired)
    # The card times out / its window is dismissed: the gate no longer lists it.
    GATE["gate_pending"] = []
    stale = V.switch_status()
    check("a marker with no card in the gate is no longer 'waiting'",
          stale.get("waiting") is False, stale)
    check("... and the status route says the same",
          V.handle_get(V.STATUS_PATH)[1].get("waiting") is False,
          V.handle_get(V.STATUS_PATH)[1])
    # A new turn-on must raise a fresh card rather than say one is waiting.
    GATE.update(allowed=True, outcome="approved", tier="ask", calls=[])
    got = ask("turn on the vault organizer")
    deadline = time.time() + 5.0
    while time.time() < deadline and not V.enabled():
        time.sleep(0.02)
    check("a new turn-on raises a fresh change_own_config card",
          got is not None and got.intent == "vault_organizer_on"
          and GATE["calls"] == ["change_own_config"], GATE["calls"])
    check("... and it really turns on after the fresh yes", V.enabled(),
          V.switch_status())
    check("... with no stale marker left", V.switch_status().get("waiting") is False,
          V.switch_status())
    V.reset_for_tests()


def t_the_plan_is_read_only_and_names_the_apply_door():
    reset_all(organizer_on=True)
    (VAULT / "Welcome.md").write_text("# Welcome\n\nThe boiler was serviced.\n",
                                      encoding="utf-8")
    (VAULT / "Garden").mkdir(exist_ok=True)
    (VAULT / "Garden" / "Gnomes.md").write_text(
        "# Gnomes\n\nThree gnomes by the shed.\n", encoding="utf-8")
    before = tree(VAULT)
    got = ask("plan my vault")
    check("the ON plan question runs the READ-ONLY plan",
          got is not None and got.intent == "vault_organizer_plan",
          got.intent if got else "the model")
    reply = got.reply if got else ""
    check("... with the scheme words and the counts",
          "without moving a single file" in reply and "note(s) read" in reply,
          reply[:500])
    check("... saying nothing has changed yet",
          "Nothing has been changed yet." in reply, reply[:500])
    check("... naming the ONE-card / never-deletes apply",
          "ONE approval card" in reply and "never deleted" in reply, reply[:500])
    check("... and the chat apply door it names is the real shape",
          'apply the plan' in reply and "apply the plan" in reply.lower(),
          reply[:500])
    check("no card was raised and the vault is byte-for-byte unchanged",
          GATE["calls"] == [] and tree(VAULT) == before,
          (GATE["calls"], tree(VAULT)))


def t_apply_the_plan_raises_the_writers_one_card_and_nothing_more():
    reset_all(organizer_on=True)
    (VAULT / "Welcome.md").write_text("# Welcome\n\nThe boiler was serviced.\n",
                                      encoding="utf-8")
    plan_reply = ask("organize my notes")
    check("a plan exists before the apply (so this is the stored plan)",
          plan_reply is not None and plan_reply.intent == "vault_organizer_plan",
          plan_reply.intent if plan_reply else "the model")
    before = tree(VAULT)
    saved_tier, saved_copy = FW.action_tier, V.COPY_DEFAULT
    try:
        FW.action_tier = lambda action: "ask"
        V.COPY_DEFAULT = False
        # DENY: the writer's card is raised, and the denial writes nothing.
        GATE.update(allowed=False, outcome="denied", tier="ask", calls=[])
        denied = ask("apply the plan")
        check("'apply the plan' reaches the writer's own intent",
              denied is not None and denied.intent == "vault_organizer_apply",
              denied.intent if denied else "the model")
        check("... raises exactly the writer's ONE card",
              GATE["calls"] == [V.GATE_ACTION], GATE["calls"])
        check("... returns the module's own denial words",
              "denied" in (denied.reply or "").lower()
              and "nothing changed" in (denied.reply or "").lower(),
              (denied.reply if denied else "")[:320])
        check("... and a denied apply leaves the vault untouched",
              tree(VAULT) == before, tree(VAULT))
        # APPROVE: one card, then exactly what the plan promised, no deletions.
        GATE.update(allowed=True, outcome="approved", tier="ask", calls=[])
        approved = ask("organize my vault now")
        check("'organize my vault now' is the apply, not a second plan",
              approved is not None and approved.intent == "vault_organizer_apply",
              approved.intent if approved else "the model")
        check("... with exactly one writer card",
              GATE["calls"] == [V.GATE_ACTION], GATE["calls"])
        body = approved.reply if approved else ""
        check("... and the module's own organized words",
              "Organized" in body and "Nothing was deleted" in body, body[:400])
        check("... and the vault really changed only after the yes",
              tree(VAULT) != before, tree(VAULT)[:4])
    finally:
        FW.action_tier, V.COPY_DEFAULT = saved_tier, saved_copy
        V.reset_for_tests()


def t_scoped_plan_is_read_only_and_counts_only():
    reset_all(organizer_on=True)
    for name, body in (("Welcome.md", "# Welcome\n\nSome words.\n"),
                       ("Alpha.md", "# Alpha\n\nMore words.\n"),
                       ("Beta.md", "# Beta\n\nOther words.\n")):
        (VAULT / name).write_text(body, encoding="utf-8")
    before = tree(VAULT)
    one = ask("organize just my Welcome note")
    check("a pick-a-set ask is the scoped plan",
          one is not None and one.intent == "vault_organizer_scoped",
          one.intent if one else "the model")
    reply = one.reply if one else ""
    check("... with a selected-note count and nothing changed yet",
          "A scoped plan for 1 selected note(s)" in reply
          and "Nothing has been changed yet." in reply, reply[:600])
    check("... naming the one-card apply and that only the picked notes change",
          "ONE approval card" in reply and "only the notes you picked" in reply.lower(),
          reply[:600])
    check("... and naming no note title at all (counts only)", "Welcome" not in reply,
          reply[:600])
    check("... with no card and the vault byte-identical",
          GATE["calls"] == [] and tree(VAULT) == before, GATE["calls"])
    two = ask("organize these notes: Welcome, Alpha")
    check("the owner's named-list shape is the scoped plan too",
          two is not None and two.intent == "vault_organizer_scoped",
          two.intent if two else "the model")
    reply2 = two.reply if two else ""
    check("... counting the two picked notes", "2 selected note(s)" in reply2,
          reply2[:600])
    check("... still naming neither title", "Welcome" not in reply2
          and "Alpha" not in reply2, reply2[:600])
    check("... with no card and the vault unchanged",
          GATE["calls"] == [] and tree(VAULT) == before, GATE["calls"])
    names = ask("reorganize a specific set of notes")
    check("a specific-set ask with no names asks for the names",
          names is not None and names.intent == "vault_organizer_scoped"
          and "Name the notes to organize" in (names.reply or ""),
          (names.reply if names else "the model")[:320])
    check("... and changes nothing", GATE["calls"] == [] and tree(VAULT) == before,
          GATE["calls"])


def t_scoped_refusals_and_hidden_lists_are_honest():
    reset_all(organizer_on=True)
    (VAULT / "Welcome.md").write_text("# Welcome\n\nSome words.\n", encoding="utf-8")
    before = tree(VAULT)
    for text, want in (
            ("organize these notes: Nope",
             "not a real .md file in this vault"),
            ("organize these notes: ../outside.md", "outside the vault")):
        got = ask(text)
        check(f"{text!r} keeps the scoped intent and says the truth",
              got is not None and got.intent == "vault_organizer_scoped"
              and want in (got.reply or ""),
              (got.reply if got else "the model")[:360])
        check("... with no card and the vault untouched",
              GATE["calls"] == [] and tree(VAULT) == before, GATE["calls"])
    # Hidden lists: the same plan, but the reply names no note title.
    pv = types.ModuleType("jarvis_private_view")
    pv.effective = lambda **k: {"app_locked": False, "hide_memory_lists": True,
                                "locked": True}
    pv.withheld_words = lambda **k: (
        'Hidden while "Hide memory lists and chat history" is on.')
    pv.state = lambda: {"app_locked": False, "hide_memory_lists": True}
    saved = sys.modules.get("jarvis_private_view")
    sys.modules["jarvis_private_view"] = pv
    try:
        hidden = ask("organize just my Welcome note")
        reply = hidden.reply if hidden else ""
        check("while the hidden lists are on, the scoped plan is counts only",
              hidden is not None and hidden.intent == "vault_organizer_scoped"
              and "A scoped plan for 1 selected note(s)" in reply, reply[:700])
        check("... and names no note title", "Welcome" not in reply, reply[:700])
        check("... and says why the titles are withheld",
              "Hide memory lists" in reply, reply[:700])
        check("... with no card and the vault untouched",
              GATE["calls"] == [] and tree(VAULT) == before, GATE["calls"])
        # The apply card is counts-only too (the module's scoped card).
        GATE.update(allowed=True, outcome="approved", tier="ask", calls=[],
                    cards=[])
        saved_tier, saved_copy = FW.action_tier, V.COPY_DEFAULT
        FW.action_tier = lambda a: "ask"
        V.COPY_DEFAULT = False
        try:
            applied = ask("apply the plan")
        finally:
            FW.action_tier, V.COPY_DEFAULT = saved_tier, saved_copy
        check("the hidden-mode apply still raises the one scoped card",
              applied is not None and applied.intent == "vault_organizer_apply"
              and GATE["calls"] == [V.GATE_ACTION], GATE["calls"])
        if GATE["cards"]:
            card_text = str((GATE["cards"][-1][1] or {}).get("text") or "")
            check("... and the card shows counts, never the hidden title",
                  "selected note" in card_text and "Welcome" not in card_text,
                  card_text[:700])
        check("... and applying after the hidden plan says its selected words",
              "selected note(s)" in (applied.reply or ""),
              (applied.reply if applied else "")[:500])
    finally:
        if saved is None:
            sys.modules.pop("jarvis_private_view", None)
        else:
            sys.modules["jarvis_private_view"] = saved
    V.reset_for_tests()


def t_scoped_apply_denies_cleanly_then_writes_only_the_selection():
    reset_all(organizer_on=True)
    for name, body in (("Welcome.md", "# Welcome\n\nSome words.\n"),
                       ("Alpha.md", "# Alpha\n\nMore words.\n"),
                       ("Beta.md", "# Beta\n\nOther words.\n")):
        (VAULT / name).write_text(body, encoding="utf-8")
    plan_reply = ask("organize these notes: Welcome, Alpha")
    check("(set-up) the scoped plan is shown",
          plan_reply is not None and plan_reply.intent == "vault_organizer_scoped",
          plan_reply.intent if plan_reply else "the model")
    before = tree(VAULT)
    saved_tier, saved_copy = FW.action_tier, V.COPY_DEFAULT
    FW.action_tier = lambda a: "ask"
    V.COPY_DEFAULT = False
    try:
        GATE.update(allowed=False, outcome="denied", tier="ask", calls=[],
                    cards=[])
        denied = ask("apply the plan")
        check("a denied scoped apply is the module's denial",
              denied is not None and denied.intent == "vault_organizer_apply"
              and "denied" in (denied.reply or "").lower()
              and "nothing changed" in (denied.reply or "").lower(),
              (denied.reply if denied else "the model")[:360])
        check("... one writer card, no more",
              GATE["calls"] == [V.GATE_ACTION], GATE["calls"])
        check("... and the vault tree is byte-identical", tree(VAULT) == before)
        GATE.update(allowed=True, outcome="approved", tier="ask", calls=[],
                    cards=[])
        approved = ask("organize my vault now")
        check("the approved scoped apply is the writer's selected words",
              approved is not None and approved.intent == "vault_organizer_apply"
              and "selected note(s)" in (approved.reply or "")
              and "Nothing was deleted" in (approved.reply or ""),
              (approved.reply if approved else "the model")[:500])
        check("... exactly one scoped card",
              GATE["calls"] == [V.GATE_ACTION], GATE["calls"])
        if GATE["cards"]:
            detail = GATE["cards"][-1][1] or {}
            card_text = str(detail.get("text") or "")
            check("... the card says scoped/selected and names no note",
                  detail.get("scoped") is True and detail.get("selected") == 2
                  and "Welcome" not in card_text and "Alpha" not in card_text
                  and "Beta" not in card_text, (detail, card_text[:500]))
        after = tree(VAULT)
        changed = {rel for rel, _sha in after if (rel, _sha) not in before}
        check("... only the selected notes changed", changed <= {"Welcome.md", "Alpha.md"},
              changed)
        check("... the unselected note is byte-identical",
              {rel: sha for rel, sha in after if rel == "Beta.md"}
              == {rel: sha for rel, sha in before if rel == "Beta.md"})
        check("... and no MOC or Vault Home was created",
              not any("_MOC - " in rel or rel == "00 - Vault Home.md"
                      for rel, _sha in after),
              [r[0] for r in after])
    finally:
        FW.action_tier, V.COPY_DEFAULT = saved_tier, saved_copy
        V.reset_for_tests()


def t_tidy_it_for_real_and_off_apply_keep_their_truth():
    reset_all()
    off = ask("tidy it for real")
    check("'tidy it for real' with the organizer OFF is the honest off answer",
          off is not None and off.intent == "vault_organizer_apply"
          and "vault organizer is off" in (off.reply or "").lower(),
          (off.reply if off else "")[:320])
    check("... naming the one-card turn-on door",
          "turn on the vault organizer" in (off.reply or "")
          and "one approval card" in (off.reply or ""), (off.reply if off else "")[:320])
    check("... with no card raised", GATE["calls"] == [], GATE["calls"])
    check("'organize my vault now' is the acting apply intent",
          Q.match("organize my vault now") is not None
          and Q.match("organize my vault now").name == "vault_organizer_apply")
    V.reset_for_tests()


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
    check("a note-reading question is the note reader, not a write or a claim",
          got is not None and got.intent == "note_read",
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
    for name in ("vault_organizer_plan", "vault_organizer_scoped",
                 "note_change_refused", "obsidian_style_refused",
                 "note_make_refused"):
        check(f"{name!r} is a read-only answer", name in Q.READ_ONLY_INTENTS)
    for name in ("note_made", "note_make_waiting", "vault_organizer_on",
                 "vault_organizer_apply"):
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


def t_note_reading_questions_really_read_or_say_they_cannot():
    """The old "chat does not read note text" refusal is replaced (2026-10-31):
    the chat now really reads one note, and on an empty vault it says honestly
    that no such note exists - never the audit's "I have located your notes"
    with no read behind it."""
    reset_all()
    before = tree(VAULT)
    for phrase in ("what does my Welcome note say?", "read my Welcome note"):
        got = ask(phrase)
        check(f"{phrase!r} goes to the note reader",
              got is not None and got.intent == "note_read",
              got.intent if got else "the model")
        reply = got.reply if got else ""
        check("... and on an empty vault says it cannot find that note",
              "could not find a note called" in reply, reply[:260])
        check("... never claiming it located or read a note",
              "located" not in reply.lower() and "I read" not in reply,
              reply[:260])
    for phrase in ("find my notes about vault", "search my notes for the boiler"):
        got = ask(phrase)
        check(f"{phrase!r} goes to the note search",
              got is not None and got.intent == "note_search",
              got.intent if got else "the model")
        reply = got.reply if got else ""
        check("... and on an empty vault says no notes match",
              "No notes in your vault match" in reply, reply[:260])
        check("... naming the real door, the Notes plate editor",
              "notes editor" in reply, reply[:300])
        check("... never claiming it located or read a note",
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
