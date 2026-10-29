"""test_hide_lane_window.py - scripts/hide-lane-window.ps1, and the window it hides.

    python3 backend/test_hide_lane_window.py

WHAT THIS IS FOR. On 2026-10-28 the owner asked, with a screenshot of the HUD
saying his model was not running: *"why does a powershell open automatically? is
that necessary? can it be done behind the scenes"*. Measured on his PC that day:

  * the window is NOT the desktop app's child. The app starts the Python
    backend through `proctree::spawn`, which passes CREATE_NO_WINDOW, and the
    backend's own console never appears (`jarvis-desktop/src-tauri/src/
    proctree.rs`; `sidecar.rs`'s `start()` is the only caller);
  * it is his own lane task. `Get-CimInstance Win32_Process` showed
    `powershell.exe ... -File "C:\\Users\\<user>\\AppData\\Local\\JarvisOllama\\
    start-lane.ps1" ...` whose parent is `svchost.exe`, and Task Scheduler's
    own record for `Jarvis Ollama - Everyday model (RTX 2060)` names exactly
    that command line, with `LogonType=Interactive`. An interactive task's
    console program is drawn in his session, so it is a visible window - at
    every logon, and every time Jarvis restarts a lane (`schtasks /run`, from
    `backend/jarvis_model_lanes.py`).

The task lives in Windows, not in this repository, and this repository may not
change the owner's PC by itself. So the fix is one script HE runs, and this
suite is what stops it drifting into something that writes when it should only
look:

  * `-Check` is the DEFAULT and writes nothing - no `Set-ScheduledTask`, no
    `Register-ScheduledTask`, no `New-Item`, and it exits 0 either way. The
    one that writes is `-Apply`, named in the words the owner is told to type;
  * the only change is `-WindowStyle Hidden` on that task's PowerShell action,
    and every other argument is kept exactly as it was (`start-lane.ps1`, the
    lane, its port, its card, its context). Nothing replaces the task;
  * the original task is exported to a dated backup BEFORE the write, `-Undo`
    restores it, and the new action is READ BACK from Task Scheduler - a write
    that did not take is reported, not assumed;
  * it never touches a task whose action is not PowerShell, and it refuses a
    task that already has a DIFFERENT `-WindowStyle` rather than guessing;
  * it names only the two `Jarvis Ollama*` tasks: no other task on the PC is
    read for writing, and the name is matched by a prefix so a renamed task
    (the 2026-10-10 accident) is still found;
  * nothing in this repository runs it. It is not in the installer, the patch
    stack or CI; the owner runs it, and only when he chooses to;
  * the output it hides still goes somewhere: `start-lane.ps1` writes
    `%LOCALAPPDATA%\\JarvisOllama\\logs\\main.log` and `coding.log`, and the
    script says so. A hidden window must not make a failure undiagnosable.

PowerShell 5.1 runs it on this PC, so this suite pins the spellings that only
work in 7 as ABSENT (`??`, `?.`, `-not $IsWindows` without a version guard).

Needs nothing but the standard library, and cannot change anything: every check
here reads a file. The one optional extra is a syntax parse, which runs only
where a PowerShell is installed and says SKIPPED (never "passed") where not.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCRIPT = REPO / "scripts" / "hide-lane-window.ps1"
INSTALLER = REPO / "scripts" / "apply-patches.ps1"
RECONCILE = REPO / "tools" / "reconcile_live_backend.py"
PROCTREE = REPO / "jarvis-desktop" / "src-tauri" / "src" / "proctree.rs"
SIDECAR = REPO / "jarvis-desktop" / "src-tauri" / "src" / "sidecar.rs"
MAIN_RS = REPO / "jarvis-desktop" / "src-tauri" / "src" / "main.rs"
LANES = REPO / "backend" / "jarvis_model_lanes.py"

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skipped(name, why):
    SKIPPED.append(name)
    print(f"SKIPPED  {name}\n        {why} It did NOT run, and it did NOT pass.")


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    if not SCRIPT.is_file():
        print(f"FAIL  the script is missing: {SCRIPT}")
        return 1
    src = text(SCRIPT)

    # ---- the safe direction is the default ------------------------------
    check("the script exists and carries its own why",
          'THE OWNER' in src and "behind the scenes" in src)
    check("`-Check` is the DEFAULT: no switch at all changes nothing",
          "if (-not $write) {" in src
          and "CHECK ONLY - nothing here changes anything" in src)
    check("only `-Apply` sets the writing flag",
          "$write = [bool]$Apply" in src and "$write = [bool]$Check" not in src)
    check("`-Apply` and `-Undo` together are refused",
          "if ($Apply -and $Undo) {" in src and "exit 2" in src)

    # A -Check run has to be unable to write whatever the file does later, so
    # what matters is what is INSIDE the check-only branch, not where the write
    # helpers live (the -Undo branch writes too, and it comes first).
    check_only = src.index("if (-not $write) {")
    check_branch = src[check_only:src.index("\n}", src.index("exit 0", check_only))]
    for call in ("Set-ScheduledTask", "Register-ScheduledTask", "Export-ScheduledTask",
                 "New-Item", "New-ScheduledTaskAction"):
        check(f"`{call}` is not inside the check-only branch",
              call not in check_branch, f"`{call}` can run during -Check")
    check("the check-only branch ends by leaving 0",
          "exit 0" in check_branch)

    # ---- the one change, and everything else kept ------------------------
    check("the flag it adds is `-WindowStyle Hidden`",
          "-WindowStyle Hidden" in src and "$Hidden   = '-WindowStyle Hidden'" in src)
    check("the original arguments are kept, whole",
          '$Hidden + \' \' + "$($action.Arguments)"' in src)
    check("the executable is the task's own, not a path this script invents",
          "New-ScheduledTaskAction" in src and "$action.Execute" in src)
    check("the working directory is passed only when the task has one",
          "if (\"$($action.WorkingDirectory)\" -ne '')" in src)
    check("a task with a DIFFERENT -WindowStyle is refused, not overwritten",
          "a DIFFERENT -WindowStyle is set on purpose" in src)
    check("a task whose action is not PowerShell is left alone",
          "not PowerShell - this script leaves it alone" in src)

    # ---- backup, undo, and a read-back ----------------------------------
    export_at = src.index("Export-ScheduledTask")
    set_at = src.index("Set-ScheduledTask")
    check("the original task is exported BEFORE the write",
          export_at < set_at, f"Export at {export_at}, Set at {set_at}")
    check("the backup is dated and outside the repository",
          "lane-window-backup" in src and "$env:LOCALAPPDATA" in src
          and "yyyyMMdd-HHmmss" in src)
    check("the new action is READ BACK from Task Scheduler, not assumed",
          "Read it BACK" in src and "Get-ScheduledTask -TaskName $task.TaskName" in src)
    check("a write that does not read back hidden is a failure, not a pass",
          "does not read back hidden" in src and "exit 1" in src)
    check("`-Undo` restores the exported task",
          "if ($restore) {" in src and "Register-ScheduledTask -TaskName $name -Xml $xml -Force" in src)

    # ---- it only ever names the owner's two lanes -----------------------
    check("the task name is the `Jarvis Ollama` prefix, not a fixed full name",
          "$Prefix   = 'Jarvis Ollama'" in src and "-TaskName ($Prefix + '*')" in src)
    check("a PC with no such task is not a fault",
          "there is no lane window to hide" in src)

    # ---- the failure stays diagnosable ----------------------------------
    check("it says where the hidden output still goes",
          "main.log" in src and "coding.log" in src)
    check("the same command line is what the lanes module already uses",
          "schtasks" in text(LANES) and "start-lane.ps1" in text(LANES))

    # ---- nothing runs it for the owner ----------------------------------
    check("the installer does not run it",
          "hide-lane-window" not in text(INSTALLER))
    check("the deploy tool does not run it",
          RECONCILE.is_file() and "hide-lane-window" not in text(RECONCILE))

    # ---- the app's own spawn is already hidden --------------------------
    proctree = text(PROCTREE)
    sidecar = text(SIDECAR)
    main_rs = text(MAIN_RS)
    check("the desktop's own child (the Python backend) is spawned with "
          "CREATE_NO_WINDOW",
          "CREATE_NO_WINDOW" in proctree
          and "creation_flags(CREATE_SUSPENDED | CREATE_NO_WINDOW" in proctree)
    check("the backend is started through that one spawn path",
          "proctree::spawn(&mut command)" in sidecar)
    check("a release build has no console of its own",
          'windows_subsystem = "windows"' in main_rs
          and "not(debug_assertions)" in main_rs)

    # ---- PowerShell 5.1 can run it --------------------------------------
    check("no PowerShell 7-only operators",
          "??" not in src and "?." not in src,
          "a `??` or `?.` would fail on the owner's PowerShell 5.1")
    is_windows_guard = "$PSVersionTable.PSVersion.Major -ge 6"
    check("`$IsWindows` is only read behind a version guard",
          "$IsWindows" not in src or is_windows_guard in src)

    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        skipped("the script parses as PowerShell",
                "There is no pwsh or powershell on this machine to parse it with.")
    else:
        parse = ("$e=$null;$t=$null;"
                 f"[System.Management.Automation.Language.Parser]::ParseFile('{SCRIPT}',"
                 "[ref]$t,[ref]$e)|Out-Null;"
                 "if($e.Count){$e|ForEach-Object{Write-Output $_.Message};exit 1};exit 0")
        done = subprocess.run([pwsh, "-NoProfile", "-NonInteractive", "-Command", parse],
                              capture_output=True, text=True, timeout=120)
        check("the script parses as PowerShell",
              done.returncode == 0, (done.stdout or "") + (done.stderr or ""))

    print()
    print(f"{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("\nFAILED:")
        for name in FAILED:
            print(f"  - {name}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
