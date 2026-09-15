<#
.SYNOPSIS
  Apply every backend patch to your OpenJarvis folder, then run the tests.

.DESCRIPTION
  backend/README.md used to say "git apply this, then this, ... and so on, in
  table order" — nineteen patches, in a required order, with a backup step you
  had to remember. That is a bad thing to ask of anyone, and the failure mode
  is the worst kind: patch eleven fails and you are left half-applied, with no
  record of which half.

  This does the whole thing, and it will not leave you half-applied:

    1. Backs up every file that is about to be touched, into a timestamped
       folder, before anything is written.
    2. DRY-RUNS all nineteen first. If any one of them would fail, it stops
       and changes nothing at all.
    3. Applies them in order.
    4. Runs the test suites and prints a summary.

  Safe to run twice. A patch that is already applied is detected and skipped
  rather than corrupting the file.

.PARAMETER BackendPath
  The folder holding jarvis_hud.py. Defaults to the path in backend/README.md.

.PARAMETER Revert
  Undo: take every applied patch back off, newest first.

.PARAMETER SkipTests
  Apply, but do not run the test suites afterwards.

.EXAMPLE
  .\scripts\apply-patches.ps1
  .\scripts\apply-patches.ps1 -BackendPath "D:\jarvis"
  .\scripts\apply-patches.ps1 -Revert
#>

[CmdletBinding()]
param(
    [string] $BackendPath = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program",
    [switch] $Revert,
    [switch] $SkipTests
)

$ErrorActionPreference = 'Stop'

# The order is the one in backend/README.md, and it is not arbitrary.
# memory-safety must land before anything makes the extractor run, or the
# first accepted proposal retires a roughly-matching unrelated fact,
# permanently. bitemporal edits code memory-safety wrote and a route
# memory-pane added, so it is also a TEXTUAL dependency and must go last.
$PATCHES = @(
    'memory-safety.patch'
    'events-pump.patch'
    'appearance.patch'
    'gate-push.patch'
    'skill-notes.patch'
    'documents-honesty.patch'
    'memory-prefix.patch'
    'extraction-wiring.patch'
    'voice-503.patch'
    'degrade-filter.patch'
    'vram-estimate.patch'
    'memory-pane.patch'
    'token-file.patch'
    'bitemporal.patch'
    'embedding-guard.patch'
    'gpu-offload.patch'
    'gate-outcome.patch'
    'no-auto-approve.patch'
    'memory-noise.patch'
)

$RepoRoot   = Split-Path -Parent $PSScriptRoot
$PatchDir   = Join-Path $RepoRoot 'backend'
$Stamp      = Get-Date -Format 'yyyy-MM-dd-HHmmss'

function Say($msg, $colour = 'Gray') { Write-Host $msg -ForegroundColor $colour }
function Ok($msg)   { Write-Host "  ok    $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  skip  $msg" -ForegroundColor Yellow }
function Bad($msg)  { Write-Host "  FAIL  $msg" -ForegroundColor Red }

# --- where is everything -----------------------------------------------------

if (-not (Test-Path -LiteralPath $BackendPath)) {
    Bad "No folder at: $BackendPath"
    Say ""
    Say "Point it at the folder holding jarvis_hud.py:" Cyan
    Say "    .\scripts\apply-patches.ps1 -BackendPath `"D:\your\path`"" Cyan
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $BackendPath 'jarvis_hud.py'))) {
    Bad "That folder exists but has no jarvis_hud.py in it: $BackendPath"
    Say "  This needs the OpenJarvis backend folder, not this repository." Yellow
    exit 1
}

# `patch` is not on a stock Windows box; `git apply` is, if Git is installed.
$UseGit = $null -ne (Get-Command git -ErrorAction SilentlyContinue)
if (-not $UseGit -and -not (Get-Command patch -ErrorAction SilentlyContinue)) {
    Bad 'Neither git nor patch is on PATH, and one of them is needed.'
    Say "  Install Git for Windows: https://git-scm.com/download/win" Cyan
    exit 1
}

Say ""
Say "Backend : $BackendPath"
Say "Patches : $PatchDir"
Say "Tool    : $(if ($UseGit) { 'git apply' } else { 'patch' })"
Say ""

# --- how to run one patch ----------------------------------------------------

function Invoke-Patch {
    param([string] $File, [switch] $Check, [switch] $Reverse)

    # NOT $args - that is an automatic variable in PowerShell, and writing to
    # it inside a function is a way to lose an afternoon.
    if ($UseGit) {
        # --3way is deliberately absent. It can leave conflict markers in a
        # working Python file, which turns "the patch did not apply" into
        # "the backend will not start and the error is a syntax error on
        # line 900".
        $gitArgs = @('apply', '--verbose')
        if ($Check)   { $gitArgs += '--check' }
        if ($Reverse) { $gitArgs += '--reverse' }
        $gitArgs += $File
        $out = & git @gitArgs 2>&1
    } else {
        $patchArgs = @('-p1')
        if ($Reverse) { $patchArgs += '-R' } else { $patchArgs += '--forward' }
        if ($Check)   { $patchArgs += '--dry-run' }
        $patchArgs += @('-i', $File)
        $out = & patch @patchArgs 2>&1
    }
    return @{ Ok = ($LASTEXITCODE -eq 0); Output = ($out | Out-String).Trim() }
}

Push-Location -LiteralPath $BackendPath
try {

    # --- revert ---------------------------------------------------------------
    if ($Revert) {
        Say "Removing patches, newest first." Cyan
        $removed = 0
        $backwards = @($PATCHES); [array]::Reverse($backwards)
        foreach ($name in $backwards) {
            $full = Join-Path $PatchDir $name
            if (-not (Test-Path -LiteralPath $full)) { continue }
            if ((Invoke-Patch -File $full -Check -Reverse).Ok) {
                $r = Invoke-Patch -File $full -Reverse
                if ($r.Ok) { Ok $name; $removed++ } else { Bad "$name`n$($r.Output)" }
            } else {
                Warn "$name (was not applied)"
            }
        }
        Say ""
        Say "Removed $removed." Cyan
        exit 0
    }

    # --- 1. what would each patch do? ----------------------------------------
    Say "Checking all $($PATCHES.Count) before changing anything." Cyan
    $todo    = @()
    $already = @()
    $broken  = @()

    foreach ($name in $PATCHES) {
        $full = Join-Path $PatchDir $name
        if (-not (Test-Path -LiteralPath $full)) {
            $broken += @{ Name = $name; Why = "missing from $PatchDir" }
            Bad "$name - not found"
            continue
        }
        if ((Invoke-Patch -File $full -Check).Ok) {
            $todo += $full
            Say "  will apply   $name"
        }
        elseif ((Invoke-Patch -File $full -Check -Reverse).Ok) {
            # It reverses cleanly, so it is already in the file.
            $already += $name
            Warn "$name (already applied)"
        }
        else {
            $r = Invoke-Patch -File $full -Check
            $broken += @{ Name = $name; Why = $r.Output }
            Bad "$name - will not apply"
        }
    }

    if ($broken.Count -gt 0) {
        Say ""
        Bad "$($broken.Count) patch(es) will not apply. NOTHING HAS BEEN CHANGED."
        Say ""
        foreach ($b in $broken) {
            Say "--- $($b.Name) ---" Yellow
            Say $b.Why
        }
        Say ""
        Say "Usually this means the backend file has moved on since the patch was" Cyan
        Say "written. Send the block above back and the patch gets regenerated." Cyan
        exit 1
    }

    if ($todo.Count -eq 0) {
        Say ""
        Ok "All $($already.Count) patches are already applied. Nothing to do."
        if (-not $SkipTests) { Say "" } else { exit 0 }
    }

    # --- 2. back up, then apply ----------------------------------------------
    if ($todo.Count -gt 0) {
        $backup = Join-Path $BackendPath "_jarvis-backup-$Stamp"
        New-Item -ItemType Directory -Path $backup | Out-Null

        # Every file named in any patch header, so a revert is always possible
        # even if this script is never run again.
        $touched = @{}
        foreach ($full in $todo) {
            foreach ($line in (Get-Content -LiteralPath $full)) {
                if ($line -match '^\+\+\+ b/(.+)$') { $touched[$Matches[1].Trim()] = $true }
            }
        }
        foreach ($f in $touched.Keys) {
            if (Test-Path -LiteralPath $f) {
                $dest = Join-Path $backup $f
                # Every current patch touches a top-level .py, but a future one
                # might not, and a backup that silently skipped a file would be
                # discovered at the worst possible moment.
                $destDir = Split-Path -Parent $dest
                if ($destDir -and -not (Test-Path -LiteralPath $destDir)) {
                    New-Item -ItemType Directory -Path $destDir -Force | Out-Null
                }
                Copy-Item -LiteralPath $f -Destination $dest
            }
        }
        Say ""
        Ok "Backed up $($touched.Count) file(s) to $backup"
        Say ""
        Say "Applying $($todo.Count)." Cyan

        foreach ($full in $todo) {
            $name = Split-Path -Leaf $full
            $r = Invoke-Patch -File $full
            if ($r.Ok) { Ok $name }
            else {
                Bad "$name`n$($r.Output)"
                Say ""
                Bad "Stopped part-way. Your originals are in:"
                Say "  $backup" Yellow
                Say "  Copy them back, or run with -Revert." Yellow
                exit 1
            }
        }
    }

} finally {
    Pop-Location
}

# --- 3. prove it -------------------------------------------------------------

if ($SkipTests) {
    Say ""
    Ok "Done. Tests skipped."
    exit 0
}

# Not `??` - that is PowerShell 7, and Windows ships 5.1, where it is a
# SYNTAX error: the whole script fails to parse before a line of it runs.
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $python) {
    Say ""
    Warn "Python is not on PATH, so the tests were not run."
    exit 0
}

Say ""
Say "Running the test suites against the patched backend." Cyan
Say ""

# The tests import the backend modules, so they run from the BACKEND folder
# with the repo's backend/ on the path - not the other way round.
$tests = Get-ChildItem -LiteralPath $PatchDir -Filter 'test_*.py' | Sort-Object Name
$pass = 0; $fail = @()

foreach ($t in $tests) {
    $out = & $python.Source $t.FullName 2>&1
    if ($LASTEXITCODE -eq 0) { Ok $t.Name; $pass++ }
    else {
        Bad $t.Name
        $fail += @{ Name = $t.Name; Output = ($out | Out-String).Trim() }
    }
}

Say ""
if ($fail.Count -eq 0) {
    Ok "$pass suites passed. The backend is patched and proven."
    Say ""
    Say "Start it, and watch the banner for the token path:" Cyan
    Say "    python jarvis_hud.py" Cyan
} else {
    Bad "$pass passed, $($fail.Count) failed."
    Say ""
    foreach ($f in $fail) {
        Say "===== $($f.Name) =====" Yellow
        Say ($f.Output -split "`n" | Select-Object -Last 25 | Out-String)
    }
    Say "Send the block above back. A failing suite here is a real finding:" Cyan
    Say "these all pass in CI, so a failure means your backend differs from" Cyan
    Say "the one the patches were written against." Cyan
    exit 1
}
