"""The owner's own words resolve to the right catalogue row.

    python3 test_catalogue_phrasing.py

THE MEASURED BUG THIS HOLDS. Three live self-awareness passes on 2026-11-06
asked Jarvis about its own features in the owner's words and it denied them:

  * pass 1: 21 of 25 availability questions denied, and all 10 of the owner's
    own trap sentences failed (`.dsh-scratch/SELF-AWARENESS-2026-11-06/`);
  * pass 2: 6 of 35 denied (`.dsh-scratch/SELF-AWARENESS-TEST2-2026-11-06/`);
  * pass 3: 94 of 116 denied - flat answers like "No, I don't have a feature
    called 'Jarvis Live'" - plus 7 of 20 how-to and 12 of 20 surface-parity
    answers (`.dsh-scratch/SELF-AWARENESS-TEST3-2026-11-06/`).

The cause was not a missing feature: every one of those rows IS in
`features/features.json`. The owner's phrasings simply did not share a name
word with the row's own words, and the capability answer only answers from a
row it can name. So the fix is DATA - richer `aliases` on the rows - and this
suite is what keeps the data honest.

WHAT IT PROVES, and it is all read-only:

  a. every measured question in `catalogue_phrasing_cases.json` names its row:
     the question shape is taken off (the same shapes the capability matcher
     takes off before it looks a feature up) and `jarvis_feature_guide.find()`
     must return exactly the expected row;
  b. a question that names NO row is recorded as an honest fall-through with
     the reason, and the finder must not answer it with a single wrong row -
     a fall-through is never dressed up as a pass;
  c. the owner's exact Notion and document trap sentences land on
     `notion-import` and `document-from-phone`;
  d. no alias names two rows: no alias is repeated on another row, and no
     row's alias has all of its distinctive words sitting in another row's
     name - the matcher must never be able to tie;
  e. the fixture is the measured set (116 sweep questions, 25 pass-1, 35
     pass-2, the trap sentences), so a shrunken fixture cannot hide a
     regression, and every expected row is a real catalogue row.

Nothing here reads the owner's PC, runs a model or touches a file.
"""
from __future__ import annotations

import json
import re
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

import jarvis_feature_guide as FG                 # noqa: E402
import jarvis_feature_catalogue as CATALOGUE      # noqa: E402

FAILED, PASSED = [], []
FIXTURE = HERE / "catalogue_phrasing_cases.json"

#: The question shapes the owner asked in. This mirrors the shapes the
#: capability matcher takes off - `jarvis_quick._CAP_LEAD` - and is kept here
#: so this suite exercises the catalogue's own finder with the owner's words,
#: not with another module's plumbing.
_HARNESS = re.compile(
    r"\s*(?:answer\s+in\s+one\s+sentence|in\s+one\s+sentence|one\s+sentence|"
    r"name\s+the\s+screen\s+or\s+button|"
    r"answer\s+yes\s+or\s+no,?\s+and\s+say\s+where\s+it\s+works)\.?\s*$", re.I)
_LEAD = re.compile(
    r"^(?:(?:hey|ok|okay)\s+)?(?:jarvis[,:]\s+)?"
    r"(?:"
    r"do\s+you\s+have\s+(?:a\s+|an\s+|any\s+)?(?:feature|features|ability|capability|way|option)s?\s*"
    r"(?:called\s+|named\s+|to\s+|for\s+|where\s+|that\s+(?:lets\s+me\s+|lets\s+you\s+|"
    r"lets\s+jarvis\s+|can\s+|will\s+|would\s+|help\s+me\s+)?)?"
    r"|does\s+jarvis\s+(?:have\s+|offer\s+|support\s+|do\s+)?(?:a\s+|an\s+|any\s+)?"
    r"(?:feature|features|ability|capability|way|option)s?\s*"
    r"(?:called\s+|that\s+(?:lets\s+me\s+|lets\s+you\s+|lets\s+jarvis\s+|can\s+)?|to\s+|for\s+)?"
    r"|is\s+there\s+(?:a|an|any)\s+(?:way|feature|option)\s+(?:to\s+|for\s+|that\s+)?"
    r"|can\s+you\s+|could\s+you\s+|can\s+i\s+|could\s+i\s+|am\s+i\s+able\s+to\s+"
    r")", re.I)


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def subject(text: str) -> str:
    """The owner's own words for the feature, with the question shape off."""
    t = " ".join(str(text or "").replace("\u2019", "'").split())
    prev = None
    while prev != t:
        prev = t
        t = _HARNESS.sub("", t).rstrip(" .?!")
    t = _LEAD.sub("", t).strip().strip("\"\u201c\u201d' ")
    t = re.sub(r"^(?:a|an|the)\s+", "", t)
    return t.strip(" \"'?.!")


def cases() -> list:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


def resolved(subject_text: str) -> list:
    """The row ids the finder returns for one subject ([] = unknown)."""
    got = FG.find(subject_text)
    if got.get("kind") == "feature":
        return [got["row"]["id"]]
    if got.get("kind") == "ambiguous":
        return ["ambiguous: " + ", ".join(r["id"] for r in got["rows"])]
    return []


def t_every_measured_question_names_its_row():
    """THE MEASURED FAILURES, one case at a time."""
    bad, table = [], {}
    for case in cases():
        section = case["section"]
        table.setdefault(section, {"named": 0, "total": 0, "fell": 0})
        table[section]["total"] += 1
        expect = case.get("expect")
        sub = subject(case["question"])
        if not expect:
            table[section]["fell"] += 1
            continue
        got = resolved(sub)
        if got == [expect]:
            table[section]["named"] += 1
        else:
            bad.append(f"[{section}] {case['probe']} expected {expect}, got "
                       f"{got or 'unknown'} - the owner's words {sub!r}")
    for section in sorted(table):
        got = table[section]
        print(f"       {section}: {got['named']} of {got['total']} questions name "
              f"their row ({got['fell']} fall through with a reason)")
    check("every measured question names its own catalogue row", not bad,
          "\n        ".join(bad))


def t_a_question_that_names_no_row_falls_through_honestly():
    """A measured question the words cannot map says so, and is listed."""
    bad, listed = [], 0
    for case in cases():
        if case.get("expect"):
            continue
        listed += 1
        sub = subject(case["question"])
        got = resolved(sub)
        if not str(case.get("fall_through") or "").strip():
            bad.append(f"{case['probe']}: no reason recorded")
        if len(got) == 1 and not got[0].startswith("ambiguous"):
            bad.append(f"{case['probe']}: answered with one row ({got[0]}) instead of "
                       f"saying it does not know - {sub!r}")
    check(f"the {listed} question(s) that name no row fall through, each with its reason",
          not bad, "\n        ".join(bad))


def t_the_owner_notion_and_document_traps_land_on_their_rows():
    """The owner's exact sentences, 2026-11-06 pass 3: all five failed live."""
    traps = [
        ("Can I open and import my Notion notes as a markdown file and can you "
         "process it in the Android app and send it to the main Jarvis?",
         "notion-import"),
        ("Can I import a Notion export from my phone?", "notion-import"),
        ("Can I import a Notion export from my phone into my vault?", "notion-import"),
        ("Can I open my Notion notes in the Android app and send them to the main Jarvis?",
         "notion-import"),
        ("Can I upload documents from my phone through the app and have you process them?",
         "document-from-phone"),
        ("Can I send a file from my phone to my PC?", "document-from-phone"),
    ]
    bad = []
    for question, expect in traps:
        got = resolved(subject(question))
        if got != [expect]:
            bad.append(f"{question!r} -> {got or 'unknown'} (expected {expect})")
    check("the owner's exact Notion and document trap sentences resolve", not bad,
          "\n        ".join(bad))


def t_every_alias_names_its_own_row_and_no_other():
    """THE TIE RULE: one alias belongs to one feature, never to two.

    Said on its own, an alias must come back as its own row - not as a
    neighbour whose title happens to be spelled the same way, and not as an
    ambiguity. `find()` checks the id, the title and the aliases in list order,
    so an alias that is another row's own name is silently answered with the
    WRONG feature; this is what catches that.
    """
    rows = FG.features()
    seen, repeated, wrong = {}, [], []
    for row in rows:
        for alias in row.get("aliases") or ():
            key = FG._norm(alias)
            if key in seen and seen[key] != row["id"]:
                repeated.append(f"{alias!r}: {seen[key]} and {row['id']}")
            seen.setdefault(key, row["id"])
            got = resolved(alias)
            if got != [row["id"]]:
                wrong.append(f"{row['id']}: {alias!r} -> {got or 'unknown'}")
    check("no alias is repeated on another row", not repeated, "\n        ".join(repeated))
    check("every alias, said exactly, names its own row and no other", not wrong,
          "\n        ".join(wrong))


def t_the_fixture_is_the_measured_set_and_every_row_is_real():
    """A shrunken fixture cannot quietly hide a regression."""
    got = cases()
    ids = {row["id"] for row in FG.features()}
    by = {}
    for case in got:
        by[case["section"]] = by.get(case["section"], 0) + 1
    check("the fixture holds the measured pass-3 sweep (116 questions)",
          by.get("sweep") == 116, f"got {by.get('sweep')}")
    check("the fixture holds the pass-1 availability questions (25)",
          by.get("pass1") == 25, f"got {by.get('pass1')}")
    check("the fixture holds the pass-2 availability questions (35)",
          by.get("pass2") == 35, f"got {by.get('pass2')}")
    check("the fixture holds the owner's trap sentences (6)",
          by.get("trap") == 6, f"got {by.get('trap')}")
    probes = [c["probe"] for c in got]
    check("every case has its own probe id", len(set(probes)) == len(probes),
          f"{len(probes)} cases, {len(set(probes))} ids")
    unknown = sorted({c["expect"] for c in got if c.get("expect")} - ids)
    check("every expected row is a real catalogue row", not unknown, ", ".join(unknown))
    invented = [c["probe"] for c in got
                if not set(FG._norm(subject(c["question"])).split())
                <= set(FG._norm(c["question"]).split())]
    check("the subject is the question's own words, never invented", not invented,
          ", ".join(invented))


if __name__ == "__main__":
    for fn in (t_every_measured_question_names_its_row,
               t_a_question_that_names_no_row_falls_through_honestly,
               t_the_owner_notion_and_document_traps_land_on_their_rows,
               t_every_alias_names_its_own_row_and_no_other,
               t_the_fixture_is_the_measured_set_and_every_row_is_real):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
