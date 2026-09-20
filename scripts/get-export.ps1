<#
.SYNOPSIS
  Download every file a Claude data-export manifest points at, and check each
  one arrived intact.

.DESCRIPTION
  A Claude export does not hand you your conversations. It hands you a
  `manifest-....json` a kilobyte long, listing five archives and a one-time URL
  for each. The manifest says it plainly:

      "Each export URL can only be used once."

  That sentence is why this script exists rather than five clicks.

  A download that succeeds cannot be redone, so every file is verified the
  moment it lands and then kept: if something later goes wrong reading them,
  nothing is fetched twice.

  Verified means checked, not assumed. A link that is spent, but still
  reachable, answers with an HTML page rather than an error - and that saves
  perfectly happily as `conversations-000.zip`, then fails much later as "the
  archive is corrupt", which sends you to look at the archive. So each file is
  opened and its first two bytes read: a real zip starts `PK`.

  THE BIG CAVEAT, learned by running this. These URLs sit behind your claude.ai
  login. PowerShell has none of your browser's cookies, so all five answered
  403 Forbidden - refused at the door, before any download. That is NOT a spent
  link, and an earlier version of this script announced that it was, which is a
  frightening thing to be told about data you cannot get back and was never
  something it could know. On a 403 it now says so and prints the URLs to open
  in the browser instead.

  All five are downloaded, not just the conversations. They are all one-use, a
  second export means a second wait, and the missing modules could as easily be
  in a Project as in a chat.

.PARAMETER Manifest
  The manifest JSON. Defaults to the newest `manifest-*` in your Downloads.

.PARAMETER OutDir
  Where the archives go. Defaults to Downloads\claude-export.

.EXAMPLE
  .\scripts\get-export.ps1
#>

[CmdletBinding()]
param(
    [string] $Manifest,
    [string] $OutDir
)

$ErrorActionPreference = 'Stop'

function Say($msg, $colour = 'Gray') { Write-Host $msg -ForegroundColor $colour }
function Ok($msg)   { Write-Host "  ok    $msg" -ForegroundColor Green }
function Bad($msg)  { Write-Host "  FAIL  $msg" -ForegroundColor Red }

# --- find the manifest -------------------------------------------------------

if (-not $Manifest) {
    $found = Get-ChildItem (Join-Path $env:USERPROFILE 'Downloads') -Filter 'manifest-*' -ErrorAction SilentlyContinue |
             Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $found) {
        Bad "No manifest-* file in your Downloads folder."
        Say "  Request one: claude.ai -> Settings -> Privacy -> Export data" Cyan
        Say "  Then pass it: .\scripts\get-export.ps1 -Manifest `"C:\path\to\manifest.json`"" Cyan
        exit 1
    }
    $Manifest = $found.FullName
}
if (-not (Test-Path -LiteralPath $Manifest)) {
    Bad "No file at: $Manifest"
    exit 1
}

# utf-8-sig would be wrong here - this file is served by claude.ai, not written
# by PowerShell, so it has no BOM. Get-Content -Raw handles it.
try {
    $m = Get-Content -LiteralPath $Manifest -Raw | ConvertFrom-Json
} catch {
    Bad "That file is not readable JSON: $($_.Exception.Message)"
    exit 1
}
if (-not $m.data_files) {
    Bad "No 'data_files' in that manifest - is it the right file?"
    exit 1
}

if (-not $OutDir) { $OutDir = Join-Path $env:USERPROFILE 'Downloads\claude-export' }
if (-not (Test-Path -LiteralPath $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
}

# PowerShell 5.1 still defaults to TLS 1.0, which claude.ai will not accept.
# Without this the first request fails with "the underlying connection was
# closed" - and that failure still spends the one-time link.
try {
    [Net.ServicePointManager]::SecurityProtocol =
        [Net.SecurityProtocolType]::Tls12 -bor [Net.ServicePointManager]::SecurityProtocol
} catch { }

Say ""
Say "Manifest : $Manifest"
Say "Created  : $($m.created_at)"
Say "Saving to: $OutDir"
Say ""
Say "THESE LINKS WORK ONCE EACH, so a download that SUCCEEDS cannot be redone." Yellow
Say "A request refused at the door - 403, not signed in - does not spend one." Yellow
Say ""

function Test-Zip([string] $path) {
    <#
      Does this file begin with PK? Every zip does.

      A spent or signed-out link does not return an error status - it returns
      an HTML page, and Invoke-WebRequest saves that quite happily under the
      name you asked for. Without this check the failure surfaces much later
      as "the archive is corrupt", which sends you looking at the archive.
    #>
    try {
        $fs = [IO.File]::OpenRead($path)
        try {
            $b = New-Object byte[] 2
            if ($fs.Read($b, 0, 2) -lt 2) { return $false }
            return ($b[0] -eq 0x50 -and $b[1] -eq 0x4B)
        } finally { $fs.Close() }
    } catch { return $false }
}

$good = @(); $bad = @(); $forbidden = 0

foreach ($f in $m.data_files) {
    $name = $f.filename
    if (-not $name) { $name = "part-$($f.batch_index).zip" }
    $dest = Join-Path $OutDir $name

    if ((Test-Path -LiteralPath $dest) -and (Test-Zip $dest)) {
        Ok "$name already downloaded, left alone"
        $good += $dest
        continue
    }

    Say "  ...   $name"
    try {
        Invoke-WebRequest -Uri $f.export_url -OutFile $dest -UseBasicParsing -TimeoutSec 600
    } catch {
        $code = $null
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        Bad "$name - $($_.Exception.Message)"
        if ($code -eq 403) { $forbidden++ }
        $bad += $name
        continue
    }

    $mb = [math]::Round((Get-Item -LiteralPath $dest).Length / 1MB, 2)
    if (Test-Zip $dest) {
        Ok "$name  $mb MB"
        $good += $dest
    } else {
        # Keep it. It is evidence about what went wrong, and deleting it would
        # not un-spend the link.
        Bad "$name - downloaded $mb MB but it is not a zip"
        Say "        Probably an HTML page: the link was already used, or you" Yellow
        Say "        are signed out of claude.ai in this machine's browser." Yellow
        $bad += $name
    }
}

Say ""
Say "$($good.Count) of $($m.data_files.Count) archives are here." Cyan

if ($bad.Count -gt 0) {
    Say ""
    Bad "$($bad.Count) did not arrive: $($bad -join ', ')"

    # A 403 is almost certainly NOT a spent link. These URLs sit behind your
    # claude.ai login, and Invoke-WebRequest carries no browser cookies - so it
    # is refused at the door, before the download that would spend the link.
    # An earlier version of this script announced "those links are spent" for
    # any failure at all, which is a frightening thing to be told and was not
    # something it could know.
    if ($forbidden -gt 0) {
        Say ""
        Say "  $forbidden of them answered 403 Forbidden. That means NOT SIGNED IN," Cyan
        Say "  not 'already used' - these links sit behind your claude.ai login" Cyan
        Say "  and PowerShell has none of your browser's cookies." Cyan
        Say ""
        Say "  Your links are very probably still good. Download them in the" Green
        Say "  BROWSER you are signed into claude.ai with:" Green
        Say ""
        foreach ($f in $m.data_files) {
            Say "    $($f.export_url)" White
        }
        Say ""
        Say "  Paste each into the address bar. Save them anywhere, then:" Cyan
        Say "      python .\scripts\recover_from_claude_export.py `"$env:USERPROFILE\Downloads`"" Cyan
    } else {
        Say "  If a link was already used it cannot be retried - that needs a" Yellow
        Say "  NEW export (Settings -> Privacy -> Export data) and a new manifest." Yellow
    }
}

if ($good.Count -eq 0) { exit 1 }

Say ""
Say "Now search them for the lost modules:" Cyan
Say "    python .\scripts\recover_from_claude_export.py `"$OutDir`"" Cyan
Say ""
Say "The archives stay in that folder. Nothing needs downloading twice." Cyan
Say ""
exit 0
