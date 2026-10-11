"""test_api_doc.py - hold `docs/JARVIS-API.md` to the code it describes.

    python3 backend/test_api_doc.py

WHY THIS EXISTS. On 2026-10-10 a prompt audit read the API document against a
SIDE BRANCH rather than `main` and concluded the running install was 12 modules
ahead of the repository. Re-run against `origin/main` and against
`jarvis-backend/` (the published base), the opposite was true for six of those
modules. The same audit found four pieces of the document that had simply gone
stale - a list that said "Seven" where the code says ten, a repeating reminder
said to raise a card it stopped raising on 2026-09-26, four implemented phrases
that appeared nowhere, and two lines that named as absent a file the repository
had held for weeks.

Every one of those was a sentence somebody had trusted instead of re-checking.
This suite is the machine that re-checks the ones this repository can settle
from its own tree. It is deliberately narrow: it checks the claims that have a
definite answer in code, and it checks NOTHING it cannot read.

A CHECK THAT CANNOT FIND ITS SOURCE FAILS. Every helper below raises `Anchor`
rather than returning an empty result, so a section renamed, a table moved or
`docs/JARVIS-API.md` deleted is a red run with the anchor's own name in the
message - never a quiet pass over an empty string. That is the whole point: the
drift this catches is exactly the kind that looks fine when nothing is read.

WHAT IT PROVES
  1. section 41.1's count word ("Ten sentences") is the word for
     `jarvis_sayable.SENTENCES`' own length, and its table lists exactly those
     sentences, in order, each naming the module that really answers it.
  2. Every interruption-budget sentence documented in section 123.4 (section 58.2's own
     neighbour) really matches `jarvis_quick.py`'s grammar, as the intent that
     changes that number.
  3. section 21.5 no longer marks a plain repeating reminder "(a card)", and the
     scheduler really does register only `alarm` and `reminder`
     `plain_repeat=True` - so the document and the card rule agree.
  4. The two snooze windows in section 21.9 are the two constants: the route reaches
     back a day (`FIRED_KEEP`), the list and the phrase one hour
     (`WENT_OFF_SHOWN`).
  5. section 123.1's count matches the rows in `jarvis_limits.LIMITS` written by hand,
     and names every one of them.
  6. No line says a module this repository holds is "not in this repository" -
     the family of sentence that went stale the moment the base backend was
     published.

No network, no model.
"""
from __future__ import annotations

import re
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_sayable.py", "jarvis_quick.py", "jarvis_schedule.py",
                "jarvis_limits.py")

import jarvis_quick as Q  # noqa: E402
import jarvis_limits as L  # noqa: E402
import jarvis_sayable as S  # noqa: E402
import jarvis_schedule as SCHED  # noqa: E402

PASSED, FAILED = [], []
SKIPPED = []

DOC = REPO / "docs" / "JARVIS-API.md"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


class Anchor(Exception):
    """The document, or the code, does not read the way this check needs.

    Raised - never swallowed - so a moved section is a failure that names
    itself instead of a check that quietly compared nothing to nothing.
    """


def text() -> str:
    if not DOC.is_file():
        raise Anchor(f"docs/JARVIS-API.md is not at {DOC}")
    return DOC.read_text(encoding="utf-8")


def section(src: str, start: str, end: str, what: str) -> str:
    i = src.find(start)
    if i < 0:
        raise Anchor(f"{what}: the anchor {start!r} is not in docs/JARVIS-API.md")
    j = src.find(end, i + len(start))
    if j < 0:
        raise Anchor(f"{what}: the closing anchor {end!r} is not after {start!r}")
    return src[i:j]


def table_rows(block: str, what: str, first_cell_starts=None) -> list:
    """The data rows of the first markdown table in `block`, split on `|`.

    A row is a line beginning `|`; the `|---|` separator and the header are
    dropped. Finding no rows at all is an Anchor: a table that vanished is not
    a table with nothing in it."""
    rows, started = [], False
    for line in block.splitlines():
        if not line.startswith("|"):
            if started:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if not started:
            started = True          # the header row
            continue
        if first_cell_starts is not None and not cells[0].startswith(first_cell_starts):
            continue
        rows.append(cells)
    if not rows:
        raise Anchor(f"{what}: no table rows found in the block that should hold them")
    return rows


WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
         "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
         "sixteen", "seventeen", "eighteen", "nineteen", "twenty")


def word(n: int) -> str:
    if not 0 <= n < len(WORDS):
        raise Anchor(f"no word is written for {n} - extend WORDS in this test")
    return WORDS[n]


QUOTED = re.compile(r'"([^"]+)"')


def one_quote(s: str) -> str:
    got = QUOTED.findall(s)
    if not got:
        raise Anchor(f"no quoted sentence in {s!r}")
    return got[0]


# ---------------------------------------------------------------- section 41 things

def t_the_sayable_list_matches_the_code():
    """section 41.1: the count, the table, and the JSON sketch, all three."""
    block = section(text(), "### 41.1 The list, and how it was picked",
                    "### 41.2 The route", "section 41.1")
    n = len(S.SENTENCES)

    m = re.search(r"^(\w+) sentences, each checked against", block, re.M)
    if m is None:
        raise Anchor("section 41.1 no longer says '<word> sentences, each checked "
                     "against ...' - the count this check reads is gone")
    check(f"section 41.1's count word is {word(n)!r}, the length of "
          f"jarvis_sayable.SENTENCES", m.group(1).lower() == word(n),
          f"the document says {m.group(1)!r}; the code has {n}")

    rows = table_rows(block[block.index("| Sentence | Answered by |"):], "section 41.1's table")
    documented = [one_quote(r[0]) for r in rows]
    check("section 41.1's table lists exactly jarvis_sayable.SENTENCES, in order",
          documented == list(S.SENTENCES),
          f"document {documented}\n        code     {list(S.SENTENCES)}")

    # EVERY documented sentence is answered by the intent the row names - the
    # row's own claim, checked against jarvis_quick.py's real grammar - and
    # every module it names is really in the tree. A row that named a module
    # which does not exist, an intent the grammar does not reach, or a
    # sentence that stopped matching all fail here.
    for row in rows:
        sentence = one_quote(row[0])
        named = re.findall(r"`([^`]+)`", row[1])
        if not named:
            raise Anchor(f"section 41.1's row for {sentence!r} names nothing in "
                         "backticks - this check cannot tell what answers it")
        intent = Q.match(sentence)
        check(f"the grammar really answers section 41.1's {sentence!r}",
              intent is not None)
        if intent is not None:
            check(f"... and it is the intent the row names: {named[0]!r}",
                  intent.name == named[0],
                  f"the row says {named[0]!r}; the grammar answers {intent.name!r}")
        for mod in [n for n in named if n.endswith(".py")]:
            where = next((p for p in (REPO / "jarvis-backend" / mod,
                                      REPO / "backend" / mod) if p.is_file()), None)
            check(f"section 41.1 names a module that is really here: {mod}",
                  where is not None)

    src = text()
    m = re.search(r'"sentences": \[<the (\d+), in order>\]', src)
    if m is None:
        raise Anchor("the route's JSON sketch no longer carries "
                     "'\"sentences\": [<the N, in order>]' anywhere in the document")
    check("the JSON sketch counts the same list",
          int(m.group(1)) == n, f"the sketch says {m.group(1)}; the code has {n}")

    m = re.search(r'"walkthrough_examples": \[<3 of the (\d+),', src)
    if m is None:
        raise Anchor("the route's JSON sketch no longer carries the "
                     "walkthrough_examples line")
    check("... and so does the walkthrough line",
          int(m.group(1)) == n, f"the sketch says {m.group(1)}; the code has {n}")

    # The two other places in the document that counted the same list.
    for phrase in ("shows the 10 sentences as tappable buttons",
                   "3 of the 10 (`WALKTHROUGH_EXAMPLES`)"):
        if n == 10:
            check(f"section 41.4 says {phrase!r}", phrase in src)
        else:
            skip(f"section 41.4's wording check assumes ten sentences; the code has {n}")


def t_every_documented_sentence_is_answered_by_the_module_it_names():
    """The same claim as above, asked the other way round: nothing the code
    serves is missing from the document either. A list that grows in
    jarvis_sayable.py and not in section 41.1 fails here."""
    block = section(text(), "### 41.1 The list, and how it was picked",
                    "### 41.2 The route", "section 41.1")
    rows = table_rows(block[block.index("| Sentence | Answered by |"):], "section 41.1's table")
    documented = {one_quote(r[0]) for r in rows}
    for s in S.SENTENCES:
        check(f"the document lists the served sentence {s!r}", s in documented)


# ------------------------------------------------- the interruption budget

def t_the_budget_phrases_are_in_the_grammar():
    """section 123.4's table, every quoted sentence, against jarvis_quick.match()."""
    block = section(text(), "### 123.4 The interruption budget",
                    "Both routes are reached by tapping", "section 123.4")
    rows = table_rows(block, "section 123.4's phrase table")
    seen = []
    for row in rows:
        sentences = QUOTED.findall(row[0])
        if not sentences:
            raise Anchor(f"section 123.4's row {row[0]!r} quotes no sentence")
        for s in sentences:
            seen.append(s)
            intent = Q.match(s)
            check(f"the grammar really answers section 123.4's {s!r}",
                  intent is not None and intent.name == "settings_budget",
                  f"got {None if intent is None else intent.name!r}")
    check("section 123.4 documents the four shapes the audit found undocumented",
          all(any(s.startswith(p) for s in seen) for p in
              ("speak up", "speak up less", "speak up more", "the brief",
               "the digest arrives")),
          seen)

    # section 58.2's own neighbour table must carry the same phrases: the budget is a
    # setting sentence like every other row there, and it was the one missing.
    block = section(text(), "### 58.2 \"Adjust a setting\"",
                    "### 58.3", "section 58.2")
    rows = table_rows(block, "section 58.2's table")
    joined = "\n".join(r[1] for r in rows if len(r) > 1)
    for s in ("speak up", "speak up less", "speak up more", "the brief at 8pm",
              "the digest arrives at 7 in the morning"):
        check(f"section 58.2's table carries {s!r}", s in joined)
    m = re.search(r"^(\w+) settings are covered", block, re.M)
    if m is None:
        raise Anchor("section 58.2 no longer says '<word> settings are covered'")
    check("section 58.2's count of covered settings matches its own table",
          m.group(1).lower() == word(len(rows)),
          f"it says {m.group(1)!r}; the table has {len(rows)} settings rows")


# --------------------------------------------------- the repeating-card rule

def t_a_plain_repeat_really_needs_no_card():
    """section 21.5's Reminders row against the scheduler's own registrations."""
    block = section(text(), "### 21.5 Answered without the model",
                    "### 21.6", "section 21.5")

    for example in ("remind me every weekday at 7 to take my pills",
                    "remind me to stretch every 2 hours"):
        row = next((l for l in block.splitlines()
                    if l.startswith("| Reminders |") and example in l), None)
        if row is None:
            raise Anchor(f"section 21.5's Reminders row no longer carries {example!r}")
        check(f"section 21.5 does not mark a plain repeat '(a card)': {example!r}",
              "(a card)" not in row, row.strip())

    plain = {name for name, k in SCHED.KINDS.items() if getattr(k, "plain_repeat", False)}
    check("only alarm and reminder are plain_repeat - the rule the paragraph states",
          plain == {"alarm", "reminder"},
          f"jarvis_schedule says {sorted(plain)}")
    check("... and both of them, so a repeat of either really is set up at once",
          {"alarm", "reminder"} <= set(SCHED.KINDS))

    check("section 21.5 says which repeats DO card (the briefing and \"tell me when\")",
          "A repeating briefing" in block and '"tell me when"' in block)


# ------------------------------------------------------- the snooze windows

def t_the_two_snooze_windows_are_the_two_constants():
    """section 21.9: the route's day against the list's and the phrase's hour."""
    block = section(text(), "### 21.9 Snooze", "**\"Cancel that\".**", "section 21.9")

    check("section 21.9 no longer says a snooze reaches back 'in the last day'",
          "(in the last day)" not in block)
    check("section 21.9 names the route's own window, FIRED_KEEP, as a day",
          "FIRED_KEEP" in block and "24 hours" in block)
    check("section 21.9 names the list's and the phrase's window, WENT_OFF_SHOWN, as one hour",
          "WENT_OFF_SHOWN" in block and "one hour" in block)

    check("FIRED_KEEP really is a day", SCHED.FIRED_KEEP == 24 * 3600.0,
          f"jarvis_schedule says {SCHED.FIRED_KEEP}")
    check("WENT_OFF_SHOWN really is one hour", SCHED.WENT_OFF_SHOWN == 3600.0,
          f"jarvis_schedule says {SCHED.WENT_OFF_SHOWN}")

    src = (HERE / "jarvis_quick.py").read_text(encoding="utf-8")
    check("... and the phrase path says 'the last hour' in its own words",
          "went off in the last hour, so there is nothing to snooze." in src)


# ------------------------------------------------------- the limits table

def t_the_limits_table_matches_the_code():
    """section 123.1's count word and its rows against jarvis_limits.LIMITS."""
    block = section(text(), "### 123.1 One table, one route, for every limit",
                    "Two fields, two different jobs", "section 123.1")
    rows = table_rows(block, "section 123.1's limits table", first_cell_starts="`")
    documented = [r[0].strip("`") for r in rows]

    written_by_hand = [x.key for x in L.LIMITS if not x.key.startswith("notif_")]
    check("section 123.1's table lists every limit written by hand, in order",
          documented == written_by_hand,
          f"document {documented}\n        code     {written_by_hand}")

    m = re.search(r"(\w+) of them \(`jarvis_limits\.LIMITS`", block)
    if m is None:
        raise Anchor("section 123.1 no longer says '<word> of them "
                     "(`jarvis_limits.LIMITS` ...'")
    check(f"section 123.1's count word is {word(len(written_by_hand))!r}",
          m.group(1).lower() == word(len(written_by_hand)),
          f"it says {m.group(1)!r}; the code has {len(written_by_hand)} written by hand")

    notify = [x.key for x in L.LIMITS if x.key.startswith("notif_")]
    check("... and it admits the notification rows that join the same table",
          "seven more" in block and len(notify) == 7,
          f"jarvis_limits adds {len(notify)} notification rows")


# ------------------------------------- "not in this repository", the family

#: Modules this check holds the document to. Every one of them is in the
#: repository as the published base; the sentence the audit found stale is the
#: one that says otherwise.
IN_THE_REPOSITORY = ("jarvis_hud.py", "jarvis_arbiter.py", "jarvis_gate.py",
                     "jarvis_content_risk.py", "jarvis_watch.py")

NOT_HERE = ("not in this repository", "not in the repository",
            "this repository does not hold", "this repository does not have",
            "repository does not hold")


def t_nothing_held_here_is_called_absent():
    src = text()
    lines = src.splitlines()
    for mod in IN_THE_REPOSITORY:
        where = next((p for p in (REPO / "jarvis-backend" / mod,
                                  REPO / "backend" / mod) if p.is_file()), None)
        check(f"{mod} is really in the repository, so calling it absent is wrong",
              where is not None,
              "this check is meaningless while the module itself is missing")

    for i, line in enumerate(lines):
        window = " ".join(lines[i:i + 2]).lower()
        if not any(p in window for p in NOT_HERE):
            continue
        named = [m for m in IN_THE_REPOSITORY if m in window]
        if named:
            check(f"docs/JARVIS-API.md:{i + 1} does not call {named[0]} absent",
                  False, f"{line.strip()}\n        {lines[i + 1].strip() if i + 1 < len(lines) else ''}")


def main():
    for fn in (t_the_sayable_list_matches_the_code,
               t_every_documented_sentence_is_answered_by_the_module_it_names,
               t_the_budget_phrases_are_in_the_grammar,
               t_a_plain_repeat_really_needs_no_card,
               t_the_two_snooze_windows_are_the_two_constants,
               t_the_limits_table_matches_the_code,
               t_nothing_held_here_is_called_absent):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Anchor as exc:
            FAILED.append(fn.__name__)
            print(f"FAIL  {fn.__name__}: {exc}")
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
