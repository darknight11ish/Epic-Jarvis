<#
.SYNOPSIS
  Test the two decisions in scripts\update-jarvis.ps1 that a real update got
  wrong, without running an update of any kind.

.DESCRIPTION
  Nothing here patches a backend, closes an app, downloads a file or installs
  anything. The functions under test are lifted out of the updater AS IT IS
  WRITTEN (the same technique the CI powershell-5 job uses) and called directly
  against synthetic inputs:

    1. The release page's reply. GitHub serves latest.json with the Content-Type
       application/octet-stream, so Invoke-WebRequest hands back a Byte[], not
       text (measured 2026-10-30: both Windows PowerShell 5.1 and 7, 4159
       bytes). A Byte[] piped into ConvertFrom-Json is unrolled into one
       pipeline item per byte, nothing parses, and the caller quietly built
       from source instead of downloading the signed release. The reply is fed
       here BOTH ways - as text and as bytes - and each must give the same
       release, which must then take the download route.

       Invoke-WebRequest itself is replaced by a function of the same name:
       PowerShell resolves a function before a cmdlet, so the updater's own
       call lands here and no network is touched.

    2. The ancestry gate. `Test-LocalAtLeastAsNew` (before the fix) returned
       TRUE for a release commit that was merely IN this folder's history,
       which included the case where the release commit IS HEAD - and its
       caller read TRUE as "build from source". So a folder standing on the
       release's own commit rebuilt instead of installing the signed release
       that is that exact code. `Get-LocalVsRelease` answers five ways instead,
       and every one is asserted below against a real throwaway git repository:
       same, release-ahead, local-ahead (the newer local build that must not be
       downgraded), dirty (standing on the release's commit with uncommitted
       work on top of it, which a build from this folder would include and the
       release would silently replace; DEF-020, 2026-10-31) and unknown
       (unrelated histories, or no git at all).

.PARAMETER Script
  The updater to test. Defaults to update-jarvis.ps1 beside this file. Point it
  at a COPY of an older script to see the tests fail on it - which is how the
  fix was shown to bite, not just to pass.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-update-jarvis.ps1

.EXAMPLE
  pwsh -NoProfile -File .\scripts\test-update-jarvis.ps1 -Script .\old-update-jarvis.ps1
#>

[CmdletBinding()]
param(
    [string] $Script = ''
)

$ErrorActionPreference = 'Stop'

if (-not $Script) { $Script = Join-Path $PSScriptRoot 'update-jarvis.ps1' }
if (-not (Test-Path -LiteralPath $Script)) {
    Write-Host "  FAIL  there is no updater at: $Script" -ForegroundColor Red
    exit 1
}
$Script = (Resolve-Path -LiteralPath $Script).Path

$script:Passed = 0
$script:Failed = 0
$script:Said = New-Object System.Collections.ArrayList

# The updater's own four words, captured instead of printed. Only the lifted
# functions call these.
function Say($msg, $colour = 'Gray') { [void]$script:Said.Add([string]$msg) }
function Ok($msg)   { [void]$script:Said.Add([string]$msg) }
function Warn($msg) { [void]$script:Said.Add([string]$msg) }
function Bad($msg)  { [void]$script:Said.Add([string]$msg) }
function Info($msg) { [void]$script:Said.Add([string]$msg) }

# Every result is printed, and a test that did NOT run is counted as a failure,
# never as a pass (the project's BLOCKED-is-never-a-pass rule).
function Assert-That {
    param([bool] $Ok, [string] $What, [string] $Detail = '')
    if ($Ok) {
        $script:Passed++
        Write-Host "  ok    $What" -ForegroundColor Green
    } else {
        $script:Failed++
        Write-Host "  FAIL  $What" -ForegroundColor Red
        if ($Detail) { Write-Host "        $Detail" -ForegroundColor Red }
    }
}

# Run git, throw on a non-zero exit, and give back its lines as an array.
# EAP is loosened around the call for the reason CLAUDE.md records: git writes
# progress to stderr, and 'Stop' would turn that into a terminating error.
function Invoke-Git {
    param([string] $Repo, [string[]] $Arguments)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $lines = @(& git -C $Repo @Arguments 2>&1)
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
    if ($code -ne 0) {
        throw ("git " + ($Arguments -join ' ') + " exited $code : " + (@($lines) -join ' / '))
    }
    return @($lines | ForEach-Object { "$_" })
}

# Lift one function out of the updater exactly as it is written. The closing
# brace is at column 0 in this file's style, so the first line that is only "}"
# ends the function - which is why the pattern can stop there.
function Get-ScriptFunction {
    param([string] $Text, [string] $Name)
    $m = [regex]::Match($Text, '(?s)function ' + [regex]::Escape($Name) + '[\s(].*?\n\}')
    if (-not $m.Success) { return '' }
    return $m.Value
}

$text = Get-Content -LiteralPath $Script -Raw

Write-Host ""
Write-Host "Testing: $Script" -ForegroundColor Cyan
Write-Host ""

# --- the release page's reply --------------------------------------------------

# The one network call the release reader makes, replaced. A function and not a
# mock library: PowerShell resolves a function before a cmdlet of the same name,
# so Get-DesktopRelease's `Invoke-WebRequest` lands here. $script:Reply is a
# String in one test and a Byte[] in the other, which is the whole point.
function Invoke-WebRequest {
    param($Uri, [switch] $UseBasicParsing, $TimeoutSec, $OutFile)
    if ($OutFile) { throw 'these tests never download a real file' }
    $script:ReplyServed = [string]$Uri
    return [pscustomobject]@{ Content = $script:Reply; StatusCode = 200 }
}

$script:Reply = $null
$script:ReplyServed = ''

foreach ($name in @('Get-ReleaseReplyText', 'Get-DesktopRelease', 'Install-DesktopFromRelease')) {
    $body = Get-ScriptFunction $text $name
    if (-not $body) {
        if ($name -eq 'Get-ReleaseReplyText') {
            # The pre-fix script has no such function; it is only needed by the
            # fixed Get-DesktopRelease, so its absence is reported with the
            # byte test below rather than as its own failure.
            continue
        }
        Assert-That $false "the updater has $name" 'not run: the function is missing, so nothing below could be tested'
        continue
    }
    Invoke-Expression $body
}

$endpoint = 'https://github.com/epic-jarvis/test/releases/download/desktop-latest/latest.json'

# A made-up manifest in the real shape: two platform entries (the NSIS one is
# the one the updater prefers), a signature, and the commit in the notes.
$json = @'
{
  "version": "9.9.9",
  "notes": "Jarvis Desktop 9.9.9, from commit abcdef1 on main.\n\n- a made-up change",
  "pub_date": "2026-10-30T00:00:00Z",
  "platforms": {
    "windows-x86_64": {
      "signature": "c2lnbmF0dXJlLXBsYWlu",
      "url": "https://github.com/epic-jarvis/test/releases/download/desktop-latest/jarvis-desktop_9.9.9_x64.exe"
    },
    "windows-x86_64-nsis": {
      "signature": "c2lnbmF0dXJlLW5zaXM=",
      "url": "https://github.com/epic-jarvis/test/releases/download/desktop-latest/jarvis-desktop_9.9.9_x64-setup.exe"
    }
  }
}
'@

function Get-ServedRelease {
    param($Reply)
    $script:Reply = $Reply
    $script:ReplyServed = ''
    $got = @(Get-DesktopRelease $endpoint)
    if ($got.Count -eq 0) { return $null }
    return $got[0]
}

$textRelease = Get-ServedRelease $json
Assert-That ($null -ne $textRelease) 'a TEXT reply is read as a release'
Assert-That ($null -ne $textRelease -and $textRelease.Version -eq '9.9.9') 'the text reply names version 9.9.9'
Assert-That ($null -ne $textRelease -and $textRelease.Url -like '*-setup.exe') 'the NSIS installer is preferred over the plain one'
Assert-That ($null -ne $textRelease -and $textRelease.Signature) 'the text reply carries the signature'
Assert-That ($null -ne $textRelease -and $textRelease.Commit -eq 'abcdef1') 'the commit is read out of the notes'

$bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
$byteRelease = Get-ServedRelease $bytes
Assert-That ($null -ne $byteRelease) 'a BYTE[] reply is read as a release (the shape the real release page sends)'
Assert-That ($null -ne $byteRelease -and $byteRelease.Version -eq '9.9.9') 'the byte reply names version 9.9.9'
Assert-That ($null -ne $byteRelease -and $null -ne $textRelease -and $byteRelease.Url -eq $textRelease.Url) 'text and bytes give the same installer address'
Assert-That ($null -ne $byteRelease -and $null -ne $textRelease -and $byteRelease.Signature -eq $textRelease.Signature) 'text and bytes give the same signature'
Assert-That ($null -ne $byteRelease -and $null -ne $textRelease -and $byteRelease.Commit -eq $textRelease.Commit) 'text and bytes give the same commit'

# The route the caller takes for a release it has: `if (-not $release) build
# else install`. -DryRun prints the plan and returns before any download, so
# this proves the download route is reachable from a parsed reply without
# touching the network or the owner's app.
foreach ($case in @(
    @{ Name = 'TEXT'; Release = $textRelease },
    @{ Name = 'BYTE[]'; Release = $byteRelease })) {
    $routeOk = $false
    $spoken = ''
    if ($null -ne $case.Release) {
        # NOT $said: PowerShell variable names are case-insensitive, so a local
        # named $said would overwrite the $script:Said ArrayList above.
        [void]$script:Said.Clear()
        $routeOk = (Install-DesktopFromRelease $case.Release $PSScriptRoot -DryRun) -eq $true
        $spoken = (@($script:Said) -join ' ')
    }
    Assert-That $routeOk "a $($case.Name) reply takes the download route (the signed release, not a build)"
    Assert-That ($spoken -match 'would download jarvis-desktop_9\.9\.9_x64-setup\.exe') "a $($case.Name) reply says it would download the installer"
}

# --- the ancestry gate ---------------------------------------------------------

$script:HaveAncestry = $false
$ancestry = Get-ScriptFunction $text 'Get-LocalVsRelease'
if ($ancestry) {
    Invoke-Expression $ancestry
    $script:HaveAncestry = $true
} else {
    Assert-That $false 'the updater has Get-LocalVsRelease (it can tell "same" from "moved past")' 'not run: the function is missing - this IS the old defect, where an equal release commit was read as "build from source"'
}

# DEF-020: the "dirty" answer is only worth anything if the CALLER acts on it,
# says why, and leaves untracked files alone. Pinned as source, because the
# answer is computed by the lifted function above and used by top-level code
# that cannot be lifted without running an update.
Assert-That ($text -match '\$where -eq ''dirty''') 'the updater builds on the new "dirty" answer'
Assert-That ($text -match 'has uncommitted') 'the updater says why a dirty folder is built instead'
Assert-That ($text -match 'status --porcelain --untracked-files=no') 'the dirty check leaves untracked files out on purpose'

function Assert-Placement {
    param($Repo, $Commit, [string] $Want, [string] $What)
    if (-not $script:HaveAncestry) {
        Assert-That $false $What 'not run: the script has no Get-LocalVsRelease, so this case cannot be asked'
        return
    }
    $got = Get-LocalVsRelease $Repo $Commit
    Assert-That ($got -eq $Want) $What "expected '$Want', got '$got'"
}

# A throwaway repository. A GUID in the name, never a clock reading: two runs
# started in the same second must not take each other's folder (the rule
# tools/check_same_tick_paths.py enforces).
$root = Join-Path ([IO.Path]::GetTempPath()) ('jarvis-update-test-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $root | Out-Null
try {
    $ident = @('-c', 'user.email=t@example.invalid', '-c', 'user.name=t')

    $repo = Join-Path $root 'repo'
    New-Item -ItemType Directory -Force -Path $repo | Out-Null
    [void](Invoke-Git $repo @('init', '-q'))
    Set-Content -LiteralPath (Join-Path $repo 'a.txt') -Value 'first'
    [void](Invoke-Git $repo @('add', '-A'))
    [void](Invoke-Git $repo ($ident + @('commit', '-qm', 'first')))
    $first = @(Invoke-Git $repo @('rev-parse', 'HEAD'))[0]
    $base = @(Invoke-Git $repo @('rev-parse', '--abbrev-ref', 'HEAD'))[0]

    Set-Content -LiteralPath (Join-Path $repo 'b.txt') -Value 'second'
    [void](Invoke-Git $repo @('add', '-A'))
    [void](Invoke-Git $repo ($ident + @('commit', '-qm', 'second')))
    $second = @(Invoke-Git $repo @('rev-parse', 'HEAD'))[0]

    # A commit that exists in this repository but is NOT in this branch: the
    # release was cut from a branch this folder has not got.
    [void](Invoke-Git $repo @('checkout', '-q', '-b', 'side'))
    Set-Content -LiteralPath (Join-Path $repo 'c.txt') -Value 'on the side branch'
    [void](Invoke-Git $repo @('add', '-A'))
    [void](Invoke-Git $repo ($ident + @('commit', '-qm', 'side')))
    $side = @(Invoke-Git $repo @('rev-parse', 'HEAD'))[0]
    [void](Invoke-Git $repo @('checkout', '-q', $base))
    if ((@(Invoke-Git $repo @('rev-parse', 'HEAD'))[0]) -ne $second) { throw 'the test repository did not go back to its second commit' }

    # A commit in this repository from an UNRELATED history: its objects are
    # here, but it shares no ancestor with HEAD. Made as an ORPHAN branch in
    # this repository rather than fetched from a second one: it is the same
    # shape and needs no second repository - a local `git fetch` runs
    # git-upload-pack through sh, which a restricted desk can refuse (Win32
    # error 5, "couldn't create signal pipe"), and this test must run at the
    # desk as well as in CI.
    [void](Invoke-Git $repo @('checkout', '-q', '--orphan', 'unrelated'))
    Set-Content -LiteralPath (Join-Path $repo 'x.txt') -Value 'unrelated'
    [void](Invoke-Git $repo @('add', '-A'))
    [void](Invoke-Git $repo ($ident + @('commit', '-qm', 'unrelated')))
    $unrelated = @(Invoke-Git $repo @('rev-parse', 'HEAD'))[0]
    [void](Invoke-Git $repo @('checkout', '-q', $base))

    $notARepo = Join-Path $root 'not-a-repo'
    New-Item -ItemType Directory -Force -Path $notARepo | Out-Null

    Assert-Placement $repo $second 'same' 'a release commit that IS HEAD: use the signed release (no rebuild)'

    # DEF-020 (fixed 2026-10-31): the COMMIT being equal is not the FILES being
    # equal. A tracked file changed but not committed means a build from this
    # folder is not the released code, and installing the release over it would
    # silently replace the work - so it must build, not install.
    Set-Content -LiteralPath (Join-Path $repo 'a.txt') -Value 'uncommitted newer work'
    Assert-Placement $repo $second 'dirty' 'a folder standing on the release commit with uncommitted work: build, do not replace it'
    [void](Invoke-Git $repo @('add', 'a.txt'))
    Assert-Placement $repo $second 'dirty' '... and a change that is only staged still counts'
    [void](Invoke-Git $repo (@('reset', '-q', '--hard', 'HEAD')))
    # Untracked files are build output and scratch, and a build does not ship
    # them: --untracked-files=no means one alone leaves the folder AT the
    # release, so the signed release is still the right route.
    Set-Content -LiteralPath (Join-Path $repo 'build-output.tmp') -Value 'scratch'
    Assert-Placement $repo $second 'same' '... while an untracked file alone does not count (it is not in the build)'
    Remove-Item -LiteralPath (Join-Path $repo 'build-output.tmp') -Force
    Assert-Placement $repo $second 'same' 'the release commit with nothing changed is the release again'

    Assert-Placement $repo $first 'local-ahead' 'a release commit this folder has moved past: keep the local build, do not downgrade'
    Assert-Placement $repo $side 'release-ahead' 'a release commit on a branch this folder is not on: update from the release'
    Assert-Placement $repo '0123456789abcdef0123456789abcdef01234567' 'release-ahead' 'a release commit this folder has never seen: update from the release'
    Assert-Placement $repo $unrelated 'unknown' 'a release commit from an unrelated history: cannot tell, so install and say so'
    Assert-Placement $notARepo $second 'unknown' 'a folder that is not a git checkout: cannot tell'
    Assert-Placement $repo '' 'unknown' 'a release that names no commit: cannot tell'
} finally {
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "$($script:Passed) passed, $($script:Failed) failed" -ForegroundColor Cyan
if ($script:Failed -gt 0) { exit 1 }
exit 0
