"""test_package_install_guards.py - the two package-install guards can fail.

    python3 backend/test_package_install_guards.py

WHY THIS SUITE EXISTS. On 2026-11-18 a delegated agent ran `pip` with the
repository root as its working directory and TMP/TEMP pointing inside the tree.
Pip left seventeen `pip-metadata-*` and `pip-unpack-*` folders at the root,
untracked, one `git add -A` from being committed. Two guards answer that:
`tools/check_package_install_context.py` refuses the install before it runs, and
`tools/check_package_manager_temp_artifacts.py` catches the folders if the
refusal is ever bypassed. A guard nothing proves is the habit again, so this
suite makes each one fail on purpose and then shows it clean.

WHAT IT PROVES, and how:

  * the install guard PASSES exactly where the audit job runs it
    (`jarvis-desktop/src-tauri`, temporary folders outside the repo), and the
    audit job's own step would be red if the working directory moved to the
    root;
  * it REFUSES (exit 1) a repository-root working directory, a TMP/TEMP inside
    the repository, and - for uv - a UV_CACHE_DIR inside it. Every refusal
    names the folder and carries the exact fix sentence;
  * the wrapper (`--run -- <command>`) really does not run the command when it
    refuses: a canary file the command would write is absent afterwards, and
    present when the same command runs in a clean context;
  * a context it cannot judge (an unknown manager, a platform that is neither
    Windows nor POSIX, no command to read the manager from) is "not checked:"
    and exit 3 - never a pass;
  * the artifact checker is clean on this tree and says how many top-level
    entries it looked at, so "nothing is wrong" cannot be read as "nothing was
    looked at";
  * it BITES on a real fixture repository: a temp folder this suite makes,
    `git init`s and removes, with `pip-metadata-*`, `pip-unpack-*`,
    `*.dist-info` and a tracked one, naming every path and printing the
    commands that remove them - and it is clean again once they are removed;
  * it does NOT fire on legitimate paths: a `pip-*` name inside a tracked test
    fixture, an ignored `.dsh-scratch/` name, an ignored `node_modules/` at the
    root, or a real root file such as `pip-notes.md`;
  * a folder with no git is "not checked:", exit 3 - never a pass.

FIXTURES ONLY. The suite never installs a package, never asks a package
manager for anything, and never writes outside `.dsh-scratch/` (git-ignored) or
the machine's temporary folder. Nothing it makes survives the run.
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TOOLS = REPO / "tools"
sys.path.insert(0, str(TOOLS))

GUARD = TOOLS / "check_package_install_context.py"
ARTIFACT_CHECK = TOOLS / "check_package_manager_temp_artifacts.py"

#: The one sentence every refusal must carry, word for word.
FIX = "run the install from a scratch directory, or set TMP/TEMP outside the repo"

GIT = shutil.which("git")

#: Git-ignored, never committed, and where this suite may make a folder that
#: must look like it is inside the repository.
SCRATCH = REPO / ".dsh-scratch" / "package-install-guard-tests"

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """Something this machine cannot run: printed separately, never a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


# ---------------------------------------------------------------------------
#   helpers - every fixture is made and removed by the test that uses it
# ---------------------------------------------------------------------------

def _scratch_inside(*parts):
    """A real folder INSIDE the repository, under the ignored .dsh-scratch/."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    path = SCRATCH.joinpath(*parts)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    return path


def _scratch_outside(prefix):
    """A real folder OUTSIDE the repository, in the machine's temp folder."""
    return Path(tempfile.mkdtemp(prefix=prefix))


def _clean_env(tmp_outside, extra=None):
    """The environment for a clean install context: temp outside the repo.

    TMPDIR and TEMPDIR are set empty rather than dropped, so a value the
    machine happens to carry cannot decide a test; the guard treats an empty
    variable as unset.
    """
    env = {"TMP": str(tmp_outside), "TEMP": str(tmp_outside),
           "TMPDIR": "", "TEMPDIR": ""}
    for name in ("PIP_CACHE_DIR", "UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR",
                 "UV_TOOL_DIR"):
        env[name] = ""
    env.update(extra or {})
    return env


def _run(script, args, *, cwd, env_extra=None):
    """One real CLI run of a guard: (exit code, stdout + stderr, env used)."""
    env = dict(os.environ)
    env.update(env_extra or {})
    done = subprocess.run([sys.executable, "-B", str(script), *args],
                          cwd=str(cwd), env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=180)
    return done.returncode, done.stdout + done.stderr, env


def _module_main(module, argv):
    """One in-process run of a guard's `main`: (exit code, what it printed)."""
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        code = module.main(argv)
    return code, printed.getvalue()


def _has_path(text, path):
    """True when `text` names `path`, ignoring Windows case and slashes."""
    left = os.path.normcase(str(path)).replace("\\", "/").rstrip("/")
    right = os.path.normcase(text).replace("\\", "/")
    return left.lower() in right.lower()


# ---------------------------------------------------------------------------
#   The install guard: clean where it will run
# ---------------------------------------------------------------------------

def t_the_install_guard_passes_where_the_audit_job_runs_it():
    """The audit job's pip step runs from `jarvis-desktop/src-tauri`."""
    outside = _scratch_outside("pkg-guard-pass-")
    try:
        cwd = REPO / "jarvis-desktop" / "src-tauri"
        code, out, _env = _run(GUARD, ["--manager", "pip"], cwd=cwd,
                               env_extra=_clean_env(outside))
        check("the audit job's working directory is a clean install context",
              code == 0, out[-1200:])
        check("... and it says so in one pass line",
              "ok    a pip install would not write into the repository" in out,
              out[-1200:])
        check("... naming both the working directory and the repository root",
              _has_path(out, cwd) and _has_path(out, REPO), out[-1200:])
    finally:
        shutil.rmtree(outside, ignore_errors=True)


# ---------------------------------------------------------------------------
#   The install guard: each refusal, with the folder and the fix named
# ---------------------------------------------------------------------------

def t_a_repository_root_working_directory_is_refused():
    outside = _scratch_outside("pkg-guard-root-")
    try:
        code, out, _env = _run(GUARD, ["--manager", "pip"], cwd=REPO,
                               env_extra=_clean_env(outside))
        check("a pip install with the repository root as the working directory "
              "is refused (exit 1)", code == 1, out[-1600:])
        check("... the message says the working directory IS the root",
              "the working directory is the repository root" in out, out[-1600:])
        check("... and names that directory", _has_path(out, REPO), out[-1600:])
        check("... and carries the exact fix sentence", FIX in out, out[-1600:])
        check("... and says nothing was installed",
              "nothing was installed" in out, out[-1600:])
    finally:
        shutil.rmtree(outside, ignore_errors=True)


def t_a_temp_folder_inside_the_repository_is_refused():
    outside = _scratch_outside("pkg-guard-tmp-")
    inside = _scratch_inside("temp-inside")
    try:
        code, out, _env = _run(GUARD, ["--manager", "pip"], cwd=outside,
                               env_extra=_clean_env(inside))
        check("TMP/TEMP inside the repository is refused even from a clean "
              "working directory (exit 1)", code == 1, out[-1600:])
        check("... the message names the variable and the folder",
              "TMP is inside the repository" in out and _has_path(out, inside),
              out[-1600:])
        check("... and carries the exact fix sentence", FIX in out, out[-1600:])
    finally:
        shutil.rmtree(inside, ignore_errors=True)
        shutil.rmtree(outside, ignore_errors=True)


def t_uv_is_checked_and_its_own_folders_count():
    outside = _scratch_outside("pkg-guard-uv-")
    inside = _scratch_inside("uv-cache-inside")
    try:
        code, out, _env = _run(
            GUARD, ["--manager", "uv"], cwd=outside,
            env_extra=_clean_env(outside, {"UV_CACHE_DIR": str(inside)}))
        check("uv with its cache inside the repository is refused (exit 1)",
              code == 1, out[-1600:])
        check("... the message names UV_CACHE_DIR and the folder",
              "UV_CACHE_DIR is inside the repository" in out
              and _has_path(out, inside), out[-1600:])
        check("... and carries the exact fix sentence", FIX in out, out[-1600:])
        cache = outside / "uv-cache"
        cache.mkdir()
        code, out, _env = _run(
            GUARD, ["--manager", "uv"], cwd=outside,
            env_extra=_clean_env(outside, {"UV_CACHE_DIR": str(cache)}))
        check("uv with its cache outside the repository passes", code == 0,
              out[-1600:])
        check("... and the pass says the folders are outside",
              "temporary folders outside it" in out, out[-1600:])
    finally:
        shutil.rmtree(inside, ignore_errors=True)
        shutil.rmtree(outside, ignore_errors=True)


def t_the_wrapper_refuses_before_it_runs_anything():
    outside = _scratch_outside("pkg-guard-wrap-")
    try:
        canary = outside / "the-command-ran.txt"
        create = (f"open({str(canary)!r}, 'w').write('ran')")
        code, out, _env = _run(
            GUARD, ["--manager", "pip", "--run", "--", sys.executable, "-c",
                    create], cwd=REPO, env_extra=_clean_env(outside))
        check("the wrapper refuses a repository-root install (exit 1)", code == 1,
              out[-1600:])
        check("... and the command it was wrapping never ran",
              not canary.exists(), str(canary))
        # The manager is read off the command itself when --manager is auto.
        code, out, _env = _run(
            GUARD, ["--run", "--", "pip", "install", "--help"], cwd=REPO,
            env_extra=_clean_env(outside))
        check("... and a command beginning 'pip install' is recognised as pip "
              "and refused before pip starts", code == 1, out[-1600:])
        check("... naming the manager it read from the command",
              "a pip install would write into the repository" in out,
              out[-1600:])
    finally:
        shutil.rmtree(outside, ignore_errors=True)


def t_the_wrapper_runs_the_command_in_a_clean_context():
    outside = _scratch_outside("pkg-guard-run-")
    try:
        canary = outside / "the-command-ran.txt"
        create = (f"open({str(canary)!r}, 'w').write('ran')")
        code, out, _env = _run(
            GUARD, ["--manager", "pip", "--run", "--", sys.executable, "-c",
                    create], cwd=outside, env_extra=_clean_env(outside))
        check("a clean context lets the wrapped command run (exit 0)", code == 0,
              out[-1600:])
        check("... the command really ran", canary.exists()
              and canary.read_text(encoding="utf-8") == "ran", str(canary))
        check("... and the output says what it ran", "running: " in out,
              out[-1600:])
    finally:
        shutil.rmtree(outside, ignore_errors=True)


def t_an_unknowable_context_is_not_checked_never_a_pass():
    outside = _scratch_outside("pkg-guard-notchecked-")
    try:
        code, out, _env = _run(GUARD, ["--manager", "conda"], cwd=outside,
                               env_extra=_clean_env(outside))
        check("an unknown package manager is NOT CHECKED, exit 3 (not 0)",
              code == 3, out[-1600:])
        check("... in those exact words", "not checked:" in out, out[-1600:])
        check("... and never printed as a pass",
              "ok    a" not in out, out[-1600:])
        code, out, _env = _run(GUARD, [], cwd=outside,
                               env_extra=_clean_env(outside))
        check("with no manager named and no command to read it from, the guard "
              "is NOT CHECKED, exit 3", code == 3, out[-1600:])
        check("... and says why", "not checked:" in out and "manager" in out,
              out[-1600:])
        # A platform whose temporary-folder rules this guard does not know is
        # NOT CHECKED too - driven at the seam so no real machine is faked.
        import check_package_install_context as INSTALL
        verdict, lines = INSTALL.evaluate(
            "pip", cwd=str(outside), environ=_clean_env(outside),
            repo=str(REPO), platform="java")
        check("a platform that is neither Windows nor POSIX is NOT CHECKED",
              verdict == "not checked", (verdict, lines))
        check("... with the exact sentence and the platform named",
              lines and lines[0].startswith("not checked:")
              and "java" in lines[0], lines)
    finally:
        shutil.rmtree(outside, ignore_errors=True)


def t_the_command_line_reader_knows_pip_and_uv():
    import check_package_install_context as INSTALL
    cases = (
        (["python3", "-m", "pip", "install", "x"], "pip"),
        (["python", "-m", "pip3", "install", "x"], "pip"),
        (["pip", "install", "x"], "pip"),
        ([r"C:\Python312\Scripts\pip.exe", "install", "x"], "pip"),
        (["uv", "pip", "install", "x"], "uv"),
        (["uv", "sync"], "uv"),
        (["python3", "-m", "uv", "pip", "install", "x"], "uv"),
        (["npm", "install"], None),
        ([], None),
    )
    for command, want in cases:
        got = INSTALL.manager_from_command(command)
        check(f"the manager read from {command!r} is {want!r}", got == want,
              got)


# ---------------------------------------------------------------------------
#   The artifact checker: clean on this tree, and it says how much it looked at
# ---------------------------------------------------------------------------

def t_the_artifact_checker_is_clean_on_this_tree():
    import check_package_manager_temp_artifacts as ART
    code, out = _module_main(ART, ["--root", str(REPO)])
    check("the artifact check exits 0 on this tree", code == 0, out[-1600:])
    looked = re.search(r"checked (\d+) top-level entries", out)
    check("... and says how many top-level entries it looked at, so 'nothing "
          "is wrong' cannot be read as 'nothing was looked at'",
          looked is not None and int(looked.group(1)) > 0, out[-1600:])


# ---------------------------------------------------------------------------
#   The artifact checker: a real fixture repository that bites, then is clean
# ---------------------------------------------------------------------------

def _fixture_repo():
    """A throwaway git work tree with the legitimate shapes already in it."""
    root = _scratch_outside("pkg-artifacts-repo-")
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1")
    subprocess.run(["git", "-C", str(root), "init", "-q"], env=env,
                   capture_output=True)
    (root / ".gitignore").write_text(".dsh-scratch/\nnode_modules/\n",
                                     encoding="utf-8")
    # A `pip-*` name INSIDE a tracked test fixture: legitimate, never a finding.
    fixture = root / "tests" / "fixtures" / "pip-unpack-abc12345"
    fixture.mkdir(parents=True)
    (fixture / "keep.txt").write_text("a test fixture, not an artifact\n",
                                      encoding="utf-8")
    # An ignored .dsh-scratch/ name and an ignored node_modules/ at the root:
    # both legitimate, neither a finding.
    scratch = root / ".dsh-scratch" / "pip-metadata-abc12345"
    scratch.mkdir(parents=True)
    (scratch / "payload").write_text("agent scratch\n", encoding="utf-8")
    modules = root / "node_modules"
    modules.mkdir()
    (modules / "mod.js").write_text("// vendored\n", encoding="utf-8")
    # A real root file whose name starts pip- : legitimate, not a finding.
    (root / "pip-notes.md").write_text("notes, not an install artifact\n",
                                       encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", ".gitignore", "tests"],
                   env=env, capture_output=True)
    return root


def _add_violations(root):
    """The four shapes a package install really leaves behind."""
    for name, reason in (("pip-metadata-1a2b3c4d",
                          "a pip metadata temporary folder"),
                         ("pip-unpack-7f6e5d4c",
                          "a pip unpack temporary folder"),
                         ("torch-2.4.1.dist-info",
                          "an installed package's metadata folder")):
        folder = root / name
        folder.mkdir()
        (folder / "payload").write_text("temporary\n", encoding="utf-8")
    tracked = root / "pip-unpack-tracked99"
    tracked.mkdir()
    (tracked / "payload").write_text("temporary\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", tracked.name],
                   capture_output=True)


def t_the_artifact_checker_does_not_fire_on_legitimate_paths():
    if GIT is None:
        return skip("git is not installed, so a tracked-from-untracked fixture "
                    "cannot be made here")
    root = _fixture_repo()
    try:
        code, out, _env = _run(ARTIFACT_CHECK, ["--root", str(root)],
                               cwd=root)
        check("a tracked pip-* fixture, an ignored .dsh-scratch name, an "
              "ignored node_modules and a pip-notes.md at the root are all "
              "clean (exit 0)", code == 0, out[-1600:])
        check("... the nested fixture is not named in the output",
              "pip-unpack-abc12345" not in out, out[-1600:])
        check("... and neither is the ignored .dsh-scratch artifact",
              "pip-metadata-abc12345" not in out, out[-1600:])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_the_artifact_checker_bites_names_and_helps_remove():
    if GIT is None:
        return skip("git is not installed, so the fixture repository cannot "
                    "be made here")
    root = _fixture_repo()
    try:
        _add_violations(root)
        code, out, _env = _run(ARTIFACT_CHECK, ["--root", str(root)],
                               cwd=root)
        check("a real fixture repository with the four artifact shapes exits 1",
              code == 1, out[-2400:])
        for name in ("pip-metadata-1a2b3c4d", "pip-unpack-7f6e5d4c",
                     "torch-2.4.1.dist-info", "pip-unpack-tracked99"):
            check(f"... the message names the path {name!r}", name in out,
                  out[-2400:])
        check("... the tracked one is marked tracked and the rest untracked",
              "(tracked)" in out and "(untracked)" in out, out[-2400:])
        check("... it prints the PowerShell removal command",
              "Remove-Item -Recurse -Force" in out, out[-2400:])
        check("... it prints the POSIX removal command", "rm -rf --" in out,
              out[-2400:])
        check("... it prints the tracked-path command that keeps the file on "
              "disk", "git rm -r --cached" in out, out[-2400:])
        check("... it never names the nested fixture or the ignored paths",
              "pip-unpack-abc12345" not in out and ".dsh-scratch" not in out
              and "node_modules" not in out and "pip-notes.md" not in out,
              out[-2400:])
        # Remove exactly what it said to remove, then show it clean.
        for name in ("pip-metadata-1a2b3c4d", "pip-unpack-7f6e5d4c",
                     "torch-2.4.1.dist-info"):
            shutil.rmtree(root / name)
        subprocess.run(["git", "-C", str(root), "rm", "-r", "--cached", "-q",
                        "--", "pip-unpack-tracked99"], capture_output=True)
        shutil.rmtree(root / "pip-unpack-tracked99")
        code, out, _env = _run(ARTIFACT_CHECK, ["--root", str(root)],
                               cwd=root)
        check("after the removal it is clean again (exit 0)", code == 0,
              out[-1600:])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_folder_with_no_git_is_not_checked_never_a_pass():
    plain = _scratch_outside("pkg-artifacts-nogit-")
    try:
        (plain / "pip-metadata-1a2b3c4d").mkdir()
        code, out, _env = _run(ARTIFACT_CHECK, ["--root", str(plain)],
                               cwd=plain)
        check("a folder that is not a git work tree is NOT CHECKED, exit 3 "
              "(not 0)", code == 3, out[-1600:])
        check("... in those exact words", "not checked:" in out, out[-1600:])
        check("... and never printed as a pass", "ok    no package-manager"
              not in out, out[-1600:])
    finally:
        shutil.rmtree(plain, ignore_errors=True)


def t_the_artifact_patterns_match_the_real_shapes_and_not_real_names():
    import check_package_manager_temp_artifacts as ART
    for name in ("pip-metadata-1a2b3c4d", "pip-unpack-7f6e5d4c",
                 "pip-build-env-abcd1234", "pip-install-0123abcd",
                 "pip-req-build-zyxw9876", "torch-2.4.1.dist-info",
                 "node_modules"):
        check(f"{name!r} is recognised as a package-manager temp artifact",
              ART.artifact_reason(name) is not None, ART.artifact_reason(name))
    for name in ("pip-notes.md", "pip-tools", "pip-requirements.txt",
                 "backend", "a-pip-metadata-thing", "dist-info"):
        check(f"{name!r} is NOT treated as an artifact",
              ART.artifact_reason(name) is None, ART.artifact_reason(name))


# ---------------------------------------------------------------------------

TESTS = (
    t_the_install_guard_passes_where_the_audit_job_runs_it,
    t_a_repository_root_working_directory_is_refused,
    t_a_temp_folder_inside_the_repository_is_refused,
    t_uv_is_checked_and_its_own_folders_count,
    t_the_wrapper_refuses_before_it_runs_anything,
    t_the_wrapper_runs_the_command_in_a_clean_context,
    t_an_unknowable_context_is_not_checked_never_a_pass,
    t_the_command_line_reader_knows_pip_and_uv,
    t_the_artifact_checker_is_clean_on_this_tree,
    t_the_artifact_checker_does_not_fire_on_legitimate_paths,
    t_the_artifact_checker_bites_names_and_helps_remove,
    t_a_folder_with_no_git_is_not_checked_never_a_pass,
    t_the_artifact_patterns_match_the_real_shapes_and_not_real_names,
)


def main():
    try:
        for test in TESTS:
            print(f"\n--- {test.__name__} ---")
            try:
                test()
            except Exception:
                FAILED.append(test.__name__)
                print("FAIL  " + test.__name__ + " raised")
                traceback.print_exc()
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        # The ignored .dsh-scratch/ parent was made by this suite when it was
        # not there; remove it too when empty, so the run leaves the tree as it
        # found it (a worktree using .dsh-scratch for its own notes keeps it).
        try:
            SCRATCH.parent.rmdir()
        except OSError:
            pass
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
