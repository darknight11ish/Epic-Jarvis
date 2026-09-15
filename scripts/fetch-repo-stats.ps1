<#
.SYNOPSIS
  Fetch the peer-project metadata that grade_repo needs, and save it.

.DESCRIPTION
  `backend/jarvis_research.py` grades a repository ADOPT / FORK AND EXTEND /
  BUILD CUSTOM. It has never been run on real data for one reason: the
  container these sessions run in cannot reach `api.github.com` or
  `github.com` — both answer 403, and only `raw.githubusercontent.com` gets
  through.

  Two attempts to get the numbers out of a second model produced no star
  counts at all and a 5-in-6 error rate on the facts that could be checked
  against source files. The reason is the same for both: neither of them can
  open this URL.

      https://api.github.com/repos/janhq/jan

  Your machine can. That is the entire gap, and this closes it.

  Writes `backend/peer-stats.json` — the raw API response per repo, no
  interpretation, so the grader can read the exact fields it expects
  (`stargazers_count`, `license.spdx_id`, `pushed_at`, `archived`).

.PARAMETER Token
  Optional GitHub personal access token. Not needed: unauthenticated is 60
  requests an hour and this makes twenty. Pass one only if you hit the limit
  because something else on your machine already used it up. It needs NO
  scopes — every repo here is public — so create it with everything unticked.

.PARAMETER OutFile
  Where to write. Defaults to backend/peer-stats.json in this repository.

.EXAMPLE
  .\scripts\fetch-repo-stats.ps1
#>

[CmdletBinding()]
param(
    [string] $Token,
    [string] $OutFile
)

$ErrorActionPreference = 'Stop'

$REPOS = @(
    'khoj-ai/khoj'
    'janhq/jan'
    'open-webui/open-webui'
    'letta-ai/letta'
    'letta-ai/letta-code'
    'mem0ai/mem0'
    'getzep/graphiti'
    'OpenVoiceOS/ovos-core'
    'rhasspy/rhasspy3'
    'rhasspy/rhasspy'
    'MycroftAI/mycroft-core'
    'home-assistant/core'
    'block/goose'
    'cline/cline'
    'openai/codex'
    'supermemoryai/supermemory'
    'qualixar/superlocalmemory'
    'k2-fsa/sherpa-onnx'
    'localsend/localsend'
    'syncthing/syncthing'
)

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutFile) { $OutFile = Join-Path $RepoRoot 'backend\peer-stats.json' }

function Say($msg, $colour = 'Gray') { Write-Host $msg -ForegroundColor $colour }

function Format-Stamp($value) {
    <#
      "2026-09-15T04:08:23Z", whatever shape it arrived in.

      grade_repo's _age_days does time.strptime(str(x)[:19], "%Y-%m-%dT%H:%M:%S")
      and returns None if that fails - so a value in any other shape does not
      error, it silently becomes "no push date", which reads as an abandoned
      project. A wrong answer that looks like a real one.
    #>
    if ($null -eq $value) { return $null }
    if ($value -is [datetime]) {
        return $value.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    }
    $text = [string]$value
    if ($text.Length -ge 19) { return $text }
    return $null
}

# GitHub requires a User-Agent and will refuse without one.
$headers = @{
    'User-Agent' = 'jarvis-peer-research'
    'Accept'     = 'application/vnd.github+json'
}
if ($Token) { $headers['Authorization'] = "Bearer $Token" }

# PowerShell 5.1 defaults to TLS 1.0, which github.com has not accepted for
# years. Without this the very first request fails with an unhelpful
# "underlying connection was closed". PowerShell 7 does not need it and is
# not harmed by it.
try {
    [Net.ServicePointManager]::SecurityProtocol =
        [Net.SecurityProtocolType]::Tls12 -bor [Net.ServicePointManager]::SecurityProtocol
} catch { }

Say ""
Say "Fetching $($REPOS.Count) repositories from api.github.com" Cyan
if (-not $Token) { Say "(unauthenticated: 60 requests an hour, this uses $($REPOS.Count))" }
Say ""

$results = [ordered]@{}
$failed  = @()

foreach ($repo in $REPOS) {
    try {
        $r = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo" -Headers $headers -TimeoutSec 30

        # ConvertFrom-Json turns an ISO date into a [datetime], so pushed_at
        # may arrive as an object rather than a string and `.Substring(0,10)`
        # would throw - sending a perfectly good repo into the catch below and
        # recording it as a fetch failure. Normalised here, once, to the exact
        # shape _age_days parses: "%Y-%m-%dT%H:%M:%S", in UTC.
        $pushed = Format-Stamp $r.pushed_at
        $updated = Format-Stamp $r.updated_at

        # Precomputed rather than an `if` inside the hashtable literal, which
        # is harder to read and easier to get subtly wrong.
        $licBlock = $null
        if ($r.license -and $r.license.spdx_id) {
            $licBlock = @{ spdx_id = $r.license.spdx_id }
        }

        # Saved under the names grade_repo reads, so there is one shape to keep
        # in step rather than two.
        $results[$repo] = [ordered]@{
            full_name        = $r.full_name
            stargazers_count = $r.stargazers_count
            license          = $licBlock
            pushed_at        = $pushed
            archived         = [bool]$r.archived
            # Not used by the grader. Here because it settles the Mycroft and
            # Rhasspy archive-date question two research passes could not.
            updated_at       = $updated
            description      = $r.description
        }

        $lic = 'none'
        if ($licBlock) { $lic = $licBlock.spdx_id }
        $arch = ''
        if ($r.archived) { $arch = '  ARCHIVED' }
        $day = 'unknown'
        if ($pushed) { $day = $pushed.Substring(0, 10) }
        Say ("  {0,-34} {1,8} stars  {2,-14} {3}{4}" -f
             $repo, $r.stargazers_count, $lic, $day, $arch)
    }
    catch {
        $code = $null
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        # A 404 on a PUBLIC repo means it was renamed, deleted, or the name in
        # the list is wrong — all three are findings, not errors to hide.
        $why = if ($code) { "HTTP $code" } else { $_.Exception.Message }
        $failed += "$repo - $why"
        Write-Host ("  {0,-34} {1}" -f $repo, $why) -ForegroundColor Red
        $results[$repo] = [ordered]@{ error = $why }
    }
}

$dir = Split-Path -Parent $OutFile
if ($dir -and -not (Test-Path -LiteralPath $dir)) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}
$results | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $OutFile -Encoding UTF8

Say ""
Say "Written to $OutFile" Green
if ($failed.Count -gt 0) {
    Say ""
    Say "$($failed.Count) could not be fetched:" Yellow
    foreach ($f in $failed) { Say "  $f" Yellow }
    Say "A 404 here is worth reporting - it means the repo moved or the name is wrong." Cyan
}
Say ""
Say "Now either commit that file, or paste it back. Then:" Cyan
Say "    python backend/grade-peers.py" Cyan
Say ""
