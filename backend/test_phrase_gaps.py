"""test_phrase_gaps.py - the two phrasings that reached no lane, and their neighbours.

    python -B backend/test_phrase_gaps.py

WHY THIS SUITE EXISTS (measured 2026-11-26, `main` at 4136d2d7f, with
`JARVIS_BACKEND` cleared so the checkout is what is read). Three of the owner's
own sentences went past every fast-path lane and were left to the model, which
is the complaint this change answers:

  "merge Ideas and Shopping"               -> (none)  now  note_merge
  "merge my two notes Ideas and Shopping"  -> (none)  now  note_merge
  "what tools work on notes"               -> (none)  now  tools_in_category

The merge lane already answered "merge my Ideas note into my Shopping note" and
"merge my Shopping note and my Ideas note"; its short form puts no "note" noun
where `_NOTE_MERGE_LIST` looks for one. The tools lane already answered "which
tools work on notes"; the owner types "what".

THE DANGER THIS FILE GUARDS IS THE NEIGHBOUR, not the gap. A sentence that moves
from one lane to another is a regression even when it still reaches SOME lane,
and the recorded 2026-11-25 failure was `can you merge two notes` being answered
in pull-request words. So every check below is a whole intent NAME, and the
neighbour table is as long as the gap table:

  - "merge Ideas into Shopping" names a SURVIVOR, which the "... into ..." form
    owns; the short form must not claim it (and it is still unclaimed, which is
    pinned rather than changed - it is out of this change's scope);
  - "merge my notes", "merge two notes", "merge my two Newsletter notes" and
    "can you merge two notes" must still ASK which notes;
  - a pull-request merge must still never reach the note lane;
  - "notes tools" and "tools for notes" are too terse, and are deliberately NOT
    claimed (the owner's brief says so);
  - "what tools are switched off", "what tools can change my settings" and
    "what github tools do you have" keep their own lanes, because "what" is
    also the word those questions start with.

THE AMBIGUITY IS PINNED HERE TOO: "merge Ideas and Shopping" can be two notes or
ONE note called "Ideas and Shopping". The intent carries BOTH readings, whole
phrase first, so `_run_note_merge` resolves the literal title first and asks
(nothing is merged) when it exists; only when it does not does the split run.
`backend/test_note_grammar_corpus.py` drives that against a real temporary
vault, both with and without the note that carries the two-name title.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import tempfile
import time
import types
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py")

#: Nothing of the owner's is read: a throwaway home, config, receipts DB and
#: vault, the same shape `test_note_referral.py` uses.
_TMP = Path(tempfile.gettempdir()) / ("jarvis-phrase-gaps-" + secrets.token_hex(6))
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
FW.audit_log = lambda event, detail: None
sys.modules["jarvis_framework"] = FW

GATE = types.ModuleType("jarvis_gate")
GATE.check = lambda *a, **k: types.SimpleNamespace(
    allowed=True, outcome="approved", tier="ask", reason="")
GATE.taint_active = lambda: False
GATE.pending = lambda: []
sys.modules["jarvis_gate"] = GATE

import jarvis_quick as Q  # noqa: E402

NOW = time.mktime(time.strptime("2026-11-26 15:00:00", "%Y-%m-%d %H:%M:%S"))
FAILED = []
PASSED = 0


def check(name: str, cond, detail: str = "") -> None:
    global PASSED
    if cond:
        PASSED += 1
        print(f"ok    {name}")
        return
    FAILED.append(name)
    print(f"FAIL  {name}" + (f"\n        {detail}" if detail else ""))


def intent_name(sentence: str) -> str:
    got = Q.match(sentence, now=NOW)
    return getattr(got, "name", "") if got is not None else ""


def intent(sentence: str):
    return Q.match(sentence, now=NOW)


# --------------------------------------------------------------------------
#  1. THE GAP: each new pattern, one test that fails without the pattern.
# --------------------------------------------------------------------------
def short_merge_form_reaches_the_merge_lane() -> None:
    """`merge <A> and <B>` and `merge my two notes <A> and <B>` both route.

    BEFORE THE CHANGE both returned no intent (the model improvised). The
    handler test that proves what the lane DOES with them lives in
    `test_note_grammar_corpus.py`; this is the routing proof, including the
    whole-phrase reading that keeps the ambiguity honest.
    """
    for sentence in ("merge Ideas and Shopping",
                     "merge my two notes Ideas and Shopping"):
        got = intent(sentence)
        name = getattr(got, "name", "") if got is not None else ""
        check(f"{sentence!r} reaches the merge lane (got {name!r})",
              name == "note_merge", f"wanted note_merge, got {name!r}")
        tries = list(getattr(got, "f", {}).get("tries") or []) if got else []
        check(f"... and carries the WHOLE phrase first, then the split "
              f"({sentence!r})",
              tries == [["Ideas and Shopping"], ["Ideas", "Shopping"]],
              f"tries were {tries!r}")


def what_tools_form_reaches_the_category_lane() -> None:
    """"what tools work on notes" is the same question as "which ..."."""
    got = intent("what tools work on notes")
    name = getattr(got, "name", "") if got is not None else ""
    check(f"'what tools work on notes' reaches the tools lane (got {name!r})",
          name == "tools_in_category", f"wanted tools_in_category, got {name!r}")
    f = getattr(got, "f", {}) if got is not None else {}
    check("... and names the Notes area, exactly as the 'which' form does",
          list(f.get("areas") or []) == ["Notes"] and f.get("words") == "notes",
          f"payload was {f!r}")
    check("... while the 'which' form still reaches it too",
          intent_name("which tools work on notes") == "tools_in_category",
          intent_name("which tools work on notes"))


# --------------------------------------------------------------------------
#  2. THE NEIGHBOURS: nothing else may move.
# --------------------------------------------------------------------------
#: (sentence, the whole intent name that must come back, or None for "no lane").
NEIGHBOURS = (
    # The merge lane's own shapes, and the asks, keep their answers.
    ("merge my Ideas note into my Shopping note", "note_merge"),
    ("merge my Shopping note and my Ideas note", "note_merge"),
    ("can you merge two notes", "note_merge_ask"),
    ("merge two notes", "note_merge_ask"),
    ("merge my notes", "note_merge_ask"),
    ("merge my two notes", "note_merge_ask"),
    ("merge my two Newsletter notes", "note_merge_ask"),
    # "... into ..." names a survivor and is a different shape; it must not be
    # swallowed by the short form (and is deliberately still unclaimed).
    ("merge Ideas into Shopping", None),
    # The 2026-11-25 measured swallow: a pull request is never a note merge.
    ("can you merge the pull request", "github_self"),
    ("merge pull request 12", None),
    # The too-terse forms are NOT in this change's scope and must stay unclaimed.
    ("notes tools", None),
    ("tools for notes", None),
    # The tools lane's neighbours: "what" is their word too, and they keep
    # their own answers.
    ("which tools work on notes", "tools_in_category"),
    ("which github tools do you have", "tools_in_category"),
    ("what github tools do you have", "github_self"),
    ("what tools are switched off", "tools_switched_off"),
    ("what tools can change my settings", "tools_settings"),
    ("what tools do you have", "tools_inventory"),
    ("list all of your tools", "tools_list_all"),
)


def neighbours_do_not_move() -> None:
    """Every sentence beside the two new patterns keeps the lane it had."""
    for sentence, want in NEIGHBOURS:
        got = intent_name(sentence)
        ok = (got == want) if want is not None else (got == "")
        check(f"{sentence!r} -> {got!r} (must stay {want!r})", ok,
              f"got {got!r}, wanted {want!r}")


def main() -> int:
    print("phrase gaps - the short merge form and the 'what tools' form, on "
          "main 4136d2d7f")
    short_merge_form_reaches_the_merge_lane()
    what_tools_form_reaches_the_category_lane()
    neighbours_do_not_move()
    print()
    print(f"{PASSED} passed, {len(FAILED)} failed")
    for name in FAILED:
        print(f"  FAILED: {name}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
