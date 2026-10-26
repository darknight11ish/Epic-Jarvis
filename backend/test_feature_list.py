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

And it proves the TEACHING claim is tested, not just made (rule 7, 2026-10-25).
A feature row can name a lesson that never mentions it, and every other rule
here stayed green while it did: "Save a draft to your Drafts folder" was taught
by a lesson containing no "draft". Every taught row now carries either
`must_mention` or a `TEACHING_GAP` line, the suite proves a made-up row whose
lesson lacks its word FAILS and that the real list passes, and `TEACHING_GAP`
records the rows whose lesson genuinely does not teach them yet - one line
each, self-emptying.

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
    # NO CEILING, AND IT SHOULD NOT COME BACK (2026-10-09). This read
    # `60 <= len(got) <= 120` with the label "a readable length, not one row
    # per route". The 120 was the builder's own number, not the owner's:
    # the request that produced this list asked for a place to see every
    # feature, and nothing in it asked for a size limit. It was recorded in
    # the commit that added it and in no owner decision.
    #
    # It then did real damage. On 2026-10-09 the list reached 120 with two
    # BUILT features still missing from it - news feeds and page watches -
    # and the ceiling was what blocked the row that would have listed them.
    # A limit that stops the list telling the truth is the wrong limit, and
    # the fix is not to raise the number: it is to have no number.
    #
    # THE FLOOR IS NOT A SIZE LIMIT and stays. It catches a list that has
    # been emptied, truncated or replaced wholesale - the one failure the
    # three calls above cannot see, because a short list covers nothing and
    # so "covers everything" would pass on an empty file.
    check("the list still holds every feature - nothing gutted it",
          60 <= len(got), len(got))
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


def t_every_lesson_is_claimed_by_a_feature_row():
    """Rule 6's reverse half: a lesson with no feature row is an orphan.

    The hole (Gemini's Part II ruling on Session B section 11.3): every other
    direction was checked - a feature the code has but the list omits, a
    `covers` id the code lost, a feature row with no lesson - but a feature ROW
    could vanish while its lesson stayed in the catalogue, and the checker
    printed that as information instead of a failure. These prove it fails now,
    naming the lesson, and that the two honest fixes both pass: name it from the
    row that teaches it, or record why it is deliberately not a feature."""
    lessons = C.lesson_ids()
    real = C.entries()
    check("CONTROL: every lesson in the catalogue is named by a feature row",
          C.lesson_problems(real) == [], C.lesson_problems(real))

    # The bite this rule exists for: the clipboard-time-machine row is removed
    # while its lesson stays in jarvis_tutorials.py.
    orphaned = [e for e in real if e.get("id") != "clipboard-time-machine"]
    problems = C.lesson_problems(orphaned)
    check("a feature row removed while its lesson remains is reported, by lesson name",
          len(problems) == 1 and "clipboard-time-machine" in problems[0]
          and "no feature row" in problems[0], problems)
    check("  ...and the line names both honest fixes (a row, or an exemption)",
          bool(problems) and "covers" in problems[0]
          and "LESSON_UNCOVERED" in problems[0], problems)

    # The other honest answer: an explicit exemption with its reason.
    exempted = C.lesson_problems(
        orphaned, lessons=lessons,
        exempt={"clipboard-time-machine": "the row was removed for this test"})
    check("...and an explicit exemption with a reason makes it pass",
          exempted == [], exempted)

    # The exemption list empties itself rather than becoming a hiding place.
    stale = C.lesson_problems(real, exempt={"clipboard-time-machine": "why"})
    check("an exemption for a lesson a row names again FAILS (delete it)",
          len(stale) == 1 and "delete the exemption" in stale[0], stale)
    unknown = C.lesson_problems(
        real, exempt={"a-lesson-that-was-deleted": "why"})
    check("an exemption for a lesson that no longer exists FAILS",
          len(unknown) == 1 and "not a lesson in jarvis_tutorials.py" in unknown[0],
          unknown)
    empty = C.lesson_problems(
        orphaned, lessons=lessons,
        exempt={"clipboard-time-machine": "   "})
    check("an exemption with no reason FAILS",
          any("has no reason" in b for b in empty), empty)


def t_a_one_sided_claim_carries_its_reason():
    """Rule 5, and the reason it covers one direction only.

    An entry whose `surface` is `"phone"` tells the owner his PC is missing the
    feature. That is the claim that misinformed him three times (PC help,
    "What did I believe on this date?", the rush-latch banner - all three said
    `phone` while the desktop rendered them), so it must carry a sentence
    saying why. The shape is all a checker can judge - it cannot tell whether a
    sentence is TRUE - so these prove the three ways it bites:
    a claim with no reason, a claim whose "reason" is the value said again, and
    an exemption in REASON_PENDING that is no longer needed."""
    def entry(**over):
        base = {"id": "z", "group": "Talking", "title": "t", "what": "w",
                "where": "w", "asks": "a", "limit": "", "surface": "phone",
                "covers": []}
        base.update(over)
        return base

    bare = C.field_problems([entry()])
    check("a `phone` entry with no reason is reported, by name",
          any("z" in b and "no `surface_reason`" in b for b in bare), bare)

    echo = C.field_problems([entry(surface_reason="phone only")])
    check("a reason that is only the value said again is refused",
          any("not a reason" in b for b in echo), echo)

    good = C.field_problems([entry(surface_reason=(
        "The phone's own display setting, which no PC control can change."))])
    check("a sentence a person wrote is accepted", good == [], good)

    check("a `desktop` entry needs no reason (the rule is one-directional)",
          C.field_problems([entry(surface="desktop")]) == [])

    stale = C.pending_problems([entry(surface="both")])
    check("an exemption that is no longer needed FAILS, so the list empties itself",
          len(stale) == len(C.REASON_PENDING) and all("delete its line" in b for b in stale),
          stale)

    # CONTROL: the committed list passes both halves - so the failures above are
    # the made-up input, not a check that is always red.
    real = C.entries()
    check("CONTROL: the real list passes rule 5, both halves",
          C.field_problems(real) == [] and C.pending_problems(real) == [],
          C.pending_problems(real))


def t_a_taught_row_must_name_words_its_lesson_uses():
    """Rule 7: a row that names a lesson must name a word that lesson really uses.

    THE HOLE (2026-10-25). Rules 2 and 6 kept the list true about the code and
    kept every lesson tied to a row, but nothing compared the row's subject with
    the lesson's text. So "Save a draft to your Drafts folder" could name
    `home-calendar-email` - a lesson with no "draft" in it - and the checker
    said "every feature is taught". This is the self-proof: a made-up row whose
    made-up lesson does not contain its word must FAIL, naming all three, and
    the real list must pass. A check that cannot fail proves nothing, which is
    why the pass case is a CONTROL at the end and the fail case is the point.

    The three ways in are all proved, because each is a way to get round the
    rule rather than through it: writing no `must_mention` at all, writing a
    word the lesson does not use, and leaving the field on a row that no lesson
    teaches.
    """
    # A made-up lesson and row, so the proof needs no edit to the real
    # catalogue and cannot pass because of what the real files happen to say.
    fake = ({"id": "fake-lesson", "title": "A made-up lesson",
             "steps": ({"title": "It does a thing",
                        "body": "It reads the thing and says what it found."},)},
            {"id": "other-lesson", "title": "A second made-up lesson",
             "steps": ({"title": "Something else entirely",
                        "body": "This one talks about a different subject."},)})

    def row(**over):
        base = {"id": "fake-feature", "group": "Talking", "title": "t",
                "what": "w", "where": "w", "asks": "a", "limit": "",
                "surface": "both", "covers": ["fake-lesson"],
                "must_mention": ["thing"]}
        base.update(over)
        return base

    good = C.keyword_problems([row()], catalogue=fake, gaps={})
    check("a row whose keyword is really in its lesson passes", good == [], good)

    # 1. The bite: the lesson does not contain the word.
    bad = C.keyword_problems([row(must_mention=["nonsense"])], catalogue=fake, gaps={})
    check("a synthetic row whose lesson lacks its keyword FAILS", len(bad) == 1, bad)
    check("  ...and the line names the feature, the lesson and the missing word",
          bool(bad) and "fake-feature" in bad[0] and "fake-lesson" in bad[0]
          and "nonsense" in bad[0], bad)

    # 2. The gate cannot be skipped by writing nothing.
    silent = C.keyword_problems([row(must_mention=None)], catalogue=fake, gaps={})
    check("a taught row with no `must_mention` FAILS (the gate is not skippable)",
          len(silent) == 1 and "no `must_mention`" in silent[0], silent)

    # 3. And the field cannot be left behind when a lesson stops teaching a row.
    stale = C.keyword_problems(
        [row(covers=[])], catalogue=fake, gaps={})
    check("`must_mention` on a row no lesson teaches FAILS (a stale field)",
          len(stale) == 1 and "delete the field" in stale[0], stale)

    # 4. Shape: short, lowercase, plain words.
    check("more than three words is refused",
          any("must hold 1 to 3" in b for b in C.keyword_problems(
              [row(must_mention=["it", "reads", "the", "thing"])],
              catalogue=fake, gaps={})))
    check("a capital letter is refused (the check is case-insensitive anyway)",
          any("write it lowercase" in b for b in C.keyword_problems(
              [row(must_mention=["Thing"])], catalogue=fake, gaps={})))
    check("an empty list is refused",
          any("must hold 1 to 3" in b for b in C.keyword_problems(
              [row(must_mention=[])], catalogue=fake, gaps={})))

    # 5. The recorded gap is a work list, not a silence: it empties itself.
    gap = {"fake-feature": ("fake-lesson", "the lesson never says it")}
    check("a recorded gap stands in for the words",
          C.keyword_problems([row(must_mention=None)], catalogue=fake, gaps=gap) == [])
    closed = C.keyword_problems([row()], catalogue=fake, gaps=gap)
    check("a row that gains keywords FAILS until its gap line is deleted",
          len(closed) == 1 and "delete the gap line" in closed[0], closed)
    wrong_lesson = C.keyword_problems(
        [row(must_mention=None)], catalogue=fake,
        gaps={"fake-feature": ("other-lesson", "why")})
    check("a gap line naming a lesson the row does not name FAILS",
          any("does not name that lesson" in b for b in wrong_lesson), wrong_lesson)
    no_reason = C.keyword_problems(
        [row(must_mention=None)], catalogue=fake,
        gaps={"fake-feature": ("fake-lesson", "  ")})
    check("a gap line with no reason FAILS",
          any("has no reason" in b for b in no_reason), no_reason)

    # CONTROL, and the one that matters most: the real list passes the very
    # check that just failed three different ways on made-up input.
    real = C.keyword_problems(C.entries())
    check("CONTROL: the committed list passes rule 7 - every real keyword is in "
          "the lesson its row names", real == [], real)
    taught = [e for e in C.entries() if any(c in set(C.lesson_ids())
                                            for c in e.get("covers") or [])]
    check("CONTROL: every taught row is either keyworded or a recorded gap",
          all(e.get("must_mention") is not None or e["id"] in C.TEACHING_GAP
              for e in taught), len(taught))
    check("every TEACHING_GAP line names a real feature row",
          all(any(x.get("id") == fid for x in C.entries()) for fid in C.TEACHING_GAP))


if __name__ == "__main__":
    for fn in (t_the_list_is_complete_and_true,
               t_the_check_is_sensitive_both_directions,
               t_every_copy_is_the_same_file,
               t_every_lesson_is_claimed_by_a_feature_row,
               t_a_one_sided_claim_carries_its_reason,
               t_a_taught_row_must_name_words_its_lesson_uses):
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
