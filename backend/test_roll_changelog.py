"""test_roll_changelog.py - the CHANGELOG fragments and their roll.

    python3 backend/test_roll_changelog.py

What this proves, in temp folders only (the real CHANGELOG.md and changelog.d/
are never written):

  1. A fragment is accepted only when its name is `YYYY-MM-DD-<slug>.md`, its
     content is ONE markdown bullet with a bold title, and `CHANGELOG.md`
     carries the heading the roll inserts under. Every bad shape gets a plain
     problem line, not a crash.
  2. The roll inserts the bullets newest first (the order CHANGELOG.md keeps)
     directly under that heading, keeps every existing entry, and removes the
     fragment files only after the new text is read back.
  3. `--dry-run` writes NOTHING; a second roll is a no-op (idempotent); `--check`
     exits 0 for good fragments and 1 for a bad one.

WHY THIS EXISTS. Every PR used to append to the same top of CHANGELOG.md, so
two PRs always conflicted and a conflicted PR gets no CI. The fix is one small
file per PR plus this roll. A tool that fails silently would be worse than the
race, so the roll is proved here, not assumed.
"""
from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
import roll_changelog as R  # noqa: E402

PASSED, FAILED = [], []
BASE = Path(tempfile.mkdtemp(prefix="jarvis-roll-changelog-"))

HEADING = "## Not in a numbered version yet"
OLD = "- **An older entry (2026-10-01).** Already in the file."


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def fresh():
    """A temp case folder: an empty changelog.d and a CHANGELOG with one entry."""
    base = Path(tempfile.mkdtemp(dir=BASE, prefix="case-"))
    frags = base / "changelog.d"
    frags.mkdir()
    changelog = base / "CHANGELOG.md"
    changelog.write_text(f"# What changed\n\n{HEADING}\n\n{OLD}\n", encoding="utf-8")
    return frags, changelog


def fragment(frags: Path, name: str, body: str) -> Path:
    p = frags / name
    p.write_text(body, encoding="utf-8")
    return p


GOOD = "- **A new thing (2026-10-23).** What it does, and one honest limit."


# ---------------------------------------------------------------- checks ----

def t_a_good_fragment_and_heading_pass():
    frags, changelog = fresh()
    check("an empty changelog.d with the heading has no problems",
          R.problems(frags, changelog) == [], R.problems(frags, changelog))
    fragment(frags, "2026-10-23-new-thing.md", GOOD + "\n")
    check("one well-formed fragment has no problems",
          R.problems(frags, changelog) == [], R.problems(frags, changelog))
    (frags / "README.md").write_text("# how this works\n", encoding="utf-8")
    check("the folder's own README.md is not treated as a fragment",
          R.problems(frags, changelog) == [])


def t_bad_fragments_are_named_one_by_one():
    frags, changelog = fresh()
    fragment(frags, "new-thing.md", GOOD + "\n")
    problem = R.problems(frags, changelog)
    check("a name without the date/slug shape is reported",
          len(problem) == 1 and "YYYY-MM-DD-<slug>.md" in problem[0], problem)
    for name, body, needle in (
        ("2026-10-23-empty.md", "\n", "empty"),
        ("2026-10-23-no-bullet.md", "A sentence, not a bullet.\n", "start with '- '"),
        ("2026-10-23-two-paras.md", "- **One.**\n\n- **Two.**\n", "blank line"),
        ("2026-10-23-no-title.md", "- a plain line without a title\n", "bold title"),
    ):
        frags2, changelog2 = fresh()
        fragment(frags2, name, body)
        got = R.problems(frags2, changelog2)
        check(f"a fragment that is {needle!r} is reported",
              len(got) == 1 and needle in got[0], got)
    frags3 = Path(tempfile.mkdtemp(dir=BASE, prefix="case-")) / "changelog.d"
    frags3.mkdir()
    no_heading = Path(tempfile.mkdtemp(dir=BASE, prefix="case-")) / "CHANGELOG.md"
    no_heading.write_text("# What changed\n\n- **Old (2026-10-01).** old.\n", encoding="utf-8")
    got = R.problems(frags3, no_heading)
    check("a CHANGELOG without the heading is reported before anything is rolled",
          len(got) == 1 and HEADING in got[0], got)


def t_the_roll_inserts_newest_first_and_removes_the_fragments():
    frags, changelog = fresh()
    fragment(frags, "2026-10-02-first.md", "- **First (2026-10-02).** one.\n")
    fragment(frags, "2026-10-23-later.md", "- **Later (2026-10-23).** two.\n")
    count, _ = R.roll(frags, changelog)
    text = changelog.read_text(encoding="utf-8")
    check("the roll reports the bullets it inserted", count == 2, count)
    check("the newest bullet is first, right under the heading",
          text.index("Later (2026-10-23)") < text.index("First (2026-10-02)"), text)
    check("the heading and the existing entry are kept",
          text.index(HEADING) < text.index("Later") < text.index(OLD), text)
    check("the fragment files are removed after the roll",
          R.fragment_paths(frags) == [], R.fragment_paths(frags))
    check("a second roll is a no-op (idempotent)", R.roll(frags, changelog)[0] == 0)


def t_dry_run_writes_nothing():
    frags, changelog = fresh()
    fragment(frags, "2026-10-23-new-thing.md", GOOD + "\n")
    before = changelog.read_text(encoding="utf-8")
    count, _ = R.roll(frags, changelog, dry_run=True)
    check("a dry run reports the bullet it would insert", count == 1, count)
    check("a dry run leaves CHANGELOG.md exactly as it was",
          changelog.read_text(encoding="utf-8") == before)
    check("a dry run leaves the fragment files in place",
          len(R.fragment_paths(frags)) == 1)


def t_the_check_exit_codes_are_real():
    frags, changelog = fresh()
    check("--check on an empty folder exits 0",
          R.main(["--check", "--fragments", str(frags), "--changelog", str(changelog)]) == 0)
    fragment(frags, "2026-10-23-new-thing.md", GOOD + "\n")
    check("--check on a good fragment exits 0",
          R.main(["--check", "--fragments", str(frags), "--changelog", str(changelog)]) == 0)
    fragment(frags, "2026-10-23-BAD_Name.md", GOOD + "\n")
    check("--check on a bad name exits 1",
          R.main(["--check", "--fragments", str(frags), "--changelog", str(changelog)]) == 1)


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
