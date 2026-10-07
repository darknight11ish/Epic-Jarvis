<#
.SYNOPSIS
  Update BOTH halves of Jarvis in one command: the backend on your PC and the
  desktop app.

.DESCRIPTION
  Updating Jarvis used to be two jobs in two windows, done in a particular
  order: run scripts\apply-patches.ps1 to patch the backend, then rebuild and
  reinstall the desktop app (docs\INSTALL.md, "Updating everything"). Doing
  them apart is not just more steps - it is the order that matters. The desktop
  app is a client of the backend: it asks the backend what it can do, and tells
  you to run apply-patches.ps1 when the backend is older than the app. So an
  app updated alone is an app that spends its time saying "your PC's Jarvis
  cannot do that yet", and a backend patched alone waits for an app that knows
  about the new features.

  This script is that whole sequence, in the one order that works:

    1. Work out which folder is the backend (a saved setting, or -BackendPath).
    2. Get the newest code, without touching anything if it cannot.
    3. Close Jarvis (the desktop app, and any Jarvis you started in PowerShell).
       A running Jarvis holds the files the patches change, and the desktop app
       restarts a backend it supervises, so this has to happen first.
    4. Patch the backend - by running scripts\apply-patches.ps1, unchanged. That
       script still rehearses every patch on a throwaway copy, backs everything
       up, and refuses to leave you half-applied. This script adds no patching
       of its own.
    5. Update the desktop app. Downloading the published installer is tried
       first (it is seconds); building it here is the fallback (it needs the
       build tools and takes minutes). Which one is used, and why, is printed.
    6. Start Jarvis again, and run the live check (backend\selftest.py
       --preflight).

  EVERY STEP IS CHECKED BEFORE IT CHANGES ANYTHING. If the backend folder is
  wrong, or Jarvis is still running and you did not say -Force, this ends with
  "NOT DONE - nothing was changed", truthfully: nothing has been touched yet.

  Run it again any time. It works out what is already done and does the rest.

  What this script does NOT do: it never approves anything for you, it never
  installs an update on its own (you ran it - that is the decision), and it
  never prints a token or a key. The desktop app's own Settings -> Updates
  button remains the route that checks the installer's signature; see the note
  under -FromSource and in docs\INSTALL.md.

.PARAMETER BackendPath
  The folder holding jarvis_hud.py. Left out, it uses the JARVIS_BACKEND
  setting that scripts\install-backend.ps1 saved; if that is not set either,
  the script says how to set it and changes nothing.

.PARAMETER Print
  Work everything out, print exactly what it would do, and change nothing. Use
  it to see the plan before letting it run.

.PARAMETER FromSource
  Build the desktop app from this folder instead of downloading the published
  installer. Use it when you are working on the app itself, or when you would
  rather not run a downloaded installer.

.PARAMETER SkipDesktop
  Update only the backend. The desktop app is left exactly as it is.

.PARAMETER SkipPatches
  Update only the desktop app (and the check): do not run
  apply-patches.ps1 at all. This exists for scripts\setup-jarvis.ps1, which
  patches the backend itself as one of its own steps and then calls this
  script for the desktop half - without this, the patcher would run twice on a
  first install, rehearsing all 121 patches a second time for no reason.

.PARAMETER SkipTests
  Passed straight to apply-patches.ps1: apply the patches without running the
  test suites afterwards. The update is then applied but NOT proven.

.PARAMETER NoCheck
  Do not run the live check at the end.

.PARAMETER Force
  Close a running Jarvis rather than asking you to. This stops the backend
  process, so anything Jarvis was doing at that moment is cut off.

.EXAMPLE
  From the folder this repository was unzipped or cloned into. One line:

  powershell -ExecutionPolicy Bypass -File .\scripts\update-jarvis.ps1

  See what it would do first, changing nothing:

  powershell -ExecutionPolicy Bypass -File .\scripts\update-jarvis.ps1 -Print

  The backend only:

  powershell -ExecutionPolicy Bypass -File .\scripts\update-jarvis.ps1 -SkipDesktop
#>

[CmdletBinding()]
param(
    [string] $BackendPath = '',
    [switch] $Print,
    [switch] $FromSource,
    [switch] $SkipPatches,
    [switch] $SkipDesktop,
    [switch] $SkipTests,
    [switch] $NoCheck,
    [switch] $Force
)

$ErrorActionPreference = 'Stop'

# Windows PowerShell 5.1 asks Windows for its TLS settings, and on a PC where
# that answer is old, every HTTPS call to GitHub fails with "the underlying
# connection was closed" - which reads like GitHub being down. 1.2 is added to
# whatever is already allowed, and never taken away.
try {
    [Net.ServicePointManager]::SecurityProtocol =
        [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch { }

# --- how this script talks -----------------------------------------------------
#
# Same four words as apply-patches.ps1, so a run of either reads the same way:
# ok (done), skip (not done, and the reason is beside it), FAIL (a real
# problem), note (worth knowing, not a problem yet).
function Say($msg, $colour = 'Gray') { Write-Host $msg -ForegroundColor $colour }
function Ok($msg)   { Write-Host "  ok    $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  skip  $msg" -ForegroundColor Yellow }
function Bad($msg)  { Write-Host "  FAIL  $msg" -ForegroundColor Red }
function Info($msg) { Write-Host "  note  $msg" -ForegroundColor Cyan }
function Step($n, $of, $title) {
    Write-Host ""
    Write-Host "[$n/$of] $title" -ForegroundColor Cyan
}

# --- what this run did, and how it ends ---------------------------------------
#
# One place decides how the run ends (Finish-Run), so a run that stopped early
# can never print "done" on its way out. $script:Problems are real problems;
# $script:Notes are things worth reading that are not failures.
$script:Problems = New-Object System.Collections.ArrayList
$script:Notes    = New-Object System.Collections.ArrayList
$script:Changed  = $false
$script:RunLog   = $null
$script:InstallLine = $null
# A throwaway source copy, when this folder had no git pull to do. Deleted at
# the end of the run - by Finish-Run, which is the one place every ending goes
# through, because the copy is still being read while the backend is patched.
$script:TempSource = $null
# What happened to the desktop half: 'done', 'skipped', 'failed' or 'none'.
# The closing banner is built from this rather than from what was asked for, so
# a run that skipped or failed the app can never print "the desktop app is up to
# date".
$script:DesktopState = 'none'

function Add-Problem($msg) { [void]$script:Problems.Add([string]$msg) }
function Add-Note($msg)    { [void]$script:Notes.Add([string]$msg) }

# Start Jarvis Desktop again, but only when THIS run closed it. Used by the two
# failure paths that end before the normal restart: without it, a run that
# stopped after closing the app leaves the owner with no app running and a line
# that says the app was "left alone".
function Restart-AppIfWeClosedIt {
    if (-not $script:AppWasRunning) { return }
    $again = Get-InstalledDesktop
    if ($again -and $again.Exe -and (Test-Path -LiteralPath $again.Exe)) {
        try {
            Start-Process -FilePath $again.Exe | Out-Null
            Ok "started the desktop app again (this run had closed it)"
        } catch {
            Warn "the desktop app was closed by this run and could not be started again"
        }
    } else {
        Warn "the desktop app was closed by this run - start it from the Start menu"
    }
}

# The end of every run. Never returns.
function Finish-Run {
    param([string] $Kind = 'done')
    $bar = ('=' * 68)
    Write-Host ""
    if ($script:Problems.Count -gt 0) {
        Write-Host $bar -ForegroundColor Red
        Write-Host " DONE WITH PROBLEMS - do not trust this update yet" -ForegroundColor Red
        Write-Host $bar -ForegroundColor Red
        $n = 0
        foreach ($p in $script:Problems) { $n++; Write-Host "  $n. $p" -ForegroundColor Red }
        if ($script:Changed) {
            Write-Host ""
            Write-Host "Files WERE changed before this went wrong - the notes below say which, and" -ForegroundColor Yellow
            Write-Host "apply-patches.ps1's own last screen and log say exactly what it did." -ForegroundColor Yellow
        } else {
            Write-Host ""
            Write-Host "Nothing was changed by this run." -ForegroundColor Green
        }
    } elseif ($Kind -eq 'print') {
        Write-Host $bar -ForegroundColor Yellow
        Write-Host " PRINTED ONLY - nothing was changed" -ForegroundColor Yellow
        Write-Host $bar -ForegroundColor Yellow
    } elseif ($Kind -eq 'stopped') {
        Write-Host $bar -ForegroundColor Red
        if ($script:Changed) {
            Write-Host " NOT DONE - Jarvis was left as it was (see the notes)" -ForegroundColor Red
        } else {
            Write-Host " NOT DONE - nothing was changed" -ForegroundColor Red
        }
        Write-Host $bar -ForegroundColor Red
    } else {
        Write-Host $bar -ForegroundColor Green
        $patched = -not $SkipPatches
        if (-not $patched -and $script:DesktopState -eq 'skipped') {
            Write-Host " DONE - nothing to do: both halves were skipped by your switches" -ForegroundColor Green
        } elseif (-not $patched -and $script:DesktopState -eq 'failed') {
            Write-Host " DONE - the desktop app was NOT updated (see the notes)" -ForegroundColor Yellow
        } elseif (-not $patched) {
            Write-Host " ALL DONE - the desktop app is up to date" -ForegroundColor Green
        } elseif ($script:DesktopState -eq 'skipped') {
            Write-Host " ALL DONE - the backend is patched (the desktop app was left alone)" -ForegroundColor Green
        } elseif ($script:DesktopState -eq 'failed') {
            Write-Host " DONE - the backend is patched, but the desktop app was NOT updated" -ForegroundColor Yellow
        } else {
            Write-Host " ALL DONE - the backend is patched and the desktop app is up to date" -ForegroundColor Green
        }
        Write-Host $bar -ForegroundColor Green
    }
    foreach ($t in $script:Notes) { Write-Host "  note  $t" -ForegroundColor Yellow }
    if ($script:InstallLine -and $Kind -ne 'stopped' -and $script:Problems.Count -eq 0) {
        Write-Host ""
        Write-Host "Next time, this one line does the whole update:" -ForegroundColor Cyan
        Write-Host "    $($script:InstallLine)" -ForegroundColor Cyan
    }
    if ($script:RunLog) {
        Write-Host ""
        Write-Host "Log of this run (this script's own output; apply-patches.ps1 keeps its" -ForegroundColor Gray
        Write-Host "own log of what it changed):" -ForegroundColor Gray
        Write-Host "    $($script:RunLog)" -ForegroundColor Gray
    }
    # The throwaway source copy, if this run made one. Silently best-effort: a
    # leftover folder in %TEMP% is not worth failing a finished update over.
    if ($script:TempSource) {
        Remove-Item -LiteralPath $script:TempSource -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ($script:Problems.Count -gt 0) { exit 1 }
    if ($Kind -eq 'stopped') { exit 1 }
    exit 0
}

trap {
    Write-Host ""
    Write-Host "  FAIL  The script stopped unexpectedly: $($_.Exception.Message)" -ForegroundColor Red
    Add-Problem "The script stopped unexpectedly: $($_.Exception.Message)"
    # This run may be the reason nothing is running any more.
    Restart-AppIfWeClosedIt
    Finish-Run
}

# --- small helpers -------------------------------------------------------------

# Run a program and give back its exit code, with its output left on screen.
#
# Native programs write to stderr when they fail, and a run with
# $ErrorActionPreference='Stop' turns the first stderr line into a terminating
# error that hides the real message (the trap CLAUDE.md records). So the
# preference is loosened around the call and put back afterwards.
function Invoke-Native {
    param([string] $Exe, [string[]] $Arguments)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Exe @Arguments
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
}

# One value out of the registry, read fresh rather than from this process.
#
# install-backend.ps1 writes JARVIS_BACKEND for the Windows account. A
# PowerShell window that was already open when it ran does not have it, which
# is exactly the window someone then runs this script in - so the registry is
# read, not $env:.
function Get-StoredUserVariable($name) {
    try {
        $item = Get-ItemProperty -LiteralPath 'HKCU:\Environment' -Name $name -ErrorAction Stop
        return [string]$item.$name
    } catch {
        return $null
    }
}

# Which Python. NOT simply `python`: on a fresh Windows 11 that name is a
# Microsoft Store shortcut that does not run Python at all. py -3 first - the
# launcher the python.org installer puts in C:\Windows - and each candidate is
# actually RUN, because a name on PATH proves nothing. Returns $null when there
# is none.
function Find-Python {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        foreach ($cand in @('py -3', 'python', 'python3')) {
            $parts = $cand -split ' '
            $cmd = Get-Command $parts[0] -CommandType Application -ErrorAction SilentlyContinue |
                   Select-Object -First 1
            if (-not $cmd) { continue }
            $pre = @()
            if ($parts.Count -gt 1) { $pre = @($parts[1..($parts.Count - 1)]) }
            $out = @(& $cmd.Source @pre -c "import sys; print(sys.executable)" 2>$null)
            if ($LASTEXITCODE -ne 0 -or $out.Count -lt 1) { continue }
            $exe = "$($out[0])".Trim()
            if (-not $exe -or -not (Test-Path -LiteralPath $exe)) { continue }
            return @{ Exe = $exe; Via = $cand }
        }
    } finally {
        $ErrorActionPreference = $prev
    }
    return $null
}

# --- is anything using the backend right now ----------------------------------

# A Python process whose command line names the backend folder or jarvis_hud.py.
# The same rule apply-patches.ps1 uses, so the two agree about what "Jarvis is
# running" means. A process started with `py -3` is `python.exe` here, which is
# why the process name is matched loosely.
function Get-RunningBackend($Backend) {
    $found = @()
    try {
        $bp = (Resolve-Path -LiteralPath $Backend).Path
        $rows = @()
        if (Get-Command Get-CimInstance -ErrorAction SilentlyContinue) {
            foreach ($p in @(Get-CimInstance -ClassName Win32_Process -ErrorAction Stop)) {
                $rows += @{ Id = [int]$p.ProcessId; Name = "$($p.Name)"; Cmd = "$($p.CommandLine)" }
            }
        } else {
            foreach ($l in @(& ps -eo 'pid=,comm=,args=' 2>$null)) {
                $m = [regex]::Match("$l", '^\s*(\d+)\s+(\S+)\s+(.*)$')
                if ($m.Success) { $rows += @{ Id = [int]$m.Groups[1].Value; Name = $m.Groups[2].Value; Cmd = $m.Groups[3].Value } }
            }
        }
        foreach ($r in $rows) {
            if ($r.Id -eq $PID) { continue }
            if ($r.Name -notmatch '^(py|pyw|python[0-9.]*|pythonw[0-9.]*)(\.exe)?$') { continue }
            if (-not $r.Cmd) { continue }
            if ($r.Cmd.IndexOf($bp, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or $r.Cmd -match 'jarvis_hud\.py') {
                $found += @{ Id = $r.Id; What = "python (pid $($r.Id))" }
            }
        }
    } catch { }
    return $found
}

# The desktop app, if it is running, and what it is called on this PC.
function Get-DesktopApp {
    $app = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -eq 'Jarvis Desktop' })
    if ($app.Count -eq 0) { return $null }
    return $app[0]
}

# Where the desktop app is installed, and which version, from the entry the
# installer wrote - so this works whether or not the app is running. Falls back
# to the running process, then to the two folders a per-user install uses.
function Get-InstalledDesktop {
    foreach ($key in @(
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall')) {
        if (-not (Test-Path -LiteralPath $key)) { continue }
        foreach ($child in @(Get-ChildItem -LiteralPath $key -ErrorAction SilentlyContinue)) {
            $v = Get-ItemProperty -LiteralPath $child.PSPath -ErrorAction SilentlyContinue
            if (-not $v -or -not $v.DisplayName) { continue }
            if ("$($v.DisplayName)" -notmatch 'Jarvis Desktop') { continue }
            $exe = $null
            if ($v.DisplayIcon) { $exe = ("$($v.DisplayIcon)" -replace ',\d+$', '').Trim('"') }
            if (-not $exe -and $v.InstallLocation) {
                $cand = Join-Path "$($v.InstallLocation)" 'Jarvis Desktop.exe'
                if (Test-Path -LiteralPath $cand) { $exe = $cand }
            }
            if ($exe -and (Test-Path -LiteralPath $exe)) {
                return @{ Exe = $exe; Version = "$($v.DisplayVersion)"; Where = 'the installed app' }
            }
        }
    }
    $run = Get-DesktopApp
    if ($run -and $run.Path -and (Test-Path -LiteralPath $run.Path)) {
        return @{ Exe = "$($run.Path)"; Version = ''; Where = 'the running app' }
    }
    foreach ($cand in @(
        (Join-Path $env:LOCALAPPDATA 'Jarvis Desktop\Jarvis Desktop.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Jarvis Desktop\Jarvis Desktop.exe'))) {
        if ($cand -and (Test-Path -LiteralPath $cand)) {
            return @{ Exe = $cand; Version = ''; Where = 'the usual install folder' }
        }
    }
    return $null
}

# --- the published desktop installer -------------------------------------------

# Where the desktop app looks for its own updates. Read out of the app's own
# configuration rather than written here, so this script and the app cannot
# disagree about where a release lives.
function Get-UpdateEndpoint($Repo) {
    $conf = Join-Path $Repo 'jarvis-desktop\src-tauri\tauri.conf.json'
    if (-not (Test-Path -LiteralPath $conf)) { return $null }
    try {
        $j = Get-Content -LiteralPath $conf -Raw | ConvertFrom-Json
        $ep = @($j.plugins.updater.endpoints)[0]
        if ($ep) { return "$ep" }
    } catch { }
    return $null
}

# The rolling release's small manifest (latest.json): the newest published
# desktop version, the installer's address, and its signature. $null when
# there is no release, or the PC cannot reach GitHub - which is a normal state,
# not a failure: the app is then built from this folder instead.
function Get-DesktopRelease($Endpoint) {
    if (-not $Endpoint) { return $null }
    try {
        $resp = Invoke-WebRequest -Uri $Endpoint -UseBasicParsing -TimeoutSec 20
    } catch {
        return $null
    }
    try {
        $m = $resp.Content | ConvertFrom-Json
    } catch {
        return $null
    }
    if (-not $m -or -not $m.version) { return $null }
    $entry = $null
    foreach ($k in @('windows-x86_64-nsis', 'windows-x86_64')) {
        $cand = $m.platforms.$k
        if ($cand -and $cand.url) { $entry = $cand; break }
    }
    if (-not $entry) { return $null }
    # An UNSIGNED release is refused here, deliberately: desktop-release.yml
    # publishes nothing without a signature, so a manifest entry with no
    # signature is not a published build. The app refuses one for the same
    # reason.
    if (-not $entry.signature) { return $null }
    try {
        $url = [Uri]"$($entry.url)"
    } catch {
        return $null
    }
    if ($url.Scheme -ne 'https') { return $null }
    # The installer must come from the same host the manifest did. A manifest
    # that points somewhere else is exactly the case the signature exists for,
    # and this script cannot check the signature - so it asks for the next best
    # thing: the file comes from where the project publishes it.
    try {
        $mine = [Uri]$Endpoint
        if ($url.Host -ne $mine.Host) { return $null }
    } catch {
        return $null
    }
    $commit = ''
    $mc = [regex]::Match("$($m.notes)", 'commit ([0-9a-fA-F]{7,40})')
    if ($mc.Success) { $commit = $mc.Groups[1].Value }
    return @{
        Version   = "$($m.version)"
        Url       = "$($entry.url)"
        Signature = "$($entry.signature)"
        Commit    = $commit
        Date      = "$($m.pub_date)"
    }
}

# Is the code in this folder at least as new as the release?
#
# The one case where downloading the published installer is WRONG: the folder
# holds a build made from work that is not in that release (the owner's own
# branch, or commits main does not have yet). Installing the release over it
# would replace newer code with older. `git merge-base --is-ancestor` answers
# it exactly: true means the release's commit is already in this folder's
# history, so this folder is the same or newer, and building is the right move.
# A folder with no .git (an unzipped download) cannot answer, and says so.
function Test-LocalAtLeastAsNew($Repo, $Commit) {
    if (-not $Commit) { return $false }
    if (-not (Test-Path -LiteralPath (Join-Path $Repo '.git'))) { return $false }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { return $false }
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $null = & git -C $Repo rev-parse --verify --quiet "$Commit^{commit}" 2>&1
        if ($LASTEXITCODE -ne 0) {
            # This PC does not have that commit at all, so the release is
            # ahead of this folder.
            return $false
        }
        $null = & git -C $Repo merge-base --is-ancestor $Commit HEAD 2>&1
        return ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $prev
    }
}

# Run an installer with no windows and no questions.
#
# /S is NSIS's silent switch, which the desktop app's own bundle accepts (its
# updater config uses /P, the same switch with a progress bar). The installer
# is a per-user one - it writes under your own %LOCALAPPDATA% - so this needs
# no administrator window.
function Invoke-SilentInstaller($Exe) {
    Info "installing it now - no clicks, usually under a minute"
    $p = $null
    try {
        $p = Start-Process -FilePath $Exe -ArgumentList '/S' -Wait -PassThru -ErrorAction Stop
    } catch {
        Bad "the installer could not be started: $($_.Exception.Message)"
        return $false
    }
    if (-not $p) { Bad 'the installer did not run'; return $false }
    if ($p.ExitCode -ne 0) {
        Bad "the installer exited with code $($p.ExitCode), so the app may not have been replaced"
        return $false
    }
    return $true
}

function Install-DesktopFromRelease($Release, [switch] $DryRun) {
    $leaf = Split-Path -Leaf ([Uri]$Release.Url).AbsolutePath
    if ($leaf -notmatch '\.exe$') {
        Bad "the release points at '$leaf', which is not an installer"
        return $false
    }
    if ($DryRun) {
        Info "would download $leaf (version $($Release.Version)) and install it silently"
        # The limit is named in the PLAN as well as in the real run. An owner who
        # does the careful thing and runs -Print first would otherwise not learn
        # it until the moment the file had already been installed - and this is
        # the one thing about this step that a person might want to decide on.
        Info "its signature would NOT be checked here (PowerShell has no minisign"
        Info "verifier, and the Tauri command line tool has no 'signer verify'); the"
        Info "SHA-256 would be printed instead. -FromSource builds instead."
        return $true
    }
    $dest = Join-Path ([IO.Path]::GetTempPath()) $leaf
    Info "downloading $leaf from the project's own release page"
    try {
        Invoke-WebRequest -Uri $Release.Url -OutFile $dest -UseBasicParsing -TimeoutSec 900
    } catch {
        Bad "the download failed: $($_.Exception.Message)"
        Info "the app was not changed; run this again, or add -FromSource to build it here"
        return $false
    }
    if (-not (Test-Path -LiteralPath $dest)) { Bad 'the download finished but no file was written'; return $false }
    $size = (Get-Item -LiteralPath $dest).Length
    $hash = (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash
    Ok ("downloaded {0:N1} MB" -f ($size / 1MB))
    Info "SHA-256 of what was downloaded: $hash"
    Info "the signature published beside it is NOT checked here - PowerShell has no"
    Info "minisign verifier, and the Tauri command line tool has no 'signer verify'."
    Info "This is the same file the download page offers; the app's own"
    Info "Settings -> Updates button is the route that checks a signature."
    if (-not (Invoke-SilentInstaller $dest)) { return $false }
    Ok "the desktop app was replaced with version $($Release.Version)"
    # The installer has run, so the copy in %TEMP% has done its job. Best
    # effort: a leftover file is not worth failing a finished update over.
    Remove-Item -LiteralPath $dest -Force -ErrorAction SilentlyContinue
    return $true
}

# --- building the desktop app here ---------------------------------------------

# Visual Studio's compiler is not on PATH in a normal PowerShell window, and
# Rust's MSVC toolchain needs it to link. vswhere finds the installation and
# vcvars64.bat sets the environment up; both are part of the Build Tools that
# docs\INSTALL.md step 2.1 installs. Best effort: when it cannot be found,
# nothing is broken yet - the build step says what actually went wrong.
function Import-VsEnvironment {
    if (Get-Command cl.exe -ErrorAction SilentlyContinue) { return $true }
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (-not (Test-Path -LiteralPath $vswhere)) { return $false }
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $inst = @(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null | Select-Object -First 1)
    } finally {
        $ErrorActionPreference = $prev
    }
    if (-not $inst) { return $false }
    $vcvars = Join-Path "$inst" 'VC\Auxiliary\Build\vcvars64.bat'
    if (-not (Test-Path -LiteralPath $vcvars)) { return $false }
    $lines = @()
    try {
        $lines = @(& cmd.exe /c "`"$vcvars`" >nul 2>&1 && set")
    } catch {
        return $false
    }
    foreach ($l in $lines) {
        $i = "$l".IndexOf('=')
        if ($i -lt 1) { continue }
        $name = "$l".Substring(0, $i)
        $val = "$l".Substring($i + 1)
        if ($name -match '^(PATH|INCLUDE|LIB|LIBPATH)$') {
            [Environment]::SetEnvironmentVariable($name, $val, 'Process')
        }
    }
    return [bool](Get-Command cl.exe -ErrorAction SilentlyContinue)
}

# What building here would need, in words that name the one command per gap.
function Test-BuildTools {
    $missing = @()
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { $missing += 'Node.js (winget install OpenJS.NodeJS.LTS)' }
    if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) { $missing += 'Rust (winget install Rustlang.Rustup)' }
    if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue) -and -not (Test-Path -LiteralPath (Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'))) {
        $missing += 'the C++ build tools (winget install Microsoft.VisualStudio.2022.BuildTools -e --override "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended")'
    }
    return $missing
}

function Build-AndInstallDesktop($Repo, [switch] $DryRun) {
    $dir = Join-Path $Repo 'jarvis-desktop'
    if (-not (Test-Path -LiteralPath (Join-Path $dir 'package.json'))) {
        Bad "there is no jarvis-desktop folder beside this script's repository folder"
        return $false
    }
    $missing = @(Test-BuildTools)
    if ($missing.Count -gt 0) {
        Bad "the desktop app cannot be built here - missing:"
        foreach ($m in $missing) { Say "          $m" Red }
        Info "install what is listed (one line, then a NEW PowerShell window), or add"
        Info "-FromSource later; the backend has been updated already."
        return $false
    }
    if ($DryRun) {
        Info "would run 'npm ci' and 'npm run tauri build' in $dir, then install the -setup.exe silently"
        Info "this is the slow part - several minutes"
        return $true
    }
    if (Import-VsEnvironment) { Ok "Visual Studio's build environment is loaded" }
    else { Warn "Visual Studio's compiler was not found on PATH; if the build fails to link, that is why" }

    Push-Location -LiteralPath $dir
    try {
        Info "running npm ci (a minute or two the first time)"
        if ((Invoke-Native 'npm' @('ci', '--no-audit', '--no-fund')) -ne 0) {
            Bad "npm ci failed - the app was not rebuilt"
            return $false
        }
        Info "building the app (several minutes; you can leave this window alone)"
        if ((Invoke-Native 'npm' @('run', 'tauri', 'build')) -ne 0) {
            Bad "the build failed - the app was not replaced"
            return $false
        }
    } finally {
        Pop-Location
    }
    $bundle = Join-Path $dir 'src-tauri\target\release\bundle\nsis'
    $setup = @(Get-ChildItem -LiteralPath $bundle -Filter '*-setup.exe' -ErrorAction SilentlyContinue |
               Sort-Object LastWriteTime -Descending | Select-Object -First 1)
    if ($setup.Count -eq 0) {
        Bad "the build finished but no installer was found in: $bundle"
        return $false
    }
    Ok "built $($setup[0].Name)"
    if (-not (Invoke-SilentInstaller $setup[0].FullName)) { return $false }
    Ok "the desktop app was replaced with the build from this folder"
    return $true
}

# --- the running backend --------------------------------------------------------

# Wait until something answers on the PC's own address, so the live check runs
# against a Jarvis that is actually up. The handshake answers 401 to a caller
# with no token, and that is still an answer.
function Wait-BackendUp {
    param([int] $Seconds = 45)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri 'http://127.0.0.1:4719/api/version' -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { return $true }
        } catch {
            $resp = $null
            try { $resp = $_.Exception.Response } catch { }
            if ($resp -and $resp.StatusCode) {
                $code = [int]$resp.StatusCode
                if ($code -ge 200 -and $code -lt 500) { return $true }
            }
        }
        Start-Sleep -Milliseconds 1500
    }
    return $false
}

# ===============================================================================
# The run
# ===============================================================================

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Stamp    = Get-Date -Format 'yyyy-MM-dd-HHmmss'
$Total    = 6

Say ""
Say "Jarvis update - the backend on this PC, and the desktop app, in one command"
Say ""

if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'apply-patches.ps1'))) {
    Bad "This script must sit in the repository's scripts folder."
    Say "  It updates by running scripts\apply-patches.ps1, which is not beside it." Cyan
    Say "  Run the copy of this file inside the folder you unzipped or cloned." Cyan
    Finish-Run 'stopped'
}

$script:InstallLine = 'powershell -ExecutionPolicy Bypass -File "' + (Join-Path $PSScriptRoot 'update-jarvis.ps1') + '"'

# --- 1. which folder is the backend -------------------------------------------
Step 1 $Total 'Finding the backend folder'

if (-not $BackendPath) {
    $stored = Get-StoredUserVariable 'JARVIS_BACKEND'
    if (-not $stored) { $stored = $env:JARVIS_BACKEND }
    if ($stored) {
        $BackendPath = "$stored".Trim()
        Ok "using the folder saved by install-backend.ps1:"
        Say "          $BackendPath"
    }
}
if (-not $BackendPath) {
    Bad "No backend folder is known, and none was given."
    if (Test-Path -LiteralPath (Join-Path $RepoRoot 'jarvis-backend\jarvis_hud.py')) {
        # This repository publishes the backend (jarvis-backend\), and the
        # folder is only absent when Jarvis has never been installed here - in
        # which case the install command is the right one, not this one.
        Say "  Jarvis does not look installed on this PC yet. Run the install command" Cyan
        Say "  first - it copies the published folder into place and patches it:" Cyan
        Say "      powershell -ExecutionPolicy Bypass -File .\scripts\setup-jarvis.ps1" Cyan
        Say "  Then this command updates both halves from then on." Cyan
        Finish-Run 'stopped'
    }
    Say "  Tell this PC once where jarvis_hud.py lives (one line, changes nothing" Cyan
    Say "  inside the folder), then run this again:" Cyan
    Say "      powershell -ExecutionPolicy Bypass -File .\scripts\install-backend.ps1 -BackendPath `"D:\your\backend\folder`"" Cyan
    Say "  Or name it on this command: ... update-jarvis.ps1 -BackendPath `"D:\your\backend\folder`"" Cyan
    Finish-Run 'stopped'
}
if (-not (Test-Path -LiteralPath $BackendPath)) {
    Bad "There is no folder at: $BackendPath"
    Finish-Run 'stopped'
}
if (-not (Test-Path -LiteralPath (Join-Path $BackendPath 'jarvis_hud.py'))) {
    Bad "That folder has no jarvis_hud.py in it, so it is not the backend folder:"
    Say "          $BackendPath" Red
    Say "  docs\INSTALL.md step 1.3 says which folder is the one." Cyan
    Finish-Run 'stopped'
}
$BackendPath = (Resolve-Path -LiteralPath $BackendPath).Path
Ok "backend: $BackendPath"
Ok "repository: $RepoRoot"

# A log of this run, beside apply-patches.ps1's own logs. -Print writes nothing
# anywhere, so it does not start one.
if (-not $Print) {
    try {
        $logDir = Join-Path $BackendPath '_jarvis-logs'
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        $script:RunLog = Join-Path $logDir "update-jarvis-$Stamp.txt"
        Start-Transcript -LiteralPath $script:RunLog -Append | Out-Null
    } catch {
        $script:RunLog = $null
    }
}
if ($Print) {
    Say ""
    Say "  -Print: this run will report the plan and change nothing." Yellow
}

# --- 2. the newest code --------------------------------------------------------
Step 2 $Total 'Getting the newest code'

# The scripts and patches that DO the update come from this folder. When it is
# a git checkout, pulling is the newest copy of them; when it is an unzipped
# download there is no git to pull, so the newest source is fetched from the
# project's own page into a temporary folder and used from there. Either way
# this only reads - the folder you are in is never rewritten.
$SourceRoot = $RepoRoot
$isGit = Test-Path -LiteralPath (Join-Path $RepoRoot '.git')
if ($isGit -and (Get-Command git -ErrorAction SilentlyContinue)) {
    if ($Print) {
        Info "would run: git pull (in $RepoRoot)"
    } else {
        Info "git pull (the code in this folder is what patches your backend)"
        $code = Invoke-Native 'git' @('-C', $RepoRoot, 'pull', '--ff-only')
        if ($code -ne 0) {
            Warn "git pull did not finish cleanly, so the code already in this folder is used"
            Info "that is what happens on a branch with local changes, or with no network"
        } else {
            Ok "this folder is up to date"
            # A git pull does rewrite files in this folder, so a run that stops
            # later must not claim nothing was touched.
            $script:Changed = $true
            Add-Note "this run updated the repository folder with git pull (your backend and apps were not touched by that)"
        }
    }
} elseif ($isGit) {
    Warn "this folder is a git checkout but git is not installed, so it cannot be updated"
    Info "winget install Git.Git -e    (then open a NEW PowerShell window)"
} else {
    # An unzipped download: no git, and the ZIP is the only way to get newer
    # patches. Fetched to a temporary folder and used from there, so the copy
    # you unzipped is left exactly as it is.
    $endpoint = Get-UpdateEndpoint $RepoRoot
    $zip = $null
    if ($endpoint) {
        $m = [regex]::Match($endpoint, '^https://([^/]+)/([^/]+)/([^/]+)/releases/')
        if ($m.Success) { $zip = "https://$($m.Groups[1].Value)/$($m.Groups[2].Value)/$($m.Groups[3].Value)/archive/refs/heads/main.zip" }
    }
    if (-not $zip) {
        Warn "this folder was unzipped rather than cloned, and the project's page could not be worked out"
        Info "the code already here is used; download the repository again to get newer patches"
    } elseif ($Print) {
        Info "would download the newest source from $zip into a temporary folder and patch from there"
    } else {
        # A name that cannot collide with another run's. NOT the date-and-time
        # stamp used for the log below: two runs started in the same second get
        # the same clock reading (Windows only moves it on the system timer
        # tick), and this folder is deleted at the end - so the second run would
        # delete the first run's copy while it was still patching from it. The
        # same trap is why scripts\apply-patches.ps1 names its rehearsal folder
        # per run (next-patcher-race), and tools\check_same_tick_paths.py reads
        # every *.ps1 for it.
        $unique = [Guid]::NewGuid().ToString('N').Substring(0, 12)
        $tmp = Join-Path ([IO.Path]::GetTempPath()) "jarvis-source-$unique"
        try {
            New-Item -ItemType Directory -Force -Path $tmp | Out-Null
            # Handed to Finish-Run, which is where every ending goes through, so
            # the copy is deleted after the patching and the live check have
            # finished reading it rather than now. (A comment here used to say it
            # was deleted and nothing deleted it.)
            $script:TempSource = $tmp
            $file = Join-Path $tmp 'source.zip'
            Info "downloading the newest source (this folder was unzipped, so there is no git pull)"
            Invoke-WebRequest -Uri $zip -OutFile $file -UseBasicParsing -TimeoutSec 600
            Expand-Archive -LiteralPath $file -DestinationPath (Join-Path $tmp 'unpacked') -Force
            $top = @(Get-ChildItem -LiteralPath (Join-Path $tmp 'unpacked') -Directory | Select-Object -First 1)
            if ($top.Count -eq 1 -and (Test-Path -LiteralPath (Join-Path $top[0].FullName 'scripts\apply-patches.ps1'))) {
                $SourceRoot = $top[0].FullName
                Ok "using the newest source from a temporary copy:"
                Say "          $SourceRoot"
            } else {
                Warn "the download did not look like this repository, so the copy already here is used"
            }
        } catch {
            Warn "the newest source could not be downloaded ($($_.Exception.Message))"
            Info "the code already here is used; download the repository again to get newer patches"
        }
    }
}

$apply = Join-Path $SourceRoot 'scripts\apply-patches.ps1'
if (-not $SkipPatches -and -not (Test-Path -LiteralPath $apply)) {
    Bad "there is no scripts\apply-patches.ps1 in the copy to patch from: $SourceRoot"
    Finish-Run 'stopped'
}

# --- 3. nothing may be using the backend while it is patched -------------------
Step 3 $Total 'Closing Jarvis'

$app = Get-DesktopApp
$running = @(Get-RunningBackend $BackendPath)
# Read once, here, because the answer decides whether the app is started again
# at the end - and by then this detection has already been re-run and found
# nothing running.
$script:AppWasRunning = [bool]$app

if ($app) { Ok "the desktop app is running (it will be closed, then started again)" }
if ($running.Count -eq 0 -and -not $app) { Ok "nothing is using the backend" }

if ($Print) {
    if ($app) { Info "would close the desktop app and any Jarvis it started" }
    if ($running.Count -gt 0) { foreach ($r in $running) { Info "would close $($r.What)" } }
} elseif ($app -or $running.Count -gt 0) {
    if ($Force) {
        foreach ($r in $running) {
            try { Stop-Process -Id $r.Id -Force -ErrorAction Stop; Ok "closed $($r.What)" }
            catch { Bad "could not close $($r.What): $($_.Exception.Message)" }
        }
        if ($app) {
            try { Stop-Process -Id $app.Id -Force -ErrorAction Stop; Ok "closed the desktop app" }
            catch { Bad "could not close the desktop app: $($_.Exception.Message)" }
        }
        Start-Sleep -Seconds 2
    } else {
        # Closing it FOR the owner would kill whatever answer was in flight, so
        # this waits instead - and it waits before anything has been changed,
        # which is why stopping here is free.
        Say ""
        Say "  Jarvis has to be closed while the update is applied - it holds the files" Yellow
        Say "  the patches change. Please close it now:" Yellow
        if ($app) { Say "      desktop app: right-click its tray icon, then 'Quit Jarvis'" Yellow }
        if ($running.Count -gt 0) { Say "      or the PowerShell window running jarvis_hud.py" Yellow }
        Say "  Waiting up to 90 seconds for that..." Yellow
        $deadline = (Get-Date).AddSeconds(90)
        while ((Get-Date) -lt $deadline) {
            Start-Sleep -Seconds 3
            $app = Get-DesktopApp
            $running = @(Get-RunningBackend $BackendPath)
            if (-not $app -and $running.Count -eq 0) { break }
        }
        if ($app -or $running.Count -gt 0) {
            Bad "Jarvis is still running, so the update has not started."
            Say "  Close it, then run this command again. Or add  -Force  and this will" Cyan
            Say "  close it for you (anything it was doing at that moment is cut off)." Cyan
            Add-Problem 'Jarvis was still running, so the update did not start.'
            Finish-Run 'stopped'
        }
        Ok "closed - carrying on"
    }
    $app = Get-DesktopApp
    $running = @(Get-RunningBackend $BackendPath)
    if ($app -or $running.Count -gt 0) {
        Bad "something is still using the backend folder after closing:"
        if ($app) { Say "          the desktop app is still running" Red }
        foreach ($r in $running) { Say "          $($r.What)" Red }
        Add-Problem 'Something was still using the backend folder, so the update did not start.'
        Finish-Run 'stopped'
    }
}

# --- 4. patch the backend ------------------------------------------------------
Step 4 $Total 'Patching the backend'

$applyArgs = @('-BackendPath', $BackendPath)
if ($SkipTests) { $applyArgs += '-SkipTests' }

if ($SkipPatches) {
    # Only scripts\setup-jarvis.ps1 uses this: it ran apply-patches.ps1 itself a
    # moment ago and calls this script for the desktop half, so the patcher is
    # not run a second time - a second run rehearses all 121 patches again for
    # no new information.
    Warn "the backend was left as it is (-SkipPatches): apply-patches.ps1 is not run here"
} elseif ($Print) {
    Info "would run: powershell -ExecutionPolicy Bypass -File `"$apply`" $($applyArgs -join ' ')"
    Info "apply-patches.ps1 rehearses every patch on a copy first, backs your files up,"
    Info "and changes nothing at all if any patch would not apply."
} else {
    Info "running apply-patches.ps1 (it rehearses every patch on a copy first)"
    Say ""
    # From here on this run may have changed the backend's files, and that has
    # to be said even when the patcher exits non-zero - which is the ORDINARY
    # case of "every patch went on, then a test suite failed" (apply-patches.ps1
    # applies first and tests afterwards). Setting this only on success is how
    # the closing screen came to say "Nothing on your PC was changed" about a
    # backend that had just been patched.
    $script:Changed = $true
    $code = Invoke-Native 'powershell' (@('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $apply) + $applyArgs)
    Say ""
    if ($code -ne 0) {
        # The desktop app is NOT touched: it is a client of this backend, and
        # updating it against a backend that just failed would be the one
        # combination that cannot work.
        Bad "apply-patches.ps1 exited $code - read its own last screen above"
        Info "that can mean two different things, and its own screen says which: it"
        Info "refused and changed nothing, or it put the patches on and a test failed."
        Info "Do not start Jarvis until that screen has been read; if it says the files"
        Info "may be half updated, paste the restore line it printed."
        Add-Problem "the backend update did not finish cleanly (apply-patches.ps1 exited $code) - its own screen above says whether any file was changed"
        Restart-AppIfWeClosedIt
        Finish-Run
    }
    Ok "the backend was patched (details and the log are in apply-patches.ps1's own output)"
}

# --- 5. the desktop app --------------------------------------------------------
Step 5 $Total 'Updating the desktop app'

$installed = Get-InstalledDesktop
if ($installed) {
    if ($installed.Version) { Ok "desktop app installed: version $($installed.Version) ($($installed.Where))" }
    else { Ok "desktop app found ($($installed.Where))" }
} else {
    Warn "the desktop app does not look installed on this PC"
}

$desktopDone = $false
if ($SkipDesktop) {
    Warn "the desktop app was left alone (-SkipDesktop)"
    $script:DesktopState = 'skipped'
} else {
    $release = $null
    if ($FromSource) {
        Warn "building from this folder (-FromSource), so the published installer is not used"
    } else {
        $endpoint = Get-UpdateEndpoint $RepoRoot
        if (-not $endpoint) {
            Warn "this repository's copy of the desktop app names no update address"
        } else {
            if ($Print) {
                # Said out loud, because it is the one thing a plan run does over
                # the network: -Print changes nothing, but it does read this one
                # small file so the plan can say which route it would take.
                Info "asking the release page for the newest desktop version (a read, not a download)"
            }
            $release = Get-DesktopRelease $endpoint
            if (-not $release) {
                Warn "no published desktop installer was found (or GitHub was not reachable)"
                Info "that is normal before the update signing key is set up - see docs\INSTALL.md,"
                Info "'The desktop installer, and the update signing key'"
            } else {
                Ok "published desktop version: $($release.Version)"
                if ($release.Commit -and (Test-LocalAtLeastAsNew $RepoRoot $release.Commit)) {
                    Info "this folder already holds $($release.Commit) or newer (your own build), so"
                    Info "installing that release over it would go backwards - building instead"
                    $release = $null
                } elseif ($release.Commit -and -not (Test-Path -LiteralPath (Join-Path $RepoRoot '.git'))) {
                    # The comparison above needs git history, and an unzipped
                    # download has none. Saying so is the difference between "this
                    # release is newer" and "I cannot tell" - the second one is
                    # what is true here, and a folder holding newer code than the
                    # release would otherwise be quietly replaced by it.
                    Warn "this folder is not a git checkout, so I cannot tell whether it is newer"
                    Info "than published version $($release.Version). Installing the published one;"
                    Info "add -FromSource to build this folder's own copy instead"
                }
            }
        }
    }

    if ($FromSource -or -not $release) {
        $desktopDone = Build-AndInstallDesktop $RepoRoot -DryRun:$Print
    } else {
        $desktopDone = Install-DesktopFromRelease $release -DryRun:$Print
    }
    if (-not $Print) {
        if ($desktopDone) {
            $script:Changed = $true
            $script:DesktopState = 'done'
        } else {
            $script:DesktopState = 'failed'
            Add-Note 'the desktop app was NOT updated - the backend was. Read the lines above.'
        }
    }
}

# --- 6. start it again, and check it -------------------------------------------
Step 6 $Total 'Starting Jarvis and checking it'

if ($Print) {
    if ($script:AppWasRunning -or $installed) { Info "would start the desktop app again" }
    if ($NoCheck) { Info "would not wait for Jarvis or run the live check (-NoCheck)" }
    else { Info "would wait for Jarvis to answer, then run backend\selftest.py --preflight" }
} else {
    $started = $false
    # Re-read, rather than deciding from the version read before the install: on
    # a FIRST install the app did not exist then, so `$installed` is $null and
    # this branch used to be skipped - the app was installed and never started.
    $again = Get-InstalledDesktop
    if ($script:AppWasRunning -or ($desktopDone -and $again)) {
        if ($again -and $again.Exe) {
            try {
                Start-Process -FilePath $again.Exe | Out-Null
                $started = $true
                Ok "started the desktop app"
            } catch {
                Warn "the desktop app could not be started automatically: $($_.Exception.Message)"
            }
        }
    }
    if (-not $started) {
        if ($again -and $again.Exe) {
            Info "start it with: `"$($again.Exe)`""
        } else {
            Info "start Jarvis Desktop from the Start menu (tray icon, then 'Show or hide the Jarvis bar')"
        }
    }

    if ($NoCheck) {
        # Nothing is going to look at the backend, so there is no reason to sit
        # here for 45 seconds waiting for it to answer.
        Warn "the live check was skipped (-NoCheck), so this did not wait for Jarvis to answer"
    } else {
        if (Wait-BackendUp -Seconds 45) {
            Ok "Jarvis is answering on this PC"
        } else {
            Warn "Jarvis is not answering on 127.0.0.1:4719 yet"
            Info "the desktop app starts it when 'Let Jarvis Desktop start and stop Jarvis' is on;"
            Info "docs\INSTALL.md step 1.8 starts it by hand"
        }
        $py = Find-Python
        $selftest = Join-Path $SourceRoot 'backend\selftest.py'
        if (-not $py) {
            Warn "no working Python was found, so the live check was not run"
        } elseif (-not (Test-Path -LiteralPath $selftest)) {
            Warn "backend\selftest.py was not found, so the live check was not run"
        } else {
            Say ""
            Say "Running the live check (it changes nothing). It ends with 'N pass, N fail, N warn'." Cyan
            Say ""
            $env:JARVIS_BACKEND = $BackendPath
            $env:PYTHONIOENCODING = 'utf-8'
            $preflightOut = $null
            if ($script:RunLog) {
                $preflightOut = Join-Path (Split-Path -Parent $script:RunLog) "preflight-$Stamp.txt"
            }
            $prev = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                if ($preflightOut) {
                    & $py.Exe $selftest --preflight 2>&1 | Tee-Object -FilePath $preflightOut
                } else {
                    & $py.Exe $selftest --preflight 2>&1
                }
                $code = $LASTEXITCODE
            } finally {
                $ErrorActionPreference = $prev
            }
            if ($preflightOut) { Info "the check's output is saved in: $preflightOut" }
            if ($code -ne 0) {
                Add-Note "the live check above reported failures (exit $code). The update itself finished; each FAIL line says what to do."
            } else {
                Ok "the live check finished with no failures"
            }
        }
    }
}

if ($Print) { Finish-Run 'print' } else { Finish-Run 'done' }
