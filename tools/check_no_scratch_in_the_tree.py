#!/usr/bin/env python3
"""The agent's scratch folders stay out of the tree.

    python3 tools/check_no_scratch_in_the_tree.py

WHY THIS EXISTS. `.dsh-scratch-tools/` and `scratchpad/` are agent scratch, not
the app - `README.md`'s own table says so of `scratchpad/` ("scratch
measurements and research, not part of the app"), and the script in
`.dsh-scratch-tools/` describes itself as a throwaway. Measured on 2026-10-14,
neither was ignored and five files were TRACKED in them:

    .dsh-scratch-tools/make_picture_card_patch.py   the writer of
        backend/picture-card.patch, built by hand from the base's own lines
    scratchpad/admem/budget_measure.py              a token-budget measurement
    scratchpad/brain-sections/brain-0{1,2,3}-*.png  three screenshots

None of it is read by code, a test or a workflow. This is the THIRD time this
repository has found the same failure, and the first two are why it is a check
and not a habit: `.gitignore`'s own history records `dshwork/` (about 88 MB of
agent scratch a plain `git add -A` would have committed) and `.dsh-scratch/`
(207,942 files, about 75 GB - among them browser `Login Data` and `Cookies`
files, a credential store in a folder a `git add -A` would have swept into a
public repository). Both notes fixed the one folder they named. This one was
not covered, and five small files is how the next 75 GB starts.

WHAT IT COSTS, AND THE TWO POINTERS THAT HAVE TO MOVE WITH IT. Untracking is
not deleting - every file above is still on this machine's disk - but no clone
carries them any more, and two of the five are named from somewhere else:

  * `scratchpad/admem/budget_measure.py` is the script behind the numbers in
    `docs/ADAPTIVE-MEMORY-DESIGN.md` section 8, which says so in as many words
    ("The script is kept ... so the numbers can be re-run rather than taken on
    trust"). A clone no longer has it.
  * `.dsh-scratch-tools/make_picture_card_patch.py` is the only in-tree writer
    of the TRACKED `backend/picture-card.patch` (it writes it at its own line
    51). The patch itself is still tracked, pinned by the stack and applied by
    the suites; only its generator is now outside the repository.

If either promise should survive a clone, the script belongs somewhere tracked
- `tools/` is where this project's other patch writers live
(`tools/gen_ollama_direct_patch.py`, `tools/gen_tasks_patch.py`) - with the
pointer in the document moved to match. That is a decision, not a check, so
this check does not make it: it fails only if the scratch comes back.

WHAT TO DO IF THIS FAILS. Do not "fix" it by editing this check. Either the
file is scratch and the tree should not carry it
(`git rm -r --cached .dsh-scratch-tools` or `git rm -r --cached scratchpad` -
`--cached` keeps it on disk), or it is genuinely meant to live in the
repository - in which case it is not scratch, it belongs under `tools/`, and
the `scratchpad/` rule in `.gitignore` is the thing that is wrong.
"""
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

#: The scratch folders, as `.gitignore` spells them, each with what is in it.
FOLDERS = (".dsh-scratch-tools/", "scratchpad/")

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name
          + (("\n      " + str(detail)) if (detail and not cond) else ""))


def tracked(*patterns):
    """Every tracked path under `patterns`, or None when there is no repository
    here to ask. `-z` so a path with a space in it survives being read back."""
    try:
        done = subprocess.run(["git", "ls-files", "-z", "--", *patterns],
                              cwd=REPO, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except OSError:
        return None
    if done.returncode != 0:
        return None
    return [p for p in done.stdout.split("\0") if p]


def main() -> int:
    paths = tracked(*FOLDERS)
    if paths is None:
        print("skip  no git repository here - this check needs the repository, "
              "not a copy of the files")
        return 0

    for folder in FOLDERS:
        hits = [p for p in paths if p.startswith(folder)]
        check(f"nothing under {folder} is tracked (it is agent scratch, not the app)",
              not hits,
              "these are tracked: " + ", ".join(sorted(hits))
              + f" - `git rm -r --cached {folder.rstrip('/')}` them (`--cached` keeps "
                "the files on disk), or write down here why one of them is not scratch")

    # The ignore rules themselves, because the files being untracked is only
    # half of it: without the rule the next `git add -A` sweeps them back in,
    # which is exactly how all five arrived. The videos check guards its
    # `.gitattributes` line the same way.
    ignore = (REPO / ".gitignore").read_text(encoding="utf-8")
    for folder in FOLDERS:
        check(f"... and .gitignore still ignores {folder}",
              re.search(r"(?m)^" + re.escape(folder) + r"[ \t]*$", ignore) is not None,
              f"`.gitignore` no longer carries a `{folder}` rule, so a plain "
              f"`git add -A` sweeps the scratch back into the tree")

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
