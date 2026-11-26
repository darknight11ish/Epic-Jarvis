"""test_note_grammar_corpus.py - the owner's note sentences, as a permanent corpus.

    python -B backend/test_note_grammar_corpus.py

WHY THIS SUITE EXISTS (Gemini's ruling 5.1, 2026-11-24, and the owner's own
complaint before it): the note lane's grammar was audited once by hand, and every
later change could reopen a hole with nothing to catch it. This file is that
audit turned into a test: about sixty sentences the owner would actually say,
each one driven through the REAL fast path (`jarvis_quick.answer`) against a
throwaway vault, and each one asserting the OUTCOME - which note changed, what
landed in it, what was refused - not only which intent name came back. A wording
change that silently starts appending "today's date" as words, or reads "all my
notes" as a note called "my", fails here in seconds.

WHAT IT PINS, in the order the rows appear:

1. CREATE: a note with a body, a favourite, a pin, a title with words in it.
2. APPEND: a line, a colon form, a dated heading, and the DATE family
   ("today's date", "yesterday's date", "tomorrow's date", "last friday",
   "the 3rd of december") which must write a real ISO day and never the words -
   plus "friday at 5", which must keep the owner's words because a bare number is
   a day of the month to dateutil and would write a date in the past.
3. FLAGS, TAGS, LINKS AND PROPERTIES on an existing note.
4. ALIASES: "when I say X I mean my Y note" writes Obsidian's own `aliases:`
   list behind one `edit_vault_note` card, a later "read my X note" really
   resolves through it, and a name that would open a DIFFERENT note is refused
   in words that name that note instead of being written.
5. DELETE: one note, several, a count, a list with no note word, the trash, and
   the refusals ("delete all my notes" is not a note called "my", while a note
   literally called Everything is deletable like any other).
6. READ / SEARCH / LIST, and the shapes that must NOT reach the note lane.

A row that says nothing was written compares the note's BYTES before and after
(`unchanged`), not just that the file still exists.

RUNS ANYWHERE: temp vault, temp settings, temp receipts DB; `jarvis_framework`
and the gate's `check` are stand-ins; no model, no network, nothing of the
owner's is read or written. The clock is FIXED so a date check is deterministic.
"""
from __future__ import annotations

import hashlib
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
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_notes_edit.py", "jarvis_notes.py", "jarvis_quick.py")

_TMP = Path(tempfile.gettempdir()) / ("jarvis-note-corpus-" + secrets.token_hex(6))
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

#: A fixed local clock: Tuesday 2026-11-24, 21:30. Every date row is read
#: against this, so "last friday" is 2026-11-20 and never depends on the day the
#: suite happens to run. `DECEMBER_3RD` is the month-named phrase the dateutil
#: fallback has to compute; "friday at 5" on this Tuesday is the phrase that must
#: NOT become a date (2026-11-05 is a Wednesday in the past).
NOW = time.mktime(time.strptime("2026-11-24 21:30:00", "%Y-%m-%d %H:%M:%S"))
TODAY, YESTERDAY, TOMORROW, LAST_FRIDAY = (
    "2026-11-24", "2026-11-23", "2026-11-25", "2026-11-20")
DECEMBER_3RD = "2026-12-03"

FW = types.ModuleType("jarvis_framework")
FW.CONFIG_DIR = CONF
FW.LOG_DIR = _TMP / "log"
FW_STATE = {"notes": {"obsidian": {"vault_directory": str(VAULT)}}}
FW.load_framework = lambda: json.loads(json.dumps(FW_STATE))
FW.action_tier = lambda action: "ask"
FW.audit_log = lambda event, detail: None
sys.modules["jarvis_framework"] = FW


class _Verdict:
    allowed = True
    outcome = "approved"
    tier = "ask"
    reason = ""


GATE = {"calls": [], "cards": []}


def gate_check(action, detail=None, prompt="", **kwargs):
    GATE["calls"].append(action)
    GATE["cards"].append((action, detail, prompt))
    return _Verdict()


GATE_MODULE = types.ModuleType("jarvis_gate")
GATE_MODULE.check = gate_check
GATE_MODULE.taint_active = lambda: False
GATE_MODULE.pending = lambda: []
sys.modules["jarvis_gate"] = GATE_MODULE

import jarvis_notes as N  # noqa: E402
import jarvis_notes_edit as E  # noqa: E402
import jarvis_quick as Q  # noqa: E402

FAILED, PASSED = [], []


class Stub:
    """The scheduler stand-in `answer()` wants; the note lane never uses it."""

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


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def put(rel: str, text: str = "the note's own words\n") -> Path:
    full = VAULT / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(text.encode("utf-8"))
    return full


def here(rel: str) -> bool:
    return (VAULT / rel).is_file()


def read(rel: str) -> str:
    return (VAULT / rel).read_text(encoding="utf-8", errors="surrogatepass")


def reset_all() -> None:
    for child in list(VAULT.iterdir()):
        if child.name == ".obsidian":
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
    try:
        E._reset_for_tests()
    except Exception:                       # noqa: BLE001 - not in every build
        pass
    GATE["calls"], GATE["cards"] = [], []


def seed() -> None:
    """The same small vault before every sentence."""
    reset_all()
    put("Shopping.md", "# Shopping\n\nmilk\n\n#work\n")
    put("mood log.md", "---\nfavorite: true\n---\n\n")
    put("Ideas.md", "# Ideas\n\n")
    put("draft.md", "# draft\n\n")
    put("Trip 2026.md", "# Trip\n\n")
    put("Exercise.md", "---\nfavorite: true\n---\n\n# Exercise\n")
    put("Workout.md", "# Workout\n\n")
    # A title that really ends in "notes" (it must resolve by its own name) and
    # a note literally called Everything (it must be deletable like any other).
    put("Release notes.md", "# Release notes\n\nv1.0\n")
    put("Everything.md", "# Everything\n\n")
    (VAULT / "Archive").mkdir(exist_ok=True)


def ask(text: str):
    return Q.answer(text, sched=Stub(), now=NOW, peer="127.0.0.1", local=True)


def intent_of(res) -> str:
    return getattr(res, "intent", "") or ""


def said(res) -> str:
    return getattr(res, "reply", "") or ""


# --------------------------------------------------------------------------
#   The corpus. Each row: sentence, the intents that count as a real answer,
#   and an optional check on the vault that must ALSO hold.
# --------------------------------------------------------------------------
def words_in(rel: str, *needles):
    def run(_res):
        if not here(rel):
            return False, f"{rel} is not there"
        text = read(rel)
        missing = [n for n in needles if n not in text]
        return not missing, f"{rel} did not carry {missing}: {text[:200]!r}"
    return run


def gone(rel: str):
    def run(_res):
        return not here(rel), f"{rel} is still there"
    return run


def trashed(rel: str):
    def run(_res):
        ok = (VAULT / ".trash" / rel).is_file()
        return ok, f"{rel} is not in .trash"
    return run


#: The vault's own bytes just before the sentence, filled by `main()` for
#: `unchanged`. A row that says "nothing was written" must be able to prove it.
BEFORE = {}


def snapshot() -> dict:
    return {str(p.relative_to(VAULT)).replace("\\", "/"): p.read_bytes()
            for p in VAULT.rglob("*.md")}


def unchanged(*rels):
    """Every named note is still there AND carries the same bytes.

    This used to check only that the files still existed, so a row saying
    "nothing was written" passed even when the note had been rewritten
    (2026-11-24). The bytes are taken after `seed()` and before the sentence.
    """
    def run(_res):
        bad = []
        for r in rels:
            if not here(r):
                bad.append(f"{r} is gone")
            elif BEFORE.get(r) != (VAULT / r).read_bytes():
                bad.append(f"{r} was changed")
        return not bad, f"these were touched: {bad}"
    return run


def alias_written(alias: str, rel: str, title: str):
    """The alias is really in `rel`'s list, ONE `edit_vault_note` card was
    raised for it, and a later "read my <alias> note" opens `rel` itself.

    The read-back is the promise the reply makes ("Say ... in any chat and I will
    look for that note"), so it is driven, not assumed - the suite's header used
    to claim it and no row performed it (2026-11-24).
    """
    def run(_res):
        if "edit_vault_note" not in GATE["calls"]:
            return False, f"no edit_vault_note card was raised: {GATE['calls']}"
        if not here(rel):
            return False, f"{rel} is not there"
        text = read(rel)
        if "aliases:" not in text or alias not in text:
            return False, f"{rel} did not carry the alias: {text[:200]!r}"
        follow = ask(f"read my {alias} note")
        got, reply = intent_of(follow), said(follow)
        if got != "note_read" or f'"{title}" says' not in reply:
            return False, (f"reading my {alias!r} note gave {got!r} and did not "
                           f"open {title!r}: {reply[:160]}")
        return True, ""
    return run


def nothing_written():
    """No card was raised and no note file appeared, vanished or changed."""
    def run(_res):
        raised = list(GATE["calls"])
        after = snapshot()
        new = sorted(set(after) - set(BEFORE))
        gone_ = sorted(set(BEFORE) - set(after))
        changed = sorted(r for r in BEFORE if r in after and BEFORE[r] != after[r])
        if raised or new or gone_ or changed:
            return False, f"cards={raised} new={new} gone={gone_} changed={changed}"
        return True, ""
    return run


def alias_collision_refused(other: str, rel: str):
    """A name that would open ANOTHER note is refused, in words naming it."""
    def run(_res):
        reply = said(_res)
        if f"There is already a note called {other}.md" not in reply:
            return False, reply[:200]
        if not here(rel):
            return False, f"{rel} is not there"
        text = read(rel)
        if "aliases" in text:
            return False, f"{rel} was changed anyway: {text[:200]!r}"
        if GATE["calls"]:
            return False, f"a card was raised for a refused alias: {GATE['calls']}"
        return True, ""
    return run


def words_kept_and_no_wrong_date(rel: str, words: str, *wrong: str):
    def run(_res):
        if not here(rel):
            return False, f"{rel} is not there"
        text = read(rel)
        bad = [w for w in wrong if w in text]
        if bad:
            return False, f"{rel} carries the wrong date(s) {bad}: {text[:200]!r}"
        if words not in text:
            return False, f"{rel} did not keep the words {words!r}: {text[:200]!r}"
        return True, ""
    return run


CREATE = ("note_created",)
APPEND = ("note_appended",)
READ = ("note_read", "note_read_about", "note_search")
LIST = ("note_list",)
DELETE_ASK = ("note_delete_ask", "note_delete_refused")
DELETED = ("note_deleted",)
#: A merge is a write AND a delete, so it answers either once it has landed or
#: while its card waits; both are a real answer, a refusal is not.
MERGED = ("note_merged", "note_merge_waiting")


def merge_landed(survivor: str, source: str):
    """The survivor really carries the other note, and that note is in .trash."""
    def run(_res):
        if not here(survivor):
            return False, f"{survivor} is not there"
        if not (VAULT / ".trash" / source).is_file():
            return False, f"{source} is not in .trash"
        text = read(survivor)
        if "<!-- merged from" not in text:
            return False, f"{survivor} carries no merge marker: {text[:200]!r}"
        return True, ""
    return run


def copied(rel: str):
    """The copy is really there, and exactly ONE note copy was made."""
    def run(_res):
        if not here(rel):
            return False, f"{rel} is not there: {sorted(p.name for p in VAULT.glob('*.md'))}"
        if "edit_vault_note" not in GATE["calls"]:
            return False, f"a copy by chat raised no card: {GATE['calls']}"
        stuck = sorted(str(p.relative_to(VAULT)) for p in VAULT.rglob("*.md")
                       if "copy" in p.stem.casefold() and str(p.relative_to(VAULT)) != rel)
        return (not stuck), f"more than one copy appeared: {stuck}"
    return run


def names_note(want: str):
    """The reply names the NOTE it is asking about, never the verb's own phrase."""
    def run(_res):
        reply = said(_res)
        if f'"{want}"' not in reply:
            return False, f"the reply did not name {want!r}: {reply[:200]}"
        return True, ""
    return run


def searched_for(want: str):
    """The needle really searched for is `want`, quoted back in the answer."""
    def run(_res):
        reply = said(_res)
        if f'"{want}"' not in reply:
            return False, f"the reply did not search for {want!r}: {reply[:220]}"
        return True, ""
    return run


def cards_raised(*wanted: str):
    """Exactly these gate actions were asked, in order, once each."""
    def run(_res):
        got = list(GATE["calls"])
        return got == list(wanted), f"cards were {got}, wanted {list(wanted)}"
    return run


ROWS = [
    # 1. CREATE
    ("create a note called Groceries", CREATE,
     lambda r: (here("Groceries.md"), "no Groceries.md")),
    ("make a note called daily log and favorite", CREATE,
     words_in("daily log.md", "favorite: true")),
    ("make a note called reading list and pin", CREATE,
     words_in("reading list.md", "pinned: true")),
    ("write a note for me about the boiler", CREATE,
     lambda r: (any(p.name.lower().startswith("boiler") or "boiler" in p.name.lower()
                    for p in VAULT.rglob("*.md")), "no boiler note")),
    ("create a note called recipes with milk and eggs", CREATE,
     words_in("recipes.md", "milk", "eggs")),
    # KNOWN GAP (2026-11-24, found by this corpus): "add a note titled X" is
    # refused as an unreadable note change instead of creating the note. The row
    # pins today's behaviour so the gap is visible; fixing the create grammar
    # flips this row to CREATE.
    ("add a note titled Ideas 2027", ("note_change_refused",), None),
    ("make a note called", ("note_create_ask", "note_create_refused"),
     lambda r: (not any(p.name.lower().startswith("make") for p in VAULT.rglob("*.md")),
                "a file was made from a nameless sentence")),
    ("create a note", ("note_create_ask", "note_create_capability"), None),

    # 2. APPEND, including the DATE family
    ("add milk to my Shopping note", APPEND, words_in("Shopping.md", "milk")),
    ("append feeling tired to my mood log", APPEND,
     words_in("mood log.md", "feeling tired")),
    ("add to my mood log: feeling good", APPEND,
     words_in("mood log.md", "feeling good")),
    ("add today's date to my mood log", APPEND, words_in("mood log.md", TODAY)),
    ("add yesterday's date to my mood log", APPEND,
     words_in("mood log.md", YESTERDAY)),
    ("add tomorrow's date to my mood log", APPEND,
     words_in("mood log.md", TOMORROW)),
    ("add last friday to my mood log", APPEND, words_in("mood log.md", LAST_FRIDAY)),
    # The dateutil fallback: a month named in the phrase is a date; a bare number
    # is NOT (measured on this same Tuesday: "friday at 5" computed 2026-11-05,
    # a Wednesday in the past, and "friday at 10" computed 2026-11-10).
    ("add the 3rd of december to my mood log", APPEND,
     words_in("mood log.md", DECEMBER_3RD)),
    ("add friday at 5 to my mood log", APPEND,
     words_kept_and_no_wrong_date("mood log.md", "friday at 5",
                                  "2026-11-05", "2026-11-10")),
    ("add light cardio to my Workout note", APPEND,
     words_in("Workout.md", "light cardio")),
    ("add a line about milk to all my notes", ("notes_batch_refused",),
     unchanged("Shopping.md", "mood log.md")),
    ("add a line to my mood log", ("note_append_ask", "note_change_refused",
                                   "notes_batch_refused", "note_which"),
     unchanged("mood log.md")),

    # 3. FLAGS, TAGS, LINKS, PROPERTIES on an existing note
    ("pin my Ideas note", ("note_flag", "note_customized", "note_pin_set"), None),
    # The raw name is tried before the "note" is taken off its end, so a title
    # that really ends in "notes" resolves as itself ("pin my release notes"
    # cleaned to "release" and answered "I could not find a note called release"
    # while Release notes.md sat in the vault, measured 2026-11-24).
    ("pin my release notes", ("note_customized", "note_flag", "note_pin_set"),
     words_in("Release notes.md", "pinned: true")),
    ("favourite my Ideas note", ("note_flag", "note_customized", "note_favourite_set"),
     None),
    ("add the tag #work to my Shopping note",
     ("note_tag", "note_customized", "note_tagged"),
     words_in("Shopping.md", "#work")),
    ("remove the tag #work from my Shopping note",
     ("note_tag", "note_tagged", "note_customized", "note_tag_removed"), None),
    ("add a link to Exercise in my mood log",
     ("note_customized", "note_link", "note_linked"),
     words_in("mood log.md", "[[Exercise]]")),
    ("set rating to 5 in my Ideas note",
     ("note_customized", "note_property_set"),
     words_in("Ideas.md", "rating: 5")),

    # 4. ALIASES, written into the note's own frontmatter. Each row proves the
    # ONE `edit_vault_note` card, the line in the file, and that a later read by
    # that name really opens that note. "gym" is used rather than "workout"
    # because the seed has Workout.md: an alias equal to another note's own name
    # can never win, and such a sentence is refused (the row below).
    ("when I say gym I mean my Exercise note",
     ("note_alias_set",), alias_written("gym", "Exercise.md", "Exercise")),
    ("call my Exercise note gym time",
     ("note_alias_set",), alias_written("gym time", "Exercise.md", "Exercise")),
    ("add legs day as another name for my Exercise note",
     ("note_alias_set",), alias_written("legs day", "Exercise.md", "Exercise")),
    # The resolver reads a file's own name before any aliases list, so this name
    # would open Workout.md for ever. Refused in words that name that note.
    ("call my Exercise note workout", ("note_alias_refused",),
     alias_collision_refused("Workout", "Exercise.md")),
    ("when I say mood log I'm referring to this particular note",
     ("note_referral",),
     lambda r: ("aliases" not in said(r).lower(), "it claims an alias it did not write")),

    # 5. DELETE, and its refusals
    ("delete my note draft", DELETED, trashed("draft.md")),
    ("delete notes Shopping, Workout and Ideas", DELETED,
     lambda r: (not here("Shopping.md") and not here("Ideas.md")
                and not here("Workout.md"), "not all three moved")),
    ("delete the notes Shopping and Workout", DELETED, gone("Shopping.md")),
    ("remove three notes: Ideas, draft and Shopping", DELETED,
     lambda r: (not here("Ideas.md") and not here("draft.md")
                and not here("Shopping.md"), "the count was read as a title")),
    ("delete draft and Shopping", DELETED,
     lambda r: (not here("draft.md") and not here("Shopping.md")
                and here("Ideas.md"), "the wrong notes moved")),
    ("trash my draft note", DELETED, gone("draft.md")),
    # A note literally called Everything is a note like any other: the set-word
    # refusal is anchored at the START of what the sentence names, so "my
    # everything note" reaches the resolver and its card (measured 2026-11-24:
    # it was refused as a mass delete and could never be deleted).
    ("delete my everything note", DELETED, trashed("Everything.md")),
    ("delete all my notes", DELETE_ASK,
     lambda r: ("every note" in said(r).lower() and "my" not in
                said(r).lower().split("called")[-1][:12], said(r))),
    ("delete every note", DELETE_ASK, unchanged("Shopping.md", "Ideas.md")),
    ("delete all notes about the trip", DELETE_ASK, unchanged("Trip 2026.md")),
    ("delete a note", DELETE_ASK, None),
    ("delete my note", DELETE_ASK, None),
    ("delete my 5pm reminder", ("<not-note>",), None),
    ("delete this line", ("note_line_delete_refused",), None),
    ("delete my note Ideaz", ("note_delete_refused",), None),

    # 6. READ, SEARCH, LIST, and the shapes that are not notes
    ("read my Shopping note", READ, lambda r: ("milk" in said(r), said(r)[:120])),
    ("what's in my mood log", READ, None),
    ("what does my Shopping note say", READ,
     lambda r: ("milk" in said(r), said(r)[:120])),
    ("search my notes for milk", READ, None),
    ("find notes about the boiler", READ, None),
    ("what notes do you have", ("note_list", "note_read"), None),
    ("list my notes", ("note_list", "note_read"), None),
    ("open my Trip 2026 note", ("note_open", "note_read"), None),
    ("is my note in the inbox pinned", ("note_flag_state", "note_flag", "note_state"), None),
    # A phone call that happens to say "note" names no note. The "call my X note
    # Y" alias shape is claimed only when X is a real note (measured 2026-11-24:
    # "call my sister about the note tomorrow" was answered 'I could not find a
    # note called "sister about the"' and raised nothing).
    ("call my sister about the note tomorrow", ("<not-note>",), nothing_written()),
    ("call my plumber about the note on the fridge", ("<not-note>",),
     nothing_written()),
    ("call my wife and tell her the note is ready", ("<not-note>",),
     nothing_written()),
    ("what tools do you have", ("tools_inventory",), None),

    # 7. RENAME and MOVE
    ("rename my Workout note to Training", ("note_renamed", "note_rename"),
     lambda r: (here("Training.md") or here("Workout/Training.md"), "no Training.md")),
    ("move my Trip 2026 note to Archive", ("note_moved", "note_move"),
     lambda r: (here("Archive/Trip 2026.md"), "not in Archive")),

    # 8. FULL NOTE CONTROL (2026-11-25): the verbs that had no sentence, and the
    #    two sentences that were answered in the wrong lane's words.
    #
    # A note merge NEVER in pull-request words, and a pull-request sentence
    # never in the note lane's - both directions, because the measured bug was
    # "can you merge two notes" answered by the GitHub lane about merge commits.
    ("can you merge two notes", ("note_merge_ask",), nothing_written()),
    ("merge my notes", ("note_merge_ask",), nothing_written()),
    ("merge my two Newsletter notes", ("note_merge_ask",), nothing_written()),
    ("can you merge the pull request", ("<not-note>",), nothing_written()),
    ("merge pull request 12", ("<not-note>",), nothing_written()),
    ("merge my Shopping note and my Ideas note", MERGED, merge_landed("Shopping.md",
                                                                     "Ideas.md")),
    ("merge my Ideas note into my Shopping note", MERGED, trashed("Ideas.md")),
    # THE SHORT FORM (2026-11-26): the same two notes with no "note" noun where
    # the grammar above needed one. Both reached NO lane before this change, so
    # the model improvised; they are the two sentences the owner typed.
    ("merge Ideas and Shopping", MERGED, merge_landed("Ideas.md", "Shopping.md")),
    ("merge my two notes Ideas and Shopping", MERGED,
     merge_landed("Ideas.md", "Shopping.md")),
    ("copy my Shopping note", ("note_copied", "note_copy_waiting"),
     copied("Shopping copy.md")),
    ("add this to the top of my Shopping note", ("note_append_ask",),
     names_note("Shopping")),
    # SEARCH drops ONE leading article/possessive - and only one, so a phrase
    # that really starts with "the" keeps its own second "the".
    ("find my notes about the garden", ("note_search",), searched_for("garden")),
    ("find my notes about the day after tomorrow", ("note_search",),
     searched_for("day after tomorrow")),
    ("search my notes for the doctor", ("note_search",), searched_for("doctor")),
    # Which notes are PINNED, four ways - a flag read, never a note called
    # "pinned notes" and never a note read of the wrong note.
    ("which notes did I pin", ("note_pinned",), nothing_written()),
    ("my pinned notes", ("note_pinned",), nothing_written()),
    ("what did I pin", ("note_pinned",), nothing_written()),
    ("show me the notes I pinned", ("note_pinned",), nothing_written()),
    ("empty the vault trash", ("note_empty_trash_empty",), nothing_written()),
]


# --------------------------------------------------------------------------
#   The alias WRITER on the frontmatter shapes a chat sentence cannot produce.
#   `_alias_add` is the function under test; the chat rows above prove it is
#   reached through `handle_customize` with one `edit_vault_note` card.
# --------------------------------------------------------------------------
def yaml_front(text: str) -> dict:
    """The note's frontmatter as PyYAML reads it - the check the audit used.

    `{}` when the block does not parse (or is not a mapping), so an unreadable
    note is a FAILED row with the text in its message rather than a traceback.
    """
    import yaml
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        got = yaml.safe_load(parts[1])
    except Exception:                       # noqa: BLE001 - invalid YAML is a finding
        return {}
    return got if isinstance(got, dict) else {}


def other_front_lines(text: str) -> list:
    """Every frontmatter line that is not part of the aliases block."""
    inner = text.split("---", 2)[1].splitlines()
    keep, skipping = [], False
    for line in inner:
        if line.startswith("aliases:"):
            skipping = True
            continue
        if skipping and line.lstrip().startswith("- "):
            continue
        skipping = False
        keep.append(line)
    return keep


NORMAL = "---\ntitle: x\naliases:\n  - old\n  - old2\ntags: [a]\n---\n\nbody\n"


def alias_writer_cases() -> None:
    print()
    print("-- the alias writer on frontmatter shapes a chat cannot produce "
          + "-" * 8)
    fresh, said, _preview, why = E._alias_add(NORMAL, "new", "Note.md")
    parsed = yaml_front(fresh) if not why else {}
    check("the normal append shape is still valid YAML with all three names",
          why == "" and parsed.get("aliases") == ["old", "old2", "new"],
          f"why={why!r} yaml={parsed!r}\n{fresh}")
    check("... and every other frontmatter line is byte-identical",
          other_front_lines(fresh) == other_front_lines(NORMAL),
          (other_front_lines(fresh), other_front_lines(NORMAL)))
    check("... and the body is untouched", fresh.endswith("\n\nbody\n"), fresh[-20:])
    check("... and the resolver reads all three names back",
          N.note_aliases(fresh) == ["old", "old2", "new"], N.note_aliases(fresh))

    # The three shapes this writer must REFUSE rather than rebuild - each one
    # measured corrupting a valid note (2026-11-24).
    REFUSED = [
        ("a comment line inside the list",
         "---\ntitle: x\naliases:\n  # my other names\n  - old\n---\n\nbody\n",
         "comment"),
        ("a blank line inside the list",
         "---\ntitle: x\naliases:\n  - old\n\n  - old2\n---\n\nbody\n", "blank"),
        ("a one-line flow list",
         '---\ntitle: x\naliases: ["Salt, Pepper", "Workout"]\n---\n\nbody\n',
         "one line"),
    ]
    for label, original, word in REFUSED:
        got, _s, _p, bad = E._alias_add(original, "new", "Note.md")
        check(f"{label} is refused in words naming it",
              bool(bad) and word in bad, f"why={bad!r}")
        check(f"... and the note is handed back untouched ({label})",
              got == original, got)
        check(f"... and the frontmatter still parses ({label})",
              yaml_front(original).get("title") == "x", yaml_front(original))

    # YAML indicators are characters in a quoted scalar, never syntax.
    for alias in ("*gym*", "&co", "- gym", "Salt, Pepper", "#tag"):
        got, _s, _p, bad = E._alias_add("---\ntitle: x\n---\n\nbody\n", alias,
                                        "Note.md")
        parsed = yaml_front(got) if not bad else {}
        check(f"alias {alias!r} is written as one YAML scalar",
              bad == "" and parsed.get("aliases") == [alias],
              f"why={bad!r} yaml={parsed!r}\n{got}")
        check(f"... and the resolver reads {alias!r} back",
              N.note_aliases(got) == [alias], N.note_aliases(got))

    # Finding 5 at the writer: a name that already opens another note.
    reset_all()
    put("Workout.md", "# Workout\n\n")
    put("Exercise.md", "---\nfavorite: true\n---\n\n# Exercise\n")
    original = read("Exercise.md")
    got, _s, _p, bad = E._alias_add(original, "workout", "Exercise.md")
    check("an alias that would open a DIFFERENT note is refused, naming that note",
          "There is already a note called Workout.md" in bad, f"why={bad!r}")
    check("... and nothing was written", got == original, got)
    got2, _s2, _p2, ok2 = E._alias_add(original, "Exercise", "Exercise.md")
    check("... while a name that opens THIS note is still written",
          ok2 == "" and "Exercise" in N.note_aliases(got2), f"why={ok2!r}\n{got2}")

    # And the same refusal through the REAL route, with no card raised.
    GATE["calls"], GATE["cards"] = [], []
    rel_sha = hashlib.sha256(original.encode("utf-8")).hexdigest()
    code, out = E.handle_customize({"path": "Exercise.md", "action": "add_alias",
                                    "alias": "workout",
                                    "expected_sha256": rel_sha},
                                   gate_check=gate_check, wait_s=0.05)
    check("the route refuses the colliding alias with 400 and no card",
          code == 400 and GATE["calls"] == []
          and "Workout.md" in str((out or {}).get("error")),
          f"{code} {out} calls={GATE['calls']}")
    check("... and the file on disk is unchanged", read("Exercise.md") == original)

    # The shape refusal through the route too: a flow list somebody wrote in
    # Obsidian must be refused, never rewritten.
    flow = '---\ntitle: x\naliases: ["Salt, Pepper", "Workout"]\n---\n\nbody\n'
    reset_all()
    put("flow.md", flow)
    GATE["calls"], GATE["cards"] = [], []
    code, out = E.handle_customize(
        {"path": "flow.md", "action": "add_alias", "alias": "new",
         "expected_sha256": hashlib.sha256(flow.encode("utf-8")).hexdigest()},
        gate_check=gate_check, wait_s=0.05)
    check("the route refuses a one-line aliases list with 400 and no card",
          code == 400 and GATE["calls"] == []
          and "one line" in str((out or {}).get("error")), f"{code} {out}")
    check("... and that note's bytes are unchanged", read("flow.md") == flow)


# --------------------------------------------------------------------------
#   The FULL NOTE CONTROL cases that need their own vault
#   (2026-11-25: the owner's "full control ... with deletions requiring a card")
# --------------------------------------------------------------------------
def full_control_cases():
    """Pinned flags, a real section, a copy, a merge and the trash - through chat.

    The rows above prove ROUTING; these prove the OUTCOME a sentence the owner
    would really say produces, against a vault built for it. Each case re-seeds,
    so one failing case cannot make the next one pass by accident.
    """
    # --- which notes are pinned: a FLAG read, naming the right note ---------
    reset_all()
    put("Pinned note.md", "---\npinned: true\n---\n\nwords\n")
    put("Unpinned note.md", "---\npinned: false\n---\n\nwords\n")
    put("Plain.md", "# Plain\n\nwords\n")
    for text in ("which notes did I pin", "my pinned notes", "what did I pin",
                 "show me the notes I pinned"):
        GATE["calls"], GATE["cards"] = [], []
        res = ask(text)
        reply = said(res)
        check(f"{text!r} names the PINNED note", "Pinned note" in reply, reply[:200])
        check(f"... and never the unpinned one ({text!r})",
              "Unpinned" not in reply and "Plain" not in reply, reply[:200])
        check(f"... with no card and no write ({text!r})",
              GATE["calls"] == [], GATE["calls"])

    # --- one SECTION, and the card says which lines go ----------------------
    reset_all()
    put("Workout.md", "# Workout\n\n## Warm-up\nstretch\n\n## Session\nsquats\n")
    GATE["calls"], GATE["cards"] = [], []
    res = ask("delete the Warm-up section from my Workout note")
    check("a section delete through chat lands", intent_of(res) in
          ("note_section_deleted", "note_section_waiting"),
          f"{intent_of(res)}: {said(res)[:160]}")
    check("... under ONE ordinary note-edit card",
          GATE["calls"] == ["edit_vault_note"], GATE["calls"])
    prompt = GATE["cards"][-1][2] if GATE["cards"] else ""
    check("... whose own line names the section AND how many lines go",
          '"Warm-up" section (2 lines)' in prompt, prompt)
    preview = ((GATE["cards"][-1][1] if GATE["cards"] else {}) or {}).get("preview") or {}
    check("... and whose detail says WHICH lines",
          preview.get("lines_from") == 3 and preview.get("lines_to") == 4,
          preview)
    body = read("Workout.md")
    check("... the section is gone and the rest of the note is untouched",
          "stretch" not in body and "## Session" in body
          and body.startswith("# Workout\n"), body)

    # --- a COPY, carded, naming the source and the new title ---------------
    reset_all()
    put("Shopping.md", "# Shopping\n\nmilk\n")
    GATE["calls"], GATE["cards"] = [], []
    res = ask("copy my Shopping note")
    check("a copy through chat lands", intent_of(res) in
          ("note_copied", "note_copy_waiting"),
          f"{intent_of(res)}: {said(res)[:160]}")
    check("... and the copy is really there", here("Shopping copy.md"),
          sorted(p.name for p in VAULT.glob("*.md")))
    check("... under ONE card, as the owner's brief asks",
          GATE["calls"] == ["edit_vault_note"], GATE["calls"])
    prompt = GATE["cards"][-1][2] if GATE["cards"] else ""
    check("... whose line names the source and the new title",
          "Shopping.md" in prompt and "Shopping copy.md" in prompt, prompt)

    # --- a MERGE into a named survivor, one delete card --------------------
    reset_all()
    put("Shopping.md", "# Shopping\n\nmilk\n")
    put("Ideas.md", "# Ideas\n\n- eggs\n")
    GATE["calls"], GATE["cards"] = [], []
    res = ask("merge my Ideas note into my Shopping note")
    check("a merge through chat lands", intent_of(res) in MERGED,
          f"{intent_of(res)}: {said(res)[:160]}")
    check("... under ONE card, and it is the DELETE action",
          GATE["calls"] == ["delete_vault_notes"], GATE["calls"])
    prompt = GATE["cards"][-1][2] if GATE["cards"] else ""
    check("... which says which note survives", '"Shopping.md" survives' in prompt,
          prompt)
    check("... the absorbed note is in the trash and the survivor carries it",
          here("Shopping.md") and (VAULT / ".trash" / "Ideas.md").is_file()
          and "- eggs" in read("Shopping.md"),
          read("Shopping.md")[:200])

    # --- the TRASH: no card when it is empty, one card when it is not ------
    reset_all()
    GATE["calls"], GATE["cards"] = [], []
    res = ask("empty the vault trash")
    check("an empty trash answers already-empty", intent_of(res) == "note_empty_trash_empty",
          f"{intent_of(res)}: {said(res)[:160]}")
    check("... and raised NO card at all", GATE["calls"] == [], GATE["calls"])
    trash = VAULT / ".trash"
    trash.mkdir(exist_ok=True)
    (trash / "Old.md").write_bytes(b"old\n")
    # `handle_empty_trash` keeps its OWN clock (it is the route, not this
    # suite's fixed one), so the age that lands on the card is measured from
    # the real `time.time()` and not from NOW.
    old = time.time() - 12 * 86400
    os.utime(trash / "Old.md", (old, old))
    GATE["calls"], GATE["cards"] = [], []
    res = ask("empty the vault trash")
    check("a trash with files answers with its own state",
          intent_of(res) in ("note_trash_emptied", "note_trash_waiting"),
          f"{intent_of(res)}: {said(res)[:160]}")
    check("... under ONE card, and it is the empty-trash action",
          GATE["calls"] == ["empty_vault_trash"], GATE["calls"])
    prompt = GATE["cards"][-1][2] if GATE["cards"] else ""
    check("... which names the file, its age and that it cannot be undone",
          "Old.md" in prompt and "12 days old" in prompt
          and "cannot be undone" in prompt, prompt)
    check("... and the file is really gone", not (trash / "Old.md").exists())


def short_merge_ambiguity_cases():
    """`merge Ideas and Shopping` is two notes OR one note with that title.

    The router carries BOTH readings, the whole phrase as one name first, so the
    choice is made against the REAL vault and is never guessed: a note literally
    called "Ideas and Shopping" makes the lane ASK and write nothing, and only
    when no such note exists do the two real notes merge (survivor first-named,
    behind the one delete card). Measured 2026-11-26: the sentence reached no
    lane at all before this change.
    """
    print()
    print("-- the short merge form and the one-note title " + "-" * 8)

    # (a) No note called "Ideas and Shopping": two names, two real notes.
    reset_all()
    put("Ideas.md", "# Ideas\n\n- eggs\n")
    put("Shopping.md", "# Shopping\n\nmilk\n")
    BEFORE.clear()
    BEFORE.update(snapshot())
    GATE["calls"], GATE["cards"] = [], []
    res = ask("merge Ideas and Shopping")
    check("'merge Ideas and Shopping' merges the two notes it names",
          intent_of(res) in MERGED, f"{intent_of(res)}: {said(res)[:160]}")
    good, why = merge_landed("Ideas.md", "Shopping.md")(res)
    check("... the first named survives and the second is in the trash", good, why)
    check("... under ONE delete card, never a silent write",
          GATE["calls"] == ["delete_vault_notes"], GATE["calls"])

    # (b) ONE note really carries the whole phrase: ask, do not assume a split.
    reset_all()
    put("Ideas.md", "# Ideas\n\n- eggs\n")
    put("Shopping.md", "# Shopping\n\nmilk\n")
    put("Ideas and Shopping.md", "# One note\n\nboth words in one title\n")
    BEFORE.clear()
    BEFORE.update(snapshot())
    GATE["calls"], GATE["cards"] = [], []
    res = ask("merge Ideas and Shopping")
    check("a note really called 'Ideas and Shopping' makes the short form ASK",
          intent_of(res) == "note_merge_ask",
          f"{intent_of(res)}: {said(res)[:160]}")
    good, why = nothing_written()(res)
    check("... and nothing was merged, carded or changed", good, why)

    # (c) The same title present does not disturb the explicit "... into ...".
    GATE["calls"], GATE["cards"] = [], []
    res = ask("merge my Ideas note into my Shopping note")
    check("... while the explicit 'into' form still merges",
          intent_of(res) in MERGED, f"{intent_of(res)}: {said(res)[:160]}")


def main() -> int:
    print(f"note grammar corpus - {len(ROWS)} sentences, clock fixed at "
          f"2026-11-24 21:30 local")
    for text, wants, after in ROWS:
        seed()
        # The bytes every "nothing was written" row compares against.
        BEFORE.clear()
        BEFORE.update(snapshot())
        try:
            res = ask(text)
        except Exception as exc:            # noqa: BLE001 - a crash IS a finding
            check(f"{text!r} answers", False, f"{type(exc).__name__}: {exc}")
            continue
        got = intent_of(res)
        if wants == ("<not-note>",):
            ok = not got.startswith("note_")
        else:
            ok = got in wants
        check(f"{text!r} -> {got}", ok, f"wanted one of {wants}, got {got!r}: {said(res)[:160]}")
        if after is not None:
            try:
                good, why = after(res)
            except Exception as exc:        # noqa: BLE001
                good, why = False, f"{type(exc).__name__}: {exc}"
            check(f"... and the vault agrees ({text!r})", good, why)
    alias_writer_cases()
    full_control_cases()
    short_merge_ambiguity_cases()
    print()
    print(f"{len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print(f"  FAILED: {name}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
