"""apply-patches.ps1: how a run ENDS - truthfully, and with the right exit code.

Found by a read-only audit of the update path (2026-09-30):

  1. "NOTHING HAS BEEN CHANGED" was false after -FixLineEndings: the CRLF->LF
     rewrite of the real files ran before the missing-file check and before
     the rehearsal.
  2. Suites counted as "proven" on exit code 0 alone - a suite that printed
     "SKIP - ..." as a pass, or a run where no suite ran at all, still ended
     "The backend is patched and proven."
  3. Failure paths that still ended as success (a missing shipped module, a
     failed pip, -SkipTests) and no explicit exit code at the end.
  4. A half-patched backend after a mid-way failure with no way back, no check
     for a running Jarvis, and a backend folder inside another git repository
     behaving differently from its rehearsal.

Each check here FAILS on the script as it was before that fix (the fixes are
in the same change; the checks were written against the old script first).

HOW IT RUNS THE REAL SCRIPT. The real patch list is 103 patches and no fake
backend can be built that takes all of them forward (the stand-in in _stack.py
is the state AFTER the stack, not before). So most checks run a copy of the
script whose only difference is the patch list - cut to two independent
patches (approval-expiry on jarvis_gate.py, brain-reads on jarvis_hud.py) - in
a small repository of symlinks, with a backend built from those two patches'
own pre-images, so the forward run really applies. Every other line of the
script is the real one. The two checks that need the real list (CRLF with
missing files; a rehearsal that fails) run the unmodified script, since they
stop before anything is applied.

Skipped where there is no PowerShell 7 (pwsh). Standard library + git + pwsh.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _stack  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name)
    if not cond and detail:
        print("        " + str(detail)[-700:])


PWSH = shutil.which("pwsh") or ("/opt/pwsh/pwsh" if os.path.exists("/opt/pwsh/pwsh") else None)
REAL_PS1 = Path(os.environ.get("JARVIS_TEST_APPLY_PS1") or HERE.parent / "scripts" / "apply-patches.ps1")

# Two independent one-hunk patches on two different files.
MINI_PATCHES = ["approval-expiry.patch", "brain-reads.patch"]
MINI_TARGETS = ["jarvis_gate.py", "jarvis_hud.py"]


def md5(p: Path) -> str:
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def preimage(target: str) -> str:
    """The file the mini patches apply to: their own hunks' pre-images."""
    lines = ["# fake backend file for a test - not Jarvis's", ""]
    for name in MINI_PATCHES:
        for _hunk, pre in _stack.hunks((HERE / name).read_text(encoding="utf-8"), target):
            lines += pre + ["", "# ----", ""]
    return "\n".join(lines) + "\n"


def build_backend(dest: Path, crlf: bool = False) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for t in MINI_TARGETS:
        data = preimage(t).encode("utf-8")
        if crlf:
            data = data.replace(b"\n", b"\r\n")
        (dest / t).write_bytes(data)


def mini_repo(root: Path, suites: dict | None = None, leave_out: tuple = (),
              requirements: str | None = None) -> Path:
    """A repository of symlinks: the real script (patch list cut), the real
    backend files, only two patches, and `suites` as its whole test set."""
    (root / "scripts").mkdir(parents=True)
    (root / "backend").mkdir()
    text = REAL_PS1.read_text(encoding="utf-8")
    m = re.search(r"^\$PATCHES = @\(\n.*?^\)\n", text, re.S | re.M)
    assert m, "could not find the patch list in apply-patches.ps1"
    lst = "$PATCHES = @(\n" + "".join(f"    '{n}'\n" for n in MINI_PATCHES) + ")\n"
    (root / "scripts" / "apply-patches.ps1").write_text(
        text[:m.start()] + lst + text[m.end():], encoding="utf-8", newline="\n")
    for src in HERE.iterdir():
        if src.name in leave_out:
            continue
        if src.suffix == ".patch" and src.name not in MINI_PATCHES:
            continue
        if src.name.startswith("test_") and src.suffix == ".py":
            continue
        if src.name == "requirements.txt" and requirements is not None:
            continue
        if src.name in ("__pycache__", ".pytest_cache"):
            continue
        (root / "backend" / src.name).symlink_to(src)
    if requirements is not None:
        (root / "backend" / "requirements.txt").write_text(requirements, encoding="utf-8")
    for name, body in (suites or {}).items():
        (root / "backend" / name).write_text(body, encoding="utf-8")
    lock = HERE.parent / "jarvis-desktop" / "src-tauri" / "Cargo.lock"
    (root / "jarvis-desktop" / "src-tauri").mkdir(parents=True)
    (root / "jarvis-desktop" / "src-tauri" / "Cargo.lock").symlink_to(lock)
    return root


def run(ps1: Path, backend: Path, *extra, env=None) -> tuple:
    e = dict(os.environ)
    e.update(env or {})
    r = subprocess.run([PWSH, "-NoProfile", "-File", str(ps1), "-BackendPath", str(backend), *extra],
                       capture_output=True, text=True, timeout=900, env=e)
    return r.returncode, r.stdout + r.stderr


def restore_line(out: str):
    m = re.search(r"^\s+(foreach \(\$d in .*)$", out, re.M)
    return m.group(1) if m else None


PASS_SUITE = "print('ok    one thing')\nprint('ok    another')\n"
SKIP_SUITE = "print('ok    a real check')\nprint('ok    SKIP - no such package here')\n"
SKIP_SUMMARY_SUITE = "print('1 passed, 0 failed, 3 skipped')\n"
FAIL_SUITE = "print('FAIL  a check')\nraise SystemExit(1)\n"

TMPDIRS = []


def tmpdir() -> Path:
    # .resolve(), so the throwaway folders are named the LONG way.
    # tempfile.mkdtemp uses %TEMP% as given, and a GitHub Windows runner's is
    # C:\Users\RUNNER~1\AppData\Local\Temp - an 8.3 short name. This suite
    # hands that path to the script as -BackendPath, and PowerShell does not
    # agree with itself about it: `Push-Location -LiteralPath <short>` makes
    # (Get-Location).Path the LONG form, while
    # (Resolve-Path -LiteralPath <short>).Path gives it back SHORT (measured
    # on this PC, 2026-10-05). The mid-way-failure check below compares those
    # two, so with a short-named TEMP it never matched, the simulated failure
    # never happened, and four checks failed on the runner while the same
    # code passes here. Resolving first removes the spelling from the
    # question - the folder is the same folder either way.
    d = Path(tempfile.mkdtemp(prefix="jarvis-outcomes-")).resolve()
    TMPDIRS.append(d)
    return d


# ---------------------------------------------------------------- the real script

def t_real_script_crlf_missing_files():
    """Item 1, the exact reproduction: CRLF backend, files missing, -FixLineEndings."""
    import test_apply_line_endings as LE
    tmp = tmpdir()
    be = tmp / "be"
    be.mkdir()
    made = LE.build_backend(be, crlf=True)
    gone = [m for m in made if m not in ("jarvis_hud.py",)][:3]
    for g in gone:
        (be / g).unlink()
    before = md5(be / "jarvis_hud.py")
    code, out = run(REAL_PS1, be, "-SkipTests", "-SkipPackages", "-FixLineEndings")
    check("CRLF + missing files + -FixLineEndings: it stops (exit 1)", code == 1, out[-500:])
    check("... and says nothing was changed", "NOTHING HAS BEEN CHANGED" in out)
    check("... and it is TRUE: jarvis_hud.py is byte for byte what it was",
          md5(be / "jarvis_hud.py") == before)
    check("... and no _jarvis-backup-*-endings folder appeared",
          not list(be.glob("_jarvis-backup-*-endings")))
    check("... and the end says DONE WITH PROBLEMS, not success",
          "DONE WITH PROBLEMS" in out and "ALL DONE" not in out)


def t_real_script_rehearsal_fails():
    """Item 1: the rehearsal fails on the converted copy -> real files untouched."""
    import test_apply_line_endings as LE
    tmp = tmpdir()
    be = tmp / "be"
    be.mkdir()
    LE.build_backend(be, crlf=True)
    # A gate file no patch fits.
    (be / "jarvis_gate.py").write_bytes(b"x = 1\r\ny = 2\r\n")
    before = {p.name: md5(p) for p in be.glob("*.py")}
    code, out = run(REAL_PS1, be, "-SkipTests", "-SkipPackages", "-FixLineEndings")
    check("a failing rehearsal with -FixLineEndings: exit 1", code == 1, out[-400:])
    check("... nothing of the owner's was rewritten",
          {p.name: md5(p) for p in be.glob("*.py")} == before
          and not list(be.glob("_jarvis-backup-*")))
    check("... it says so in plain words", "NOTHING HAS BEEN CHANGED" in out)


# ---------------------------------------------------------------- the mini script

def t_mini_success_and_endings():
    tmp = tmpdir()
    root = mini_repo(tmp / "r")
    be = tmp / "be"
    build_backend(be)
    script = root / "scripts" / "apply-patches.ps1"
    pre = {n: md5(be / n) for n in MINI_TARGETS}
    code, out = run(script, be, "-SkipTests", "-SkipPackages")
    check("mini: a clean forward run applies both patches and exits 0", code == 0, out[-800:])
    check("mini: both real files changed (patched)",
          all(md5(be / n) != pre[n] for n in MINI_TARGETS))
    check("mini: -SkipTests never says 'proven'",
          "patched and proven" not in out, out[-500:])
    check("mini: -SkipTests is called out as not proven",
          "NOT fully proven" in out and "-SkipTests" in out, out[-600:])
    check("mini: the backup folder is named", "Your files from before this run are in:" in out)
    check("mini: the delete-old-backups line is there", "_jarvis-backup-*" in out)
    code2, out2 = run(script, be, "-SkipTests", "-SkipPackages")
    check("mini: a second run says already applied and exits 0",
          code2 == 0 and "already applied" in out2, out2[-500:])


def t_mini_fixendings_success():
    tmp = tmpdir()
    root = mini_repo(tmp / "r")
    be = tmp / "be"
    build_backend(be, crlf=True)
    orig = {n: (be / n).read_bytes() for n in MINI_TARGETS}
    script = root / "scripts" / "apply-patches.ps1"
    code, out = run(script, be, "-SkipTests", "-SkipPackages", "-FixLineEndings")
    check("mini CRLF + -FixLineEndings: exits 0", code == 0, out[-900:])
    hud = (be / "jarvis_hud.py").read_bytes()
    check("... the files are LF and patched", b"\r\n" not in hud and hud != orig["jarvis_hud.py"].replace(b"\r\n", b"\n"))
    endings = list(be.glob("_jarvis-backup-*-endings"))
    check("... the CRLF originals are kept, byte for byte",
          len(endings) == 1 and all((endings[0] / n).read_bytes() == orig[n] for n in MINI_TARGETS))
    # The restore line, produced by a later failure, is proven separately; here
    # the order of the messages: the rehearsal came before the conversion.
    check("... the message says the rehearsal comes first",
          "rehearsed on a" in out and "Only if the whole rehearsal works" in out)
    check("... the second half of the run checked the real files again",
          "Checked again on the real files" in out)


def t_mini_locked_file():
    """A file that cannot be replaced: earlier conversions are put back."""
    tmp = tmpdir()
    root = mini_repo(tmp / "r")
    be = tmp / "be"
    build_backend(be, crlf=True)
    orig = {n: md5(be / n) for n in MINI_TARGETS}
    # jarvis_gate.py converts first (sorted), jarvis_hud.py second: block the second.
    (be / "jarvis_hud.py.lf-tmp").mkdir()
    script = root / "scripts" / "apply-patches.ps1"
    code, out = run(script, be, "-SkipTests", "-SkipPackages", "-FixLineEndings")
    check("locked file: exit 1", code == 1, out[-600:])
    check("locked file: names the file and says close Jarvis",
          "jarvis_hud.py" in out and "Close Jarvis" in out and "locked" in out, out[-900:])
    check("locked file: the already-converted file is back to CRLF exactly",
          md5(be / "jarvis_gate.py") == orig["jarvis_gate.py"])
    check("locked file: the locked one is untouched",
          md5(be / "jarvis_hud.py") == orig["jarvis_hud.py"])
    check("locked file: no orphan .lf-tmp FILE left (the blocking folder is not ours to remove)",
          not [p for p in be.glob("*.lf-tmp") if p.is_file()])
    check("locked file: says plainly nothing of theirs was changed",
          "nothing of yours is changed" in out, out[-700:])


def t_mini_midway_failure_restore():
    """The second patch fails to apply for real: the run ends with a restore line that works."""
    tmp = tmpdir()
    root = mini_repo(tmp / "r")
    be = tmp / "be"
    build_backend(be, crlf=False)
    orig = {n: md5(be / n) for n in MINI_TARGETS}
    script = root / "scripts" / "apply-patches.ps1"
    # Make the real (not rehearsed) second patch fail: swap jarvis_hud.py under the
    # script's feet is not possible, so use a PATH shim: a `git` that fails on the
    # 4th real call in the real folder. Simpler and honest: a hook in the temp
    # copy of the script that fails the real run of one patch.
    text = script.read_text(encoding="utf-8")
    hook = ("function Invoke-Patch {\n    param([string] $File, [switch] $Check, [switch] $Reverse)\n"
            "    if ((Get-Location).Path -eq (Resolve-Path -LiteralPath $BackendPath).Path -and "
            "$File -like '*brain-reads*' -and -not $Check -and -not $Reverse) "
            "{ return @{ Ok = $false; Output = 'simulated failure' } }\n")
    text = text.replace("function Invoke-Patch {\n    param([string] $File, [switch] $Check, [switch] $Reverse)\n", hook, 1)
    assert "simulated failure" in text
    script.write_text(text, encoding="utf-8", newline="\n")
    code, out = run(script, be, "-SkipTests", "-SkipPackages")
    check("mid-way failure: exit 1 and DONE WITH PROBLEMS",
          code == 1 and "DONE WITH PROBLEMS" in out, out[-900:])
    check("mid-way failure: says the backend is only partly updated",
          "PARTLY updated" in out or "partly updated" in out)
    line = restore_line(out)
    check("mid-way failure: prints a one-line restore command", bool(line), out[-900:])
    check("mid-way failure: says to restart Jarvis and not to start it yet",
          "Do NOT start it yet" in out and "start it again" in out)
    check("mid-way failure: the first patch really did change a file (so the restore matters)",
          md5(be / "jarvis_gate.py") != orig["jarvis_gate.py"])
    if line:
        r = subprocess.run([PWSH, "-NoProfile", "-Command", line], capture_output=True, text=True, timeout=120)
        check("mid-way failure: the restore line puts every file back exactly",
              r.returncode == 0 and all(md5(be / n) == orig[n] for n in MINI_TARGETS),
              r.stdout + r.stderr)


def t_mini_running_jarvis():
    tmp = tmpdir()
    root = mini_repo(tmp / "r")
    be = tmp / "be"
    build_backend(be)
    before = {n: md5(be / n) for n in MINI_TARGETS}
    script = root / "scripts" / "apply-patches.ps1"
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)", str(be / "jarvis_hud.py")])
    try:
        time.sleep(0.5)
        code, out = run(script, be, "-SkipTests", "-SkipPackages")
        check("running Jarvis: the run refuses (exit 1)", code == 1, out[-600:])
        check("running Jarvis: says close Jarvis first and that nothing changed",
              "Close Jarvis first" in out and "NOTHING HAS BEEN CHANGED" in out)
        check("running Jarvis: nothing was touched", {n: md5(be / n) for n in MINI_TARGETS} == before)
        code2, out2 = run(script, be, "-SkipTests", "-SkipPackages", "-Force")
        check("running Jarvis: -Force goes ahead", code2 == 0, out2[-600:])
    finally:
        p.kill()
        p.wait()


def t_mini_inside_outer_repo():
    """The backend folder sits inside another repository whose attributes say CRLF."""
    if not shutil.which("git"):
        print("SKIP  git is not installed")
        return
    tmp = tmpdir()
    root = mini_repo(tmp / "r")
    outer = tmp / "outer"
    be = outer / "sub" / "backend"
    build_backend(be)
    subprocess.run(["git", "init", "-q"], cwd=outer, check=True)
    (outer / ".gitattributes").write_text("*.py text eol=crlf\n", encoding="utf-8")
    script = root / "scripts" / "apply-patches.ps1"
    # Both the rehearsal (in a temp folder) and the real run must agree.
    code, out = run(script, be, "-SkipTests", "-SkipPackages")
    check("inside another git repo: warns about it", "sits inside another git repository" in out, out[:800])
    check("inside another git repo: rehearsal and real run agree (both succeed)",
          code == 0 and "Checked again on the real files" in out, out[-900:])
    data = (be / "jarvis_hud.py").read_bytes()
    check("inside another git repo: the real file was patched the way the rehearsal predicted (LF stays LF)",
          b"\r\n" not in data)
    # -Revert must behave exactly as it does outside a repo.
    tmp2 = tmpdir()
    root2 = mini_repo(tmp2 / "r")
    be2 = tmp2 / "backend"
    build_backend(be2)
    run(root2 / "scripts" / "apply-patches.ps1", be2, "-SkipTests", "-SkipPackages")
    run(script, be, "-Revert")
    run(root2 / "scripts" / "apply-patches.ps1", be2, "-Revert")
    check("inside another git repo: -Revert leaves the same bytes as outside one",
          all((be / n).read_bytes() == (be2 / n).read_bytes() for n in MINI_TARGETS))


def t_mini_test_suites_summary():
    tmp = tmpdir()
    # 1) everything clean: proven, exit 0
    root = mini_repo(tmp / "a", suites={"test_one.py": PASS_SUITE, "test_two.py": PASS_SUITE})
    be = tmp / "a-be"
    build_backend(be)
    code, out = run(root / "scripts" / "apply-patches.ps1", be, "-SkipPackages")
    check("suites: all clean -> exit 0", code == 0, out[-900:])
    check("suites: all clean -> 'patched and proven'", "the backend is patched and proven" in out, out[-600:])
    check("suites: all clean -> '2 suites passed, none skipped'", "2 suites passed, none skipped" in out)
    # 2) one prints SKIP as a pass: never 'proven', the name is listed
    root = mini_repo(tmp / "b", suites={"test_one.py": PASS_SUITE, "test_skippy.py": SKIP_SUITE})
    be = tmp / "b-be"
    build_backend(be)
    code, out = run(root / "scripts" / "apply-patches.ps1", be, "-SkipPackages")
    check("suites: a skipped suite -> exit 0 (the patches are on)", code == 0, out[-900:])
    check("suites: a skipped suite -> NEVER 'proven'", "patched and proven" not in out, out[-900:])
    check("suites: a skipped suite is named", "test_skippy.py" in out and "could not fully run" in out, out[-900:])
    check("suites: the count says 2 passed, 1 skipped",
          "2 suites passed, but 1 of them skipped" in out, out[-900:])
    # 3) a summary line "N skipped" counts too
    root = mini_repo(tmp / "c", suites={"test_sum.py": SKIP_SUMMARY_SUITE})
    be = tmp / "c-be"
    build_backend(be)
    code, out = run(root / "scripts" / "apply-patches.ps1", be, "-SkipPackages")
    check("suites: '3 skipped' in a summary line is counted", "patched and proven" not in out and "test_sum.py (3)" in out, out[-700:])
    # 4) zero suites: a problem
    root = mini_repo(tmp / "d", suites={})
    be = tmp / "d-be"
    build_backend(be)
    code, out = run(root / "scripts" / "apply-patches.ps1", be, "-SkipPackages")
    check("suites: zero suites ran -> exit 1, never 'proven'",
          code == 1 and "patched and proven" not in out and "DONE WITH PROBLEMS" in out, out[-700:])
    # 5) a failing suite
    root = mini_repo(tmp / "e", suites={"test_ok.py": PASS_SUITE, "test_bad.py": FAIL_SUITE})
    be = tmp / "e-be"
    build_backend(be)
    code, out = run(root / "scripts" / "apply-patches.ps1", be, "-SkipPackages")
    check("suites: a failing suite -> exit 1, DONE WITH PROBLEMS, named",
          code == 1 and "DONE WITH PROBLEMS" in out and "test_bad.py" in out and "patched and proven" not in out,
          out[-700:])


def t_mini_problems_end_red():
    tmp = tmpdir()
    # a shipped module missing from the repository
    root = mini_repo(tmp / "a", leave_out=("jarvis_intake.py",))
    be = tmp / "a-be"
    build_backend(be)
    code, out = run(root / "scripts" / "apply-patches.ps1", be, "-SkipTests", "-SkipPackages")
    check("a missing shipped module: exit 1 and listed under DONE WITH PROBLEMS",
          code == 1 and "DONE WITH PROBLEMS" in out and "jarvis_intake.py" in out.split("DONE WITH PROBLEMS")[-1],
          out[-800:])
    check("a missing shipped module: the patches themselves were applied, and it says files WERE changed",
          "WERE changed" in out)
    # pip fails
    root = mini_repo(tmp / "b", requirements="./this-folder-does-not-exist-zzz\n")
    be = tmp / "b-be"
    build_backend(be)
    code, out = run(root / "scripts" / "apply-patches.ps1", be, "-SkipTests")
    check("pip failure: exit 1 and listed as a problem",
          code == 1 and "DONE WITH PROBLEMS" in out and "pip could not install" in out.split("DONE WITH PROBLEMS")[-1],
          out[-800:])


def t_mini_wording_after_a_late_problem():
    """A problem AFTER the patches went on (pip) must not scare the owner into a restore."""
    tmp = tmpdir()
    root = mini_repo(tmp / "a", requirements="./this-folder-does-not-exist-zzz\n")
    be = tmp / "a-be"
    build_backend(be)
    code, out = run(root / "scripts" / "apply-patches.ps1", be, "-SkipTests")
    tail = out.split("DONE WITH PROBLEMS")[-1]
    check("late problem (pip): says the patches themselves are on",
          "the patches themselves are on" in tail, tail[:700])
    check("late problem (pip): does NOT say 'Do NOT start it yet'", "Do NOT start it yet" not in tail)


def t_mini_partial_install_is_not_proven():
    tmp = tmpdir()
    root = mini_repo(tmp / "a", suites={"test_one.py": PASS_SUITE})
    be = tmp / "a-be"
    build_backend(be)
    (be / "jarvis_gate.py").unlink()
    code, out = run(root / "scripts" / "apply-patches.ps1", be, "-SkipPackages", "-SkipMissing")
    check("partial install (-SkipMissing) with passing suites: exit 0", code == 0, out[-800:])
    check("partial install: never 'patched and proven'; says PARTIAL",
          "patched and proven" not in out and "PARTIAL install" in out.split("=====")[-1], out[-700:])


def t_mini_revert_ends_plainly():
    tmp = tmpdir()
    root = mini_repo(tmp / "a")
    be = tmp / "a-be"
    build_backend(be)
    pre = {n: md5(be / n) for n in MINI_TARGETS}
    run(root / "scripts" / "apply-patches.ps1", be, "-SkipTests", "-SkipPackages")
    code, out = run(root / "scripts" / "apply-patches.ps1", be, "-Revert")
    check("-Revert: exit 0, says the patches were taken off",
          code == 0 and "the patches were taken off" in out, out[-600:])
    check("-Revert: the files are what they were before", {n: md5(be / n) for n in MINI_TARGETS} == pre)


def main():
    if not PWSH:
        print("SKIP  no PowerShell 7 (pwsh) here")
        return 0
    for fn in (t_real_script_crlf_missing_files, t_real_script_rehearsal_fails,
               t_mini_success_and_endings, t_mini_fixendings_success, t_mini_locked_file,
               t_mini_midway_failure_restore, t_mini_running_jarvis, t_mini_inside_outer_repo,
               t_mini_test_suites_summary, t_mini_problems_end_red,
               t_mini_wording_after_a_late_problem, t_mini_partial_install_is_not_proven,
               t_mini_revert_ends_plainly):
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    for d in TMPDIRS:
        shutil.rmtree(d, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
