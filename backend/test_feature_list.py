"""Is "Everything Jarvis can do" still the whole truth, on both apps?

    python3 test_feature_list.py

WHY THIS EXISTS. The owner asked, 2026-10-08, for one button that lists the
entire feature set of Jarvis, with an extend button on each feature for more
(docs/FEATURES-LIST-DESIGN.md). The list is `features/features.json`, and it
rots two ways, both silent:

  - a feature is BUILT and nobody adds it - the page then lies by omission,
    which is exactly what the owner asked to be able to avoid; and
  - a feature is REMOVED and the line stays - the page then promises a button
    that is not there.

`tools/check_feature_list.py` is the check for both, against the real
registries (the Brain's read allow-list, the desktop's generated menu
catalogue, the phone's MenuPlaces.kt). This suite runs it, and then proves the
check itself is sensitive: a made-up route section, menu id or `covers` entry
must FAIL, in the checker's own terms, naming the id. A check that cannot fail
is a comment, and the whole point of this one is that it can.

It also holds the three copies of the list together: the source, the file the
desktop page fetches, and the asset the phone reads. They must be
byte-identical, the same rule `test_base_matches_repo.py` applies to the
backend copies - two copies that drift mean the two apps disagree about what
Jarvis does, in the owner's own words.

Needs nothing from the owner's PC; runs anywhere, including CI (it is picked up
by backend/run_suites.py like every other test_*.py).
"""
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
import check_feature_list as C  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def t_the_list_is_complete_and_true():
    """Every route section and menu id covered or in INTERNAL, every id real,
    every entry readable, the three copies one file."""
    bad = C.problems()
    check("the feature list covers every route section and menu id, and every line is true",
          not bad, "\n        ".join(bad))
    got = C.entries()
    groups = [e["group"] for e in got]
    seen = [g for i, g in enumerate(groups) if i == 0 or groups[i - 1] != g]
    check("the nine groups are all used, in the design's order",
          seen == C.GROUPS, seen)
    check("the list is a readable length, not one row per route",
          60 <= len(got) <= 120, len(got))
    ids = [e["id"] for e in got]
    check("no entry id is used twice", len(ids) == len(set(ids)))


def t_the_check_is_sensitive_both_directions():
    """The check must FAIL when a feature is added or removed unnoticed.

    This is the part that matters: the completeness test is only worth having
    if a new route section or menu id, and a `covers` id that is gone, are both
    caught - naming the id, so the failure says what to fix."""
    known = C.known_ids()
    real = C.entries()

    # A feature that was built and never listed.
    missing = C.uncovered([], {"a_new_pane_nobody_listed": "made up"})
    check("an unlisted route section or menu id is reported, by name",
          missing == ["a_new_pane_nobody_listed"], missing)

    # A line that promises something the code no longer has.
    phantom = C.phantom_covers(
        [{"id": "x", "covers": ["a_pane_that_was_removed"]}], known)
    check("a `covers` id that is no longer in the code is reported, by name",
          len(phantom) == 1 and "a_pane_that_was_removed" in phantom[0]
          and phantom[0].startswith("x:"), phantom)

    # And a row that has lost one of its three required answers.
    fields = C.field_problems([{"id": "y", "group": "Talking", "title": "t",
                                "what": "w", "where": "", "asks": "a",
                                "limit": "", "surface": "both", "covers": []}])
    check("an entry with an empty `where` is reported, by name",
          any("y" in b and "`where` is empty" in b for b in fields), fields)

    # CONTROL: the real list passes the same three calls, so the failures above
    # are the made-up input and not the checks being always-red.
    check("CONTROL: the real list passes all three of those calls",
          C.uncovered(real, known) == [] and C.phantom_covers(real, known) == []
          and C.field_problems(real) == [])


def t_every_copy_is_the_same_file():
    bad = C.copy_problems()
    check("the source and the two apps' copies are byte-identical", not bad,
          "\n        ".join(bad))
    # ...and each copy really is read by something, or the copies are pointless.
    page = (REPO / "jarvis-desktop" / "src" / "features.js").read_text(encoding="utf-8")
    screen = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis"
              / "client" / "net" / "Features.kt").read_text(encoding="utf-8")
    check("the desktop page fetches its copy", '"features.json"' in page)
    check("the phone reads its copy from assets", '"features.json"' in screen)
    check("the source's own copy sits where the checker says",
          C.source_bytes() == (REPO / "features" / "features.json").read_bytes())


if __name__ == "__main__":
    for fn in (t_the_list_is_complete_and_true,
               t_the_check_is_sensitive_both_directions,
               t_every_copy_is_the_same_file):
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
