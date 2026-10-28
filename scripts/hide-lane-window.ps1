# hide-lane-window.ps1 - stop the owners' Ollama lane tasks showing a PowerShell window.
#
# THE OWNER'S QUESTION, 2026-10-28: "why does a powershell open automatically?
# is that necessary? can it be done behind the scenes".
#
# WHAT IT REALLY IS. Not a Jarvis window. This PC's two Ollama lanes are two
# Windows logon tasks (`Jarvis Ollama - Everyday model (RTX 2060)` and
# `Jarvis Ollama - Coding model (RTX 2080 Super)`), and each task's action is
# `powershell.exe -NoProfile -NoLogo -NonInteractive -ExecutionPolicy Bypass
#  -File "%LOCALAPPDATA%\JarvisOllama\start-lane.ps1" -Lane ... -Port ...`.
# Task Scheduler runs an interactive task's console program in the owner's own
# session, so that console is a real, visible window: at every logon, and every
# time Jarvis restarts a lane that died (`jarvis_model_lanes.py` runs
# `schtasks /run /tn <name>`, and the task's own action is what draws the
# window). Measured on this PC on 2026-10-28, with the app's own backend child
# correctly hidden (`proctree.rs` passes CREATE_NO_WINDOW):
#
#   powershell.exe -NoProfile -NoLogo -NonInteractive -ExecutionPolicy Bypass
#     -File "C:\Users\...\JarvisOllama\start-lane.ps1" ...
#   parent: svchost.exe (the Task Scheduler service)
#   task:   "Jarvis Ollama - Everyday model (RTX 2060)", LogonType=Interactive
#
# WHY A SCRIPT RATHER THAN A CODE CHANGE. Nothing in this repository starts
# that process: the task and its command line live in Windows, not here, and
# `jarvis_model_lanes.py` deliberately runs the OWNER'S OWN task rather than
# building a command line of its own. So the window is hidden where it is
# drawn - in the task's action - and this script is the one-time fix. It does
# not start, stop or restart a lane, and it does not touch `start-lane.ps1`.
#
# HOW TO USE IT. One line, in a normal PowerShell window (no administrator
# needed; these are the owner's own tasks):
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\hide-lane-window.ps1 -Check
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\hide-lane-window.ps1 -Apply
#
# `-Check` (the default) writes NOTHING and prints what each task would say.
# `-Apply` adds `-WindowStyle Hidden` to the task's PowerShell action, backs the
# original task up first, and reads it back afterwards. `-Undo` puts the newest
# backup back. Nothing else about the task changes: same program, same
# arguments, same triggers, same "only when the user is logged on" principal,
# so `jarvis_model_lanes.task_running()` still sees it running.
#
# WHAT IS LOST. The window was the only place `start-lane.ps1`'s output showed.
# That output already goes to a log file (`%LOCALAPPDATA%\JarvisOllama\logs\
# main.log` and `coding.log`, the same files `health.ps1` reads), so a failure
# is still diagnosable after this; what goes away is the live scrollback. If a
# lane ever fails to start, read that log - and `-Undo` restores the window if
# watching it is what is wanted.
#
# PowerShell 5.1 runs this (the owner's PC has 5.1): nothing here uses a
# PowerShell 7-only spelling - no null-coalescing operator, no null-conditional
# access, and `$IsWindows` is read only behind a version guard.

[CmdletBinding()]
param(
    [switch]$Check,
    [switch]$Apply,
    [switch]$Undo
)

$ErrorActionPreference = 'Stop'

$Prefix   = 'Jarvis Ollama'
$BackupRoot = Join-Path $env:LOCALAPPDATA 'JarvisOllama\lane-window-backup'
$Hidden   = '-WindowStyle Hidden'

function Say([string]$m) { Write-Output $m }

if ($Apply -and $Undo) {
    Say 'Give one of -Apply or -Undo, not both. Nothing was changed.'
    exit 2
}
# No switch at all is the same as -Check: the safe direction is the default.
$write = [bool]$Apply
$restore = [bool]$Undo

if (-not $IsWindows -and $PSVersionTable.PSVersion.Major -ge 6) {
    Say 'This is not Windows: there are no Task Scheduler tasks to look at here. Nothing was changed.'
    exit 0
}
$tasksModule = Get-Module -ListAvailable -Name ScheduledTasks
if (-not $tasksModule) {
    Say 'This PC has no ScheduledTasks module, so its tasks cannot be read. Nothing was changed.'
    exit 2
}
Import-Module ScheduledTasks -ErrorAction Stop

function Lane-Tasks {
    Get-ScheduledTask -TaskName ($Prefix + '*') -ErrorAction SilentlyContinue
}

function Safe-Name([string]$name) {
    return ($name -replace '[^A-Za-z0-9 ._-]', '_')
}

# The verdict the display half leaves behind. A separate variable rather than
# a return value, because every line it prints is also Write-Output (so a run
# can be pasted into a file and still read), and a function that prints AND
# returns would hand the caller an array of both.
$script:verdict = ''

function Show-Task($task) {
    $exe = ''
    $arg = ''
    foreach ($a in $task.Actions) {
        if ("$($a.Execute)" -match '(?i)powershell(\.exe)?$') {
            $exe = $a.Execute
            $arg = "$($a.Arguments)"
        }
    }
    Say ("  task      : {0}  [{1}]" -f $task.TaskName, $task.State)
    if (-not $exe) {
        Say '  action    : not PowerShell - this script leaves it alone.'
        $script:verdict = 'other'
        return
    }
    Say ("  program   : {0}" -f $exe)
    Say ("  arguments : {0}" -f $arg)
    if ($arg -match '(?i)-WindowStyle\s+Hidden') {
        Say '  window    : hidden already. Nothing to do.'
        $script:verdict = 'hidden'
        return
    }
    if ($arg -match '(?i)-WindowStyle') {
        Say '  window    : a DIFFERENT -WindowStyle is set on purpose. Refusing to guess; nothing was changed.'
        $script:verdict = 'refused'
        return
    }
    Say '  window    : VISIBLE - Task Scheduler runs this console program in your session.'
    $script:verdict = 'visible'
}

if ($restore) {
    if (-not (Test-Path $BackupRoot)) {
        Say "No backups under $BackupRoot. Nothing was restored."
        exit 2
    }
    $newest = Get-ChildItem $BackupRoot -Directory | Sort-Object Name -Descending | Select-Object -First 1
    if (-not $newest) {
        Say "No backups under $BackupRoot. Nothing was restored."
        exit 2
    }
    Say ("Restoring the tasks saved in {0}" -f $newest.FullName)
    $files = Get-ChildItem $newest.FullName -Filter '*.xml'
    if (-not $files) {
        Say 'That backup folder holds no task files. Nothing was restored.'
        exit 2
    }
    foreach ($file in $files) {
        $name = [System.IO.Path]::GetFileNameWithoutExtension($file.Name)
        try {
            $xml = Get-Content $file.FullName -Raw
            Register-ScheduledTask -TaskName $name -Xml $xml -Force | Out-Null
            Say ("  restored  : {0}" -f $name)
        } catch {
            Say ("  FAILED    : {0} - {1}" -f $name, $_.Exception.Message)
            exit 1
        }
    }
    Say 'Done. Start the tasks again (or log on) for the change to take effect.'
    exit 0
}

$tasks = @(Lane-Tasks)
if ($tasks.Count -eq 0) {
    Say ("No task named '{0}*' on this PC, so there is no lane window to hide." -f $Prefix)
    Say 'That is not a fault: a PC that starts Ollama another way has nothing here.'
    exit 0
}

if (-not $write) {
    Say 'CHECK ONLY - nothing here changes anything. (`-Apply` is the one that writes.)'
    $bad = 0
    foreach ($task in $tasks) {
        Say ''
        Show-Task $task
        if ($script:verdict -eq 'visible') { $bad = $bad + 1 }
        if ($script:verdict -eq 'refused') { $bad = $bad + 1 }
    }
    Say ''
    if ($bad -gt 0) {
        Say ("{0} task(s) would show a window. Run this again with -Apply to hide it." -f $bad)
    } else {
        Say 'Nothing to change.'
    }
    exit 0
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupDir = Join-Path $BackupRoot $stamp
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Say ("Backup folder: {0}" -f $backupDir)

$changed = 0
foreach ($task in $tasks) {
    Say ''
    Show-Task $task
    if ($script:verdict -ne 'visible') { continue }

    $action = $null
    foreach ($a in $task.Actions) {
        if ("$($a.Execute)" -match '(?i)powershell(\.exe)?$') { $action = $a }
    }
    if (-not $action) { continue }

    $backupFile = Join-Path $backupDir ((Safe-Name $task.TaskName) + '.xml')
    try {
        Export-ScheduledTask -TaskName $task.TaskName | Set-Content -Path $backupFile -Encoding UTF8
    } catch {
        Say ("  FAILED    : could not save the original task ({0}). Nothing was changed for it." -f $_.Exception.Message)
        continue
    }
    Say ("  backup    : {0}" -f $backupFile)

    $newArgs = $Hidden + ' ' + "$($action.Arguments)"
    try {
        $splat = @{ Execute = $action.Execute; Argument = $newArgs }
        if ("$($action.WorkingDirectory)" -ne '') {
            $splat['WorkingDirectory'] = "$($action.WorkingDirectory)"
        }
        $newAction = New-ScheduledTaskAction @splat
        Set-ScheduledTask -TaskName $task.TaskName -Action $newAction | Out-Null
    } catch {
        Say ("  FAILED    : {0}. Nothing was changed for it." -f $_.Exception.Message)
        continue
    }

    # Read it BACK: the task is the authority, not the write that was asked for.
    $check = Get-ScheduledTask -TaskName $task.TaskName
    $nowArgs = ''
    foreach ($a in $check.Actions) {
        if ("$($a.Execute)" -match '(?i)powershell(\.exe)?$') { $nowArgs = "$($a.Arguments)" }
    }
    if ($nowArgs -match '(?i)-WindowStyle\s+Hidden') {
        Say '  changed   : the task now starts its window hidden.'
        Say ("  arguments : {0}" -f $nowArgs)
        $changed = $changed + 1
    } else {
        Say '  FAILED    : the task was written but does not read back hidden. Use -Undo.'
        exit 1
    }
}

Say ''
if ($changed -eq 0) {
    Say 'Nothing was changed.'
} else {
    Say ("{0} task(s) changed. The next logon, and the next time Jarvis restarts a lane, will not show a window." -f $changed)
    Say ("To put it back: run this again with -Undo (newest backup: {0})." -f $backupDir)
}
exit 0
