"""test_roll_decisions.py - the DECISIONS fragments, their roll, and the race.

    python3 backend/test_roll_decisions.py

What this proves, in temp folders only (the real docs/DECISIONS.md and
decisions.d/ are never written):

  1. A fragment is accepted only when its name is `YYYY-MM-DD-<slug>.md`, its
     content is ONE dated bullet with a bold title whose date agrees with the
     name, and `docs/DECISIONS.md` carries the anchor heading the tool looks
     for. Every bad shape gets a plain problem line, not a crash.
  2. The roll appends the bullets at the END of the record, in date order (the
     record is chronological, oldest first - NOT CHANGELOG.md's newest-first),
     keeps every existing entry and the anchor, and removes the fragment files
     only after the new text is read back.
  3. `--dry-run` writes NOTHING; a second roll is a no-op (idempotent); `--check`
     exits 0 for good fragments and 1 for a bad one.
  4. A `docs/CLAIMS.tsv` source that cites a fragment as
     `decisions.d/<name>.md:<line>` is re-anchored to the exact line its entry
     lands on, and no other row is touched.
  5. TWO PULL REQUESTS WITH DIFFERENT FRAGMENTS DO NOT CONFLICT: each changes one
     path of its own and no path the other changes, so git has nothing to
     conflict about - and the merged tree rolls both bullets with nothing lost.
     That property is the whole reason this exists, so it is measured here and
     not assumed.
  6. Nothing runs the roll automatically: every mention in CI carries `--check`.
  7. The real record is well formed today, and a resolver in this tool
     (`record_files`) really does see the rolled file and the fragments.

WHY THIS EXISTS. Every PR used to append to the end of docs/DECISIONS.md, so two
PRs always conflicted and a conflicted PR gets no CI - PR #386, and #369/#371
before it. The fix is one small file per PR plus this roll. A tool that fails
silently would be worse than the race, so the roll is proved here, not assumed.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
import roll_decisions as R  # noqa: E402

PASSED, FAILED = [], []
BASE = Path(tempfile.mkdtemp(prefix="jarvis-roll-decisions-"))

HEADING = ("## Decisions written as `decisions.d/` fragments, folded in here "
           "in date order")
OLD = "**Decided:** what was decided then, kept word for word."

RECORD = f"""# Decisions, dated

**This is the record.** An opening line.

## 2026-10-20 - An older decision

{OLD}

## 2026-10-27 - A newer decision

**Decided:** what was decided later, also kept word for word.

{HEADING}

From 2026-10-28 the fragments are folded in here.
"""

GOOD = "- **2026-10-28 — A quieter HUD:** what changed, and one honest limit."

CLAIMS = """# The claims register.

A01\ta claim that came from a decision\tgrep:tools:a phrase\tbuilt\tdecisions.d/2026-10-23-later.md:1
A02\ta claim already in the record\tgrep:tools:another phrase\tbuilt\tdocs/DECISIONS.md:3
"""


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def fresh() -> tuple:
    """A temp case folder: an empty decisions.d and a record with one entry."""
    base = Path(tempfile.mkdtemp(dir=BASE, prefix="case-"))
    frags = base / "decisions.d"
    frags.mkdir()
    decisions = base / "DECISIONS.md"
    decisions.write_text(RECORD, encoding="utf-8")
    return frags, decisions


def fragment(frags: Path, name: str, body: str) -> Path:
    path = frags / name
    path.write_text(body, encoding="utf-8")
    return path


def lines_of(path: Path) -> list:
    return path.read_text(encoding="utf-8").splitlines()


# ---------------------------------------------------------------- checks ----

def t_a_good_fragment_and_the_anchor_pass():
    frags, decisions = fresh()
    check("an empty decisions.d with the anchor has no problems",
          R.problems(frags, decisions) == [], R.problems(frags, decisions))
    fragment(frags, "2026-10-28-a-quieter-hud.md", GOOD + "\n")
    check("one well-formed fragment has no problems",
          R.problems(frags, decisions) == [], R.problems(frags, decisions))
    (frags / "README.md").write_text("# how this works\n", encoding="utf-8")
    check("the folder's own README.md is not treated as a fragment",
          R.problems(frags, decisions) == [], R.problems(frags, decisions))


def t_bad_fragments_are_named_one_by_one():
    frags, decisions = fresh()
    fragment(frags, "a-quieter-hud.md", GOOD + "\n")
    found = R.problems(frags, decisions)
    check("a name without the date/slug shape is reported",
          len(found) == 1 and "YYYY-MM-DD-<slug>.md" in found[0], found)
    for name, body, needle in (
        ("2026-10-28-empty.md", "\n", "empty"),
        ("2026-10-28-no-bullet.md", "A sentence, not a bullet.\n", "start with '- '"),
        ("2026-10-28-two-paras.md", "- **One.**\n\n- **Two.**\n", "blank line"),
        ("2026-10-28-no-title.md", "- a plain line without a title\n", "bold title"),
        ("2026-10-28-undated.md", "- **No date in this one:** prose.\n", "YYYY-MM-DD"),
        ("2026-10-28-wrong-date.md",
         "- **2026-10-27 — Wrong date:** prose.\n", "must agree"),
    ):
        frags2, decisions2 = fresh()
        fragment(frags2, name, body)
        got = R.problems(frags2, decisions2)
        check(f"a fragment that is {needle!r} is reported",
              len(got) == 1 and needle in got[0], got)
    frags3 = Path(tempfile.mkdtemp(dir=BASE, prefix="case-")) / "decisions.d"
    frags3.mkdir()
    no_anchor = Path(tempfile.mkdtemp(dir=BASE, prefix="case-")) / "DECISIONS.md"
    no_anchor.write_text("# Decisions, dated\n\n## 2026-10-20 - Old\n\nold.\n",
                         encoding="utf-8")
    got = R.problems(frags3, no_anchor)
    check("a record without the anchor heading is reported before anything rolls",
          len(got) == 1 and "anchor" in got[0], got)


def t_the_roll_appends_at_the_end_in_date_order():
    frags, decisions = fresh()
    fragment(frags, "2026-10-02-first.md", "- **2026-10-02 — First:** one.\n")
    fragment(frags, "2026-10-23-later.md", "- **2026-10-23 — Later:** two.\n")
    count, _ = R.roll(frags, decisions)
    text = decisions.read_text(encoding="utf-8")
    check("the roll reports the bullets it inserted", count == 2, count)
    check("the older bullet is first and the newer one after it, because the "
          "record is chronological oldest-first",
          text.index("- **2026-10-02 — First:**")
          < text.index("- **2026-10-23 — Later:**"), text)
    check("both bullets come AFTER everything that was already in the record",
          text.index(OLD) < text.index(HEADING)
          < text.index("- **2026-10-02 — First:**")
          < text.index("- **2026-10-23 — Later:**"), text)
    check("the two bullets are separated by a blank line, so each reads as its "
          "own entry",
          "\n\n- **2026-10-23 — Later:**" in text, text)
    check("the record still ends with the newest bullet",
          text.rstrip().endswith("- **2026-10-23 — Later:** two."), text[-200:])
    check("every older entry and the anchor are kept",
          all(part in text for part in (OLD, "## 2026-10-27", HEADING)), text)
    check("the fragment files are removed after the roll",
          R.fragment_paths(frags) == [], R.fragment_paths(frags))
    after = decisions.read_text(encoding="utf-8")
    check("a second roll is a no-op (idempotent)",
          R.roll(frags, decisions)[0] == 0
          and decisions.read_text(encoding="utf-8") == after)


def t_dry_run_writes_nothing():
    frags, decisions = fresh()
    fragment(frags, "2026-10-28-a-quieter-hud.md", GOOD + "\n")
    claims = Path(tempfile.mkdtemp(dir=BASE, prefix="case-")) / "CLAIMS.tsv"
    claims.write_text(CLAIMS, encoding="utf-8")
    before = decisions.read_text(encoding="utf-8")
    before_claims = claims.read_text(encoding="utf-8")
    count, _ = R.roll(frags, decisions, dry_run=True, claims=claims)
    check("a dry run reports the bullet it would insert", count == 1, count)
    check("a dry run leaves the record exactly as it was",
          decisions.read_text(encoding="utf-8") == before)
    check("a dry run leaves the claims register exactly as it was",
          claims.read_text(encoding="utf-8") == before_claims)
    check("a dry run leaves the fragment files in place",
          len(R.fragment_paths(frags)) == 1)


def t_the_check_exit_codes_are_real():
    frags, decisions = fresh()
    args = ["--check", "--fragments", str(frags), "--decisions", str(decisions)]
    check("--check on an empty folder exits 0", R.main(args) == 0)
    fragment(frags, "2026-10-28-a-quieter-hud.md", GOOD + "\n")
    check("--check on a good fragment exits 0", R.main(args) == 0)
    fragment(frags, "2026-10-28-BAD_Name.md", GOOD + "\n")
    check("--check on a bad name exits 1", R.main(args) == 1)


def t_a_claims_source_is_reanchored_to_the_exact_line():
    frags, decisions = fresh()
    fragment(frags, "2026-10-23-later.md", "- **2026-10-23 — Later:** two.\n")
    claims = Path(tempfile.mkdtemp(dir=BASE, prefix="case-")) / "CLAIMS.tsv"
    claims.write_text(CLAIMS, encoding="utf-8")
    R.roll(frags, decisions, claims=claims)
    rows = {line.split("\t")[0]: line.split("\t") for line in
            claims.read_text(encoding="utf-8").splitlines() if "\t" in line}
    source = rows["A01"][4]
    check("the source that named the fragment now names the record",
          source.startswith("docs/DECISIONS.md:"), source)
    record_lines = lines_of(decisions)
    number = int(source.split(":")[-1])
    check("... and its line number really is the entry's first line",
          1 <= number <= len(record_lines)
          and record_lines[number - 1].startswith("- **2026-10-23 — Later:**"),
          record_lines[max(number - 2, 0):number + 1])
    check("a row that already named the record is untouched",
          rows["A02"][4] == "docs/DECISIONS.md:3", rows["A02"])
    check("the row's claim, check and state are untouched",
          rows["A01"][1] == "a claim that came from a decision"
          and rows["A01"][2] == "grep:tools:a phrase"
          and rows["A01"][3] == "built", rows["A01"])


def t_two_pull_requests_with_different_fragments_do_not_conflict():
    """The property this whole mechanism exists for, measured on two branches.

    Each branch starts from the same tree and adds ONE fragment file. A git
    merge conflicts when both sides changed the same path, so the proof is that
    the two sets of changed paths do not meet - and then that the merged tree
    rolls both bullets with every old word still there.
    """
    shared = Path(tempfile.mkdtemp(dir=BASE, prefix="shared-"))
    (shared / "decisions.d").mkdir()
    (shared / "DECISIONS.md").write_text(RECORD, encoding="utf-8")

    def branch(name: str, fragment_name: str) -> Path:
        tree = Path(tempfile.mkdtemp(dir=BASE, prefix=f"branch-{name}-"))
        shutil.copytree(shared, tree, dirs_exist_ok=True)
        fragment(tree / "decisions.d", fragment_name,
                 f"- **2026-10-28 — {name}:** the {name} branch's own entry.\n")
        return tree

    def changed(tree: Path) -> set:
        before = {p.relative_to(shared).as_posix() for p in shared.rglob("*")
                  if p.is_file()}
        now = {p.relative_to(tree).as_posix() for p in tree.rglob("*") if p.is_file()}
        return now - before

    left = branch("Left", "2026-10-28-left.md")
    right = branch("Right", "2026-10-28-right.md")
    left_changed, right_changed = changed(left), changed(right)
    check("each pull request changes ONE path, its own fragment",
          left_changed == {"decisions.d/2026-10-28-left.md"}
          and right_changed == {"decisions.d/2026-10-28-right.md"},
          (sorted(left_changed), sorted(right_changed)))
    check("... and the two paths do not meet, so git has nothing to conflict about",
          left_changed & right_changed == set(), sorted(left_changed & right_changed))

    merged = Path(tempfile.mkdtemp(dir=BASE, prefix="merged-"))
    shutil.copytree(shared, merged, dirs_exist_ok=True)
    for tree in (left, right):
        for path in (tree / "decisions.d").glob("*.md"):
            shutil.copy2(path, merged / "decisions.d" / path.name)
    count, _ = R.roll(merged / "decisions.d", merged / "DECISIONS.md")
    text = (merged / "DECISIONS.md").read_text(encoding="utf-8")
    check("the merged tree rolls both entries", count == 2, count)
    check("neither branch's words were lost",
          "the Left branch's own entry" in text
          and "the Right branch's own entry" in text, text[-600:])
    check("every old entry survived the merge and the roll",
          all(part in text for part in (OLD, "## 2026-10-27", HEADING)), text)


def t_the_record_reader_sees_both_places():
    """`record_files` is what the promise guards and the claims checker read the
    record with: the rolled file first, then the unrolled fragments, in order."""
    root = Path(tempfile.mkdtemp(dir=BASE, prefix="root-"))
    (root / "docs").mkdir()
    (root / "docs" / "DECISIONS.md").write_text(RECORD, encoding="utf-8")
    (root / "decisions.d").mkdir()
    (root / "decisions.d" / "README.md").write_text("# how\n", encoding="utf-8")
    fragment(root / "decisions.d", "2026-10-28-later.md",
             "- **2026-10-28 — Later:** in a fragment.\n")
    fragment(root / "decisions.d", "2026-10-02-earlier.md",
             "- **2026-10-02 — Earlier:** in another fragment.\n")
    found = [p.relative_to(root).as_posix() for p in R.record_files(root)]
    check("the record is the rolled file and both fragments, README excluded",
          found == ["docs/DECISIONS.md", "decisions.d/2026-10-02-earlier.md",
                    "decisions.d/2026-10-28-later.md"], found)
    text = R.record_text(root)
    check("its text carries the old entry and both fragments",
          OLD in text and "in a fragment." in text and "in another fragment." in text)


def t_the_real_record_is_well_formed():
    frags = REPO / "decisions.d"
    decisions = REPO / "docs" / "DECISIONS.md"
    found = R.problems(frags, decisions)
    check("the real decisions.d and docs/DECISIONS.md have no problems",
          found == [], found)
    text = decisions.read_text(encoding="utf-8")
    check("the real record carries the anchor heading exactly once",
          text.count(R.MARKER) == 1, text.count(R.MARKER))


def t_nothing_runs_the_roll_automatically():
    """The roll is deliberate: CI may check the fragments, never fold them in."""
    mentions = []
    for path in sorted((REPO / ".github" / "workflows").glob("*.yml")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "roll_decisions" in line:
                mentions.append((path.name, number, line.strip()))
    check("CI mentions the decisions roll at all (otherwise this guard is vacuous)",
          bool(mentions), mentions)
    check("every CI mention of it is `--check`, never the roll itself",
          all("--check" in line for _, _, line in mentions), mentions)
    runner = REPO / "backend" / "run_suites.py"
    check("the suite runner never rolls the decisions",
          "roll_decisions" not in runner.read_text(encoding="utf-8"))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn) and fn.__module__ == "__main__":
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
