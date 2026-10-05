<#
.SYNOPSIS
  Tell this PC where your Jarvis backend folder is, so the live check finds it
  and the test suites stop being pointed at the wrong folder.

.DESCRIPTION
  Twenty-odd commands in this repository start with the same eleven words:

      $env:JARVIS_BACKEND = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"

  That path is the author's own PC. On any other PC it is at best wrong and
  at worst points at somebody else's files. Setting the variable ONCE, here,
  is what retires it for everything that reads JARVIS_BACKEND: the live check
  (backend\selftest.py --preflight), the test suites and the memory evaluator
  all use it when it is set, and the repository's own backend folder when it
  is not (which is the wrong folder - it holds patches, not jarvis_hud.py).

  Honest about one thing: apply-patches.ps1 does NOT read this variable. It
  has a default folder of its own written into it and uses that when
  -BackendPath is left out, so the patch command still wants your path on it,
  spelled the same way as here. Making that script read this setting too is a
  change to the one script allowed to alter your backend, so it is written
  down rather than done quietly. docs\INSTALL.md, step 1.5, says the same.

  What this changes: one environment variable, for your Windows account
  (User, not Machine - no administrator needed, and nothing outside your
  account is touched). Nothing inside the backend folder is read beyond its
  file names, and nothing inside it is written.

  The shape is the same as apply-patches.ps1, deliberately:

    1. CHECKS everything first and changes NOTHING. A folder that is not a
       backend folder is refused before the variable is set, so a wrong path
       can never be half-installed.
    2. Makes the one change, then re-reads it back to prove it took.
    3. Prints what it changed, the way to undo it, and the exact next
       command - with your path already in it.

  Safe to run twice: a second run finds the variable already right and
  changes nothing (it says so, and exits 0). Run it again after moving the
  backend folder, or when a different copy of Jarvis should be the one the
  checks look at.

.PARAMETER BackendPath
  The folder holding jarvis_hud.py. This is the folder the backend's own
  files live in - NOT this repository, and not this repository's backend
  folder.

.PARAMETER Print
  Find and check the folder, print the commands, change nothing. Use it to
  see what the script would do before letting it.

.EXAMPLE
  From the folder this repository is cloned into. -ExecutionPolicy Bypass
  lets Windows run a script file for this one command, without changing any
  setting:

  powershell -ExecutionPolicy Bypass -File .\scripts\install-backend.ps1 -BackendPath "D:\jarvis"
  powershell -ExecutionPolicy Bypass -File .\scripts\install-backend.ps1 -BackendPath "D:\jarvis" -Print
#>

[CmdletBinding()]
param(
    [string] $BackendPath = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program",
    [switch] $Print
)

$ErrorActionPreference = 'Stop'

function Say($msg, $colour = 'Gray') { Write-Host $msg -ForegroundColor $colour }

# Read one value this script stores, straight out of the registry rather than
# out of this session. The session copy of an environment variable holds the
# value this PowerShell process was STARTED with, so it knows nothing about
# what an earlier run of this script set - a second run would otherwise
# always think it had work to do. Returns $null when the value has never been
# set, or was removed again.
function Get-StoredUserVariable($name) {
    try {
        $item = Get-ItemProperty -LiteralPath 'HKCU:\Environment' -Name $name -ErrorAction Stop
        return [string]$item.$name
    } catch {
        return $null
    }
}

# --- the one thing this run did, and how it ends ------------------------------
#
# apply-patches.ps1 ends in ONE place that says plainly whether it worked and
# what to do next; a script that prints "done" from six different exits is how
# a half-done run looks like a good one. Same shape here, smaller: there is
# only one change to make, so $script:Changed is one boolean.
$script:Changed = $false

function Finish {
    param([int] $Code, [string] $Kind, [string] $Backend)
    $bar = ('=' * 68)
    Write-Host ""
    if ($Code -ne 0) {
        Write-Host $bar -ForegroundColor Red
        Write-Host " NOT DONE - nothing was changed" -ForegroundColor Red
        Write-Host $bar -ForegroundColor Red
    } else {
        Write-Host $bar -ForegroundColor Green
        if ($Kind -eq 'twice')     { Write-Host " ALREADY SET UP - nothing needed changing" -ForegroundColor Green }
        elseif ($Kind -eq 'print') { Write-Host " PRINTED ONLY - nothing was changed" -ForegroundColor Yellow }
        else                       { Write-Host " DONE - your PC now knows where the backend is" -ForegroundColor Green }
        Write-Host $bar -ForegroundColor Green
    }
    Write-Host ""
    if ($Code -eq 0 -and $Backend) {
        if ($Kind -eq 'print') {
            # -Print set nothing, so the honest thing to report is what is
            # THERE, not the folder that was only checked. A script that says
            # "already holds X" after changing nothing is how -Print gets
            # mistaken for a real run.
            Write-Host "This run changed nothing. JARVIS_BACKEND currently holds:" -ForegroundColor Cyan
            $now = Get-StoredUserVariable 'JARVIS_BACKEND'
            if ($now) { Write-Host "    $now" -ForegroundColor Cyan }
            else      { Write-Host "    (nothing - it is not set)" -ForegroundColor Cyan }
        } elseif ($script:Changed) {
            Write-Host "What changed: JARVIS_BACKEND, for your Windows account, now holds:" -ForegroundColor Cyan
            Write-Host "    $Backend" -ForegroundColor Cyan
            Write-Host "Programs started from now on (a NEW PowerShell window, Jarvis itself," -ForegroundColor Gray
            Write-Host "the test suites) inherit it. A window that is already open does not." -ForegroundColor Gray
        } else {
            Write-Host "Nothing changed. JARVIS_BACKEND already holds:" -ForegroundColor Cyan
            Write-Host "    $Backend" -ForegroundColor Cyan
        }
        Write-Host ""
        # No undo line under -Print: nothing was changed, so there is nothing
        # to put back, and a line that removes a setting reads like a warning
        # about a change that did not happen.
        if ($script:Undo -and $Kind -ne 'print') {
            Write-Host "To undo it, paste this one line:" -ForegroundColor Gray
            Write-Host "    $($script:Undo)" -ForegroundColor Gray
            Write-Host ""
        }
    }
    if ($script:Next) {
        Write-Host "Next, in a NEW PowerShell window (it picks up the new setting):" -ForegroundColor Cyan
        Write-Host "    $($script:Next)" -ForegroundColor Cyan
        Write-Host ""
    }
    exit $Code
}

# Anything nobody planned for - a locked registry key, no permission to write
# it - lands here instead of scrolling past as a red block, so the run still
# ends by saying whether the change was made.
trap {
    Write-Host ""
    Write-Host "  FAIL  The script stopped unexpectedly: $($_.Exception.Message)" -ForegroundColor Red
    if ($script:Changed) {
        Write-Host "  JARVIS_BACKEND was set before that happened, so the change stands:" -ForegroundColor Yellow
        Write-Host "      $($script:Backend)" -ForegroundColor Yellow
        if ($script:Undo) { Write-Host "  To undo it: $($script:Undo)" -ForegroundColor Yellow }
    }
    Finish 1 'failed'
}

# --- what a backend folder looks like ----------------------------------------
#
# jarvis_hud.py is the one file that makes a folder a backend folder: it is
# what the patch script patches, what the desktop app is pointed at, and what
# the variable is FOR. The others are only reported, never required - this
# repository ships most of them (apply-patches.ps1 copies them in), and a
# backend that has not been patched yet is a normal starting point, not an
# error. Requiring them here would refuse a folder that is exactly right.
$NEEDS    = @('jarvis_hud.py')
$NICE     = @('jarvis_gate.py', 'jarvis_framework.py', 'jarvis_memory.py',
              'jarvis_agent.py', 'jarvis_intake.py', 'jarvis-framework.toml')

Say ""
Say "Jarvis backend folder"
Say ""

# --- 1. the folder exists, and is a folder ------------------------------------
if (-not (Test-Path -LiteralPath $BackendPath)) {
    Write-Host "  FAIL  There is no folder at:" -ForegroundColor Red
    Say   "            $BackendPath" Red
    Say ""
    Say   "  Nothing was changed. Point -BackendPath at your Jarvis backend folder -" Cyan
    Say   "  the one holding jarvis_hud.py:" Cyan
    Say   '      powershell -ExecutionPolicy Bypass -File .\scripts\install-backend.ps1 -BackendPath "D:\your\backend\folder"' Cyan
    Finish 1 'failed'
}
if (-not (Test-Path -LiteralPath $BackendPath -PathType Container)) {
    Write-Host "  FAIL  That is a file, not a folder:" -ForegroundColor Red
    Say   "            $BackendPath" Red
    Say ""
    Say   "  The variable wants the FOLDER that holds it, not the file itself." Cyan
    Finish 1 'failed'
}

# The real path, with no .. or shortcuts left in it. Everything from here on
# uses this one, so what gets stored is what gets checked.
$Resolved = (Resolve-Path -LiteralPath $BackendPath).Path
Say "  ok    Folder: $Resolved" Green

# --- 2. this repository is not a backend folder -------------------------------
#
# The mistake this catches, in the owner's own words: pointing the variable at
# the repository's backend\ folder, which holds the PATCHES and the test
# suites, not the program. It has a backend\selftest.py and a backend\_where.py
# and looks plausible from a directory listing, and the failure it causes is
# quiet - the suites test the repository against itself and pass, while your
# real Jarvis is never looked at. This repository is the only folder that can
# be mistaken for a backend, so it is the one that is named here.
$RepoRoot = Split-Path -Parent $PSScriptRoot
$norm = { param($p) $p.TrimEnd('\', '/').ToLowerInvariant() }
$here = & $norm $Resolved
foreach ($notBackend in @($RepoRoot, (Join-Path $RepoRoot 'backend'))) {
    if ($here -eq (& $norm $notBackend)) {
        Write-Host "  FAIL  That is not a backend folder - it is this repository:" -ForegroundColor Red
        Say   "            $Resolved" Red
        Say ""
        Say   "  This repository holds CHANGES for Jarvis, not Jarvis. Its backend\" Cyan
        Say   "  folder is patches and tests. Point the variable at the folder that" Cyan
        Say   "  holds the real jarvis_hud.py on your PC - docs\INSTALL.md step 1.3" Cyan
        Say   "  says where that came from, and check-backend.ps1 -BackendPath finds" Cyan
        Say   "  it if you are unsure. (OpenJarvis is a different project that shares" Cyan
        Say   "  the name and is not this one either.)" Cyan
        Say ""
        Say   "  Nothing was changed." Cyan
        Finish 1 'failed'
    }
}

# --- 3. the files that make it a backend folder -------------------------------
$missing = @()
foreach ($f in $NEEDS) {
    if (-not (Test-Path -LiteralPath (Join-Path $Resolved $f) -PathType Leaf)) { $missing += $f }
}
if ($missing.Count -gt 0) {
    Write-Host "  FAIL  That folder has no $($missing -join ', ') in it:" -ForegroundColor Red
    Say   "            $Resolved" Red
    Say ""
    Say   "  It exists, so the path is not misspelled - but it is not the folder" Cyan
    Say   "  the checks and the patches are about. Find the one that holds" Cyan
    Say   "  jarvis_hud.py before setting this:" Cyan
    Say   "      powershell -ExecutionPolicy Bypass -File .\scripts\check-backend.ps1 -BackendPath `"$Resolved`"" Cyan
    Say ""
    Say   "  Nothing was changed." Cyan
    Finish 1 'failed'
}
Say "  ok    It has jarvis_hud.py, so it is a backend folder" Green

$have = @()
foreach ($f in $NICE) {
    if (Test-Path -LiteralPath (Join-Path $Resolved $f) -PathType Leaf) { $have += $f }
}
if ($have.Count -gt 0) { Say "  ok    Also there: $($have -join ', ')" Green }
$pyCount = @(Get-ChildItem -LiteralPath $Resolved -Filter '*.py' -File -ErrorAction SilentlyContinue).Count
Say "  ok    $pyCount .py file(s) in it" Green

# --- 4. where it would be stored, checked before anything is stored -----------
$stored   = Get-StoredUserVariable 'JARVIS_BACKEND'
$machine  = [Environment]::GetEnvironmentVariable('JARVIS_BACKEND', 'Machine')
$alreadyOk = $false
if ($stored -and ((& $norm $stored) -eq $here)) { $alreadyOk = $true }

if ($alreadyOk) {
    Say ""
    Write-Host "  ok    JARVIS_BACKEND is already this folder - no change needed" Green
} elseif ($stored) {
    Say ""
    Say   "  note  JARVIS_BACKEND is set to a DIFFERENT folder right now:" Yellow
    Say   "            $stored" Yellow
    Say   "        This run replaces it with the folder checked above. If that other" Yellow
    Say   "        folder is another copy of Jarvis you still use, stop here and run" Yellow
    Say   "        again with that one instead - only one backend can be the one the" Yellow
    Say   "        checks look at." Yellow
} else {
    Say ""
    Say   "  ok    JARVIS_BACKEND is not set yet, so this is a new setting" Green
}
if ($machine -and ((& $norm $machine) -ne $here)) {
    Say   "        Careful: the whole PC also has one, set to:" Yellow
    Say   "            $machine" Yellow
    Say   "        That is a machine-wide setting (it usually means an administrator" Yellow
    Say   "        made it). Windows gives it to programs BEFORE your own, so the" Yellow
    Say   "        tests would keep using that folder even after this run." Yellow
}

# --- 5. the commands this run suggests ----------------------------------------
#
# Built now, printed by Finish, so a run that stops early never prints a next
# step for a folder it refused.
$pyLine = $null
foreach ($cand in @('py -3', 'python', 'python3')) {
    $parts = $cand -split ' '
    $cmd = Get-Command $parts[0] -CommandType Application -ErrorAction SilentlyContinue |
           Select-Object -First 1
    if ($cmd) {
        try {
            $out = @(& $cmd.Source -c "import sys; print(sys.executable)" 2>$null)
            if ($LASTEXITCODE -eq 0 -and $out.Count -ge 1) { $pyLine = $cand; break }
        } catch { }
    }
}
$selftest = Join-Path $RepoRoot 'backend\selftest.py'
$saved    = '"$env:USERPROFILE\Desktop\preflight.txt"'
if (Test-Path -LiteralPath $selftest) {
    $run = if ($pyLine) { $pyLine } else { 'py -3' }
    $script:Next = "$run `"$selftest`" --preflight | Tee-Object -FilePath $saved"
} else {
    $script:Next = "see docs\INSTALL.md step 1.10 - this script could not find backend\selftest.py beside it"
}

# The one line that puts things back. Built from what is stored NOW, so it is
# right whether this is the first run or the fifth.
if ($stored) {
    $esc = $stored -replace "'", "''"
    $script:Undo = "[Environment]::SetEnvironmentVariable('JARVIS_BACKEND', '$esc', 'User')"
} else {
    $script:Undo = "Remove-ItemProperty -LiteralPath 'HKCU:\Environment' -Name 'JARVIS_BACKEND' -ErrorAction SilentlyContinue"
}

# --- 6. the one change ---------------------------------------------------------
if ($Print) {
    Say ""
    Say "  -Print: stopping here. Nothing was changed. Without it, this run would set" Cyan
    Say "  JARVIS_BACKEND (for your Windows account) to:" Cyan
    Say "      $Resolved" Cyan
    Finish 0 'print' $Resolved
}

if ($alreadyOk) { Finish 0 'twice' $Resolved }

# Session first, so anything this script starts sees it; then stored, so new
# programs do. The write is the only thing in this script that changes
# anything, and it is one registry value under your own account.
$env:JARVIS_BACKEND = $Resolved
[Environment]::SetEnvironmentVariable('JARVIS_BACKEND', $Resolved, 'User')
$script:Changed = $true

# Prove it took, by reading it back the same way step 4 read the old one. A
# setting that silently did not save would otherwise look exactly like one
# that did.
$check = Get-StoredUserVariable 'JARVIS_BACKEND'
if (-not $check -or ((& $norm $check) -ne $here)) {
    Write-Host "  FAIL  The setting did not save. It reads back as:" -ForegroundColor Red
    Say   "            $(if ($check) { $check } else { '(nothing)' })" Red
    Say ""
    Say   "  Your Windows account may not allow writes to its own environment" Cyan
    Say   "  settings (rare; a policy set by someone else can do it). Nothing else" Cyan
    Say   "  was changed, so there is nothing to undo. Set it by hand instead:" Cyan
    Say   "      [Environment]::SetEnvironmentVariable('JARVIS_BACKEND', '$Resolved', 'User')" Cyan
    $script:Changed = $false
    Finish 1 'failed'
}

Say ""
Write-Host "  ok    JARVIS_BACKEND set, and read back to confirm it" -ForegroundColor Green
Say   "        (stored under HKCU:\Environment for your Windows account only)" Gray

Finish 0 'done' $Resolved
