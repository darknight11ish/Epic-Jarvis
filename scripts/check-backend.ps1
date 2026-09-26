<#
.SYNOPSIS
  Is your backend folder complete? Lists every module it needs and says which
  are there.

.DESCRIPTION
  `jarvis_hud.py` is one program made of many files that import each other. If
  one is missing, Python does not tell you which until you try to run it - and
  several of the imports are wrapped in `try`, so the program can start, look
  healthy, and fail later on a real request.

  Worse, a single missing file can hide the rest. `jarvis_framework` is
  imported by nearly everything, so the moment it is absent the FIRST import
  fails and you never find out what else is gone.

  This reads the import lines of every file you have, works out the full list
  of modules they need, and says which are present. Run it after recovering
  files to see how far you have got.

  It changes nothing. It only reads.

.PARAMETER BackendPath
  The folder holding jarvis_hud.py.

.EXAMPLE
  From the folder this repository is cloned into:

  powershell -ExecutionPolicy Bypass -File .\scripts\check-backend.ps1
  powershell -ExecutionPolicy Bypass -File .\scripts\check-backend.ps1 -BackendPath "D:\jarvis"
#>

[CmdletBinding()]
param(
    [string] $BackendPath = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"
)

$ErrorActionPreference = 'Stop'

function Say($msg, $colour = 'Gray') { Write-Host $msg -ForegroundColor $colour }

if (-not (Test-Path -LiteralPath $BackendPath)) {
    Write-Host "  FAIL  No folder at: $BackendPath" -ForegroundColor Red
    Say "        Point it somewhere else with -BackendPath `"D:\your\path`"" Cyan
    exit 1
}

$files = @(Get-ChildItem -LiteralPath $BackendPath -Filter '*.py' -ErrorAction SilentlyContinue)
if ($files.Count -eq 0) {
    Write-Host "  FAIL  No .py files in: $BackendPath" -ForegroundColor Red
    exit 1
}

# Which module does an import line actually NAME?
#
# This distinguishes a module from a nickname, and getting it wrong over-counts
# badly - a first pass at this reported four missing files that were not files
# at all. `from jarvis_gate import confirm as jarvis_confirm` mentions
# "jarvis_confirm", but that is a function inside jarvis_gate, not a file that
# needs to exist. Only the name after `from`, or the names after `import` in a
# plain `import a, b as c` line, are modules.
$needed = @{}
foreach ($f in $files) {
    foreach ($line in (Get-Content -LiteralPath $f.FullName)) {

        $mods = @()
        if ($line -match '^\s*from\s+([A-Za-z_][A-Za-z0-9_\.]*)\s+import\s') {
            # from X import anything  ->  only X is a file
            $mods = @($Matches[1])
        }
        elseif ($line -match '^\s*import\s+(.+?)\s*(#.*)?$') {
            # import A, B as b, C  ->  A, B and C are all files
            foreach ($part in ($Matches[1] -split ',')) {
                $name = ($part.Trim() -split '\s+as\s+')[0].Trim()
                if ($name) { $mods += $name }
            }
        }

        foreach ($m in $mods) {
            # Only the project's own modules. A missing `os` is not a thing.
            $top = ($m -split '\.')[0]
            if ($top -notlike 'jarvis_*') { continue }
            if (-not $needed.ContainsKey($top)) { $needed[$top] = @() }
            if ($needed[$top] -notcontains $f.Name) { $needed[$top] += $f.Name }
        }
    }
}


# Which of them this repository ships whole? apply-patches.ps1 copies those in
# itself, so a backend without them is not incomplete - it is just not
# updated yet. This script used to call them MISSING and say "do not run
# apply-patches.ps1 yet", about the very files apply-patches.ps1 puts there.
# Read from backend\_where.py's SHIPPED, which a test keeps equal to the
# script's own list.
$shippedHere = @{}
$wherePy = Join-Path (Join-Path (Split-Path -Parent $PSScriptRoot) 'backend') '_where.py'
if (Test-Path -LiteralPath $wherePy) {
    $whereText = [IO.File]::ReadAllText($wherePy)
    $at = $whereText.IndexOf('SHIPPED = (')
    if ($at -ge 0) {
        $end = $whereText.IndexOf("`n)", $at)
        if ($end -lt 0) { $end = $whereText.Length }
        $block = $whereText.Substring($at, $end - $at)
        foreach ($mm in [regex]::Matches($block, '"(?:rebuilt/)?(jarvis_\w+)\.py"')) {
            $shippedHere[$mm.Groups[1].Value] = $true
        }
    }
}

$have     = @()
$missing  = @()
$comingIn = @()
foreach ($m in ($needed.Keys | Sort-Object)) {
    if (Test-Path -LiteralPath (Join-Path $BackendPath "$m.py")) { $have += $m }
    elseif ($shippedHere.ContainsKey($m)) { $comingIn += $m }
    else { $missing += $m }
}

Say ""
Say "Backend : $BackendPath"
Say "Modules : $($needed.Count) needed, $($have.Count) present, $($comingIn.Count) to be copied in by apply-patches.ps1, $($missing.Count) missing"
Say ""

foreach ($m in $have) {
    Write-Host ("  ok       {0}" -f $m) -ForegroundColor Green
}
if ($comingIn.Count -gt 0) {
    Say ""
    foreach ($m in $comingIn) {
        Write-Host ("  not yet  {0,-22} this repository ships it; apply-patches.ps1 copies it in" -f $m) -ForegroundColor Cyan
    }
}
if ($missing.Count -gt 0) {
    Say ""
    # Most-needed first. The one fifteen files import is the one to find first:
    # until it is there, nothing else can even be tested.
    foreach ($m in ($missing | Sort-Object { -$needed[$_].Count })) {
        $who = $needed[$m]
        $n = $who.Count
        Write-Host ("  MISSING  {0,-22} {1} file(s) need it" -f $m, $n) -ForegroundColor Red
        Say ("             $($who -join ', ')") DarkGray
    }
}

Say ""
if ($missing.Count -eq 0) {
    Write-Host "  Nothing is missing that only your PC can have." -ForegroundColor Green
    Say ""
    Say "  That is not the same as the backend working - a file could still be" Cyan
    Say "  an empty stub - but nothing is absent. Next (one line, from the folder" Cyan
    Say "  this repository is cloned into):" Cyan
    Say "      powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1 -BackendPath `"$BackendPath`"" Cyan
    Say ""
    exit 0
}

Write-Host "  $($missing.Count) module(s) are not in that folder, and this repository does not have them either." -ForegroundColor Yellow
Say ""
Say "  Find the one at the top of that list first. Until it is there, Python" Cyan
Say "  stops at the first import and cannot tell you whether the rest work." Cyan
Say ""
Say "  Do not run apply-patches.ps1 yet. Patching an incomplete backend fixes" Cyan
Say "  the wrong problem." Cyan
Say ""
exit 1
