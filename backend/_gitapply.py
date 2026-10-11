"""`git apply` from a scratch directory, when that directory is inside a repo.

WHY THIS EXISTS

`backend/_stack.py` and `backend/_skeleton.py` build a stand-in for one of the
owner's files by writing small patches into a temporary folder and applying
them with `git apply`. That only works while git treats the temporary folder as
the place the patch's paths are relative to.

It does not, when the folder is inside a git work tree. `git apply`, run
anywhere inside a repository, resolves the paths in the patch against the
work-tree ROOT rather than the current directory. So in a scratch folder at
`<repo>/tmp/jarvis-stack-abc/`:

  * `git apply --include jarvis_gate.py one.patch` matches nothing (the path it
    sees is `tmp/jarvis-stack-abc/jarvis_gate.py`), prints "Skipped patch", and
    **exits 0**. The stand-in comes back EMPTY, and every check written against
    it is vacuous - about a dozen suites went that way in the review of
    2026-10-08, in an environment whose TMPDIR pointed inside the repository;
  * `git apply --check new.patch` looks for the file at the repository root,
    does not find it, and fails - so a rehearsal reports a broken patch that is
    not broken.

`GIT_CEILING_DIRECTORIES` is the documented way to say "stop looking for a
repository at or above here": with it set to the work-tree root, the scratch
folder is outside any repository as far as git is concerned, and the paths
resolve against the scratch folder - which is what every caller already
assumes.

Nothing changes when the scratch folder is genuinely outside a repository,
which is the normal case on the owner's PC and in CI, where TMPDIR is not in
the checkout.
"""
import os
import subprocess
from pathlib import Path


def work_tree_root(git: str, where: Path):
    """The work-tree root `where` sits inside, or None when it sits in none.

    Asked with the environment as it is, so a caller that already set
    `GIT_CEILING_DIRECTORIES` gets that answer rather than a second opinion.
    Never raises: git missing, a directory that is gone or a git that refuses
    all mean the same thing here - no ceiling is needed."""
    try:
        r = subprocess.run([git, "rev-parse", "--show-toplevel"], cwd=str(where),
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    root = (r.stdout or "").strip()
    return root or None


def env_for(git: str, where: Path) -> dict:
    """The environment for a `git apply` run in `where`.

    `os.environ`, plus `GIT_CEILING_DIRECTORIES` when `where` is inside a work
    tree. One call per `git apply` is not needed - the answer cannot change
    while one scratch folder is being filled - so callers compute it once."""
    env = dict(os.environ)
    root = work_tree_root(git, where)
    if root:
        env["GIT_CEILING_DIRECTORIES"] = root
    return env
