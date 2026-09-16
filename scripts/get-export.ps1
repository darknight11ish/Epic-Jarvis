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

  A one-time URL is spent whether or not the download worked. Click one while
  signed out, or lose the connection half way, and the link is gone - the file
  is not, but you cannot fetch it again without requesting a whole new export
  and waiting for a second email. So every download here is verified the moment
  it lands, and the files are kept: if something later goes wrong reading them,
  nothing has to be fetched twice.

  Verified means checked, not assumed. A spent or unauthenticated link does not
  answer with an error - it answers with an HTML page, which saves perfectly
  happily as `conversations-000.zip` and fails much later with an error about
  the archive being corrupt. So each file is opened and its first two bytes read:
  a real zip starts `PK`. An HTML page starts `<!`.

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
Say "THESE LINKS WORK ONCE EACH. Do not re-run this on the same manifest -" Yellow
Say "a second attempt gets nothing and the files are already spent." Yellow
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

$good = @(); $bad = @()

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
        Bad "$name - $($_.Exception.Message)"
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
    Say "  Those links are spent. To get those files you need a NEW export" Yellow
    Say "  (Settings -> Privacy -> Export data) and a new manifest." Yellow
}

if ($good.Count -eq 0) { exit 1 }

Say ""
Say "Now search them for the lost modules:" Cyan
Say "    python .\scripts\recover_from_claude_export.py `"$OutDir`"" Cyan
Say ""
Say "The archives stay in that folder. Nothing needs downloading twice." Cyan
Say ""
exit 0
