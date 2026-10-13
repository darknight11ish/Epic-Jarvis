#Requires -Version 5.1
<#
.SYNOPSIS
  Free disk space by removing ONLY regenerable Rust build output (target
  directories) inside this repository's .dsh-scratch worktrees.

.DESCRIPTION
  WHY THIS EXISTS. On 2026-10-13 C: reached 1.47 GB free of 476 GB and a
  `git worktree add` died with "No space left on device". The cause was
  structural, not a one-off: this repository is worked in about 180 git
  worktrees under .dsh-scratch (a worktree is a second checkout of the code,
  on another branch), and each one keeps its own Rust build directory at
  jarvis-desktop/src-tauri/target. Those add up to tens of GB, and they refill
  with every build. The same drive holds the owner's voice print, chat history
  and settings under .openjarvis, so a full system drive is a durability
  problem as well as a space one.

  WHAT IT REMOVES: directories named exactly `target` that sit under
  .dsh-scratch. Cargo regenerates every one of them from source; nothing in
  them is the only copy of anything.

  WHAT IT NEVER TOUCHES, deliberately:
    * source of any kind - only a directory whose own name is `target` is ever
      considered, and nothing inside it is inspected before removal;
    * node_modules (teammates' test runs depend on them being warm), .git, and
      every worktree checkout itself;
    * anything at all outside .dsh-scratch - including this repository's own
      jarvis-desktop/src-tauri/target, which is not under .dsh-scratch and is
      therefore never a candidate;
    * junctions and symlinks: a `target` that is a link is refused, never
      followed and never deleted.

  DRY RUN BY DEFAULT. It prints what it WOULD remove and the space it would
  free, and removes nothing unless -Clean is given. An irreversible bulk
  delete should take a deliberate second action.

  THE GUARDS, all checked before anything is removed, and each one is reported:
    1. the folder's own name must be exactly `target`;
    2. the full path must be under .dsh-scratch;
    3. it must be a directory;
    4. it must not be a junction or a symlink;
    5. cargo, rustc or link must not be running - deleting a build directory
       mid-build corrupts it. (clippy-driver and rustdoc run as children of
       cargo, so a running cargo covers them too.)
  A guard that refuses exits with code 2 and removes nothing.

.PARAMETER Clean
  Actually remove the directories. Without it, this is a dry run.

.PARAMETER Root
  The repository root to work in. Defaults to the repository this script is
  in (the parent of the folder holding the script).

.PARAMETER Inspect
  Check ONE path through the same guards and report the verdict, then stop.
  This never removes anything; it is how the guards are proved to refuse.

.PARAMETER MaxDepth
  How deep under .dsh-scratch a `target` may be found. The normal shape is
  .dsh-scratch/<worktree>/jarvis-desktop/src-tauri/target, which is 4.

.EXAMPLE
  # dry run, from anywhere, one line:
  powershell -NoProfile -ExecutionPolicy Bypass -File "<repo>\tools\clean-worktree-targets.ps1"

.EXAMPLE
  # the same, actually removing:
  powershell -NoProfile -ExecutionPolicy Bypass -File "<repo>\tools\clean-worktree-targets.ps1" -Clean

.EXAMPLE
  # prove a guard refuses (exit code 2, removes nothing):
  powershell -NoProfile -ExecutionPolicy Bypass -File "<repo>\tools\clean-worktree-targets.ps1" -Inspect "<repo>\somewhere\not-target"
#>
[CmdletBinding()]
param(
    [switch]$Clean,
    [string]$Root = '',
    [string]$Inspect = '',
    [int]$MaxDepth = 4
)

$ErrorActionPreference = 'Stop'

#: Exit codes. 0 = it did what was asked (dry run or clean). 2 = a guard
#: refused, and nothing was removed. 1 = something else went wrong.
$EXIT_OK = 0
$EXIT_GUARD = 2

function Write-Bytes {
    param([long]$Bytes)
    if ($Bytes -ge 1073741824) { return ('{0:N2} GB' -f ($Bytes / 1073741824.0)) }
    if ($Bytes -ge 1048576) { return ('{0:N1} MB' -f ($Bytes / 1048576.0)) }
    if ($Bytes -ge 1024) { return ('{0:N0} KB' -f ($Bytes / 1024.0)) }
    return "$Bytes bytes"
}

function Get-FreeSpace {
    param([string]$Path)
    try {
        $root = [System.IO.Path]::GetPathRoot([System.IO.Path]::GetFullPath($Path))
        $drive = New-Object System.IO.DriveInfo($root)
        return [long]$drive.AvailableFreeSpace
    } catch {
        return [long]-1
    }
}

function Get-FolderBytes {
    # Every file under one directory, summed. EnumerateFiles with
    # AllDirectories is used rather than Get-ChildItem because a build
    # directory holds hundreds of thousands of files and this runs over
    # dozens of them.
    param([string]$Path)
    $total = [long]0
    try {
        $files = [System.IO.Directory]::EnumerateFiles($Path, '*', [System.IO.SearchOption]::AllDirectories)
        foreach ($f in $files) {
            try {
                $total += [long](New-Object System.IO.FileInfo($f)).Length
            } catch {
                # A file that cannot be read is left out of the total rather
                # than failing the run; the directory must still be removable.
            }
        }
    } catch {
        # Same for a directory that cannot be walked.
    }
    return $total
}

function Test-DirIsLink {
    param([string]$Path)
    try {
        $attrs = [System.IO.File]::GetAttributes($Path)
        return (($attrs -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)
    } catch {
        return $true
    }
}

function Test-Candidate {
    # THE GUARDS, in one place, used by both the sweep and -Inspect. Returns
    # a hashtable: Ok true/false and the sentence to print when it refuses.
    param([string]$Path, [string]$ScratchFull)

    $full = ''
    try {
        $full = [System.IO.Path]::GetFullPath($Path)
    } catch {
        return @{ Ok = $false; Why = "the path could not be resolved: $Path"; Full = $Path }
    }

    $leaf = [System.IO.Path]::GetFileName($full.TrimEnd('\'))
    if ($leaf -ne 'target') {
        return @{ Ok = $false; Full = $full
                  Why = "the folder is named '$leaf', not 'target' - only Rust build output is ever removed" }
    }

    $prefix = $ScratchFull.TrimEnd('\') + '\'
    if (-not $full.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        return @{ Ok = $false; Full = $full
                  Why = "the path is not under $ScratchFull - nothing outside the worktree scratch folder is touched" }
    }

    if (-not (Test-Path -LiteralPath $full -PathType Container)) {
        return @{ Ok = $false; Full = $full; Why = 'it is not a directory (or it no longer exists)' }
    }

    if (Test-DirIsLink -Path $full) {
        return @{ Ok = $false; Full = $full
                  Why = 'it is a junction or a symlink, which this tool never follows and never deletes' }
    }

    return @{ Ok = $true; Why = ''; Full = $full }
}

function Get-BuildProcesses {
    # cargo, rustc and link - the three that write into a target directory.
    # `link` is the MSVC linker cargo invokes for the last step of a build.
    $found = @()
    foreach ($name in @('cargo', 'rustc', 'link')) {
        $procs = @(Get-Process -Name $name -ErrorAction SilentlyContinue)
        foreach ($p in $procs) {
            $found += ("{0} (pid {1})" -f $p.ProcessName, $p.Id)
        }
    }
    return $found
}

function Get-TargetDirs {
    # Every directory under the scratch folder whose own name is exactly
    # `target`, down to MaxDepth. Junctions and symlinks are never descended
    # into, and a `target` directory is not descended into either - there is
    # nothing under it worth the walk.
    param([string]$Scratch, [int]$Depth)

    $found = New-Object System.Collections.ArrayList
    $queue = New-Object System.Collections.Queue
    $queue.Enqueue(@{ Path = $Scratch; Level = 0 })

    while ($queue.Count -gt 0) {
        $item = $queue.Dequeue()
        $children = @()
        try {
            $children = @([System.IO.Directory]::EnumerateDirectories($item.Path))
        } catch {
            continue
        }
        foreach ($child in $children) {
            $name = [System.IO.Path]::GetFileName($child.TrimEnd('\'))
            if ($name -eq 'target') {
                # Collected whether or not it is a link, so that a link is
                # REFUSED and reported rather than silently skipped. Nothing
                # is ever descended into.
                [void]$found.Add($child)
                continue
            }
            if (Test-DirIsLink -Path $child) {
                continue
            }
            if (($item.Level + 1) -lt $Depth) {
                $queue.Enqueue(@{ Path = $child; Level = $item.Level + 1 })
            }
        }
    }
    return $found
}

function Find-RepoRoot {
    # THE MAIN CHECKOUT, not the worktree this script happens to sit in.
    # A worktree has no .dsh-scratch of its own (its .git is a FILE pointing
    # at the main repository), so "the parent of the script's folder" is the
    # wrong answer the moment this tool is run from inside a worktree - which
    # is exactly where it is run from. Walk up until a folder has a
    # .dsh-scratch folder of its own, or a .git DIRECTORY (the main
    # checkout), and stop there.
    param([string]$Start)

    $dir = $Start
    while ($dir -ne '' -and $dir -ne $null) {
        if (Test-Path -LiteralPath (Join-Path $dir '.dsh-scratch') -PathType Container) {
            return $dir
        }
        if (Test-Path -LiteralPath (Join-Path $dir '.git') -PathType Container) {
            return $dir
        }
        $parent = Split-Path -Parent $dir
        if ($parent -eq $dir -or $parent -eq '') {
            break
        }
        $dir = $parent
    }
    return ''
}

# ---------------------------------------------------------------------------
# Where we are
# ---------------------------------------------------------------------------

if ($Root -ne '') {
    $rootPath = $Root
} else {
    if ($PSScriptRoot -eq '') {
        Write-Host "ERROR: the script's own folder could not be found; pass -Root." -ForegroundColor Red
        exit 1
    }
    $rootPath = Find-RepoRoot -Start $PSScriptRoot
    if ($rootPath -eq '') {
        Write-Host "ERROR: could not find the repository root above $PSScriptRoot." -ForegroundColor Red
        Write-Host "       Pass it yourself:  -Root `"C:\path\to\Epic-Jarvis-main`"" -ForegroundColor Red
        exit 1
    }
}

if (-not (Test-Path -LiteralPath $rootPath -PathType Container)) {
    Write-Host "ERROR: the repository root does not exist: $rootPath" -ForegroundColor Red
    exit 1
}
$rootFull = [System.IO.Path]::GetFullPath($rootPath)
$scratch = Join-Path $rootFull '.dsh-scratch'
$scratchFull = [System.IO.Path]::GetFullPath($scratch)

Write-Host ""
Write-Host "Jarvis worktree build-output cleanup"
Write-Host "  repository : $rootFull"
Write-Host "  only under : $scratchFull"
if ($Clean) {
    Write-Host "  mode       : CLEAN - directories will be REMOVED" -ForegroundColor Yellow
} else {
    Write-Host "  mode       : dry run - NOTHING will be removed (add -Clean to remove)"
}

# ---------------------------------------------------------------------------
# -Inspect: one path, the same guards, and never a removal.
# It runs BEFORE the .dsh-scratch check, because a path that is not under
# .dsh-scratch is one of the things it exists to refuse.
# ---------------------------------------------------------------------------

if ($Inspect -ne '') {
    $verdict = Test-Candidate -Path $Inspect -ScratchFull $scratchFull
    Write-Host ""
    Write-Host "  inspecting : $($verdict.Full)"
    if ($verdict.Ok) {
        Write-Host "  verdict    : PASSES every guard - this WOULD be a candidate" -ForegroundColor Green
        Write-Host "               (-Inspect never removes anything; run without -Inspect for the list)"
        Write-Host "Exit code $EXIT_OK."
        exit $EXIT_OK
    }
    Write-Host "REFUSED: $($verdict.Why)" -ForegroundColor Red
    Write-Host "Nothing was removed. Exit code $EXIT_GUARD."
    exit $EXIT_GUARD
}

if (-not (Test-Path -LiteralPath $scratchFull -PathType Container)) {
    Write-Host ""
    Write-Host "REFUSED: there is no .dsh-scratch folder under that root, so there is nothing" -ForegroundColor Red
    Write-Host "         this tool is allowed to touch." -ForegroundColor Red
    Write-Host "Nothing was removed. Exit code $EXIT_GUARD."
    exit $EXIT_GUARD
}

# ---------------------------------------------------------------------------
# Guard: no build may be running
# ---------------------------------------------------------------------------

$builds = Get-BuildProcesses
if ($builds.Count -gt 0) {
    Write-Host ""
    Write-Host "REFUSED: a Rust build is running, and removing a build directory under it" -ForegroundColor Red
    Write-Host "         would corrupt that build:" -ForegroundColor Red
    foreach ($b in $builds) {
        Write-Host "           $b"
    }
    Write-Host ""
    Write-Host "Nothing was removed. Wait for the build to finish and run this again."
    Write-Host "Exit code $EXIT_GUARD."
    exit $EXIT_GUARD
}
Write-Host "  guard      : no cargo, rustc or link is running - OK"

# ---------------------------------------------------------------------------
# The candidates
# ---------------------------------------------------------------------------

$freeBefore = Get-FreeSpace -Path $rootFull
$candidates = Get-TargetDirs -Scratch $scratchFull -Depth $MaxDepth

$usable = New-Object System.Collections.ArrayList
$refused = New-Object System.Collections.ArrayList
foreach ($c in $candidates) {
    $verdict = Test-Candidate -Path $c -ScratchFull $scratchFull
    if ($verdict.Ok) {
        [void]$usable.Add($verdict.Full)
    } else {
        [void]$refused.Add($verdict)
    }
}

Write-Host ""
if ($usable.Count -eq 0) {
    Write-Host "No target directories found under .dsh-scratch - nothing to do."
} else {
    Write-Host "$($usable.Count) target director$(if ($usable.Count -eq 1) { 'y' } else { 'ies' }) found:"
    $totalBytes = [long]0
    foreach ($dir in $usable) {
        $bytes = Get-FolderBytes -Path $dir
        $totalBytes += $bytes
        $short = $dir
        if ($short.StartsWith($scratchFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            $short = '.dsh-scratch' + $short.Substring($scratchFull.Length)
        }
        Write-Host ("  {0,10}  {1}" -f (Write-Bytes -Bytes $bytes), $short)
    }
    Write-Host ""
    Write-Host "  total      : $(Write-Bytes -Bytes $totalBytes)"
}

if ($refused.Count -gt 0) {
    Write-Host ""
    Write-Host "REFUSED by a guard, and left alone:" -ForegroundColor Yellow
    foreach ($r in $refused) {
        Write-Host "  $($r.Full)"
        Write-Host "    $($r.Why)"
    }
}

if ($freeBefore -ge 0) {
    Write-Host ""
    Write-Host "  free before: $(Write-Bytes -Bytes $freeBefore)"
}

# ---------------------------------------------------------------------------
# Do it, or say what would have been done
# ---------------------------------------------------------------------------

if ($usable.Count -eq 0) {
    Write-Host ""
    Write-Host "Nothing was written anywhere: this run only read the disk."
    Write-Host "Exit code $EXIT_OK."
    exit $EXIT_OK
}

if (-not $Clean) {
    Write-Host ""
    Write-Host "DRY RUN - nothing was removed, and nothing was written anywhere." -ForegroundColor Yellow
    Write-Host "To remove these $($usable.Count) directories, run the same one line with -Clean:" -ForegroundColor Yellow
    Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`" -Clean"
    Write-Host "Exit code $EXIT_OK."
    exit $EXIT_OK
}

Write-Host ""
Write-Host "Removing..." -ForegroundColor Yellow
$removed = 0
$failed = New-Object System.Collections.ArrayList
foreach ($dir in $usable) {
    try {
        Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction Stop
        $removed++
    } catch {
        [void]$failed.Add("$dir - $($_.Exception.Message)")
    }
}

$freeAfter = Get-FreeSpace -Path $rootFull
Write-Host ""
Write-Host "Removed $removed of $($usable.Count) director$(if ($usable.Count -eq 1) { 'y' } else { 'ies' })."
foreach ($f in $failed) {
    Write-Host "  could not remove: $f" -ForegroundColor Red
}
if ($freeBefore -ge 0 -and $freeAfter -ge 0) {
    Write-Host "  free before: $(Write-Bytes -Bytes $freeBefore)"
    Write-Host "  free after : $(Write-Bytes -Bytes $freeAfter)"
    $gained = $freeAfter - $freeBefore
    if ($gained -gt 0) {
        Write-Host "  freed      : $(Write-Bytes -Bytes $gained)" -ForegroundColor Green
    }
}
Write-Host ""
Write-Host "The only thing this run wrote was the removal of the directories listed above."
Write-Host "Nothing else was touched: no source, no node_modules, no .git, no worktree itself."
if ($failed.Count -gt 0) {
    Write-Host "Exit code 1: $($failed.Count) director$(if ($failed.Count -eq 1) { 'y' } else { 'ies' }) could not be removed." -ForegroundColor Red
    exit 1
}
Write-Host "Exit code $EXIT_OK."
exit $EXIT_OK
