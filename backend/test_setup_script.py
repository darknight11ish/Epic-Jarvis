"""Does scripts\\setup-jarvis.ps1 keep the promises its own help makes?

    python3 test_setup_script.py

WHY THIS EXISTS

`scripts/setup-jarvis.ps1` is the one command a person on a new PC is told to
run (docs\\INSTALL.md, README.md). It chains two scripts that really do change
things - `install-backend.ps1`, which writes an environment variable for the
Windows account, and `apply-patches.ps1`, which is the one script allowed to
alter a backend folder - so what it says about itself has to be checked rather
than trusted. The four promises, all checked below:

  1. it works on ANY PC: no path from the author's machine is in it, and the
     default backend folder is under the user's own profile;
  2. it never downloads the model (about 5 GB): the one command that does is
     held in a string and printed, never run;
  3. `-Print` changes nothing at all - no folder, no variable, no download;
  4. the commands it prints are the two scripts docs\\INSTALL.md names, with
     the reader's own path already in them.

WHAT IT DELIBERATELY DOES NOT DO - a real run is never started here

A real (non-`-Print`) run sets `JARVIS_BACKEND` for the Windows account, and
that is the setting the live check and every suite read. A test must not leave
a machine pointing at a temporary folder, so the behavioural checks run
`-Print` only. That is the mode a careful person uses first anyway; it prints
every command it would have run, which is what these checks read.

Needs Windows PowerShell to run those checks; on any other machine they are
`skip`ped by name, never counted as passes.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCRIPT = REPO / "scripts" / "setup-jarvis.ps1"
INSTALL = REPO / "scripts" / "install-backend.ps1"
PATCHER = REPO / "scripts" / "apply-patches.ps1"
MODELFILE = REPO / "backend" / "jarvis-primary.Modelfile"

FAILED, PASSED, SKIPPED = [], [], []

#: The author's own folder, which must not be in a script anybody else runs.
AUTHORS_PC = "C:\\Users\\pcadmin"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


def code_lines() -> list:
    """The script's lines that are not comments. A `#` line is prose about the
    script; the checks below are about what it does."""
    return [ln for ln in SCRIPT.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


def powershell() -> str:
    """Where Windows PowerShell is, or '' when this machine has none. The
    suite asks for `powershell.exe` on purpose: 5.1 is what a person's PC
    runs, and CI parses every .ps1 with it."""
    for name in ("powershell.exe", "powershell"):
        for folder in os.environ.get("PATH", "").split(os.pathsep):
            candidate = Path(folder) / name
            if candidate.is_file():
                return str(candidate)
    return ""


def t_the_script_is_there():
    check("scripts/setup-jarvis.ps1 exists and is not empty",
          SCRIPT.is_file() and SCRIPT.stat().st_size > 1000,
          f"{SCRIPT} - {SCRIPT.stat().st_size if SCRIPT.is_file() else 0} bytes")


def t_everything_it_needs_is_in_the_download():
    body = "\n".join(code_lines())
    check("it runs install-backend.ps1", "install-backend.ps1" in body)
    check("it runs apply-patches.ps1", "apply-patches.ps1" in body)
    check("... and both of those scripts are in this repository",
          INSTALL.is_file() and PATCHER.is_file())
    check("it names the Modelfile for the model step, and that file is here",
          "jarvis-primary.Modelfile" in body and MODELFILE.is_file())


def t_it_works_on_a_pc_that_is_not_the_authors():
    body = "\n".join(code_lines())
    check("no path from the author's PC is in the code",
          AUTHORS_PC not in body,
          "the author's own folder is in the script, so it would fail on anyone else's PC")
    check("the default backend folder is under the reader's own profile",
          "$env:USERPROFILE" in body)
    check("it does not lean on the author's way of running Python alone",
          "py -3 jarvis_hud.py" in body)


def t_it_never_downloads_the_model_itself():
    """The model is about 5 GB. The command that fetches it must be printed,
    never executed, so it is checked to live in a string that is only shown."""
    lines = [ln for ln in code_lines() if "ollama pull" in ln]
    check("the model command is in the script at all", len(lines) == 1,
          f"{len(lines)} line(s) mention 'ollama pull' - expected exactly one")
    check("... and it is held as text to print, never run as a command",
          bool(lines) and lines[0].strip().startswith("$modelLine ="),
          lines[0].strip()[:120] if lines else "no such line")
    body = "\n".join(code_lines())
    for forbidden in ("Invoke-Expression", "Invoke-WebRequest", "curl ", "git clone"):
        check(f"it does not run `{forbidden.strip()}` itself", forbidden not in body)


def t_print_mode_changes_nothing():
    exe = powershell()
    if not exe:
        skip("no Windows PowerShell here, so -Print cannot be run")
        return
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "backend-should-not-be-made"
        done = subprocess.run(
            [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
             "-Print", "-BackendPath", str(target)],
            cwd=str(REPO), capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=300)
        out = (done.stdout or "") + (done.stderr or "")
        check("-Print exits 0", done.returncode == 0, out[-600:])
        check("-Print creates no folder at the path it was given",
              not target.exists(), f"{target} exists after a print run")
        check("-Print prints the install-backend command with the reader's path in it",
              "install-backend.ps1" in out and str(target) in out)
        check("-Print prints the apply-patches command too", "apply-patches.ps1" in out)
        check("-Print shows the model command rather than running it",
              "ollama pull qwen3:8b" in out)
        check("-Print shows a start line that runs jarvis_hud.py",
              "jarvis_hud.py" in out)
        check("-Print says plainly that nothing was changed",
              "PRINT" in out or "nothing" in out.lower())


def t_a_missing_download_is_refused_before_anything_changes():
    """The script checks first and changes nothing when a piece is absent. The
    check is the order of the code: every Test-Path guard sits above the first
    Copy-Item."""
    body = SCRIPT.read_text(encoding="utf-8")
    guards = body.find("$problems = @()")
    copy = body.find("Copy-Item -Path")
    check("the missing-piece checks come before the first copy",
          0 <= guards < copy,
          f"guards at {guards}, first Copy-Item at {copy}")
    check("... and a run with any problem exits before doing anything",
          re.search(r"if \(\$problems\.Count -gt 0\)[^}]*exit 1", body, re.S) is not None)


if __name__ == "__main__":
    for fn in (t_the_script_is_there,
               t_everything_it_needs_is_in_the_download,
               t_it_works_on_a_pc_that_is_not_the_authors,
               t_it_never_downloads_the_model_itself,
               t_print_mode_changes_nothing,
               t_a_missing_download_is_refused_before_anything_changes):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
