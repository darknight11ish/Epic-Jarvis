"""The launch videos stay in a release, not in the tree.

    python3 test_no_videos_in_the_tree.py

WHY THIS EXISTS. The ten launch `.mp4`s were 184 MB, and `videos/` was 199 MB of
a 296 MB repository - 67% of everything, in files no code, test or script ever
reads. Git cannot delta-compress an already-compressed video either, so every
re-run of a composition stored a whole new copy on top: the cost could only
grow.

On 2026-10-07 the owner chose to move them out. They are NOT deleted - they are
assets on the `launch-videos` release - and `videos/` keeps every plan,
composition brief and project file, so any of them can still be rendered again.
The README links to the release instead of the files.

`.gitattributes` marks `*.mp4` binary, but that only stops git diffing them; it
never stopped one being committed, which is how 184 MB arrived in the first
place. This is the check that would have. It is deliberately about `.mp4`, not
about size: the repository has a handful of legitimately large files (the
`docs/critters/` pictures, the poster JPGs beside each video), and a blunt size
limit would fight those for no gain.

WHAT TO DO IF THIS FAILS. Do not "fix" it by editing this test. Either the file
belongs in the release (edit that release and upload it, which is how a
re-render replaces one), or it is genuinely meant to live in the tree - in which
case say so here with the reason, the way every other deliberate exception in
this repository is written down.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name + (("\n      " + str(detail)) if (detail and not cond) else ""))


def tracked(pattern: str) -> list:
    out = subprocess.run(["git", "ls-files", "--", pattern], cwd=REPO,
                         capture_output=True, text=True)
    return [p for p in out.stdout.split("\n") if p.strip()]


def main() -> int:
    git_dir = REPO / ".git"
    if not git_dir.exists():
        print("skip  no .git here - this check needs the repository, not a copy of the files")
        return 0

    videos = tracked("*.mp4")
    check("no .mp4 is tracked in the tree (they live in the `launch-videos` release)",
          not videos,
          "these are tracked: " + ", ".join(videos)
          + " - upload them to the launch-videos release and `git rm` them, or write "
            "down here why this one is different")

    check("... and .gitattributes still marks *.mp4 binary",
          "*.mp4" in (REPO / ".gitattributes").read_text(encoding="utf-8"),
          "*.gitattributes no longer carries the *.mp4 rule")

    # The sources must still be here. If someone "tidied" the whole videos/
    # folder away with the videos, the plans needed to render them again are
    # gone - which is the one outcome the 2026-10-07 decision promised would
    # not happen.
    briefs = tracked("videos/*/composition-brief.md")
    check("the composition briefs are still in the tree, so a video can be rendered again",
          len(briefs) >= 5,
          f"only {len(briefs)} brief(s) found; expected at least 5 (v1-v6 minus any without one)")

    projects = tracked("videos/*/composition/*")
    check("... and their project files are still here",
          len(projects) >= 20,
          f"only {len(projects)} project file(s) found")

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
