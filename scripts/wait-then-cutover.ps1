# wait-then-cutover.ps1 - run the model move the moment the PC is genuinely quiet.
#
# WHY THIS EXISTS
#   The model move must not run while a lane has a model in memory or while a
#   test is mid-flight: the tests load models from the very store being moved,
#   and stopping the lanes would break them. On 2026-10-10 other agents kept a
#   model loaded and tests running for hours, so instead of polling by hand this
#   waits for a real quiet window and then runs the move ONCE.
#
# WHAT IT DOES
#   Every 15 seconds it checks:
#     * no model loaded on ports 11434 / 11435 / 11436
#     * no python test/run_suites process running
#   When both are true it runs:
#     scripts\move-models-to-d.ps1 -CutOver
#   If the window never opens inside the time limit, it stops and says so,
#   having changed nothing at all.
#
# THE MOVE SCRIPT STILL HAS ITS OWN GUARDS - this only decides WHEN to try.
#
# PowerShell 5.1 runs this, so nothing PowerShell 7-only may appear, and a
# double-quoted string must write ${name}, never $name: - see CLAUDE.md.

[CmdletBinding()]
param(
    [int]$Minutes = 30,
    [string]$Repo = 'C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main'
)

$ErrorActionPreference = 'Continue'
$LogDir = Join-Path $env:LOCALAPPDATA 'JarvisOllama\logs'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$LogPath = Join-Path $LogDir 'wait-then-cutover.log'
$MoveLog = Join-Path $LogDir 'move-models-to-d.log'

function Say([string]$Text) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Text
    Write-Output $line
    try { Add-Content -Path $LogPath -Value $line -ErrorAction SilentlyContinue } catch { }
}

function Get-LoadedLanes {
    $loaded = @()
    foreach ($port in 11434, 11435, 11436) {
        try {
            $ps = Invoke-RestMethod "http://127.0.0.1:${port}/api/ps" -TimeoutSec 4
            $models = @($ps.models)
            if ($models.Count -gt 0) { $loaded += "$port has '$($models[0].name)'" }
        } catch { }
    }
    return $loaded
}

function Get-BusyTests {
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue
    $busy = @()
    foreach ($p in $procs) {
        $cmd = ''
        if ($p.CommandLine) { $cmd = $p.CommandLine }
        if ($cmd -match 'run_suites|test_|pytest|eval_') {
            $leaf = ($cmd -split '\\')[-1]
            $busy += [pscustomobject]@{ Pid = $p.ProcessId; Name = $leaf }
        }
    }
    return $busy
}

Say '============================================================='
Say "Waiting for a quiet moment, up to ${Minutes} minute(s)."
Say 'Nothing is copied, stopped or deleted while it waits.'
Say '============================================================='

$deadline = (Get-Date).AddMinutes($Minutes)
$attempt = 0
$started = $false

while ((Get-Date) -lt $deadline) {
    $attempt++
    $loaded = Get-LoadedLanes
    $tests = @(Get-BusyTests)
    $free = [math]::Round((Get-PSDrive C).Free / 1GB, 2)

    if (@($loaded).Count -eq 0 -and $tests.Count -eq 0) {
        Say "QUIET: nothing loaded, no tests running, C: has ${free} GB free. Starting the move."
        $started = $true
        break
    }

    if ($attempt % 4 -eq 1) {
        Say ("not yet (check {0}): C: {1} GB free; loaded: {2}; tests: {3}" -f `
             $attempt, $free,
             $(if (@($loaded).Count -gt 0) { @($loaded) -join '; ' } else { 'none' }),
             $(if ($tests.Count -gt 0) { ($tests | ForEach-Object { $_.Name }) -join ', ' } else { 'none' }))
    }
    Start-Sleep -Seconds 15
}

if (-not $started) {
    Say 'STOP: no quiet moment arrived inside the time limit. Nothing was changed.'
    Say 'The D: copies are complete and verified; C: still has the originals.'
    Say 'Run this file again later, or run move-models-to-d.ps1 -CutOver by hand.'
    exit 2
}

# Run the real move. Its own guards decide whether it may proceed; this script
# only chose the moment.
$move = Join-Path $Repo 'scripts\move-models-to-d.ps1'
if (-not (Test-Path $move)) {
    Say "STOP: ${move} was not found."
    exit 3
}

Say "running: powershell -NoProfile -File ${move} -CutOver"
$before = (Get-Date)
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $move -CutOver 2>&1 | ForEach-Object {
    Write-Output $_
    try { Add-Content -Path $LogPath -Value $_ -ErrorAction SilentlyContinue } catch { }
}
$code = $LASTEXITCODE
$took = [math]::Round(((Get-Date) - $before).TotalMinutes, 1)
Say "move finished with exit code ${code} after ${took} minute(s)."

$freeAfter = [math]::Round((Get-PSDrive C).Free / 1GB, 2)
Say "C: now has ${freeAfter} GB free."

if ($code -eq 0) {
    Say 'DONE: the move reported success.'
    exit 0
}
Say "The move did not report success (exit ${code}). Read ${MoveLog} for why."
Say 'Nothing was deleted unless the move got past its own verification.'
exit $code
