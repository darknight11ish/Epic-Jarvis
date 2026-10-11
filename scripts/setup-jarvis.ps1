<#
.SYNOPSIS
  One command on a new PC: put the backend in place, install its packages, say
  what is still missing, install the desktop app, and start Jarvis.

.DESCRIPTION
  docs\INSTALL.md walks a person through the whole first part in order. This
  runs the same scripts, in the same order, without the walking:

    1.3  copy jarvis-backend\ to a folder of your own
    1.5  scripts\install-backend.ps1   writes down where that folder is
         scripts\apply-patches.ps1     Python packages, the settings file, tests
    1.7  say whether Ollama and Jarvis's model are ready, and print the exact
         command when they are not
    1.8  start the backend
    part 2  the desktop app: scripts\update-jarvis.ps1 installs the published
         installer, or builds it here, and then runs the live check

  WHAT IT WILL NOT DO ITSELF. It never downloads the model: that is about 5 GB,
  so the one command that does it is printed for you to read and run yourself.
  It never writes inside this download. It copies the backend; it does not move
  it. And it never overwrites a backend folder that is already there: a second
  run says so and hands the folder to apply-patches.ps1, which is idempotent on
  purpose.

  THE DESKTOP APP IS THE ONE THING IT DOES NOT DO ITSELF. It calls
  scripts\update-jarvis.ps1 for that, at the end, with -SkipPatches so the
  patcher is not run twice. That script fetches the published installer from
  this project's own release page and says so before it does (or builds the app
  from this folder when there is no release, or when you add -FromSource). Add
  -SkipDesktop to leave the app alone entirely.

  Everything it changes, it names as it goes: one folder under your own
  Documents, one environment variable for your Windows account (set by
  install-backend.ps1, User scope, no administrator needed), and whatever the
  desktop installer does - it installs for your account only, under
  %LOCALAPPDATA%, so it needs no administrator window either.

  If a step fails, it stops and says which one, and nothing later is attempted.
  The scripts it runs each rehearse before they change anything.

.PARAMETER BackendPath
  Where the backend should live. Default: Documents\jarvis-backend under your
  own user folder - never a path from somebody else's PC.

.PARAMETER Print
  Do all the checking and print the exact commands, with your paths already in
  them. Nothing is copied, installed, downloaded or started.

.PARAMETER NoStart
  Do not start the backend. The start line is printed instead.

.PARAMETER SkipDesktop
  Leave the desktop app exactly as it is: do not call update-jarvis.ps1 at all.

.PARAMETER FromSource
  Passed to update-jarvis.ps1: build the desktop app from this folder instead
  of installing the published one. It needs the C++ build tools, Rust and
  Node.js, and takes a few minutes.

.PARAMETER SkipPackages
  Passed to apply-patches.ps1: do not install the Python packages. The features
  that need them stay off until you install them.

.PARAMETER SkipTests
  Passed to apply-patches.ps1: do not run the test suites. Quicker, and less
  proven - the patcher says so in its own words when it finishes.

.PARAMETER Force
  Passed to both scripts this one runs, where it means two different things:
  to apply-patches.ps1, "run even while a Jarvis program looks like it is
  running" (use it when you know the folder is not in use); to
  update-jarvis.ps1, "close a running Jarvis rather than asking you to" - which
  stops the app and the backend process, cutting off anything Jarvis was doing
  at that moment. It does not mean "overwrite the backend folder": this script
  never overwrites one.

.EXAMPLE
  From the folder you downloaded this repository into. -ExecutionPolicy Bypass
  lets Windows run a script file for this one command, without changing any
  setting:

  powershell -ExecutionPolicy Bypass -File .\scripts\setup-jarvis.ps1
  powershell -ExecutionPolicy Bypass -File .\scripts\setup-jarvis.ps1 -Print

.EXAMPLE
  Somewhere else, and without the long test run:

  powershell -ExecutionPolicy Bypass -File .\scripts\setup-jarvis.ps1 -BackendPath "D:\jarvis" -SkipTests

.EXAMPLE
  The backend only, no desktop app:

  powershell -ExecutionPolicy Bypass -File .\scripts\setup-jarvis.ps1 -SkipDesktop
#>

[CmdletBinding()]
param(
    [string] $BackendPath = (Join-Path $env:USERPROFILE 'Documents\jarvis-backend'),
    [switch] $Print,
    [switch] $NoStart,
    [switch] $SkipDesktop,
    [switch] $FromSource,
    [switch] $SkipPackages,
    [switch] $SkipTests,
    [switch] $Force
)

$ErrorActionPreference = 'Stop'

function Say($msg, $colour = 'Gray') { Write-Host $msg -ForegroundColor $colour }
function Title($msg) { Say ""; Say $msg White }
function Step($n, $msg) { Say ""; Say "  [$n/6] $msg" Cyan }

$repo         = Split-Path -Parent $PSScriptRoot
$base         = Join-Path $repo 'jarvis-backend'
$installScript = Join-Path $PSScriptRoot 'install-backend.ps1'
$patchScript   = Join-Path $PSScriptRoot 'apply-patches.ps1'
$modelfile     = Join-Path $repo 'backend\jarvis-primary.Modelfile'

Title "Jarvis - one command"
Say "  download   : $repo"
Say "  backend to : $BackendPath"
if ($Print) { Say "  mode       : PRINT - nothing will be copied, installed or started" Yellow }
else        { Say "  mode       : real run" }

# ---------------------------------------------------------------- the checks
# Everything is looked at BEFORE anything is changed, the way the two scripts
# this one calls do it: a missing piece is named, and nothing is half-done.
Title "Checking this download"
$problems = @()
if (-not (Test-Path -LiteralPath (Join-Path $base 'jarvis_hud.py'))) {
    $problems += "jarvis-backend\jarvis_hud.py is not here. Download the repository again, or unzip it fully - this script cannot build the backend from nothing."
}
if (-not (Test-Path -LiteralPath $installScript)) { $problems += "scripts\install-backend.ps1 is missing from this download." }
if (-not (Test-Path -LiteralPath $patchScript))   { $problems += "scripts\apply-patches.ps1 is missing from this download." }
if (-not (Test-Path -LiteralPath $modelfile))     { $problems += "backend\jarvis-primary.Modelfile is missing (needed later, for the model)." }

$python = Get-Command py -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if (-not $python) {
    $problems += "Python is not installed, or not on PATH. Install Python 3.12 from python.org and tick 'Add python.exe to PATH'."
}

foreach ($p in $problems) { Say "  FAIL  $p" Red }
if ($problems.Count -gt 0) { Say ""; Say "  Nothing was changed. Fix the line(s) above and run this again." Yellow; exit 1 }
Say "  ok    the backend, both scripts and the Modelfile are here" Green
Say ("  ok    Python found: {0}" -f $python.Source) Green

# ------------------------------------------------------- 1. the backend folder
Step 1 "the backend folder"
$already = Test-Path -LiteralPath (Join-Path $BackendPath 'jarvis_hud.py')
if ($already) {
    Say "  already there: $BackendPath holds jarvis_hud.py, so nothing is copied." Green
    Say "  (This script never overwrites a backend folder. apply-patches.ps1 brings it" DarkGray
    Say "   up to date instead, and it is safe to run again.)" DarkGray
} elseif ($Print) {
    Say "  would run : New-Item -ItemType Directory -Force `"$BackendPath`""
    Say "  would run : Copy-Item -Recurse -Force `"$base\*`" `"$BackendPath`""
} else {
    New-Item -ItemType Directory -Force -Path $BackendPath | Out-Null
    Copy-Item -Path (Join-Path $base '*') -Destination $BackendPath -Recurse -Force
    Say ("  copied {0} files from jarvis-backend\ to {1}" -f (Get-ChildItem -LiteralPath $BackendPath -File -Recurse).Count, $BackendPath) Green
}

# ------------------------------------------------- 2. tell this PC where it is
Step 2 "tell this PC where the backend is (scripts\install-backend.ps1)"
$installLine = "powershell -ExecutionPolicy Bypass -File `"$installScript`" -BackendPath `"$BackendPath`""
Say "  $installLine" DarkGray
if (-not $Print) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $installScript -BackendPath $BackendPath
    if ($LASTEXITCODE -ne 0) {
        Say ""
        Say "  FAIL  install-backend.ps1 exited $LASTEXITCODE - read what it printed above." Red
        Say "  Already done: the backend folder $BackendPath was created and filled. Nothing" Yellow
        Say "  later was attempted. Run this command again once that is fixed." Yellow
        exit $LASTEXITCODE
    }
}

# ------------------------------------------- 3. packages, settings and tests
Step 3 "Python packages, the settings file, and the tests (scripts\apply-patches.ps1)"
$patchArgs = @()
if ($SkipPackages) { $patchArgs += '-SkipPackages' }
if ($SkipTests)    { $patchArgs += '-SkipTests' }
if ($Force)        { $patchArgs += '-Force' }
$patchLine = "powershell -ExecutionPolicy Bypass -File `"$patchScript`" -BackendPath `"$BackendPath`""
if ($patchArgs.Count -gt 0) { $patchLine += ' ' + ($patchArgs -join ' ') }
Say "  $patchLine" DarkGray
if (-not $Print) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $patchScript -BackendPath $BackendPath @patchArgs
    if ($LASTEXITCODE -ne 0) {
        Say ""
        Say "  FAIL  apply-patches.ps1 exited $LASTEXITCODE - read what it printed above; its own" Red
        Say "  last screen says whether it changed any file." Red
        Say "  Already done: the backend folder is in place and JARVIS_BACKEND is set for your" Yellow
        Say "  account. Nothing later was attempted - in particular the desktop app was not" Yellow
        Say "  installed. Run this command again once the first problem is fixed." Yellow
        exit $LASTEXITCODE
    }
}

# ------------------------------------------------------------- 4. the model
Step 4 "Ollama and Jarvis's model"
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
$modelLine = "[Environment]::SetEnvironmentVariable('OLLAMA_KV_CACHE_TYPE', 'q8_0', 'User'); [Environment]::SetEnvironmentVariable('OLLAMA_KEEP_ALIVE', '-1', 'User'); ollama pull qwen3:8b; ollama create jarvis-primary -f `"$modelfile`""
$modelReady = $false
if (-not $ollama) {
    Say "  Ollama is not installed. Install it from ollama.com, then click its tray icon once." Red
} else {
    # Asked for real, in -Print too: `ollama list` only reads, and a plan that
    # skipped this step said "Jarvis needs its model first" - and printed the
    # 5 GB command - on a PC that already had the model.
    Say ("  ollama found: {0}" -f $ollama.Source) Green
    $listed = & ollama list 2>$null
    if ($LASTEXITCODE -eq 0 -and ($listed -join "`n") -match 'jarvis-primary') {
        $modelReady = $true
        Say "  the jarvis-primary model is ready" Green
    } else {
        Say "  the jarvis-primary model is NOT built yet." Yellow
    }
}

# ------------------------------------------------------------- 5. start it
Step 5 "start the backend"
$startLine = "cd `"$BackendPath`"; `$env:HF_HUB_DISABLE_TELEMETRY = '1'; `$env:DO_NOT_TRACK = '1'; `$env:ANONYMIZED_TELEMETRY = 'False'; py -3 jarvis_hud.py"
if ($NoStart) {
    Say "  -NoStart was given. Start it yourself with:" DarkGray
    Say "  $startLine" DarkGray
} elseif (-not $modelReady) {
    Say "  not started: Jarvis needs its model first, and the answer would be a confusing" Yellow
    Say "  error rather than a working assistant." Yellow
    Say ""
    Say "  Run these two lines, in this order, then run this script again:" White
    Say ""
    Say "    $modelLine" Cyan
    Say ""
    Say "    $startLine" Cyan
    Say ""
    Say "  (The first line downloads about 5 GB and builds Jarvis's tuned copy of the" DarkGray
    Say "   model. Quit Ollama from its tray icon and start it again afterwards, so it" DarkGray
    Say "   reads the two settings that line sets. docs\INSTALL.md, step 1.7, says the" DarkGray
    Say "   same, and MODEL-TOPOLOGY.md says why this model.)" DarkGray
} elseif ($Print) {
    Say "  would run : $startLine"
} else {
    Say "  starting it in a new window. That window IS Jarvis: close it to stop him." Green
    Start-Process -FilePath 'powershell' -ArgumentList @('-NoExit', '-Command', $startLine) | Out-Null
    Say ""
    Say "  What to look for in that window, at the top (docs\INSTALL.md, step 1.8):" DarkGray
    Say "    a 'token' line saying 'in Windows Credential Manager' - the pairing token was made" DarkGray
    Say "    and saved. Anything else on that line says why." DarkGray
}

# ------------------------------------------------- 6. the desktop app, and the check
Step 6 "the desktop app, and the live check (scripts\update-jarvis.ps1)"
$updateScript = Join-Path $PSScriptRoot 'update-jarvis.ps1'
$updateArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $updateScript,
                '-BackendPath', $BackendPath, '-SkipPatches')
if ($FromSource) { $updateArgs += '-FromSource' }
if ($Force)      { $updateArgs += '-Force' }
# Built for PRINTING, not for running: both paths here and the backend folder
# can hold spaces (this repository's own folder does), and a printed line that
# cannot be pasted is no use to the person reading it.
$updateLine = 'powershell -NoProfile -ExecutionPolicy Bypass -File "' + $updateScript +
              '" -BackendPath "' + $BackendPath + '" -SkipPatches'
if ($FromSource) { $updateLine += ' -FromSource' }
if ($Force)      { $updateLine += ' -Force' }

if ($SkipDesktop) {
    Say "  -SkipDesktop was given, so the desktop app was left exactly as it is." DarkGray
    Say "  Install it whenever you like with:" DarkGray
    Say "  $updateLine" DarkGray
} elseif (-not (Test-Path -LiteralPath $updateScript)) {
    Say "  FAIL  scripts\update-jarvis.ps1 is missing from this download, so the desktop" Red
    Say "        app was not installed. The backend above is in place and usable." Red
    exit 1
} elseif ($Print) {
    Say "  would run : $updateLine" 
    Say "  (that script installs the published desktop installer, or builds the app from" DarkGray
    Say "   this folder when there is no release, then runs the live check. -SkipPatches" DarkGray
    Say "   is there because step 3 above already patched the backend.)" DarkGray
} else {
    Say "  $updateLine" DarkGray
    Say "  Install the desktop app, then check the whole chain. This is the long step, and" DarkGray
    Say "  the one that may download (see the note above this script's step 6): the" DarkGray
    Say "  published installer, or a few minutes of building when there is none." DarkGray
    & powershell @updateArgs
    if ($LASTEXITCODE -ne 0) {
        Say ""
        Say "  FAIL  update-jarvis.ps1 exited $LASTEXITCODE. The backend above IS installed and" Red
        Say "        patched; read what it printed for the desktop app, then run this command" Red
        Say "        again - everything already done is recognised and skipped." Red
        exit $LASTEXITCODE
    }
}

# ------------------------------------------------------------------ done
Title "Done"
if ($Print) {
    Say "  PRINT mode: nothing above was run. Run the same command without -Print." Yellow
} else {
    Say "  backend : $BackendPath" Green
    Say "  changes : that folder, and one environment variable for your account (JARVIS_BACKEND)" Green
    Say "  undone  : delete the folder; the variable is removed by" Green
    Say "            [Environment]::SetEnvironmentVariable('JARVIS_BACKEND', `$null, 'User')" DarkGray
    if (-not $NoStart -and $modelReady) { Say "  Jarvis is starting in its own window." Green }
    if (-not $SkipDesktop) {
        Say ""
        Say "  From now on, one command updates both halves - the backend and the desktop app:" White
        Say "    powershell -ExecutionPolicy Bypass -File `"$PSScriptRoot\update-jarvis.ps1`"" Cyan
    }
}
Say ""
