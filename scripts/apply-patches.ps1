<#
.SYNOPSIS
  Apply every backend patch to your OpenJarvis folder, then run the tests.

.DESCRIPTION
  backend/README.md used to say "git apply this, then this, ... and so on, in
  table order" — twenty patches, in a required order, with a backup step you
  had to remember. That is a bad thing to ask of anyone, and the failure mode
  is the worst kind: patch eleven fails and you are left half-applied, with no
  record of which half.

  This does the whole thing, and it will not leave you half-applied:

    1. Backs up every file that is about to be touched, into a timestamped
       folder, before anything is written.
    2. DRY-RUNS all twenty first. If any one of them would fail, it stops
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

.PARAMETER SkipMissing
  Leave out any patch that needs a backend file which is not there, and apply
  the rest. A PARTIAL install: the features those patches carry will not be
  present. Only use it once you have looked for the missing files and they
  really are gone - the script prints the command to search for them.

.EXAMPLE
  .\scripts\apply-patches.ps1
  .\scripts\apply-patches.ps1 -BackendPath "D:\jarvis"
  .\scripts\apply-patches.ps1 -SkipMissing
  .\scripts\apply-patches.ps1 -Revert
#>

[CmdletBinding()]
param(
    [string] $BackendPath = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program",
    [switch] $Revert,
    [switch] $SkipTests,
    [switch] $SkipMissing
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
    # After memory-noise: its context is that patch's dedupe rewrite (the
    # 'pending','rejected' query) and memory-safety's queue_full() field.
    'decide-once.patch'
    'event-allowlist.patch'
    # Last: it rewrites `pending()` and `_push` in jarvis_gate.py, which
    # gate-outcome and no-auto-approve have already edited, and the
    # doorbell copy in jarvis_events.py that event-allowlist wrote. Its
    # context lines are their output, so it cannot go earlier.
    'approval-notice.patch'
    # Textually independent of everything above - it only ADDS new entries
    # to two dictionaries in jarvis_gate.py, touching no line any other
    # patch here touches. Listed last for readability, not because order
    # matters for this one.
    'ui-control-wiring.patch'
    # Also independent - touches jarvis_hud.py's /api/chat, but a different
    # few lines than degrade-filter or any other patch that lands there.
    'ollama-direct.patch'
    # Textually independent of ollama-direct too, but listed right after it:
    # a tool-enabled local turn only makes sense once the local lane is
    # actually reaching Ollama.
    'tool-calling-wiring.patch'
    # Its context lines are token-file's output (the token banner and the
    # line above HUD_TOKEN), which nothing after token-file touches. Last so
    # a backend that already has everything above takes only this.
    'loopback-too.patch'
    # After all of them. Its jarvis_extract.py context is the output of
    # memory-safety, memory-noise and decide-once (the dedupe lines, the
    # full-queue counter, setup_status's dropped_full block and the file's
    # last function), and its jarvis_hud.py context is the learner and call
    # site extraction-wiring wrote and the memory block memory-pane wrote.
    # It needs backend\jarvis_intake.py copied into the backend folder too;
    # without it every hook falls back to the old behaviour.
    'memory-intake.patch'
)

# --- the six patches whose fixes are already IN the rebuilt modules --------
#
# Ten of the backend's twenty-six modules were rebuilt after the originals were
# found to exist nowhere, and two of them - jarvis_memory and jarvis_events -
# were rebuilt WITH the fixes these patches make. So on a backend carrying the
# rebuilt modules, six patches cannot apply: their context lines are the
# unfixed code, which no longer exists.
#
# That is correct and expected, and the script still refused the whole run over
# it, applying none of the other fifteen. The owner was blocked by a state this
# repository created.
#
# Four of the six ALSO patch a surviving file, and that half is still needed.
# backend/rebuilt-patches/ holds those halves, split by target file. The other
# two touch only a rebuilt module and are skipped entirely.
$REBUILT_SUPERSEDES = @{
    'memory-safety.patch'     = 'jarvis_memory.py, already in the rebuild'
    'extraction-wiring.patch' = 'jarvis_events.py, already in the rebuild'
    'bitemporal.patch'        = 'jarvis_memory.py, already in the rebuild'
    'embedding-guard.patch'   = 'jarvis_memory.py only - nothing else to apply'
    'event-allowlist.patch'   = 'jarvis_events.py only - nothing else to apply'
    'approval-notice.patch'   = 'jarvis_events.py, already in the rebuild'
}

$RepoRoot   = Split-Path -Parent $PSScriptRoot
$PatchDir   = Join-Path $RepoRoot 'backend'
$Stamp      = Get-Date -Format 'yyyy-MM-dd-HHmmss'

# The list above is hand-ordered because the order matters, which means it can
# fall behind the directory - and it did: event-allowlist.patch was written,
# documented in backend/README.md, and never added here, so it silently did
# not get applied. A missing patch produces no error anywhere; it just is not
# there. Checked on every run.
# Is this backend carrying the rebuilt modules? Detected by a marker the
# rebuild puts in its own docstring, not by a version number nobody maintains.
$SplitDir = Join-Path $PatchDir 'rebuilt-patches'
$UsingRebuilt = $false
$memPath = Join-Path $BackendPath 'jarvis_memory.py'
if (Test-Path -LiteralPath $memPath) {
    $head = Get-Content -LiteralPath $memPath -TotalCount 12 -ErrorAction SilentlyContinue
    if ($head -join "`n" -match 'PART RECOVERED, PART REBUILT') { $UsingRebuilt = $true }
}

$onDisk = @(Get-ChildItem -LiteralPath $PatchDir -Filter '*.patch' -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty Name)
$unlisted = @($onDisk | Where-Object { $PATCHES -notcontains $_ })
if ($unlisted.Count -gt 0) {
    Write-Host "  FAIL  $($unlisted.Count) patch file(s) exist but are not in this script's list:" -ForegroundColor Red
    foreach ($u in $unlisted) { Write-Host "          $u" -ForegroundColor Red }
    Write-Host "        Add them to `$PATCHES, in the right place - the order is a" -ForegroundColor Cyan
    Write-Host "        dependency order, not alphabetical. See backend/README.md." -ForegroundColor Cyan
    exit 1
}

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

# --- substitute the split patches, if the rebuilt modules are installed ------
if ($UsingRebuilt) {
    $swapped = @()
    foreach ($name in $PATCHES) {
        if (-not $REBUILT_SUPERSEDES.ContainsKey($name)) { $swapped += $name; continue }
        $half = Join-Path $SplitDir $name
        if (Test-Path -LiteralPath $half) {
            $swapped += "rebuilt-patches\$name"
        }
        # else: the whole patch is superseded, so it is simply left out.
    }
    $PATCHES = $swapped
}

# --- line endings ------------------------------------------------------------
#
# A unified diff's context lines must match the target byte for byte, so CRLF
# on either side breaks every hunk of every patch at once. `git apply` reports
# it as "patch does not apply", which sends you looking for a wrong patch.
# There are two sides and they are handled differently.
#
# THE PATCH FILES - fixed here, silently, every run.
#
# This cost a whole run of twenty. The patches are LF in the repository, but a
# Windows clone with the default `core.autocrlf=true` writes them to disk as
# CRLF, and `.gitattributes` (which says `*.patch -text`) does NOT retroactively
# rewrite files that were already checked out before it existed. So a clone
# made last week still has CRLF patches today, `git checkout -- .` does not
# touch them, and all twenty fail with an error that names none of this.
#
# Rather than ask anyone to fix their working tree, every patch is copied to a
# temp folder with its endings forced to LF and the copy is what gets applied.
# Nothing in the repository or the backend is rewritten. It is correct on a
# machine where the files were already LF, so there is no case to detect.
$LfDir = Join-Path ([IO.Path]::GetTempPath()) "jarvis-patches-lf-$Stamp"
New-Item -ItemType Directory -Path $LfDir -Force | Out-Null
$crlfPatches = 0
foreach ($name in $PATCHES) {
    $src = Join-Path $PatchDir $name
    if (-not (Test-Path -LiteralPath $src)) { continue }
    $flat = Split-Path -Leaf $name
    # Byte-level. Get-Content/Set-Content would re-encode, and a patch can
    # carry any bytes its target carries.
    $raw = [IO.File]::ReadAllBytes($src)
    $out = New-Object 'System.Collections.Generic.List[byte]'
    for ($i = 0; $i -lt $raw.Length; $i++) {
        # Drop a CR only when it is part of CRLF. A bare CR inside a line is
        # content and stays.
        if ($raw[$i] -eq 13 -and $i + 1 -lt $raw.Length -and $raw[$i + 1] -eq 10) {
            $crlfPatches++
            continue
        }
        $out.Add($raw[$i])
    }
    [IO.File]::WriteAllBytes((Join-Path $LfDir $flat), $out.ToArray())
}
# Everything that applies a patch reads from here, never from $PatchDir.
$PatchSrc = $LfDir
if ($crlfPatches -gt 0) {
    Say "Endings : normalised $crlfPatches CRLF line(s) to LF in a temp copy of" Yellow
    Say "          the patches (your files are untouched - that is git's" Yellow
    Say "          autocrlf having written them that way, not anything you did)" Yellow
}

# THE BACKEND FILES - reported, never fixed. Rewriting someone's source to
# make a patch fit is a much bigger thing to do silently than it looks.
$probe = Join-Path $BackendPath 'jarvis_hud.py'
if (Test-Path -LiteralPath $probe) {
    $bytes = [IO.File]::ReadAllBytes($probe)
    $crlf = 0
    for ($i = 1; $i -lt $bytes.Length; $i++) {
        if ($bytes[$i] -eq 10 -and $bytes[$i - 1] -eq 13) { $crlf++ }
    }
    $lf = 0
    foreach ($b in $bytes) { if ($b -eq 10) { $lf++ } }
    if ($crlf -gt 0) {
        Say "Endings : jarvis_hud.py has $crlf CRLF line(s) of $lf" Yellow
        Say "          The patches are LF. If they will not apply, THIS is why," Yellow
        Say "          not a wrong patch. Say so and it gets handled properly." Yellow
    } else {
        Say "Endings : LF, which is what the patches expect"
    }
}
Say ""

# --- how to run one patch ----------------------------------------------------

function Invoke-Patch {
    param([string] $File, [switch] $Check, [switch] $Reverse)

    # `$ErrorActionPreference = 'Stop'` at the top of this file turns ANY
    # stderr output from a native program into a terminating error - even when
    # the program succeeded. `git apply --verbose` writes "Checking patch
    # jarvis_memory.py..." to stderr on every single call, so the first check
    # killed the script with a NativeCommandError and nineteen patches never
    # got looked at.
    #
    # Relaxed here and restored in the finally, rather than globally: the Stop
    # preference is doing real work elsewhere in this file, where a failed
    # Copy-Item must not be shrugged off before the backup is complete.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {

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

    } finally {
        $ErrorActionPreference = $prev
    }
    return @{ Ok = ($LASTEXITCODE -eq 0); Output = ($out | Out-String).Trim() }
}

# --- does the backend actually have the files the patches name? --------------
#
# `git apply` answers a missing target with "error: <name>: No such file or
# directory", one line, inside the output of the patch that wanted it. With
# twenty patches failing for a different reason at the same time, that line is
# unfindable - and it is the only one that is not about line endings. Asked
# once, up front, in words.
$wanted = @{}
foreach ($name in $PATCHES) {
    $src = Join-Path $PatchSrc $name
    if (-not (Test-Path -LiteralPath $src)) { continue }
    foreach ($line in (Get-Content -LiteralPath $src)) {
        if ($line -match '^\+\+\+ b/(.+)$') {
            $t = $Matches[1].Trim()
            if (-not $wanted.ContainsKey($t)) { $wanted[$t] = @() }
            $wanted[$t] += $name
        }
    }
}
$absent = @($wanted.Keys | Where-Object {
    -not (Test-Path -LiteralPath (Join-Path $BackendPath $_))
} | Sort-Object)

if ($absent.Count -gt 0) {
    # Which patches are actually stopped by this, and which are not. A patch
    # is blocked if ANY file it touches is missing - there is no applying half
    # of one. Worth separating, because "two files are missing" reads like the
    # whole run is lost when in fact most of it is fine.
    $blocked = @{}
    foreach ($a in $absent) { foreach ($n in $wanted[$a]) { $blocked[$n] = $true } }
    $clear = @($PATCHES | Where-Object { -not $blocked.ContainsKey($_) })

    Say ""
    Bad "$($absent.Count) file(s) the patches expect are not in your backend folder:"
    foreach ($a in $absent) {
        Say "          $a   (wanted by $($wanted[$a] -join ', '))" Red
    }
    Say ""
    Say "That folder is: $BackendPath" Cyan
    Say ""
    Say "$($blocked.Count) patch(es) are stopped by this. $($clear.Count) are not." Cyan
    Say ""
    Say "Find the missing files first - this searches your whole user folder:" Cyan
    foreach ($a in $absent) {
        Say "    Get-ChildItem `$env:USERPROFILE -Filter $a -Recurse -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName" Cyan
    }
    Say ""
    Say "If they turn up somewhere else, that folder is your backend - pass it" Cyan
    Say "with -BackendPath. If they are genuinely gone, you can apply the" Cyan
    Say "$($clear.Count) that do not need them:" Cyan
    Say "    .\scripts\apply-patches.ps1 -SkipMissing" Cyan

    if (-not $SkipMissing) {
        Say ""
        Say "NOTHING HAS BEEN CHANGED." Yellow
        exit 1
    }

    # -SkipMissing is safe to offer because it changes nothing about how the
    # decision is made: the shortened stack still has to apply cleanly to a
    # throwaway copy before a real file is opened. If dropping these six
    # breaks the ones below them - and it may, because several share a file
    # and so share context - the rehearsal says so and the run stops there.
    Say ""
    Say "-SkipMissing: leaving out $($blocked.Count), rehearsing the other $($clear.Count)." Yellow
    Say "  Left out:" Yellow
    foreach ($n in $PATCHES) { if ($blocked.ContainsKey($n)) { Say "    $n" Yellow } }
    Say ""
    Say "  This is a PARTIAL install. The features those patches carry will not" Yellow
    Say "  be there, and backend/README.md says what each one was for." Yellow
    $PATCHES = $clear
    if ($PATCHES.Count -eq 0) {
        Bad "Nothing is left to apply."
        exit 1
    }
}

Push-Location -LiteralPath $BackendPath
try {

    # --- revert ---------------------------------------------------------------
    if ($Revert) {
        Say "Removing patches, newest first." Cyan
        $removed = 0
        $backwards = @($PATCHES); [array]::Reverse($backwards)
        foreach ($name in $backwards) {
            $full = Join-Path $PatchSrc (Split-Path -Leaf $name)
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

    # --- 1. rehearse the WHOLE STACK on a copy -------------------------------
    #
    # Two earlier versions of this got it wrong in the same way, from opposite
    # directions, and both times the cause was treating a STACK as a SET.
    #
    # v1 ran `git apply --check` on each patch against the unpatched tree and
    # refused to start if any failed. bitemporal edits code memory-safety
    # wrote, so it cannot apply to a pristine backend and never could: the
    # check could only ever report failures that were not real.
    #
    # v2 applied them in order to a copy - right - but decided "already
    # applied?" per patch, by reverse-checking it alone. That fails too:
    # memory-safety cannot be reversed out of a tree that has bitemporal on
    # top of it, because bitemporal rewrote its context. Running the script
    # twice reported six phantom failures.
    #
    # So the question is asked about the whole stack, never about one patch:
    #
    #   Does the ENTIRE stack reverse cleanly?  -> already applied, nothing to do
    #   Does the ENTIRE stack apply cleanly?    -> go ahead for real
    #   Neither                                 -> say so and touch nothing
    #
    # Both rehearsals run on a throwaway copy, so the real files are not
    # opened until an answer is known.
    $rehearsal = Join-Path ([IO.Path]::GetTempPath()) "jarvis-rehearsal-$Stamp"
    $broken    = @()
    $already   = $false

    function Reset-Rehearsal {
        if (Test-Path -LiteralPath $rehearsal) {
            Remove-Item -LiteralPath $rehearsal -Recurse -Force
        }
        New-Item -ItemType Directory -Path $rehearsal -Force | Out-Null
        Copy-Item -Path (Join-Path $BackendPath '*.py') -Destination $rehearsal -Force
    }

    try {
        # (a) is it already patched? Reverse the stack, newest first.
        Reset-Rehearsal
        Push-Location -LiteralPath $rehearsal
        $reversedAll = $true
        $backwards = @($PATCHES); [array]::Reverse($backwards)
        foreach ($name in $backwards) {
            $full = Join-Path $PatchSrc (Split-Path -Leaf $name)
            if (-not (Test-Path -LiteralPath $full)) { $reversedAll = $false; break }
            if (-not (Invoke-Patch -File $full -Reverse).Ok) { $reversedAll = $false; break }
        }
        Pop-Location

        if ($reversedAll) {
            $already = $true
            Say ""
            Ok "All $($PATCHES.Count) patches are already applied. Nothing to do."
        }
        else {
            # (b) will the stack apply? Forward, in order.
            Say "Rehearsing all $($PATCHES.Count) on a copy first." Cyan
            Reset-Rehearsal
            Push-Location -LiteralPath $rehearsal
            foreach ($name in $PATCHES) {
                $full = Join-Path $PatchSrc (Split-Path -Leaf $name)
                if (-not (Test-Path -LiteralPath $full)) {
                    $broken += @{ Name = $name; Why = "missing from $PatchDir" }
                    Bad "$name - not found"
                    continue
                }
                $r = Invoke-Patch -File $full
                if ($r.Ok) { Say "  ok           $name" }
                else {
                    $broken += @{ Name = $name; Why = $r.Output }
                    Bad "$name - will not apply"
                }
            }
            Pop-Location
        }
    } finally {
        Remove-Item -LiteralPath $rehearsal -Recurse -Force -ErrorAction SilentlyContinue
    }

    if ($broken.Count -gt 0) {
        Say ""
        Bad "$($broken.Count) patch(es) will not apply. NOTHING HAS BEEN CHANGED."
        Say "(The rehearsal ran on a copy. Your backend was never opened.)" Cyan
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

    if ($already) {
        if ($SkipTests) { exit 0 }
        Say ""
    }

    # --- 2. back up, then apply ----------------------------------------------
    if (-not $already) {
        $todo = @($PATCHES | ForEach-Object { Join-Path $PatchSrc (Split-Path -Leaf $_) })
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
    # The LF copies were only ever an intermediate. Leaving twenty patch files
    # in %TEMP% after every run is the kind of litter nobody notices until a
    # disk is full.
    Remove-Item -LiteralPath $LfDir -Recurse -Force -ErrorAction SilentlyContinue
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

# THE ONE THING THAT MAKES THESE RUNNABLE HERE AT ALL.
#
# The suites live in this repository; the modules they test live in the
# owner's backend folder. Until _where.py existed they used one path for both,
# so they only ran in the dev container where the modules are symlinked in -
# and this script would have run them anyway and produced eighteen import
# errors that look exactly like the patches having broken something.
#
# _where.py reads JARVIS_BACKEND for the modules and derives the repo from its
# own location, so both roots are right at once.
$env:JARVIS_BACKEND = (Resolve-Path -LiteralPath $BackendPath).Path

$tests = Get-ChildItem -LiteralPath $PatchDir -Filter 'test_*.py' | Sort-Object Name
$pass = 0; $fail = @()

# Same trap as Invoke-Patch: a test that prints anything to stderr - which a
# failing one does, and several passing ones do too - would terminate the run
# rather than be reported as a failure.
$prev = $ErrorActionPreference
$ErrorActionPreference = 'Continue'

foreach ($t in $tests) {
    $out = & $python.Source $t.FullName 2>&1
    if ($LASTEXITCODE -eq 0) { Ok $t.Name; $pass++ }
    else {
        Bad $t.Name
        $fail += @{ Name = $t.Name; Output = ($out | Out-String).Trim() }
    }
}

$ErrorActionPreference = $prev

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
    Say "Send the block above back. A failing suite here is a real finding." Cyan
    Say "" 
    Say "These suites do NOT run in CI - CI builds the desktop app, and the" Cyan
    Say "Python backend is not in the repository, so there is nothing there" Cyan
    Say "for them to run against. Your machine is the first place they meet" Cyan
    Say "the real modules. A failure means the backend here differs from the" Cyan
    Say "one the patches were written against, or that a rebuilt module is" Cyan
    Say "wrong - and the second one has happened." Cyan
    exit 1
}
