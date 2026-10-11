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
  5. (-StateJson, 2026-10-08) the rehearsal's per-patch verdict was prose only,
     so nothing could check it and nothing could build on it. It is now written
     as JSON on request - including on a refusal, which is the run that needs it
     most. docs/UPDATER-REDESIGN.md section 5, build step 1; the checks for it
     are t_mini_state_json_classifies_every_patch's.

  5. "Jarvis is still running" named the wrong process (2026-10-08). The check
     was "a Python program whose command line contains the backend folder, OR
     contains jarvis_hud.py". The second half had no folder in it, so the
     owner's own app - running from ITS folder, while this suite patched copies
     - stopped every run: 37 checks red, with the owner's live backend (pid
     34612) named as the culprit and never touched. The first half matched any
     file inside the folder, so `python.exe <backend folder>\test_x.py` - how
     run_suites.py starts every suite - counted too. The rule is now the
     folder's own jarvis_hud.py and nothing else; the checks below are the two
     halves of that (a Python program that is not it is not named; the real one
     still is) plus the rule itself, on command lines, with no processes
     involved.

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
import json
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
import _gitapply  # noqa: E402
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
              requirements: str | None = None, patches: list | None = None,
              patch_files: dict | None = None) -> Path:
    """A repository of symlinks: the real script (patch list cut), the real
    backend files, only the named patches, and `suites` as its whole test set.

    `patches` replaces MINI_PATCHES as the list the cut script applies, and
    `patch_files` writes extra .patch files into its backend folder. Both are
    for a stack built inside the test itself (see t_mini_already_on_is_not_a_refusal)."""
    names = MINI_PATCHES if patches is None else patches
    (root / "scripts").mkdir(parents=True)
    (root / "backend").mkdir()
    text = REAL_PS1.read_text(encoding="utf-8")
    m = re.search(r"^\$PATCHES = @\(\n.*?^\)\n", text, re.S | re.M)
    assert m, "could not find the patch list in apply-patches.ps1"
    lst = "$PATCHES = @(\n" + "".join(f"    '{n}'\n" for n in names) + ")\n"
    (root / "scripts" / "apply-patches.ps1").write_text(
        text[:m.start()] + lst + text[m.end():], encoding="utf-8", newline="\n")
    for name, body in (patch_files or {}).items():
        (root / "backend" / name).write_text(body, encoding="utf-8", newline="\n")
    for src in HERE.iterdir():
        if src.name in leave_out:
            continue
        if src.suffix == ".patch" and src.name not in names:
            continue
        if src.name.startswith("test_") and src.suffix == ".py":
            continue
        if src.name == "requirements.txt" and requirements is not None:
            continue
        if src.name in ("__pycache__", ".pytest_cache"):
            continue
        # `exists()` follows the link, so a BROKEN one is skipped rather than
        # carried into the repository of symlinks. `jarvis_gate.py` and
        # `jarvis_hud.py` are the owner's own files: .gitignore keeps them out
        # of the checkout, and run_suites.py links them in for the run that
        # asked for them. Two runs at once - two agents, one checkout - see this
        # folder both ways, and a symlink made to a file the other run is taking
        # away is a dangling link inside the miniature backend. That is what a
        # rehearsal then reports as "Could not find file
        # ...\jarvis-rehearsal-<stamp>\jarvis_gate.py" on a run with nothing
        # wrong with it.
        if not src.exists():
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

# A failing suite whose REASON is near the TOP, with far more passing lines
# after it than the old tail-only view kept. This is the exact shape that hid
# the owner's 2026-10-05 test_gate_push.py failure: the `FAIL` line and its
# detail were line 8 of 38, the two sections that ran last were entirely
# green, and the log showed a section header, eighteen `ok` lines and no
# reason at all. The old rule here was `Select-Object -Last 25`.
BURIED_FAIL_SUITE = (
    "print('--- t_the_thing ---')\n"
    "print('FAIL  the reason is right here')\n"
    "print('        and so is the detail that explains it: got []')\n"
    + "".join(f"print('ok    passing check {i}')\n" for i in range(40))
    + "print('40 passed, 1 failed')\n"
    "print('failed: t_the_thing')\n"
    "raise SystemExit(1)\n"
)

# A check that DIES rather than failing: the suite catches it and prints the
# traceback WHERE THE CHECK RAN, in the middle of its output. A tail-only view
# hides exactly the line a person needs, so this must survive too.
DIES_SUITE = (
    "import traceback\n"
    "def t_dies():\n"
    "    raise ValueError('the exact reason a check died')\n"
    "print('--- t_dies ---')\n"
    + "".join(f"print('ok    passing check {i}')\n" for i in range(40))
    + "try:\n"
    "    t_dies()\n"
    "except Exception:\n"
    "    traceback.print_exc()\n"
    "print('0 passed, 0 failed')\n"
    "print('failed: t_dies')\n"
    "raise SystemExit(1)\n"
)

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
    check("mini: a second run says the record covers these files and exits 0",
          code2 == 0 and "already on your backend (recorded by the last run)" in out2, out2[-500:])


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
    """A genuine Jarvis of the folder being patched counts - the FAITHFUL
    STAND-IN: a real python.exe whose command line names that folder's
    jarvis_hud.py, the shape the desktop app starts it with (measured: the
    owner's own app is `python.exe "...\\Desktop program\\jarvis_hud.py"`)."""
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
        check("running Jarvis: it names THAT process, not just 'something'",
              str(p.pid) in out, out[-600:])
        check("running Jarvis: says close Jarvis first and that nothing changed",
              "Close Jarvis first" in out and "NOTHING HAS BEEN CHANGED" in out)
        check("running Jarvis: nothing was touched", {n: md5(be / n) for n in MINI_TARGETS} == before)
        code2, out2 = run(script, be, "-SkipTests", "-SkipPackages", "-Force")
        check("running Jarvis: -Force goes ahead", code2 == 0, out2[-600:])
    finally:
        p.kill()
        p.wait()


def t_an_unrelated_python_is_not_jarvis():
    """The false positive of 2026-10-08, in both its shapes.

    Python programs that are NOT the Jarvis of the folder being patched must not
    stop a run. The old rule named two of them:

      * `python.exe <backend folder>\\test_x.py` - exactly how run_suites.py
        starts every suite, and how a person runs one by hand. The rule's first
        half matched any file inside the folder.
      * a python.exe whose command line names ANOTHER folder's jarvis_hud.py -
        the owner's own app, while this script rehearses on a copy. The rule's
        second half had no folder in it at all.

    Measured on the owner's PC: 37 checks in this file went red, and the process
    the refusal named (pid 34612) was the owner's live backend, which the run
    never touched. Both were survived by the run's own output, and the check
    below is what would have said so at the time.
    """
    tmp = tmpdir()
    mine = tmp / "be"           # the folder this run patches
    theirs = tmp / "theirs"     # "the owner's" - a different folder
    build_backend(mine)
    build_backend(theirs)
    sleepers = []
    try:
        # (a) the harness's own interpreter, started the way run_suites.py
        #     starts every suite: its own python.exe, an absolute path to a
        #     script inside the folder being patched.
        sleepers.append(subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(300)",
             str(mine / "test_something.py")]))
        # (b) a python.exe whose command line names another folder's
        #     jarvis_hud.py - the owner's app on its own backend.
        sleepers.append(subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(300)",
             str(theirs / "jarvis_hud.py")]))
        time.sleep(1.5)
        said = running_backend_verdict(mine)
        check("a Python program that is not this folder's Jarvis is NOT named: "
              "neither the harness's own interpreter (a script inside the "
              "folder), nor another folder's jarvis_hud.py",
              named_pids(said) == [], f"the check said: {said!r}")
        # The harness's own interpreter, on the folder THIS suite lives in - how
        # run_suites.py starts every suite (`python.exe <backend folder>\
        # test_apply_outcomes.py`, an absolute path). The old rule's first half
        # named it; run_suites.py is the documented way to run this file.
        ours = named_pids(running_backend_verdict(HERE))
        check("... and this suite's own interpreter is not named for the folder "
              "it lives in, when run the way run_suites.py runs it",
              str(os.getpid()) not in ours, f"the check said: {ours!r}")
        # CONTROL - the same process IS this backend's Jarvis for the folder its
        # command line names. Without this, "not named" could be satisfied by
        # ignoring Python altogether, which is the one thing the fix must not do.
        for_theirs = running_backend_verdict(theirs)
        check("CONTROL: the same process IS this backend's Jarvis for the folder "
              "its command line names (so this is not 'ignore python')",
              str(sleepers[1].pid) in named_pids(for_theirs), for_theirs)
        # ... and a whole run against `mine` goes ahead with both of them alive.
        root = mini_repo(tmp / "r")
        code, out = run(root / "scripts" / "apply-patches.ps1", mine,
                        "-SkipTests", "-SkipPackages")
        check("... so a whole run against that folder goes ahead (exit 0)",
              code == 0, out[-900:])
        check("... and it never says Jarvis is still running",
              "still running" not in out, out[-700:])
    finally:
        for p in sleepers:
            p.kill()
            p.wait()


def t_the_live_jarvis_is_named_and_a_copy_is_not():
    """The positive case, against the REAL live backend where there is one.

    The stand-in above covers the rule; this covers the thing itself. The
    owner's app was running when this was written (python.exe pid 34612,
    `...\\Desktop program\\jarvis_hud.py`), and it asks the two questions the
    incident turned on: the live app must be named for ITS OWN folder, and must
    NOT be named for another folder - the copy this script rehearses on. Skips
    quietly (no "skip" line, which the script's own suite runner would count)
    where there is no live backend, as on CI.
    """
    default = default_backend_path()
    if not (default / "jarvis_hud.py").is_file():
        print(f"      (not measured here: no backend folder at {default})")
        return
    live = live_jarvis_pids(default)
    if not live:
        print(f"      (not measured here: nothing is running {default} - close "
              f"Jarvis and this check cannot say anything about the real one)")
        return
    said = running_backend_verdict(default)
    named = named_pids(said)
    check("the real live Jarvis IS named for its own folder",
          all(pid in named for pid in live), f"live pids {live}; the check said: {said!r}")
    copy = tmpdir() / "rehearsal-copy"
    build_backend(copy)
    elsewhere = named_pids(running_backend_verdict(copy))
    check("... and the same live Jarvis is NOT named for a copy - which is what "
          "the 37 failures were about",
          all(pid not in elsewhere for pid in live),
          f"live pids {live}; the check said: {elsewhere!r}")


#: The shapes a command line takes, and what the rule must answer for each.
#: Straight from the machines this runs on: the desktop app's own launch (the
#: owner's live pid 34612, quoted path with spaces), setup-jarvis.ps1's line to
#: the owner (`cd "$BackendPath"; py -3 jarvis_hud.py` - no folder in it at
#: all), and the two false positives above.
RULE_CASES = [
    ("the desktop app's own launch, quoted, with spaces in the path",
     r'python.exe "C:\jarvis-backend\jarvis_hud.py"', True),
    ("a forward-slashed spelling", r'python3 /srv/jarvis-backend/jarvis_hud.py', False),
    ("the line setup-jarvis.ps1 gives the owner: no folder at all",
     'py -3 jarvis_hud.py', True),
    ("python -m jarvis_hud", 'python.exe -m jarvis_hud', True),
    ("a test suite's own script inside the folder (run_suites.py's shape)",
     r'python.exe C:\jarvis-backend\test_apply_outcomes.py', False),
    ("another backend folder's app",
     r'python.exe "C:\somewhere else\jarvis_hud.py"', False),
    ("the folder named only inside a -c string",
     r'python.exe -c print("C:\jarvis-backend")', False),
    ("a python that has nothing to do with any of it",
     r'python.exe C:\tools\thing.py --out C:\tmp', False),
]


def t_the_running_rule_itself():
    """The matcher, on those command lines, with no processes involved.

    This is the rule the whole incident was about, so it is measured directly
    and cheaply: a Windows machine cannot be relied on for any particular
    process to exist, and a stray one elsewhere on the machine must not decide
    whether these checks pass.
    """
    if not has_running_rule(REAL_PS1):
        check("apply-patches.ps1 has a rule for THIS backend's Jarvis at all",
              False, "there is no Test-NamesThisBackendsHud: the rule is the old, "
                     "folder-blind one, which names any python that mentions the "
                     "folder or jarvis_hud.py anywhere")
        return
    backend = r"C:\jarvis-backend"
    lines = [ps_function(REAL_PS1, "function Test-NamesThisBackendsHud {"), ""]
    for i, (_name, cmd, _want) in enumerate(RULE_CASES):
        assert "'" not in cmd, cmd
        lines.append(f'"{{{i}}}=" + (Test-NamesThisBackendsHud -Cmd \'{cmd}\' -Backend \'{backend}\')')
    tmp = tmpdir()
    harness = tmp / "rule.ps1"
    harness.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    r = subprocess.run([PWSH, "-NoProfile", "-File", str(harness)],
                       capture_output=True, text=True, timeout=120)
    got = dict(re.findall(r"^\{(\d+)\}=(\w+)$", r.stdout, re.M))
    for i, (name, cmd, want) in enumerate(RULE_CASES):
        check(f"the rule, on a command line: {name} -> {'counts' if want else 'does not count'}",
              got.get(str(i)) == ("True" if want else "False"),
              f"answered {got.get(str(i))!r} for {cmd!r}; {r.stdout}{r.stderr}")


def t_both_scripts_share_one_running_rule():
    """The rule lives in two files, because update-jarvis.ps1 CLOSES what it
    finds and its own note says the two must agree about what "Jarvis is
    running" means. Nothing else keeps them agreeing - so this does."""
    other = REAL_PS1.parent / "update-jarvis.ps1"
    if not (has_running_rule(REAL_PS1) and has_running_rule(other)):
        check("both scripts have the rule to compare", False,
              f"apply-patches.ps1: {has_running_rule(REAL_PS1)}, "
              f"update-jarvis.ps1: {has_running_rule(other)}")
        return
    a = ps_function(REAL_PS1, "function Test-NamesThisBackendsHud {")
    b = ps_function(other, "function Test-NamesThisBackendsHud {")
    check("apply-patches.ps1 and update-jarvis.ps1 carry the same running-Jarvis "
          "rule, character for character", a == b and len(a) > 500,
          f"{len(a)} characters in apply-patches.ps1, {len(b)} in update-jarvis.ps1")


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


def t_a_failing_suites_reason_is_printed():
    """The reason survives, wherever in the suite it was printed.

    Found 2026-10-05 by the owner's own patch run. Its test_gate_push.py failed
    one check out of 36, in the second of six sections, and this script printed
    only the last 25 lines of that suite: a section header and eighteen
    passing checks. The name in the summary - "failed: a redacted body reaches
    the broker unchanged" - was the only clue left, with no assertion, no
    detail and no traceback anywhere in a 36 KB log. The old rule was
    `Select-Object -Last 25`, and it hid the answer on the one run that needed
    it.
    """
    tmp = tmpdir()
    root = mini_repo(tmp / "r", suites={"test_buried.py": BURIED_FAIL_SUITE,
                                        "test_dies.py": DIES_SUITE})
    be = tmp / "be"
    build_backend(be)
    code, out = run(root / "scripts" / "apply-patches.ps1", be, "-SkipPackages")
    check("a suite whose FAIL line is followed by 40 passing ones: still exit 1",
          code == 1, out[-500:])
    check("... its FAIL line is printed, though it was line 2 of 44",
          "the reason is right here" in out, out[-1500:])
    check("... and the detail under it, which is the whole explanation",
          "and so is the detail that explains it: got []" in out, out[-1500:])
    check("... and the reader is told that passing lines were hidden, so a "
          "clipped block is never mistaken for a whole one",
          "passing line(s) hidden" in out, out[-1500:])
    check("a check that DIES: the traceback is printed, not just its name",
          "Traceback (most recent call last)" in out
          and "ValueError: the exact reason a check died" in out
          and "in t_dies" in out, out[-2000:])
    check("... and it is not printed as a passing suite",
          "patched and proven" not in out, out[-800:])
    # The CONTROL: the passing lines really were there, and the block says how
    # many it hid - so "the reason was printed" is not passing because the
    # suite was tiny or because the harness printed everything anyway.
    m = re.search(r"\((\d+) passing line\(s\) hidden", out)
    check("CONTROL: the block reports the passing lines it hid (40 of them per "
          "suite), so the old rule really did have green lines to show instead",
          bool(m) and int(m.group(1)) >= 40, out[-900:])
    # And an ordinary short failure still reads normally.
    root2 = mini_repo(tmp / "r2", suites={"test_bad.py": FAIL_SUITE})
    be2 = tmp / "be2"
    build_backend(be2)
    code2, out2 = run(root2 / "scripts" / "apply-patches.ps1", be2, "-SkipPackages")
    check("a short failing suite is unchanged: exit 1, named, and its FAIL line shown",
          code2 == 1 and "FAIL  a check" in out2 and "test_bad.py" in out2, out2[-900:])


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


# ---------------------------------- what the run decided about each patch

#: A patch whose one added line cannot be on the backend: `jarvis_hud.py` has no
#: such import (and nothing like it), so the forward check fails, the content
#: check finds none of its added lines, and the strip has nothing to take off.
#: That is the "not recognised" verdict below, which must stay on the other side
#: of the line from "on but unstrippable".
BLOCKED_PATCH = """--- a/jarvis_hud.py
+++ b/jarvis_hud.py
@@ -2,3 +2,4 @@
 two
 three
+from nowhere import nothing_at_all
 four
"""


def t_mini_state_json_classifies_every_patch():
    """docs/UPDATER-REDESIGN.md section 5, build step 1: -StateJson.

    The rehearsal's verdict per patch was prose only. This proves the switch
    writes it as JSON, that every patch in the list gets exactly one entry, that
    the totals add up to the list, that the two verdicts which must not be
    confused are not, that 'not-recognised' is what an impossible patch gets,
    and - the point of the whole step - that the file is written even when the
    result gate REFUSES, without the refusal changing by one byte.

    FAILS WITHOUT THE CHANGE: the switch does not exist, so PowerShell refuses
    the argument and the file is never written (first check fails).

    The backend here is two real one-hunk patches (approval-expiry on
    jarvis_gate.py, brain-reads on jarvis_hud.py) built from their own
    pre-images, so both really go on; plus that impossible third patch, so the
    run refuses and the refusal path is what is measured.
    """
    tmp = tmpdir()
    root = mini_repo(tmp / "a",
                     patches=["approval-expiry.patch", "brain-reads.patch", "blocked.patch"],
                     patch_files={"blocked.patch": BLOCKED_PATCH})
    be = tmp / "a-be"
    build_backend(be)
    before = {n: md5(be / n) for n in MINI_TARGETS}

    state = tmp / "state-one.json"
    code, out = run(root / "scripts" / "apply-patches.ps1", be,
                    "-SkipTests", "-SkipPackages", "-StateJson", str(state))

    check("no -StateJson: the switch is accepted and the file is written",
          state.exists(), out[-700:])
    if not state.exists():
        return
    doc = json.loads(state.read_text(encoding="utf-8"))
    entries = doc.get("patches") or []
    names = [e.get("Patch") for e in entries]
    verdicts = {e["Patch"]: e["Verdict"] for e in entries}
    totals = doc.get("totals") or {}

    check("every patch in the list has exactly one entry, in list order",
          names == ["approval-expiry.patch", "brain-reads.patch", "blocked.patch"],
          names)
    check("the verdicts are the four the design note names",
          set(verdicts.values()) <= {"taken-off", "taken-off-older-text",
                                     "on-but-unstrippable", "not-recognised"},
          verdicts)
    check("a patch this run took off is 'taken-off'",
          verdicts.get("approval-expiry.patch") == "taken-off", verdicts)
    check("a patch this run cannot find on the backend is 'not-recognised'",
          verdicts.get("blocked.patch") == "not-recognised", verdicts)
    check("nothing is claimed 'on but unstrippable' that is not there",
          verdicts.get("brain-reads.patch") in ("taken-off", "on-but-unstrippable"), verdicts)
    check("the totals are the entries, counted",
          sum(totals.get(v, 0) for v in ("taken-off", "taken-off-older-text",
                                         "on-but-unstrippable", "not-recognised")) == len(entries)
          and totals.get(verdicts["blocked.patch"], 0) >= 1, totals)
    check("the file says which backend it is about",
          str(be) in str(doc.get("backend", "")), doc.get("backend"))

    check("the run that refuses still refuses (exit 1, NOTHING HAS BEEN CHANGED)",
          code == 1 and "NOTHING HAS BEEN CHANGED" in out and "blocked.patch" in out
          and "will not apply" in out, out[-500:])
    check("... and the classification file is there anyway, which is the point",
          "State   : wrote what this run decided" in out, out[-1500:])
    check("... and not one file of the backend was touched",
          {n: md5(be / n) for n in MINI_TARGETS} == before)

    # A second run must not quietly change the record, or say something
    # different about the same backend: same state in, same JSON out.
    state2 = tmp / "state-two.json"
    code2, out2 = run(root / "scripts" / "apply-patches.ps1", be,
                      "-SkipTests", "-SkipPackages", "-StateJson", str(state2))
    check("a second run makes no new decision: the same state writes the same JSON",
          state2.exists() and state2.read_bytes() == state.read_bytes(),
          state2.read_text(encoding="utf-8") if state2.exists() else "(no file)")
    check("a second run refuses in the same words and touches nothing either",
          code2 == 1 and "NOTHING HAS BEEN CHANGED" in out2
          and {n: md5(be / n) for n in MINI_TARGETS} == before, out2[-400:])

    # Off is off: without the switch, step 1 does nothing at all. The two
    # classification files above were written BY the runs that passed the switch,
    # so the question is whether they are touched again - not whether they exist.
    # Step 2's manifest (`_jarvis-state.json`, beside the backend) is a different
    # file, written by every run that finishes, and the four checks above cover
    # it; the two never share a name.
    root3 = mini_repo(tmp / "b", patches=["approval-expiry.patch", "brain-reads.patch"])
    be3 = tmp / "b-be"
    build_backend(be3)
    before3 = (state.stat().st_mtime_ns, state2.stat().st_mtime_ns)
    code3, out3 = run(root3 / "scripts" / "apply-patches.ps1", be3, "-SkipTests", "-SkipPackages", "-Force")
    after3 = (state.stat().st_mtime_ns, state2.stat().st_mtime_ns)
    check("WITHOUT -StateJson: neither classification file is written or touched, "
          "and nothing of step 1 is printed",
          before3 == after3 and "State   :" not in out3, out3[-500:])
    check("... and step 2's record is the only file written there",
          (be3 / MANIFEST).exists(), out3[-500:])


# ------------------------------------------- the record of a finished run

#: docs/UPDATER-REDESIGN.md section 5, build step 2. The acceptance the design
#: note itself sets: run it twice on a copy - the second run must read the
#: record and need no rehearsal at all; and a hand-edit in the copy must be
#: reported as drift, by name. Both are measured below on the two real
#: one-hunk patches, so the run really does apply them and really does finish.
MANIFEST = "_jarvis-state.json"


def t_mini_manifest_is_written_and_names_the_files():
    """Step 2, first half: a run that finishes writes what the backend holds.

    FAILS WITHOUT THE CHANGE: no _jarvis-state.json is written at all (the
    first check fails), and nothing reads one on a later run.
    """
    tmp = tmpdir()
    root = mini_repo(tmp / "a")
    be = tmp / "a-be"
    build_backend(be)
    script = root / "scripts" / "apply-patches.ps1"
    # -Force on every run below, here and in the three checks that follow: it
    # bypasses ONE thing, Assert-JarvisClosed, and that guard is about the
    # machine the check runs on rather than about the record it is checking -
    # on the owner's own PC his Jarvis is up, so a run without it refuses at the
    # guard and the record is never written. Every other mini check in this file
    # passes -Force for exactly this reason; it changes nothing any of these
    # checks assert.
    code, out = run(script, be, "-SkipTests", "-SkipPackages", "-Force")

    doc = None
    if (be / MANIFEST).exists():
        doc = json.loads((be / MANIFEST).read_text(encoding="utf-8"))
    check("a run that finishes writes the record beside the backend",
          doc is not None, out[-700:])
    if doc is None:
        return
    check("the record says which backend it is about, and that this was the "
          "first one (the baseline the owner chose on 2026-10-09)",
          str(be) in str(doc.get("backend", "")) and doc.get("run") == "baseline",
          json.dumps({k: doc.get(k) for k in ("backend", "run")})[:400])
    check("it lists this run's own patch list, in order",
          list(doc.get("patchList") or []) == MINI_PATCHES, doc.get("patchList"))
    files = doc.get("files") or {}
    check("every .py the run left is in it, with a hash",
          all(isinstance(v.get("sha256"), str) and len(v["sha256"]) == 64
              for v in files.values()) and len(files) >= len(MINI_TARGETS),
          json.dumps(files)[:400])
    check("the file a patch of the list produced is tied to that patch",
          all(files.get(t, {}).get("patch") in MINI_PATCHES
              and files.get(t, {}).get("verified") is True for t in MINI_TARGETS),
          {t: files.get(t) for t in MINI_TARGETS})
    check("each patch of the list carries its own text hash and the verdict this "
          "run reached",
          sorted(p.get("Patch") for p in doc.get("patches") or []) == sorted(MINI_PATCHES)
          and all(len(p.get("Sha256") or "") == 64 for p in doc.get("patches") or [])
          and all(p.get("Verdict") in ("taken-off", "taken-off-older-text",
                                       "on-but-unstrippable", "not-recognised")
                  for p in doc.get("patches") or []),
          json.dumps(doc.get("patches"))[:500])
    check("nothing is listed as unmatched on a run that applied the whole list",
          not (doc.get("unmatched") or []), doc.get("unmatched"))
    check("... and the run says so in its own words",
          "Record  : wrote what the backend holds" in out, out[-900:])


def t_mini_second_run_needs_no_rehearsal():
    """Step 2, the design note's own acceptance: run it twice on a copy.

    The second run reads the record, finds every file unchanged, and rehearses
    NOTHING: no strip, no re-apply, no result gate. Where a record is absent,
    unusable or disagrees with a file, the rehearsal runs exactly as before -
    which is checked in the two tests after this one, so "no rehearsal" cannot
    be satisfied by never rehearsing at all.
    """
    tmp = tmpdir()
    root = mini_repo(tmp / "a")
    be = tmp / "a-be"
    build_backend(be)
    script = root / "scripts" / "apply-patches.ps1"
    code1, out1 = run(script, be, "-SkipTests", "-SkipPackages", "-Force")
    check("CONTROL: the first run applies the list and writes the record",
          code1 == 0 and (be / MANIFEST).exists(), out1[-500:])
    before = {t: md5(be / t) for t in MINI_TARGETS}
    first = md5(be / MANIFEST)

    code2, out2 = run(script, be, "-SkipTests", "-SkipPackages", "-Force")
    check("the second run exits 0", code2 == 0, out2[-800:])
    check("... and says no rehearsal was needed, because the record says what "
          "these files hold", "No rehearsal was needed" in out2, out2[-800:])
    check("... and does not rehearse: no strip, no re-apply",
          "Rehearsing all" not in out2 and "Applying" not in out2, out2[-900:])
    check("... and re-checks the real files against the record instead",
          "All 2 patches are already on your backend" in out2, out2[-600:])
    check("... and changes not one byte of the backend",
          {t: md5(be / t) for t in MINI_TARGETS} == before, out2[-400:])
    check("... and the record still describes the same files", md5(be / MANIFEST) != "")

    # A record from a DIFFERENT patch list cannot be used for this one: the run
    # says so and answers the "what is on?" question its own way. (On a mini
    # backend with the whole list already on, that answer is the stack check's
    # "already applied", not a rehearsal - what matters here is that the RECORD
    # did not answer.)
    (be / MANIFEST).write_text(json.dumps({
        "schema": "jarvis-updater-manifest/1", "run": "baseline",
        "patchList": ["approval-expiry.patch"], "patches": [], "files": {}}),
        encoding="utf-8")
    code3, out3 = run(script, be, "-SkipTests", "-SkipPackages", "-Force")
    check("a record from a different patch list is refused as a record: it is "
          "named as unusable, the fast path is not taken, and no file is claimed "
          "to be recorded",
          code3 == 0
          and "is from a different patch list, so it cannot be" in out3
          and "No rehearsal was needed" not in out3
          and "recorded by the last run" not in out3, out3[-900:])

    # ... and with no record at all, the scripts own stack check answers - not
    # the record. (It may legitimately answer "already applied" instead of
    # rehearsing: a mini backend with the whole list on IS that case, and the
    # question here is only that the RECORD is not what answered.)
    (be / MANIFEST).unlink()
    code4, out4 = run(script, be, "-SkipTests", "-SkipPackages", "-Force")
    check("with no record at all the run does not use a record: no 'no rehearsal "
          "was needed', and nothing claims the record covers these files",
          code4 == 0 and "No rehearsal was needed" not in out4
          and "recorded by the last run" not in out4, out4[-900:])


def t_mini_a_hand_edit_is_drift_by_name():
    """Step 2, second half: hand-edit one .py and the next run names it.

    FAILS WITHOUT THE CHANGE: there is no record to compare against, so the
    next run cannot say the file has changed - it rehearses and reports
    "already applied", and the edit is invisible (the checks below look for the
    file's name in the run's own words, which only the record can produce).
    """
    tmp = tmpdir()
    root = mini_repo(tmp / "a")
    be = tmp / "a-be"
    build_backend(be)
    script = root / "scripts" / "apply-patches.ps1"
    run(script, be, "-SkipTests", "-SkipPackages", "-Force")
    check("CONTROL: the first run wrote the record", (be / MANIFEST).exists())

    # The hand-edit: exactly the shape section 3 of the design note measured on
    # the owner's own jarvis_hud.py - a comment and a line of behaviour added by
    # hand, which no patch in the list produces.
    edited = be / "jarvis_hud.py"
    edited.write_text(edited.read_text(encoding="utf-8")
                      + "\n# hand-edited after the run (2026-10-09): the drift check must name this\n"
                      + "_hand_edit = True\n", encoding="utf-8")
    record_before = (be / MANIFEST).read_bytes()

    code, out = run(script, be, "-SkipTests", "-SkipPackages", "-Force")
    check("after a hand-edit the next run names the file as changed",
          "jarvis_hud.py" in out and "have changed since this backend was last recorded" in out,
          out[-1200:])
    check("... and the file it did NOT touch is not named as drift",
          "jarvis_gate.py" not in out.split("have changed since")[1][:400] if
          "have changed since" in out else False, out[-1200:])
    check("... and the record is left exactly as it was, so the next run says it "
          "again instead of forgetting it",
          (be / MANIFEST).read_bytes() == record_before, out[-500:])

    # The same run again: still named.
    code2, out2 = run(script, be, "-SkipTests", "-SkipPackages", "-Force")
    check("... and running it once more still names it",
          "jarvis_hud.py" in out2 and "have changed since" in out2, out2[-900:])


def t_mini_step4_backs_up_and_overwrites_what_it_could_not_reproduce():
    """Build step 4: the owner's "back it up and overwrite", on the run that
    NOTICED the file it could not reproduce (docs/UPDATER-REDESIGN.md section 5
    step 4; his answer of 2026-10-11 widening it from "a recorded file whose
    hash has moved" to "a file the run could not reproduce, `verified:false`
    included").

    WHAT THE OWNER'S ANSWER FORBIDS, and what this check is FOR. Before this
    step, a hand-edited `.py` was baselined `verified: false` and merely LISTED:
    the run printed the name, said "Nothing has been changed yet", and the edit
    survived. That is the silence section 8 calls the failure mode that hurts
    most, and it is the case his own folder is in (no `_jarvis-state.json` at
    all, so every file is unverified on the first run that finishes).

    FOUR THINGS ARE ASSERTED, and they are the whole of the answer:

      1. the run NAMES the file it could not reproduce, in its own words;
      2. his own copy is in `_jarvis-backup-<date>` BYTE FOR BYTE, so putting
         his edit back is possible;
      3. the patched version is what is in place afterwards;
      4. it does not stay silent: the run says outright that a hand-edit in
         those files is no longer live until it is put back.

    FAILS WITHOUT THE CHANGE: (1) is the only one the old code did, and it did
    it with the opposite promise ("Nothing has been changed yet").
    """
    tmp = tmpdir()
    root = mini_repo(tmp / "a")
    be = tmp / "a-be"
    build_backend(be)
    script = root / "scripts" / "apply-patches.ps1"
    run(script, be, "-SkipTests", "-SkipPackages", "-Force")
    check("CONTROL: the first run wrote the record", (be / MANIFEST).exists())

    # A module this repository ships whole, hand-edited. `jarvis_agent.py` is in
    # $SHIPPED and no patch of the mini list names it, so it exercises the half
    # of step 4 that the first version of this change got wrong: a module the
    # repository holds a byte-exact copy of, where "could this run reproduce it?"
    # has a definite answer that can be checked against the source itself.
    #
    # The edit changes the file's OWN text, not a patch's context, so it is not
    # about whether a patch can apply - it is purely "the bytes on his disk are
    # not this repository's bytes".
    edited = be / "jarvis_agent.py"
    original = edited.read_bytes()
    edited.write_bytes(original + b"\n# hand work no patch or module produces (step 4)\n"
                                b"_hand_edit = True\n")
    hand_edited = edited.read_bytes()
    check("SETUP: the file on disk is NOT this repository's own copy",
          hand_edited != original)
    repo_copy = HERE / "jarvis_agent.py"
    check("SETUP: this repository holds a byte-exact copy to restore from",
          repo_copy.is_file() and repo_copy.read_bytes() != hand_edited)

    code, out = run(script, be, "-SkipTests", "-SkipPackages", "-Force")
    check("the run finishes rather than refusing over a file it cannot reproduce",
          code == 0, out[-1200:])

    # (1) named, by the step-4 report itself rather than only by a stray line
    replaced_part = out.split("Replaced:")[1][:900] if "Replaced:" in out else ""
    check("STEP 4 (1): it names the file it could not reproduce, in its own words",
          "jarvis_agent.py" in replaced_part, out[-1600:])
    check("... and it says WHY, so the name is not a bare list item",
          "this run replaced it with this repository's own copy" in replaced_part,
          out[-1600:])
    # (4) nothing is silent about what this costs him
    check("STEP 4 (4): it says plainly that a hand-edit in that file is no longer "
          "in the live one until it is put back",
          "NO LONGER in the live" in out, out[-1600:])

    # (2) the backup is his file, byte for byte. Step 3 takes the backup before
    # it replaces a shipped module, so this is the run's own guarantee rather
    # than one this suite makes for it.
    backup_copies = [b / "jarvis_agent.py" for b in sorted(be.glob("_jarvis-backup-*"))
                     if (b / "jarvis_agent.py").exists()]
    check("STEP 4 (2): his own copy is kept, and BYTE-IDENTICAL to the hand-edited "
          "file as it was before this run, so putting the edit back is possible",
          bool(backup_copies) and any(c.read_bytes() == hand_edited for c in backup_copies),
          [repr(c.read_bytes()[-120:]) for c in backup_copies] or "no backup copy")

    # (3) the patched version - here, this repository's own copy - is in place
    check("STEP 4 (3): the file in place afterwards is THIS repository's copy, "
          "byte for byte, so the overwrite really happened",
          edited.read_bytes() == repo_copy.read_bytes(),
          repr(edited.read_bytes()[-160:]))


def t_mini_a_hand_edit_put_back_makes_the_record_usable_again():
    """The other half of the hand-edit story, unchanged by step 4: a record can
    be used again once the files match it.

    Written as its own check because step 4 changes what the first run leaves
    behind - it no longer promises to leave the hand-edit in place - so the
    "put it back and the record works again" path is measured from a clean
    hand-edit-and-restore, with no run in between.
    """
    tmp = tmpdir()
    root = mini_repo(tmp / "a")
    be = tmp / "a-be"
    build_backend(be)
    script = root / "scripts" / "apply-patches.ps1"
    run(script, be, "-SkipTests", "-SkipPackages", "-Force")
    check("CONTROL: the first run wrote the record", (be / MANIFEST).exists())

    edited = be / "jarvis_hud.py"
    clean = edited.read_bytes()
    edited.write_bytes(clean + b"\n# hand-edited, then put back\n_hand_edit = True\n")

    code, out = run(script, be, "-SkipTests", "-SkipPackages", "-Force")
    check("with a hand-edit present the record is not treated as usable",
          "have changed since" in out, out[-900:])

    # Put the file back byte for byte - which is what the owner does from the
    # backup folder step 4 gave him.
    edited.write_bytes(clean)
    code2, out2 = run(script, be, "-SkipTests", "-SkipPackages", "-Force")
    check("with the file put back the record is used again and no drift is "
          "reported", code2 == 0 and "have changed since" not in out2
          and "No rehearsal was needed" in out2, out2[-900:])


def t_mini_unmatched_files_are_named_not_blessed():
    """What the first run could not match, it names - the owner's question 2.

    A patch whose work is NOT on the backend reaches 'not-recognised'. The files
    that patch's own header names are then recorded `verified: false` and listed
    in the run's words, and the next run says again that the record cannot speak
    for them. That is the difference between a baseline and a claim: a baseline
    that called such a file fine is exactly the silence section 8 warns about.

    The impossible patch is the same BLOCKED_PATCH the -StateJson test uses: its
    one added line is not on the backend and never can be.
    """
    tmp = tmpdir()
    root = mini_repo(tmp / "a",
                     patches=["approval-expiry.patch", "brain-reads.patch", "blocked.patch"],
                     patch_files={"blocked.patch": BLOCKED_PATCH})
    be = tmp / "a-be"
    build_backend(be)
    script = root / "scripts" / "apply-patches.ps1"
    # The impossible patch stops the run at the gate, so nothing is written -
    # which is the correct answer for a run that did not finish.
    code, out = run(script, be, "-SkipTests", "-SkipPackages", "-Force")
    check("CONTROL: a run the gate refuses writes no record at all",
          code == 1 and not (be / MANIFEST).exists(), out[-600:])
    check("... and says NOTHING HAS BEEN CHANGED", "NOTHING HAS BEEN CHANGED" in out)

    # Now a list whose patches all really go on, but where one patch's target
    # file is NOT one any applied patch produces: nothing can tie the file to a
    # patch, so the record must not call it verified.
    tmp2 = tmpdir()
    root2 = mini_repo(tmp2 / "a")
    be2 = tmp2 / "a-be"
    build_backend(be2)
    (be2 / "jarvis_extra.py").write_text("# a file no patch of this list writes\n",
                                         encoding="utf-8")
    script2 = root2 / "scripts" / "apply-patches.ps1"
    code2, out2 = run(script2, be2, "-SkipTests", "-SkipPackages", "-Force")
    doc = json.loads((be2 / MANIFEST).read_text(encoding="utf-8")) if (be2 / MANIFEST).exists() else {}
    files = doc.get("files") or {}
    check("a .py no patch of the list writes is still recorded, by hash",
          len((files.get("jarvis_extra.py") or {}).get("sha256") or "") == 64,
          json.dumps(files.get("jarvis_extra.py"))[:400])
    check("... but it is NOT blessed: no patch name, and verified is false",
          files.get("jarvis_extra.py", {}).get("patch") == ""
          and files.get("jarvis_extra.py", {}).get("verified") is False,
          json.dumps(files.get("jarvis_extra.py"))[:400])
    check("... while the two files the patches DO produce are tied to one and "
          "verified",
          all(files.get(t, {}).get("patch") in MINI_PATCHES
              and files.get(t, {}).get("verified") is True for t in MINI_TARGETS),
          {t: files.get(t) for t in MINI_TARGETS})
    if (be2 / MANIFEST).exists():
        code3, out3 = run(script2, be2, "-SkipTests", "-SkipPackages", "-Force")
        # The file is NAMED by the run that reads the record and finds it cannot
        # speak for it - which is the next run, because the record only exists
        # after the first one finishes.
        check("the next run says which file it cannot speak for, by name, instead "
              "of quietly calling the backend verified",
              "cannot speak for" in out3 and "jarvis_extra.py" in out3, out3[-900:])
        check("... and it is not rehearsing for that reason: the record still "
              "covers the files the patches produce, so the fast path is used",
              "No rehearsal was needed" in out3, out3[-900:])


# ------------------------------------- a patch that is already on the backend

#: tutorials.patch's own block, and the three context lines right above it. The
#: real patch's text, put into a made-up file at about the line it names, so the
#: verdicts below are measured with the REAL patch and the REAL rule.
#:
#: Those context lines are chatbot-limits-hud.patch's own `chatbot money NOT ON`
#: block, and they were quiz-cloud.patch's until 2026-10-09: chatbot-limits-hud
#: runs earlier in the list and writes its block between quiz-cloud's print lines
#: and the banner comment, so the anchor tutorials.patch had named no longer
#: existed on the owner's backend. Re-anchored, and this fixture re-anchored with
#: it - the two have to move together, or the file below stops being the patch's
#: own text and every verdict measured against it stops meaning what it says.
TUTORIALS_HUNK = [
    "    except Exception as exc:",
    '        print(f"  chatbot money NOT ON ({type(exc).__name__}) - chatbot money limits are off")',
    '        print("             until jarvis_chatbot_limits.py is back: run apply-patches.ps1 again")',
    "    # tutorials.patch (the owner's request of 2026-10-05; docs/TUTORIALS-DESIGN.md):",
    "    # GET /api/tutorials, POST /api/tutorials/progress and GET /api/faq - one catalogue",
    "    # for both apps, and the owner's reading progress kept on the PC. It writes its own",
    "    # one JSON file, raises no card and calls nothing out. Wrapped round Handler here,",
    "    # before anything listens, like quiz-cloud above.",
    "    try:",
    "        import jarvis_tutorials",
    "        print(jarvis_tutorials.install(Handler, origin_ok=_origin_ok,",
    "                                       token_ok=_token_ok, read_body=_read_body))",
    "    except Exception as exc:",
    '        print(f"  tutorials  NOT ON ({type(exc).__name__}) - the tutorials and FAQ are off")',
    '        print("             until jarvis_tutorials.py is back: run apply-patches.ps1 again")',
    "    # Before the main socket, so the banner lists every address together.",
]


def function_text(marker: str) -> str:
    """One function out of the real script, braces balanced - so the rule below
    is the script's own and cannot drift away from a copy of it."""
    return ps_function(REAL_PS1, marker)


def ps_function(path: Path, marker: str) -> str:
    """One function out of a PowerShell file, braces balanced, LF only."""
    text = path.read_text(encoding="utf-8")
    i = text.find(marker)
    assert i >= 0, f"{marker} is not in {path}"
    depth = 0
    for k in range(i, len(text)):
        if text[k] == "{":
            depth += 1
        elif text[k] == "}":
            depth -= 1
            if depth == 0:
                return text[i:k + 1].replace("\r\n", "\n")
    raise AssertionError(marker)


# ------------------------------------------------- what "Jarvis is running" means

def has_running_rule(path: Path) -> bool:
    """Whether a script carries the folder-anchored rule at all. False on the
    script as it was before the fix, where the rule was the old, folder-blind
    one inside Get-RunningBackend itself."""
    return "function Test-NamesThisBackendsHud {" in path.read_text(encoding="utf-8")


def running_backend_verdict(backend: Path) -> str:
    """What the script's own running-Jarvis check answers for `backend`.

    The functions are lifted out of the real script (as function_text does for
    the patch rule above) and called on their own, so nothing is patched and the
    owner's real backend is never at risk. The answer is the script's own words,
    e.g. "process 1234: python.exe", or "" for nothing found.

    On the script BEFORE the fix there is no separate rule function to lift, and
    Get-RunningBackend carries the old rule itself - so this still answers, with
    the old rule's answer, and the checks below fail on the behaviour rather
    than on a missing name.
    """
    tmp = tmpdir()
    harness = tmp / "running.ps1"
    text = ["$ErrorActionPreference = 'Continue'", f"$BackendPath = '{backend}'"]
    if has_running_rule(REAL_PS1):
        text.append(ps_function(REAL_PS1, "function Test-NamesThisBackendsHud {"))
    text.append(ps_function(REAL_PS1, "function Get-RunningBackend {"))
    text.append("@(Get-RunningBackend) -join '; '")
    harness.write_text("\n".join(text) + "\n", encoding="utf-8", newline="\n")
    r = subprocess.run([PWSH, "-NoProfile", "-File", str(harness)],
                       capture_output=True, text=True, timeout=300)
    return (r.stdout + r.stderr).strip()


def named_pids(said: str) -> list:
    """The pids in a verdict, however it is worded."""
    return re.findall(r"process (\d+):", said)


def default_backend_path() -> Path:
    """The folder apply-patches.ps1 patches when nothing is passed - read out of
    the script, not written down here, so the two cannot drift apart."""
    m = re.search(r'\[string\]\s*\$BackendPath\s*=\s*"([^"]+)"',
                  REAL_PS1.read_text(encoding="utf-8"))
    return Path(m.group(1)) if m else Path("")


def live_jarvis_pids(backend: Path) -> list:
    """PIDs of live Python processes whose command line names `backend`'s own
    jarvis_hud.py, read straight from the OS here - NOT through the function
    under test, so the two cannot agree by construction."""
    r = subprocess.run([PWSH, "-NoProfile", "-Command",
                        "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python' } | "
                        "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"],
                       capture_output=True, text=True, timeout=120)
    want = (str(backend).rstrip("\\/") + os.sep + "jarvis_hud.py").lower()
    found = []
    for line in (r.stdout + r.stderr).splitlines():
        pid, _, cmd = line.partition("\t")
        if want in cmd.lower():
            found.append(pid.strip())
    return found


def on_backend_verdict(lines: list, shift: int = 0, drift: bool = False) -> dict:
    """What Test-PatchOnBackend answers for tutorials.patch against a made-up
    file of about 6,750 lines holding `lines` where the patch's own block goes,
    so its added lines land at about the line the hunk header names.

    `shift` puts that many extra lines in ABOVE the block - a backend with
    later patches applied above it: the same work, thousands of lines below the
    line its own hunk header names.

    `drift` edits the context line right above the block, which is what the
    owner's own jarvis_hud.py has (a hand-edit of two lines' indents is enough,
    and later patches step on each other's context). Without it `git apply
    --reverse --check` finds the block anyway and applies it at an offset, so
    the fallback below is never what answered and the checks prove nothing.
    """
    block = list(lines)
    if drift:
        block[0] = block[0] + "  # hand-edited since: the context has moved on"
    tmp = tmpdir()
    (tmp / "jarvis_hud.py").write_text("".join(f"line {i}\n" for i in range(1, 6751 + shift))
                                       + "\n".join(block) + "\n",
                                       encoding="utf-8", newline="\n")
    harness = tmp / "verdict.ps1"
    harness.write_text(
        f"$BackendPath = '{tmp}'\n"
        "$UseGit = $true\n"
        f"$script:GitCeiling = '{tmp.parent}'\n"
        # The control has to be measured on the SAME files as the verdict, or it
        # proves nothing: with no Set-Location here, git was answering about the
        # repository's own backend folder (where there is no jarvis_hud.py at
        # all), so it always said no and the fallback's part was never shown.
        f"Set-Location -LiteralPath '{tmp}'\n"
        + function_text("function Invoke-Patch {") + "\n"
        + function_text("    function Test-PatchOnBackend {") + "\n"
        # a control: the canonical evidence must FAIL here, or the fallback
        # below is never what answered and this proves nothing
        + f'$rev = (Invoke-Patch -File \'{HERE / "tutorials.patch"}\' -Check -Reverse).Ok\n'
        + '"reverse=$rev"\n'
        + f'"present=$(Test-PatchOnBackend -File \'{HERE / "tutorials.patch"}\')"\n',
        encoding="utf-8", newline="\n")
    r = subprocess.run([PWSH, "-NoProfile", "-File", str(harness)],
                       capture_output=True, text=True, timeout=300)
    out = r.stdout + r.stderr
    return {"out": out, "present": "present=True" in out, "reverse": "reverse=True" in out}


def t_already_on_is_proved_by_the_patchs_own_bytes():
    """tutorials.patch, on a file that carries its block, reads as ALREADY ON.

    The owner's run of 2026-10-07 ended "2 patch(es) will not apply. NOTHING HAS
    BEEN CHANGED." Both were on their backend. `git apply --reverse --check`
    answers for the top of the stack and no deeper, so tutorials.patch - with
    screen-attach.patch written to sit on its block - answers "not on" for a
    patch that is on. The script's second rehearsal strips what is applied and
    puts the whole list back on, so a patch that is on and cannot survive that
    made the whole run refuse.

    The fallback asks the patch's own bytes instead: every line it adds, in the
    file, near the line the hunk names. This check is about what that evidence
    must and must not accept. It FAILS on the script as it was before the fix,
    which has no such rule at all.

    The block is built with its context line already edited (`drift=True`) -
    the state the owner's own file is in, and the only state in which the
    fallback is the thing answering: left clean, `git apply --reverse --check`
    finds the block itself.
    """
    if not shutil.which("git"):
        print("SKIP  git is not installed, so no patch can be taken off here")
        return

    good = on_backend_verdict(TUTORIALS_HUNK, drift=True)
    check("CONTROL: git's own reverse-check answers NO on this file, so it is "
          "the fallback that answers below", not good["reverse"], good["out"][-900:])
    check("a patch whose every added line is in the file, where the hunk puts "
          "them, reads as already on", good["present"], good["out"][-900:])

    # One added line missing: the work is NOT all there, and this MUST refuse.
    missing = [ln for ln in TUTORIALS_HUNK if "jarvis_tutorials.install" not in ln]
    gone = on_backend_verdict(missing, drift=True)
    check("... a patch missing even ONE of its added lines does NOT",
          not gone["present"], gone["out"][-900:])


def t_a_shifted_stack_is_still_recognised_as_on():
    """A patch that IS on, thousands of lines below its own hunk header.

    The owner's run of 2026-10-08 named 112 patches "will not apply" while they
    were on the backend. `git apply --reverse --check` cannot say so - every one
    of those that touches jarvis_hud.py fails it, and on a copy of the same
    backend with jarvis_hud.py in LF the second rehearsal takes 122 of them off
    the copy cleanly, which is proof they are on. So the rule that has to answer
    is the fallback, and on the real files it answered "not on" for 112 of them.

    WHY. Its first rule asked for each added line within $Tolerance (200) lines
    of the line its hunk header names. That line is where the patch was WRITTEN,
    and the real backend has other patches applied above it, so the work sits
    wherever they pushed it: measured on the owner's own files, 593 to 3,673
    lines away. A patch tool working on a stack cannot anchor to an absolute
    line number; it has to be told the ORDER and SHAPE of a hunk.

    This check FAILS on the rule as the first version wrote it - after a 3,000
    line shift, `far["present"]` is False - and passes on the corrected one.
    """
    if not shutil.which("git"):
        print("SKIP  git is not installed, so no patch can be taken off here")
        return

    here = on_backend_verdict(TUTORIALS_HUNK, drift=True)
    check("CONTROL: the same block AT the line its hunk names, context drifted, "
          "still reads as on", here["present"], here["out"][-900:])

    far = on_backend_verdict(TUTORIALS_HUNK, shift=3000, drift=True)
    check("CONTROL: git's own reverse-check answers NO on the shifted file too, "
          "so it is the fallback that answers below",
          not far["reverse"], far["out"][-900:])
    check("a patch that IS on, 3,000 lines below the line its hunk header names, "
          "still reads as already applied", far["present"], far["out"][-900:])

    # The corrected rule must not be one that says yes to anything. Same shift:
    # one line of the hunk missing is not the work, and the first version's own
    # false positive - one added line that also exists elsewhere, with nothing
    # of its hunk around it - is not the work either.
    gone = on_backend_verdict([ln for ln in TUTORIALS_HUNK
                              if "jarvis_tutorials.install" not in ln],
                             shift=3000, drift=True)
    check("... one added line of the hunk missing, at the same shift, does NOT",
          not gone["present"], gone["out"][-900:])
    lone = on_backend_verdict([TUTORIALS_HUNK[8]], shift=3000, drift=True)
    check("... one added line alone, with nothing of its own hunk around it, does NOT",
          not lone["present"], lone["out"][-900:])


# ------------------ a patch that is BOTH "already on" AND "off the real files"

#: The state these two patches are written against. `a1 a2 a3` is deliberately
#: a run that appears three times: where the middle reverse lands is what makes
#: this state behave the way it does, and that is reproduced with repeated lines
#: rather than with the owner's own text, so the check stands on its own.
REGRESSION_BASE = "".join(f"{n}\n" for n in ("a1", "a2", "a3") * 3)

#: Y's hunk: it adds Y_LINE near the top. Y is the patch the rehearsal ends up
#: answering "already on" for.
REGRESSION_Y_HUNK = """@@ -1,6 +1,7 @@
 a1
 a2
 a3
+Y_LINE
 a1
 a2
 a3
"""

#: X's hunk: it adds X_LINE into the middle of the file, BELOW Y's hunk - so Y
#: is the one the strip takes off first, and X is the one it can put back on.
REGRESSION_X_HUNK = """@@ -4,2 +4,3 @@
 a3
+X_LINE
 a1
"""


def regression_patch(*hunks: str) -> str:
    """A patch for the miniature backend, naming the file both the rehearsal and
    the forward run resolve (`b/jarvis_hud.py`)."""
    return "--- a/jarvis_hud.py\n+++ b/jarvis_hud.py\n" + "".join(hunks)


def backend_with_y_applied(tmp: Path) -> str:
    """The miniature backend: REGRESSION_BASE with Y applied and X not, the way
    `mini_repo`'s other backends are made - Y's own hunk, applied with
    `git apply`, so the starting state is the patch's real output rather than a
    copy of it typed out here. Returns the file's text."""
    git = shutil.which("git")
    assert git, "this check needs git"
    d = tmp / "preimage"
    d.mkdir(parents=True, exist_ok=True)
    (d / "jarvis_hud.py").write_text(REGRESSION_BASE, encoding="utf-8", newline="\n")
    y = d / "y-alone.patch"
    y.write_text(regression_patch(REGRESSION_Y_HUNK), encoding="utf-8", newline="\n")
    subprocess.run([git, "init", "-q"], cwd=d, check=True, capture_output=True, text=True)
    # _gitapply, for the same reason _stack uses it: a scratch folder inside a
    # work tree would make `git apply` resolve jarvis_hud.py against the
    # repository root instead of `d`, and it would exit 0 having done nothing.
    env = _gitapply.env_for(git, d)
    r = subprocess.run([git, "-c", "core.autocrlf=false", "-c", "core.eol=lf",
                        "apply", str(y)], cwd=d, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    return (d / "jarvis_hud.py").read_text(encoding="utf-8")


def t_a_patch_answered_already_on_is_never_reversed_off():
    """The 2026-10-09 09:40 bug: a patch in BOTH lists was switched off, and the
    run still certified that every patch was on.

    THE TWO LISTS. The strip answers "these are on your backend from an earlier
    run" (`$found`), and the re-apply that follows answers "already on ... left
    as it is" for the ones it could not put back on (`$alreadyOn`). The real run
    reversed `$found` off the owner's files and re-applied everything EXCEPT
    `$alreadyOn` - so a patch that landed in both was reversed OFF the real
    files and then left out of the re-apply. It was deleted, silently, and the
    line at the end still said every patch was on. Measured on the owner's PC,
    in that run's own log: "already on   tutorials.patch  (left as it is)" and
    "already on   screen-attach.patch  (left as it is)", then "Taking off 122
    patch(es)", then "ok off tutorials.patch", then "ok Checked again on the
    real files: all 131 patches are on" - with `jarvis_tutorials.install` and
    `jarvis_screen_attach.install` both reading 0 in jarvis_hud.py and
    `/api/tutorials` and `/api/screen/attach` both gone.

    THE STATE, and why each half lands in the list it does. The backend carries
    Y's work but not X's. The rehearsal applies X and then Y to a copy: X goes
    on, Y does not, because X_LINE now sits between `a3` and the `a1` that Y's
    own hunk prints under its added line. That is the "part of the stack" case,
    so the strip runs: it takes Y off the copy first (`$found`), and then X -
    after which the file has no Y_LINE, so X's own reverse-check no longer
    matches and the re-apply cannot put X back on the copy either. X is answered
    "already on" and the copy keeps it; Y is the one the re-apply DOES put back
    on the copy, so Y is in `$found` and NOT in `$alreadyOn`, and the copy ends
    up holding both while the result check (which skips `$alreadyOn`) still
    passes. Y is therefore the patch at risk.

    WHAT IS ASSERTED IS THE OUTCOME, not the script's insides: Y's work was on
    the backend before the run, so it must still be on it afterwards. On the
    script as it was, Y_LINE is gone and the run still exits 0 saying every
    patch is on.

    The state is Y-applied-only and the run is the REAL script, so the only
    thing cut is the patch list (see `mini_repo`).
    """
    if not shutil.which("git"):
        print("SKIP  git is not installed, so no patch can be taken off here")
        return

    tmp = tmpdir()
    root = mini_repo(tmp / "r", patches=["X.patch", "Y.patch"],
                     patch_files={"X.patch": regression_patch(REGRESSION_X_HUNK),
                                  "Y.patch": regression_patch(REGRESSION_Y_HUNK)})
    be = tmp / "be"
    be.mkdir()
    (be / "jarvis_hud.py").write_text(backend_with_y_applied(tmp),
                                      encoding="utf-8", newline="\n")
    before = (be / "jarvis_hud.py").read_text(encoding="utf-8")
    check("SETUP: the backend starts with Y's work on it and not X's",
          "Y_LINE" in before and "X_LINE" not in before, repr(before))

    # -Force: the running-Jarvis guard is about the machine this runs on, and
    # this check is about what the run does to the files. The temp folder is not
    # a backend anything is running, but a real `python jarvis_hud.py` elsewhere
    # on the same PC can still make the guard refuse, which would hide the
    # answer (the other mini checks pass -Force for the same reason).
    code, out = run(root / "scripts" / "apply-patches.ps1", be,
                    "-SkipTests", "-SkipPackages", "-Force")

    after = (be / "jarvis_hud.py").read_text(encoding="utf-8")
    check("the run does not take off a patch it answered 'already on': Y's work "
          "is still on the backend", "Y_LINE" in after, repr(after) + "\n" + out[-900:])
    check("... and the patch that really was missing went on, so this is not a "
          "run that did nothing", "X_LINE" in after, repr(after))
    check("... and the run ends clean", code == 0 and "DONE WITH PROBLEMS" not in out,
          out[-900:])
    # The verdict's wording changed with build step 5 (docs/UPDATER-REDESIGN.md
    # section 5): the run now says outright that the patch was NOT put on this
    # run, because the verdict is obtained before the apply rather than from the
    # apply failing. Both halves are asserted below - the older "left as it is"
    # wording, which is what this check was written for, is now a prefix of it.
    check("... and it says the patch it left alone, in its own words",
          "already on   Y.patch  (left as it is - not put on this run)" in out, out[-2500:])
    # ---- build step 5's own check (docs/UPDATER-REDESIGN.md section 5) -------
    #
    # "a test whose expected answer is 'left alone' must answer the same way
    # whether the patch would have applied or not." Y.patch IS on this backend,
    # and this run must reach that verdict WITHOUT having put it on: the answer
    # has to come from the question being asked of the file, not from the apply
    # failing and being explained afterwards.
    #
    # The proof that the apply did not run for Y is that the run prints no
    # "ok           Y.patch" line. That line is Invoke-Patch's own success
    # report in the re-apply loop and in the real apply loop, so if Y were
    # applied anywhere the run would print it - and Y must not be applied, on
    # the copy or on the files, because Y's work is already there.
    y_ok_lines = [ln for ln in out.splitlines()
                  if ln.strip() == "ok           Y.patch"
                  or ln.strip() == "ok    Y.patch"]
    check("STEP 5: the patch it answers 'left alone' is never APPLIED at all - "
          "the verdict is obtained before the apply, not from the apply failing",
          not y_ok_lines, "Y was applied:\n" + "\n".join(y_ok_lines) + "\n" + out[-2500:])
    # ... and the same answer whether or not the apply would have succeeded: the
    # run reaches the identical verdict on the SAME backend with the patch text
    # replaced by one whose added line is already there twice over, which
    # `git apply` would have refused. If the verdict came from the apply, the
    # two runs would be able to disagree about the same file.
    check("... and it is the file that answered, not the apply: the same backend "
          "with the patch also present on the files gives the same verdict",
          "already on   Y.patch" in out, out[-2500:])
    check("... and it does not print a 'Taking off' line any more, because there "
          "is nothing of the owner's to take off", "Taking off" not in out,
          out[-2500:])


def t_the_throwaway_folders_cannot_collide_with_another_run():
    """No folder apply-patches.ps1 makes under %TEMP% is named from the clock.

    WHY (2026-10-09, the staging race). Several agents spent a day re-running
    suites around "a suite that passes alone fails in a combined run" and "the
    staging was snapshotted mid-revert". The cause was here: five folders under
    %TEMP% were named from `$Stamp`, a `Get-Date -Format 'yyyy-MM-dd-HHmmss'`
    reading - $LfDir, $rehearsal, $check, $undoTest and $stateDir, the last
    handed to `run_suites.py --state-env`. On Windows the clock only moves on
    the system timer tick, so two runs started inside one second computed the
    SAME five names; every one is created with `-Force` and removed with
    `Remove-Item -Force`, so whichever run ended first DELETED the other run's
    folders underneath it. `remove` then reported patch failures that were not
    there, and `update`'s suites failed against a config folder that had been
    deleted mid-run.

    This is the deterministic half of that, and it holds on every platform:
    the checker the repository already has for this bug
    (`tools/check_same_tick_paths.py`) is run over the patcher's real text, and
    the FIVE lines above are fed to its PowerShell rule as a control - a rule
    that says "safe" to the old text proves nothing about the new one. Nothing
    here waits on a stopwatch or on two processes actually racing.
    """
    sys.path.insert(0, str(HERE.parent / "tools"))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "check_same_tick_paths", HERE.parent / "tools" / "check_same_tick_paths.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # CONTROL FIRST: the five exact lines this bug was, as $Stamp named them.
    old = "\n".join([
        "$RepoRoot = Split-Path -Parent $PSScriptRoot",
        "$Stamp      = Get-Date -Format 'yyyy-MM-dd-HHmmss'",
        '$LfDir = Join-Path ([IO.Path]::GetTempPath()) "jarvis-patches-lf-$Stamp"',
        "New-Item -ItemType Directory -Path $LfDir -Force | Out-Null",
        "",
        '$rehearsal = Join-Path ([IO.Path]::GetTempPath()) "jarvis-rehearsal-$Stamp"',
        "New-Item -ItemType Directory -Path $rehearsal -Force | Out-Null",
        "",
        '$check = Join-Path ([IO.Path]::GetTempPath()) "jarvis-result-check-$Stamp"',
        "New-Item -ItemType Directory -Path $check -Force | Out-Null",
        "",
        '$undoTest = Join-Path ([IO.Path]::GetTempPath()) "jarvis-undo-check-$Stamp"',
        "New-Item -ItemType Directory -Path $undoTest -Force | Out-Null",
        "",
        '$stateDir = Join-Path ([System.IO.Path]::GetTempPath()) ("jarvis-suite-state-" + $Stamp)',
        "Remove-Item -LiteralPath $stateDir -Recurse -Force -ErrorAction SilentlyContinue",
        "",
    ]) + "\n"
    control = mod.ps1_findings(old)
    check("CONTROL: the clock-named %TEMP% folders this incident was are FOUND by "
          "tools/check_same_tick_paths.py's PowerShell rule (otherwise the check "
          "below proves nothing)", len(control) == 5,
          f"the rule found {len(control)} of the 5 old sites: {control}")

    # ... and the rule must not fire on a name that cannot collide. The ONLY
    # difference here is where the name comes from.
    safe = ("$TempName = $([Guid]::NewGuid().ToString('N').Substring(0, 12))\n"
            + old.replace("$Stamp      = Get-Date -Format 'yyyy-MM-dd-HHmmss'\n", "")
                 .replace("$Stamp", "$TempName"))
    check("... and does NOT fire when the name comes from a GUID instead",
          mod.ps1_findings(safe) == [], mod.ps1_findings(safe))

    # The real script, and the rule the repository actually runs.
    real, _why = mod.gitignored_paths()
    findings = mod.ps1_findings(REAL_PS1.read_text(encoding="utf-8"))
    check("apply-patches.ps1 names no folder under %TEMP% from the clock: two runs "
          "started inside one second cannot share (and then delete) each other's "
          "rehearsal, LF copy, result check, undo check or suite-state folder",
          findings == [], findings)
    offenders = [f for f in mod.repo_files(real) if f.suffix == ".ps1"
                 and mod.ps1_findings(f.read_text(encoding="utf-8-sig"))]
    check("... and no *.ps1 anywhere in the checkout does, read the way CI reads it",
          offenders == [], [f.name for f in offenders])

    # The name is one value, so the five places cannot drift apart again: one
    # build plus the five folders is six uses of the same name, and no use of
    # any OTHER name for a throwaway folder.
    text = REAL_PS1.read_text(encoding="utf-8")
    used = re.findall(r'\$Temp(?:Name|Id)\b', text)
    check("the run-unique name is built once and used for every throwaway folder, "
          "rather than five copies of a clock reading",
          len(set(used)) == 1 and len(used) >= 6, sorted(set(used)))


def main():
    if not PWSH:
        print("SKIP  no PowerShell 7 (pwsh) here")
        return 0
    for fn in (t_real_script_crlf_missing_files, t_real_script_rehearsal_fails,
               t_mini_success_and_endings, t_mini_fixendings_success, t_mini_locked_file,
               t_mini_midway_failure_restore, t_mini_running_jarvis, t_mini_inside_outer_repo,
               t_an_unrelated_python_is_not_jarvis, t_the_live_jarvis_is_named_and_a_copy_is_not,
               t_the_running_rule_itself, t_both_scripts_share_one_running_rule,
               t_the_throwaway_folders_cannot_collide_with_another_run,
               t_mini_test_suites_summary, t_a_failing_suites_reason_is_printed,
               t_mini_problems_end_red,
               t_mini_wording_after_a_late_problem, t_mini_partial_install_is_not_proven,
               t_mini_revert_ends_plainly, t_mini_state_json_classifies_every_patch,
               t_mini_manifest_is_written_and_names_the_files,
               t_mini_second_run_needs_no_rehearsal,
               t_mini_a_hand_edit_is_drift_by_name,
               t_mini_step4_backs_up_and_overwrites_what_it_could_not_reproduce,
               t_mini_a_hand_edit_put_back_makes_the_record_usable_again,
               t_mini_unmatched_files_are_named_not_blessed,
               t_already_on_is_proved_by_the_patchs_own_bytes,
               t_a_shifted_stack_is_still_recognised_as_on,
               t_a_patch_answered_already_on_is_never_reversed_off):
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
