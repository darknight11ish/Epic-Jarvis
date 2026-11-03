"""test_learning_exclusion.py - habit and mood data are EXCLUDED FROM LEARNING
ENTIRELY, by construction, not by a card.

    python3 backend/test_learning_exclusion.py

WHY THIS IS A SEPARATE SUITE, AND WHY IT IS THE STRICTEST FORM AVAILABLE

The owner's 2026-11-02 decision D2 (life-coach set) is not "a card stands in
front of it" - it is "habit names, mood values and answer logs never become
learned facts at all". Card-gating is the weaker thing this project already
does for health and money (jarvis_sensitive.py), and the reason it is not
enough here is written in jarvis_intake.mood_rule's own docstring: a card can
arrive in the owner's review queue "possibly minutes after a hard moment".

So this suite does not check a card. It checks that there is NO PATH:

  1. NO IMPORT IN EITHER DIRECTION. Neither new module imports a module that
     can write or read a learned fact, and no such module imports either new
     one. Both directions are walked from the AST of every backend source file,
     so a new learner file is covered without anyone remembering to come here.
  2. NO FACT SQL. Neither module holds SQL that touches the `facts` table, and
     neither names memory.db.
  3. NOT CARD-GATED. Neither module imports jarvis_sensitive or jarvis_gate -
     so this is not the sensitive-category mechanism wearing a different hat.
     If someone ever turns this into a "wait for a yes" rule, this check fails.
  4. IT IS NOT A MODEL TOOL. jarvis_agent.py never names either module, so no
     tool of the model's can reach the stores; and neither module names a model
     stream.
  5. IT REALLY ONLY LIVES IN ITS OWN STORE. With a throwaway config folder,
     writing a habit and a mood creates habits.db and mood.db and NOTHING else
     - no memory.db, no chat log - and a sentinel written into each lives in
     that one file and in no other SQLite file in the folder.
  6. THE OTHER HALF OF THE BELT IS STILL THERE. jarvis_intake's own mood rule
     ("Moods ... is not a fact. Do not propose it.") is unchanged, so the model
     is still told not to propose a mood even in ordinary chat where D2 does
     not govern.

WHAT THIS SUITE DOES NOT CLAIM. It does not claim a model cannot write a fact
about the owner's mood or a thing they do - that is ordinary chat, the owner's
own words, and the existing learning rules (with the mood rule above) govern it.
It claims the habit and mood RECORDS are not a source a fact can come from.

    python3 backend/test_learning_exclusion.py
"""
from __future__ import annotations

import ast
import json
import os
import re
import sqlite3
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import jarvis_habits as H  # noqa: E402
import jarvis_mood as M  # noqa: E402

PASSED, FAILED = [], []
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-exclusion-"))

#: The modules whose job is to turn words into learned facts, or to hold them.
#: This is the seed list; `learners()` below widens it from the source, so a
#: file added next year that imports jarvis_memory or writes the facts table is
#: covered without an edit here.
SEED_LEARNERS = ("jarvis_intake.py", "jarvis_auto_learn.py", "jarvis_extract.py",
                 "jarvis_memory.py", "rebuilt/jarvis_memory.py",
                 "jarvis_sensitive.py", "jarvis_entities.py", "jarvis_profiles.py",
                 "jarvis_recall.py", "rebuilt/jarvis_recall.py")

#: The two modules this lane added.
NEW = ("jarvis_habits.py", "jarvis_mood.py")

#: The two store files, by the exact names they would appear under.
STORE_NAMES = ("habits.db", "mood.db")

FACTS_SQL = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+facts\b", re.I)
NON_SOURCE = re.compile(r"^(?:test_|eval_|_)")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   Walking the source
# --------------------------------------------------------------------------

def sources() -> dict:
    """{path relative to backend/: source text} for every real module."""
    out = {}
    for folder in (HERE, HERE / "rebuilt"):
        for p in sorted(folder.glob("*.py")):
            if NON_SOURCE.match(p.name) or p.name in (
                    "_where.py", "run_suites.py", "recover_from_claude_export.py"):
                continue
            out[p.relative_to(HERE).as_posix()] = p.read_text(encoding="utf-8")
    return out


def parsed(text: str):
    return ast.parse(text)


def imports_of(tree) -> set:
    """Every module name a file imports, dotted as written (and its top level)."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name)
                out.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and not node.level:
                out.add(node.module)
                out.add(node.module.split(".")[0])
    return out


def holds_facts_sql(tree) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if FACTS_SQL.search(node.value) and len(node.value) < 900:
                return True
    return False


def learners(sources_: dict) -> dict:
    """Every module that can write or read a learned fact, by capability.

    Capability, not intention: a file that imports jarvis_memory, or holds SQL
    against the `facts` table, is in - whatever it is called. This is the same
    derivation `test_topics_leaks.py` uses for its READERS list, narrowed to
    the modules that are part of the learner itself.
    """
    out = {}
    for rel, text in sources_.items():
        if rel in NEW:
            continue
        tree = parsed(text)
        names = imports_of(tree)
        if "jarvis_memory" in names or holds_facts_sql(tree):
            out[rel] = text
    for seed in SEED_LEARNERS:
        if seed in sources_:
            out[seed] = sources_[seed]
    return out


# --------------------------------------------------------------------------
#   1. No import in either direction
# --------------------------------------------------------------------------

def t_no_learner_imports_a_store_module():
    learner = learners(sources())
    check("the learner set was found at all (a derivation that found nothing "
          "would pass every check below for the wrong reason)",
          len(learner) >= 5, str(sorted(learner)))
    bad = []
    for rel, text in learner.items():
        names = imports_of(parsed(text))
        for store in ("jarvis_habits", "jarvis_mood"):
            if store in names:
                bad.append(f"{rel} imports {store}")
    check("no learner module imports jarvis_habits or jarvis_mood",
          not bad, "; ".join(bad))


def t_no_learner_names_a_store_or_its_file():
    """A learner could reach a store without importing it (a path constant, an
    SQL file name). This is the check for that: the exact names, never the
    English word "habit"."""
    learner = learners(sources())
    bad = []
    for rel, text in learner.items():
        for name in ("jarvis_habits", "jarvis_mood") + STORE_NAMES:
            if name in text:
                bad.append(f"{rel} names {name}")
    check("no learner module names the store modules or their two files",
          not bad, "; ".join(bad))


DB_NAME = re.compile(r"^[A-Za-z0-9_.\-]+\.db$")


def _db_names(tree) -> set:
    """The .db FILENAMES a module actually uses, as whole short strings.

    Whole-short-string only, deliberately: both module docstrings SAY they sit
    beside memory.db in prose, and a grep cannot tell a sentence from a path.
    A filename used to open a file is a short constant that is nothing but a
    filename.
    """
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if len(node.value) < 40 and DB_NAME.match(node.value):
                out.add(node.value)
    return out


def t_the_stores_import_no_learner_and_no_fact_sql():
    learner = learners(sources())
    learner_mods = {rel.split("/")[-1][:-3] for rel in learner}
    for rel in NEW:
        tree = parsed(sources()[rel])
        names = imports_of(tree)
        hit = sorted(names & learner_mods)
        check(f"{rel} imports none of the learner modules", not hit, str(hit))
        check(f"{rel} holds no SQL against the facts table",
              not holds_facts_sql(tree))
        used = _db_names(tree)
        check(f"{rel} opens its own one store file and no other",
              used == {rel.replace("jarvis_", "").replace(".py", ".db")}, str(used))


# --------------------------------------------------------------------------
#   3. Not card-gated: the mechanism itself is absent
# --------------------------------------------------------------------------

def t_this_is_not_the_sensitive_category_mechanism():
    for rel in NEW:
        names = imports_of(parsed(sources()[rel]))
        check(f"{rel} does not import jarvis_sensitive (so it is not a "
              "card-gated sensitive category)", "jarvis_sensitive" not in names,
              str(sorted(n for n in names if "sens" in n)))
        check(f"{rel} does not import jarvis_gate (so no card can be raised)",
              "jarvis_gate" not in names)
    # ... and neither module is on the sensitive module's own list of callers.
    sens = sources().get("jarvis_sensitive.py", "")
    check("jarvis_sensitive.py does not name either store module",
          "jarvis_habits" not in sens and "jarvis_mood" not in sens)


# --------------------------------------------------------------------------
#   4. Not a model tool
# --------------------------------------------------------------------------

def t_no_model_can_reach_a_store():
    agent = sources().get("jarvis_agent.py", "")
    check("jarvis_agent.py exists and was read", bool(agent))
    for name in ("jarvis_habits", "jarvis_mood"):
        check(f"jarvis_agent.py never names {name} - no tool can reach it",
              name not in agent)
    attrs = set()
    for rel in NEW:
        for node in ast.walk(parsed(sources()[rel])):
            if isinstance(node, ast.Attribute):
                attrs.add(node.attr)
    for call in ("open_stream", "run_local_turn", "chat_once", "generate"):
        check(f"neither store module calls {call}", call not in attrs,
              str(sorted(a for a in attrs if call.split("_")[0] in a)))


# --------------------------------------------------------------------------
#   5. The data really lives only in its own two files
# --------------------------------------------------------------------------

class _StubScheduler:
    """Enough of the scheduler module for a habit to be created, without
    starting a thread or writing schedule.db."""

    def __init__(self):
        self.jobs = {}

    def get(self):
        return self

    def add_repeat(self, kind, rule, text="", source="app", action=None):
        jid = f"j{len(self.jobs) + 1}"
        self.jobs[jid] = {"id": jid, "kind": kind, "text": text}
        return self.jobs[jid]

    def act(self, jid, verb):
        self.jobs.pop(jid, None)
        return {"ok": True}


def t_writing_a_habit_and_a_mood_creates_no_fact_store():
    folder = Path(tempfile.mkdtemp(prefix="jarvis-exclusion-", dir=str(_TMP)))
    os.environ["JARVIS_CONFIG_DIR"] = str(folder)
    os.environ["OPENJARVIS_CONFIG_DIR"] = str(folder)
    os.environ["JARVIS_HABITS_DB"] = str(folder / "habits.db")
    os.environ["JARVIS_MOOD_DB"] = str(folder / "mood.db")
    old = H._scheduler
    H._scheduler = lambda: _StubScheduler()
    sentinel = "SENTINEL-EXCLUSION-7f3a"
    try:
        hid = H.create(f"Walk {sentinel}")["id"]
        H.record_tick(hid, day="2026-11-02", words=sentinel)
        M.record(3, words=sentinel, day="2026-11-02")
        made = sorted(p.name for p in folder.iterdir())
        check("writing a habit and a mood made exactly the two stores",
              made == ["habits.db", "mood.db"], str(made))
        check("... and NOT a memory.db", "memory.db" not in made, str(made))
        check("... and no chat log or history file",
              not [n for n in made if "chat" in n or "history" in n], str(made))

        # Every byte of every file in the folder: the sentinel lives in the two
        # stores and nowhere else.
        holders = []
        for p in sorted(folder.iterdir()):
            if not p.is_file():
                continue
            if sentinel.encode() in p.read_bytes():
                holders.append(p.name)
        check("the sentinel lives in the two stores only, and in no other file",
              holders == ["habits.db", "mood.db"], str(holders))

        # And in SQLite terms: the only tables holding it are the two this
        # lane made. A `facts` table anywhere would fail here.
        tables = {}
        for name in ("habits.db", "mood.db"):
            con = sqlite3.connect(str(folder / name))
            try:
                tables[name] = sorted(
                    r[0] for r in con.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"))
            finally:
                con.close()
        check("the habit store holds only its own two tables",
              tables["habits.db"] == ["habits", "ticks"], str(tables["habits.db"]))
        check("the mood store holds only its own one table",
              tables["mood.db"] == ["moods"], str(tables["mood.db"]))
    finally:
        H._scheduler = old


# --------------------------------------------------------------------------
#   6. The other half of the belt is untouched
# --------------------------------------------------------------------------

def t_the_existing_mood_rule_still_stands():
    import jarvis_intake
    rule = jarvis_intake.mood_rule()
    check("jarvis_intake still says a mood is not a fact",
          "is not a fact" in rule and "Do not propose it" in rule, rule)
    check("... and the rule is still assembled into the prompt rules",
          "mood_rule" in sources().get("jarvis_intake.py", ""))


# --------------------------------------------------------------------------
#   The guard can fail
# --------------------------------------------------------------------------

def t_the_guard_can_fail():
    """A synthetic module that imports a learner, or holds facts SQL, IS seen -
    so a green run above means something."""
    fake = "import jarvis_memory\nrows = jarvis_memory.store().search('x')\n"
    check("the derivation sees a module that imports jarvis_memory",
          "jarvis_memory" in imports_of(parsed(fake)))
    fake2 = 'c.execute("SELECT text FROM facts WHERE id=1")\n'
    check("the derivation sees SQL against the facts table",
          holds_facts_sql(parsed(fake2)))
    check("... and does not mistake a docstring sentence for SQL",
          not holds_facts_sql(parsed('x = "the facts table is not read here"\n')))
    check("the new module's own docstring is not counted as an import",
          "jarvis_memory" not in imports_of(parsed(sources()["jarvis_habits.py"])))


def main():
    tests = [t_no_learner_imports_a_store_module,
             t_no_learner_names_a_store_or_its_file,
             t_the_stores_import_no_learner_and_no_fact_sql,
             t_this_is_not_the_sensitive_category_mechanism,
             t_no_model_can_reach_a_store,
             t_writing_a_habit_and_a_mood_creates_no_fact_store,
             t_the_existing_mood_rule_still_stands,
             t_the_guard_can_fail]
    for fn in tests:
        print("\n-- " + fn.__name__ + " " + "-" * 40)
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            check(fn.__name__ + " ran", False, traceback.format_exc()[-900:])
    print("\n" + "=" * 74)
    print(f"PASS {len(PASSED)}  FAIL {len(FAILED)}  SKIP 0")
    for name in FAILED:
        print("  FAIL:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
