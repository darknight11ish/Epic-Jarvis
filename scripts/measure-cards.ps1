<#
.SYNOPSIS
  Are both graphics cards fitted, is the model really on the 12 GB one, and is
  a whole card left over for longer conversations? Reads only.

.DESCRIPTION
  The 2026-10-05 audit asked for Ollama's log file, and the note taken that
  morning records that no log was found. Measured again while this script was
  written, later the same morning, **the log IS there on this PC** -
  %LOCALAPPDATA%\Ollama\server.log, 894,789 bytes, created 2026-09-02 and last
  written 2026-10-05 09:48, with `load_tensors: offloaded 37/37 layers to GPU`
  in its last lines. So both routes work here. `ollama ps` still leads: it
  prints the processor split, the size, the context and the keep-alive
  directly, which is better evidence than a log line, and it is there whenever
  a model is loaded. The log is read **if** it exists; on a machine without one
  the check says so in one plain line and carries on - never a warning, never a
  failure.

  What it reads, in order:

    1. `ollama ps`                          - the processor split, size, context, UNTIL
    2. `nvidia-smi`                         - every card, total/used/free memory
    3. `nvidia-smi --query-compute-apps`    - which card the model's process is on
                                              (with a fallback from the cards'
                                              own memory, because some Windows
                                              drivers name no process at all)
    4. http://127.0.0.1:11434/api/ps        - size_vram against size, the exact split
    5. Ollama's log, if it exists           - optional extra, never required
    6. the context in use against 16,384    - the one change these numbers justify

  WHAT IT DOES NOT DO

  It writes nothing, starts nothing, loads or unloads no model, and sends no
  message to any model - `ollama ps` and `/api/ps` only report what is already
  in memory. So it is safe to run while Jarvis is running, and safe to run
  again straight after a change.

  It reads Ollama only at a this-PC address, with the proxy switched off for
  that one call (the same rule `jarvis_speed.py` follows), and it sends no
  header of its own - nothing to authenticate, so there is no token or key
  anywhere in this script to send, print or leak. No text of any conversation
  is read.

  The only file it ever writes is one scoreboard row, and only with -Save.

  WHY THE CONCLUSION IS "RAISE IT", NOT "DROP IT"

  The audit said that if the model were spilling, dropping the context to 8,192
  would fix it. On this machine the model is not spilling, and the arithmetic
  runs the other way: 16,384 needs about 6.5 GB, the 12 GB card holds it with
  room to spare, and 16,384 holds about four times the conversation 4,096 does.
  The old advice is kept here only so nobody re-applies it by mistake.

.PARAMETER Save
  Add one row to the card scoreboard (`cards.jsonl`, beside `speed.jsonl`) and
  print the same row to paste into docs\MEASURE-CARDS.md. Without -Save,
  nothing on this PC is written or changed.

.PARAMETER Scoreboard
  Where -Save writes, if you want it somewhere else. Default: the Jarvis
  settings folder (`%OPENJARVIS_CONFIG_DIR%`, else `%USERPROFILE%\.openjarvis`).

.PARAMETER OllamaUrl
  Ollama's address. Only a this-PC address is read; anything else is refused
  and said so, rather than sending the check off the machine.

.EXAMPLE
  From the folder this repository is cloned into:

  powershell -ExecutionPolicy Bypass -File .\scripts\measure-cards.ps1

.EXAMPLE
  The same, and add the row to the scoreboard:

  powershell -ExecutionPolicy Bypass -File .\scripts\measure-cards.ps1 -Save

.NOTES
  What the words mean, how to read each block, and the first-ever measured row:
  docs\MEASURE-CARDS.md. The measurement those numbers came from:
  docs\MEASURED-2026-10-05-owner-pc.md.
#>

[CmdletBinding()]
param(
    [switch] $Save,
    [string] $Scoreboard = "",
    [string] $OllamaUrl  = "http://127.0.0.1:11434"
)

# A missing log file, a card that answers oddly, or an Ollama that is not
# running are all things to SAY, not reasons to fail. The owner runs this by
# hand, once, and needs the answer at the end of it.
$ErrorActionPreference = 'Continue'

# The everyday model, and the numbers that were worked out for it. The context
# comparison at the end is only valid for this model: a different model has a
# different cache size per token. MODEL-TOPOLOGY.md "The budget" and
# HARDWARE-PROFILES.md section 8.2 hold the arithmetic.
$EverydayNames      = @('jarvis-primary', 'qwen3:8b')
$CtxEveryday        = 16384     # the documented everyday configuration
$Need16kMiB         = 6656      # about 6.5 GB of model on the card, in total
$CacheBytesPerToken = 78336     # q8_0 KV of Qwen 3 8B: 2 x 36 layers x 8 heads x 128 x 1.0625 B

# ==========================================================================
#   Small helpers
# ==========================================================================

function Say {
    param([string] $Message = "", [string] $Colour = 'Gray')
    Write-Host $Message -ForegroundColor $Colour
}

function Join-IfSet {
    param([string] $Base, [string] $Child)
    # Join-Path refuses an empty base, and an environment variable that is not
    # set is normal on a machine this check must still work on.
    if (-not $Base) { return "" }
    return (Join-Path $Base $Child)
}

function Invoke-Read {
    param([string] $Exe, [string[]] $Arguments = @())
    # Runs one read-only tool and returns its output lines. Never throws: a tool
    # that is missing, or that objects, comes back as ran = $false so the check
    # carries on with what the other tools said.
    try { $found = Get-Command $Exe -ErrorAction Stop }
    catch { return [pscustomobject]@{ ran = $false; lines = @() } }
    try {
        $lines = @(& $found.Source @Arguments 2>$null | ForEach-Object { [string] $_ })
        return [pscustomobject]@{ ran = $true; lines = $lines }
    } catch {
        return [pscustomobject]@{ ran = $false; lines = @() }
    }
}

function ConvertTo-MiB {
    param([string] $Text)
    # "5.6 GB" as Ollama prints it (1,000-based, the way `ollama ps` sizes are
    # printed) -> MiB, so it can be compared with nvidia-smi's numbers. $null
    # when the text is not a size at all.
    if ($Text -match '^\s*([0-9]+(?:\.[0-9]+)?)\s*([KMGTP])B\s*$') {
        $n    = [double] $Matches[1]
        $unit = $Matches[2]
        switch ($unit) {
            'K' { return [long][math]::Round($n * 1000 / 1048576) }
            'M' { return [long][math]::Round($n * 1000000 / 1048576) }
            'G' { return [long][math]::Round($n * 1000000000 / 1048576) }
            'T' { return [long][math]::Round($n * 1000000000000 / 1048576) }
        }
    }
    return $null
}

function Format-Gb {
    param([double] $MiB)
    return ([math]::Round($MiB / 1024, 1)).ToString('0.0')
}

function Format-CardGb {
    param([double] $MiB)
    # A card's own size, as the whole number it is sold as: 12,288 MiB -> "12".
    return ([math]::Round($MiB / 1024, 0)).ToString('0')
}

function Read-PsTable {
    param([string[]] $Lines)
    # `ollama ps` prints one small table:
    #
    #   NAME        ID              SIZE      PROCESSOR    CONTEXT    UNTIL
    #   qwen3:8b    500a1f067a9f    5.6 GB    100% GPU     4096       Forever
    #
    # Read by shape rather than by column padding, because the padding changes
    # with the longest name on screen. PROCESSOR holds a space in every value
    # Ollama prints ("100% GPU", "52%/48% CPU/GPU"), and UNTIL is everything
    # left over, because it can hold spaces too ("4 minutes from now"). CONTEXT
    # is missing on older Ollama, so a shape without it is tried second.
    # Nothing here loads a model.
    $withCtx = '^(?<name>\S+)\s+(?<id>[0-9a-fA-F]+)\s+(?<size>[0-9.]+\s*[KMGTP]B)\s+(?<proc>[0-9]+%(?:/[0-9]+%)?\s+[A-Za-z/]+)\s+(?<ctx>\d+)\s+(?<until>\S.*)$'
    $noCtx   = '^(?<name>\S+)\s+(?<id>[0-9a-fA-F]+)\s+(?<size>[0-9.]+\s*[KMGTP]B)\s+(?<proc>[0-9]+%(?:/[0-9]+%)?\s+[A-Za-z/]+)\s+(?<until>\S.*)$'
    $rows = @()
    foreach ($line in $Lines) {
        $text = ([string] $line).Trim()
        if (-not $text) { continue }
        if ($text -match '^NAME\b') { continue }          # the header
        $m   = [regex]::Match($text, $withCtx)
        $ctx = 0
        $good = $false
        if ($m.Success) {
            [void] [int]::TryParse($m.Groups['ctx'].Value, [ref] $ctx)
            $untilText = $m.Groups['until'].Value.Trim()
            # Two guards against a row that carries no CONTEXT column at all. A
            # real context is hundreds of tokens or more, and a real UNTIL either
            # says "Forever" or starts with its own number ("4 minutes from
            # now") - so a "context" of 4 with "minutes from now" left over is a
            # duration being mistaken for a context.
            if ($ctx -ge 256 -and $untilText -notmatch '^(seconds?|minutes?|hours?|days?|from|ago)\b') { $good = $true }
        }
        if (-not $good) {
            $m   = [regex]::Match($text, $noCtx)
            $ctx = 0
            if (-not $m.Success) { continue }
        }
        $rows += [pscustomobject] @{
            name      = $m.Groups['name'].Value
            id        = $m.Groups['id'].Value
            size_text = $m.Groups['size'].Value
            processor = $m.Groups['proc'].Value
            context   = $ctx
            until     = $m.Groups['until'].Value.Trim()
        }
    }
    return $rows
}

function Test-IsThisPc {
    param([string] $Url)
    $name = ""
    try { $name = ([System.Uri] $Url).Host } catch { return $false }
    foreach ($ok in @('localhost', '127.0.0.1', '::1', '[::1]')) {
        if ($name -eq $ok) { return $true }
    }
    return $false
}

function Get-ThisPcJson {
    param([string] $Url)
    # One small JSON answer from a this-PC address. The proxy is switched off
    # for the call on purpose, the rule jarvis_speed.py follows: with a proxy
    # set, this request and Ollama's answer would travel to it instead. No
    # header of its own is sent, so there is no token here to print or leak.
    try {
        $request = [System.Net.WebRequest]::Create($Url)
        $request.Proxy    = $null
        $request.Method   = 'GET'
        $request.Timeout  = 4000
        $response = $request.GetResponse()
        try {
            $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
            $text   = $reader.ReadToEnd()
        } finally {
            $response.Close()
        }
        return ($text | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Add-ScoreboardRow {
    param([string] $Path, [string] $Line)
    # Append one JSON line and never rewrite what is there - the rule
    # speed.jsonl keeps. Written with no byte-order mark, because a BOM at the
    # front of a JSON lines file breaks the first line of anything that reads
    # it back. Returns $true when it landed.
    try {
        $dir = Split-Path -Parent $Path
        if ($dir -and -not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::AppendAllText($Path, $Line + [Environment]::NewLine, $utf8NoBom)
        return $true
    } catch {
        return $false
    }
}

function Short-CardName {
    param([string] $Name)
    # "NVIDIA GeForce RTX 2060" -> "RTX 2060", for the one-line row that goes on
    # the scoreboard. The full name stays in the JSON row.
    return ($Name -replace '^NVIDIA\s+(GeForce\s+)?', '')
}

# ==========================================================================
#   The heading
# ==========================================================================

Say ""
Say "Jarvis: the graphics cards, and what the model is doing" White
Say "reads only - nothing is written, started, loaded or unloaded" DarkGray
Say ""

$osText = "Windows (version not read)"
try { $osText = "Windows " + [System.Environment]::OSVersion.Version.ToString() } catch { }
$machine = $env:COMPUTERNAME
if (-not $machine) { $machine = "(machine name not set)" }

$readSomething = $false
$ollamaVersion = ""
$psRows        = @()
$gpus          = @()
$jsonPs        = $null

# ==========================================================================
#   1. `ollama ps` - the primary check
# ==========================================================================

Say "1. What Ollama says it is running   (ollama ps)" White
Say ""

$psRun = Invoke-Read 'ollama' @('ps')
if (-not $psRun.ran) {
    Say "   ollama would not run, or is not on PATH. The cards below can still be" DarkGray
    Say "   read; the split between card and processor cannot." DarkGray
    Say ""
} else {
    $readSomething = $true
    $psRows = @(Read-PsTable $psRun.lines)
    $dataLines = @($psRun.lines | Where-Object { $_.Trim() -and $_.Trim() -notmatch '^NAME\b' })
    if ($dataLines.Count -eq 0) {
        Say "   No model is loaded in Ollama right now, so there is no split to read." Yellow
        Say "   Send Jarvis one message (or ask it anything), then run this again." Cyan
        Say ""
    } elseif ($psRows.Count -eq 0) {
        Say "   Ollama answered, but this check could not read its table. As it" Yellow
        Say "   printed, word for word:" Yellow
        foreach ($line in $psRun.lines) { Say ("     " + $line) DarkGray }
        Say ""
    } else {
        foreach ($line in $psRun.lines) { Say ("   " + $line) Gray }
        Say ""
    }
}

# The version is part of the fingerprint a scoreboard row is keyed by
# (HARDWARE-PROFILES.md section 4.7). Reading it loads nothing.
$verRun = Invoke-Read 'ollama' @('--version')
if ($verRun.ran -and $verRun.lines.Count -gt 0) {
    $ollamaVersion = ($verRun.lines[0] -replace '^ollama version is\s*', '').Trim()
}

# One entry per loaded model: the findings, in plain words.
$found = @()
foreach ($row in $psRows) {
    $sizeMiB = ConvertTo-MiB $row.size_text
    $isEveryday = $false
    foreach ($want in $EverydayNames) {
        if ($row.name -like "$want*") { $isEveryday = $true }
    }
    $splitOk = ($row.processor -match '^\s*100%\s*GPU\s*$')
    $forever = ($row.until -eq 'Forever')

    if ($splitOk) {
        Say ("   ok      {0}: every layer is on a graphics card ({1}). No spill." -f $row.name, $row.processor) Green
    } else {
        Say ("   SPILL   {0}: PROCESSOR is ""{1}"" - part of your model is running on" -f $row.name, $row.processor) Red
        Say  "           your processor. That part is about five times slower, and" Red
        Say  "           nothing else warns you about it." Red
    }

    $found += [pscustomobject] @{
        name       = $row.name
        size_text  = $row.size_text
        size_mb    = $sizeMiB
        processor  = $row.processor
        context    = $row.context
        until      = $row.until
        forever    = $forever
        spill      = (-not $splitOk)
        everyday   = $isEveryday
    }
}
if ($found.Count -gt 0) { Say "" }

# ==========================================================================
#   2. The cards themselves   (`nvidia-smi`, NVIDIA's own tool)
# ==========================================================================

Say "2. The graphics cards   (nvidia-smi)" White
Say ""

$gpuRun = Invoke-Read 'nvidia-smi' @(
    '--query-gpu=index,uuid,name,driver_version,memory.total,memory.used,memory.free',
    '--format=csv,noheader,nounits'
)
if (-not $gpuRun.ran -or $gpuRun.lines.Count -eq 0) {
    Say "   nvidia-smi would not run, or listed no NVIDIA card. On a PC with no" Yellow
    Say "   NVIDIA card that is expected, and this check simply has nothing to add." Yellow
    Say ""
} else {
    $readSomething = $true
    foreach ($line in $gpuRun.lines) {
        $cell = @($line -split ',' | ForEach-Object { $_.Trim() })
        if ($cell.Count -lt 7) { continue }
        $gpus += [pscustomobject] @{
            index    = [int] $cell[0]
            uuid     = $cell[1]
            name     = $cell[2]
            driver   = $cell[3]
            total_mb = [long] $cell[4]
            used_mb  = [long] $cell[5]
            free_mb  = [long] $cell[6]
        }
    }
    foreach ($gpu in $gpus) {
        Say ("   #{0}  {1,-26} {2,7} MiB total   {3,7} used   {4,7} free" -f `
             $gpu.index, $gpu.name, $gpu.total_mb.ToString('N0'), $gpu.used_mb.ToString('N0'), $gpu.free_mb.ToString('N0')) Gray
    }
    Say ""
}

# Which card is the model's process on? This is the question the documents got
# the wrong way round: they call the 2080 SUPER the primary card, and the
# machine has the model on the 12 GB card.
$modelCard   = $null
$modelProcMb = 0
$modelProc   = ""
$appsRun = Invoke-Read 'nvidia-smi' @(
    '--query-compute-apps=gpu_uuid,pid,process_name,used_memory',
    '--format=csv,noheader,nounits'
)
if ($appsRun.ran -and $gpus.Count -gt 0) {
    foreach ($line in $appsRun.lines) {
        $cell = @($line -split ',' | ForEach-Object { $_.Trim() })
        if ($cell.Count -lt 4) { continue }
        if ($cell[2] -notmatch '(?i)llama|ollama') { continue }
        $used = [long] 0
        [void] [long]::TryParse($cell[3], [ref] $used)
        if ($used -gt $modelProcMb) {
            $modelProcMb = $used
            $modelProc   = $cell[2]
            foreach ($gpu in $gpus) { if ($gpu.uuid -eq $cell[0]) { $modelCard = $gpu } }
        }
    }
}
if ($modelCard) {
    Say ("   The model is on #{0} ({1}, {2} MiB)." -f $modelCard.index, $modelProc, $modelCard.used_mb.ToString('N0')) Green
    Say ""
} elseif ($gpus.Count -gt 0 -and $found.Count -gt 0) {
    # nvidia-smi named no process, which happens on some Windows drivers. Do
    # NOT fall back to "the card with the most free memory": measured
    # 2026-10-05, that named the 2080 SUPER while the model was on the 12 GB
    # card, and every number below it was then about the wrong card. The
    # model's own size is the better evidence: its card is the one already
    # holding at least that much, and the closest to it.
    $modelMiB = 0
    foreach ($m in $found) { if ($m.size_mb -and $m.size_mb -gt $modelMiB) { $modelMiB = $m.size_mb } }
    $best = $null
    foreach ($gpu in $gpus) {
        if ($modelMiB -le 0) { continue }
        if ($gpu.used_mb -ge ($modelMiB * 0.8)) {
            if (-not $best -or $gpu.used_mb -lt $best.used_mb) { $best = $gpu }
        }
    }
    if ($best) {
        $modelCard = $best
        $sizeForWords = "its own size"
        if ($found[0].size_text) { $sizeForWords = $found[0].size_text }
        Say "   nvidia-smi did not name the model's process. The cards' own memory says" Yellow
        Say ("   the model is on #{0}: {1} MiB in use there, and the model is {2}." -f `
             $best.index, $best.used_mb.ToString('N0'), $sizeForWords) Yellow
    } else {
        $modelCard = @($gpus | Sort-Object -Property total_mb -Descending)[0]
        Say "   nvidia-smi did not name the model's process, and no card's memory matches" Yellow
        Say "   the model's size, so which card it is on could not be read. The comparison" Yellow
        Say ("   below uses #{0}, the biggest card - read it as the best case." -f $modelCard.index) Yellow
    }
    Say ""
}

# ==========================================================================
#   3. The run-time split   (Ollama's /api/ps - loads nothing)
# ==========================================================================

Say "3. The run-time split   (/api/ps on this PC)" White
Say ""

$base = $OllamaUrl.TrimEnd('/')
if (-not (Test-IsThisPc $base)) {
    Say ("   Not read: {0} is not a this-PC address, and this check only talks to" -f $base) DarkGray
    Say  "   this PC." DarkGray
    Say ""
} else {
    $jsonPs = Get-ThisPcJson ($base + '/api/ps')
    if ($null -eq $jsonPs) {
        Say "   Ollama did not answer on 127.0.0.1:11434. If Jarvis itself is working," DarkGray
        Say "   that is only this check's own call failing - try again in a moment." DarkGray
        Say ""
    } else {
        $readSomething = $true
        $psModels = @($jsonPs.models)
        if ($psModels.Count -eq 0) {
            Say "   Ollama is up, and no model is loaded." DarkGray
            Say ""
        }
        foreach ($m in $psModels) {
            $name    = [string] $m.name
            $sizeB   = [long] $m.size
            $vramB   = [long] $m.size_vram
            $sizeMb  = [long][math]::Round($sizeB / 1MB)
            $vramMb  = [long][math]::Round($vramB / 1MB)
            $pct     = $null
            if ($sizeB -gt 0) { $pct = [int][math]::Round(100 * $vramB / $sizeB) }
            $ctxPs   = 0
            if ($m.context_length) { [void] [int]::TryParse([string] $m.context_length, [ref] $ctxPs) }
            $expires = ""
            if ($m.expires_at) { $expires = ([string] $m.expires_at) }

            $pctText = "unknown"
            if ($null -ne $pct) { $pctText = "$pct%" }
            Say ("   {0}: on the card {1} MiB of {2} MiB = {3}   (context {4})" -f `
                 $name, $vramMb.ToString('N0'), $sizeMb.ToString('N0'), $pctText, $ctxPs) Gray

            # The exact bytes are the better evidence. If they disagree with the
            # rounded PROCESSOR cell from `ollama ps`, say which one to believe.
            $psRow = $null
            foreach ($cand in $found) { if ($cand.name -eq $name) { $psRow = $cand } }
            if ($psRow) {
                if ($null -ne $pct) {
                    if (($pct -ge 100) -and $psRow.spill) {
                        Say "        (the exact bytes say every layer is on the card; the rounded" Yellow
                        Say "         PROCESSOR cell above says otherwise - believe the bytes)" Yellow
                    } elseif (($pct -lt 100) -and -not $psRow.spill) {
                        Say "        (the exact bytes say part of it is off the card, which is the" Red
                        Say "         one thing here to fix - believe the bytes, not the summary)" Red
                    }
                }
                $psRow | Add-Member -NotePropertyName vram_mb -NotePropertyValue $vramMb -Force
                $psRow | Add-Member -NotePropertyName size_bytes -NotePropertyValue $sizeB -Force
                $psRow | Add-Member -NotePropertyName on_gpu_percent -NotePropertyValue $pct -Force
            }
            if ($expires) {
                # Ollama's own expiry stamp. For a model held forever it is a
                # far-future placeholder date, which reads like nonsense unless
                # it is called that; and its nanoseconds are noise either way.
                $expiresText = $expires
                if ($expiresText -match '^(.*?)\.\d+') { $expiresText = $Matches[1] }
                $heldForever = $false
                if ($psRow) { $heldForever = $psRow.forever }
                if ($heldForever) {
                    Say ("        never unloads (Ollama's date for it is a far-future placeholder: {0})" -f $expiresText) DarkGray
                } else {
                    Say ("        unloads at {0}" -f $expiresText) DarkGray
                }
            }
        }
        if ($psModels.Count -gt 0) { Say "" }
    }
}

# ==========================================================================
#   4. The context - the one number worth changing
# ==========================================================================
#
# Said plainly, because the old advice was the opposite: there is no spill, so
# nothing needs dropping to 8,192. 16,384 fits, and it is worth having.

Say "4. The context - how much conversation the model keeps" White
Say ""

$everyday = $null
foreach ($cand in $found) { if ($cand.everyday -and -not $everyday) { $everyday = $cand } }
if (-not $everyday -and $found.Count -gt 0) { $everyday = $found[0] }

$fits     = $null
$roomMiB  = 0
$spareMiB = 0

if (-not $everyday) {
    Say "   No model is loaded, so there is nothing to compare yet. The everyday" DarkGray
    Say "   setting is 16,384 tokens of context (about 6.5 GB on the card), and it" DarkGray
    Say "   fits on a 12 GB card with room to spare." DarkGray
    Say ""
} else {
    $ctxNow = $everyday.context
    if ($ctxNow -gt 0) {
        Say ("   running now                {0} tokens" -f $ctxNow.ToString('N0')) Gray
    } else {
        # Older Ollama prints no CONTEXT column. Say so rather than implying 0.
        Say  "   running now                (this Ollama does not print a CONTEXT column)" DarkGray
    }
    Say ("   the everyday setting       {0} tokens" -f $CtxEveryday.ToString('N0')) Gray
    Say ("   16,384 needs               about {0} GB of model on the card, in total" -f (Format-Gb $Need16kMiB)) Gray

    if ($modelCard) {
        # The room is the card minus whatever is NOT the model. That is only
        # known when nvidia-smi named the model's process; without it, the
        # whole card is counted, which is the best case and is said so.
        $otherMiB = 0
        $roomMiB  = $modelCard.total_mb
        if ($modelProcMb -gt 0) {
            $otherMiB = [math]::Max(0, $modelCard.used_mb - $modelProcMb)
            $roomMiB  = $modelCard.total_mb - $otherMiB
        }
        $spareMiB = $roomMiB - $Need16kMiB
        $fits     = ($spareMiB -ge 0)
        Say ("   room on that card          {0} MiB total, {1} MiB free right now (nvidia-smi)" -f `
             $modelCard.total_mb.ToString('N0'), $modelCard.free_mb.ToString('N0')) Gray
        if ($modelProcMb -gt 0) {
            if ($otherMiB -gt 0) {
                Say ("                              {0} MiB of that card is used by something other" -f $otherMiB.ToString('N0')) DarkGray
                Say  "                              than the model (a monitor, or another program)" DarkGray
            } else {
                Say  "                              nothing but the model is using that card right now" DarkGray
            }
        } else {
            Say  "                              the model's own share of that could not be read, so" DarkGray
            Say  "                              the whole card is counted as room for it" DarkGray
        }
    }
    Say ""

    if ($null -eq $fits) {
        Say "   The cards could not be read, so whether 16,384 fits cannot be said here." Yellow
        Say "   16,384 needs about 6.5 GB: on a 12 GB card that fits, on an 8 GB card it" Gray
        Say "   does not." Gray
    } elseif ($fits) {
        Say ("   So: 16,384 FITS - about {0} MiB to spare on the card. Raising the context" -f $spareMiB.ToString('N0')) Green
        Say  "   is the one change these numbers justify, and it does not need the second" Green
        Say  "   card switched on to do it." Green
    } else {
        Say ("   So: 16,384 does NOT fit as things stand - it is {0} MiB over." -f ([math]::Abs($spareMiB)).ToString('N0')) Red
        Say  "   Free the card (close a game or a browser with hardware video) and run this" Cyan
        Say  "   again, or leave the context where it is." Cyan
    }

    # The daily consequence, and only for the model these numbers were worked
    # out for. For any other model the cache per token is different, and this
    # check will not guess it.
    if ($everyday.everyday) {
        $extraBytes = [double] ($CtxEveryday - $ctxNow) * $CacheBytesPerToken
        $extraMiB   = [long][math]::Round($extraBytes / 1MB)
        Say ""
        if ($ctxNow -le 0) {
            Say "   This Ollama does not print the context in use, so the comparison above is" DarkGray
            Say "   between the everyday setting and the card alone." DarkGray
        } elseif ($extraMiB -gt 0) {
            Say ("   That raise costs about {0} GB more than now (16,384 holds about four" -f (Format-Gb $extraMiB)) Gray
            Say  "   times the conversation 4,096 does, before the oldest turns are dropped)." Gray
        } elseif ($ctxNow -ge $CtxEveryday) {
            Say ("   The loaded model is already at {0} tokens - nothing to raise." -f $ctxNow.ToString('N0')) Green
        }
    } else {
        Say ""
        Say ("   ({0} is not the everyday model, so this check does not guess its cache" -f $everyday.name) DarkGray
        Say  "    size; the 6.5 GB figure above is for Qwen 3 8B.)" DarkGray
    }

    Say ""
    Say "   The setting is the context length, num_ctx. It lives in the everyday model's" Cyan
    Say "   own file, backend\jarvis-primary.Modelfile (PARAMETER num_ctx 16384), and" Cyan
    Say "   Ollama reads it only when that tuned copy is the model loaded. To apply it" Cyan
    Say "   (this check does not run it):" Cyan
    Say ""
    Say "       ollama create jarvis-primary -f backend\jarvis-primary.Modelfile" White
    Say ""
    Say "   The other way, which needs Ollama restarted, is the setting" Cyan
    Say "   OLLAMA_CONTEXT_LENGTH=16384 for Ollama itself. Either way, run this check" Cyan
    Say "   again afterwards and watch the CONTEXT column change." Cyan
    Say ""
}

# ==========================================================================
#   5. What "Forever" costs
# ==========================================================================

Say "5. What the UNTIL column costs" White
Say ""
if ($found.Count -eq 0) {
    Say "   Nothing is loaded, so nothing is being held." DarkGray
} else {
    foreach ($m in $found) {
        if ($m.forever) {
            Say ("   {0}: UNTIL is Forever, so the model never unloads and {1} stays held on" -f $m.name, $m.size_text) Gray
            Say  "   the card for as long as Ollama runs (OLLAMA_KEEP_ALIVE=-1). That is on" Gray
            Say  "   purpose - the first word after you step away is not delayed by a load -" Gray
            Say  "   and it is affordable on the 12 GB card; it is still memory that is never" Gray
            Say  "   free for anything else." Gray
        } else {
            Say ("   {0}: UNTIL is ""{1}"", so it unloads then, and the next question after" -f $m.name, $m.until) Gray
            Say  "   that waits for it to load again (about 6 seconds on this PC)." Gray
        }
    }
}
Say ""

# ==========================================================================
#   6. Ollama's log - an optional extra, never required
# ==========================================================================
#
# Corrected 2026-10-05, the same morning the note above this one was written.
# That note said this file does not exist on this PC, and that nothing under
# %LOCALAPPDATA%\Ollama or %USERPROFILE%\.ollama\logs matches *.log. Both
# claims were wrong: %LOCALAPPDATA%\Ollama\server.log IS there - created
# 2026-09-02, 894,789 bytes at 09:48 that morning, 905,644 bytes by 10:24 and
# still growing as Ollama answers requests - and it holds both of these lines:
#
#     load_tensors: offloaded 37/37 layers to GPU
#     llama_context: flash_attn            = auto
#
# The lesson is worth more than the correction, so it stays written down here:
# **a search that returns nothing does not prove a file is absent.** It says
# only that THAT search did not find it. The file can be somewhere else, or
# named something else, or the search can simply have looked at too little of
# it - and that last one is a real trap with this log, which only ever grows.
#
# So `ollama ps` leads: it answers whenever a model is loaded. The log is read
# when it is found (the block below says how much of it was read), and when it
# is not found, one plain line says so and nothing is treated as wrong.

Say "6. Ollama's own log   (optional extra)" White
Say ""

$logFile = ""
$logTried = @()
$candidates = @(
    (Join-IfSet $env:LOCALAPPDATA 'Ollama\server.log')
)
$logDirs = @(
    (Join-IfSet $env:LOCALAPPDATA 'Ollama'),
    (Join-IfSet $env:USERPROFILE '.ollama'),
    (Join-IfSet $env:USERPROFILE '.ollama\logs')
)
foreach ($cand in $candidates) {
    if (-not $cand) { continue }
    $logTried += $cand
    if ((Test-Path -LiteralPath $cand -PathType Leaf) -and -not $logFile) { $logFile = $cand }
}
if (-not $logFile) {
    foreach ($dir in $logDirs) {
        if (-not $dir) { continue }
        $logTried += $dir
        if (-not (Test-Path -LiteralPath $dir)) { continue }
        $hit = @(Get-ChildItem -LiteralPath $dir -Filter '*.log' -File -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($hit.Count -gt 0) { $logFile = $hit[0].FullName; break }
    }
}

if (-not $logFile) {
    # One plain line, no warning colour: a missing log is not a fault.
    Say "   No Ollama log file turned up on this PC - looked in:" DarkGray
    foreach ($path in $logTried) { Say ("     " + $path) DarkGray }
    Say "   Measured on 2026-10-05: the log IS on this PC - 905,644 bytes and growing -" DarkGray
    Say "   so a search that finds nothing here means the search did not find it, not" DarkGray
    Say "   that the file is not there. Either way the ollama ps table above is the" DarkGray
    Say "   better evidence, and nothing is missing from this check." DarkGray
    Say ""
} else {
    $readSomething = $true

    # A tail is a WINDOW, not the whole file, and "the file holds none of these
    # lines" is a different fact from "I did not read that far". So: read the
    # whole file when it is a reasonable size (this PC's is about 0.9 MB), and
    # for a very large file read a large tail instead and SAY which window was
    # searched. Select-String streams the file line by line, so even the
    # whole-file read never holds the file in memory.
    $fileBytes = -1
    try { $fileBytes = (Get-Item -LiteralPath $logFile -ErrorAction Stop).Length } catch { $fileBytes = -1 }
    $wholeFileLimit = 64MB
    $tailLines      = 20000
    $logPattern     = 'offloaded \d+/\d+ layers to GPU|flash_attn|inference compute|vram-based default context'
    $readWholeFile  = ($fileBytes -ge 0 -and $fileBytes -le $wholeFileLimit)

    if ($fileBytes -ge 0) {
        Say ("   Reading {0}  ({1:N1} MB)" -f $logFile, ($fileBytes / 1MB)) Gray
    } else {
        Say ("   Reading {0}" -f $logFile) Gray
    }

    $hits = @()
    if ($readWholeFile) {
        $windowSaid = "the whole file"
        try { $hits = @(Select-String -LiteralPath $logFile -Pattern $logPattern -ErrorAction SilentlyContinue | Select-Object -Last 6) } catch { $hits = @() }
    } else {
        $tail = @()
        try { $tail = @(Get-Content -LiteralPath $logFile -Tail $tailLines -ErrorAction SilentlyContinue) } catch { $tail = @() }
        $windowSaid = ("the last {0:N0} lines" -f $tailLines)
        # Fewer lines came back than were asked for, so that tail was the whole
        # file - which means this really can say "the whole file".
        if ($tail.Count -gt 0 -and $tail.Count -lt $tailLines) { $windowSaid = "the whole file" }
        $hits = @($tail | Select-String -Pattern $logPattern | Select-Object -Last 6)
    }

    if ($hits.Count -eq 0) {
        if ($windowSaid -eq "the whole file") {
            Say "   Searched the whole file, and it holds none of the lines worth reading" DarkGray
            Say "   (no 'offloaded N/M layers', no 'flash_attn', no 'inference compute')." DarkGray
            Say "   That is the file's own answer, not a limit of this check. Not a problem -" DarkGray
            Say "   the CONTEXT and PROCESSOR columns above are the answer this check wants." DarkGray
        } else {
            Say ("   Searched {0} - that window holds none of the lines worth" -f $windowSaid) DarkGray
            Say "   reading: no 'offloaded N/M layers', no 'flash_attn', no 'inference" DarkGray
            Say "   compute'. Those lines may still be further back in the file, which this" DarkGray
            Say "   check did NOT read, so this is not the same as the file holding nothing." DarkGray
            Say "   To search the whole file yourself, open it in Notepad and use Find (Ctrl+F)." DarkGray
            Say "   Not a problem either way - the CONTEXT and PROCESSOR columns above are" DarkGray
            Say "   the answer this check wants." DarkGray
        }
    } else {
        Say ("   Searched {0}. The lines worth reading:" -f $windowSaid) DarkGray
        foreach ($hit in $hits) { Say ("     " + $hit.Line) DarkGray }
        Say "   'offloaded N/M layers to GPU' with N = M means the whole model is on the" DarkGray
        Say "   card; a smaller N means part of it is not." DarkGray
    }
    Say ""
}

# ==========================================================================
#   The verdict
# ==========================================================================

$spill = $false
foreach ($m in $found) { if ($m.spill) { $spill = $true } }

$parts = @()
if ($gpus.Count -eq 0) {
    $parts += "the cards could not be read"
} elseif ($gpus.Count -eq 1) {
    $parts += ("one card was read: #{0} {1} ({2} MiB total)" -f $gpus[0].index, $gpus[0].name, $gpus[0].total_mb.ToString('N0'))
} else {
    $cardWords = @()
    foreach ($gpu in $gpus) { $cardWords += ("#{0} {1} ({2} MiB total)" -f $gpu.index, $gpu.name, $gpu.total_mb.ToString('N0')) }
    $parts += ("{0} cards are working - {1}" -f $gpus.Count, ($cardWords -join "; "))
}
if ($found.Count -eq 0) {
    $parts += "no model is loaded, so there is no split to judge"
} else {
    foreach ($m in $found) {
        if ($m.spill) {
            $parts += ("{0} has part of it on the processor - that is the one thing here to fix" -f $m.name)
        } else {
            $where = ""
            if ($modelCard) {
                $where = (" - card #{0}, the {1} GB one" -f $modelCard.index, (Format-CardGb $modelCard.total_mb))
            }
            $parts += ("{0} is entirely on a graphics card{1}" -f $m.name, $where)
        }
    }
}
if ($null -ne $fits) {
    if ($fits) {
        $parts += "16,384 of context fits with room to spare, so you can raise it for longer conversations"
    } else {
        $parts += "16,384 of context would not fit as things stand"
    }
}

Say "In plain words:" White
Say ("  " + ($parts -join "; ") + ".") Gray
Say ""
# "Nothing here needs fixing" is only said when enough was read to judge it.
if ($spill) {
    Say "  Lower the context, or free the card, then run this same check again." Cyan
} elseif ($gpus.Count -gt 0 -and $found.Count -gt 0 -and ($null -eq $fits -or $fits)) {
    Say "  Nothing here needs fixing." Green
} else {
    Say "  This check could not read enough to judge. The lines above say what was" Yellow
    Say "  missing, and it is safe to run again once that is sorted." Yellow
}
Say ""
Say "  Machine : $machine, $osText" DarkGray
if ($ollamaVersion) { Say "  Ollama  : $ollamaVersion" DarkGray }
Say "  What the words mean, and the first measured row: docs\MEASURE-CARDS.md" DarkGray
Say ""

# ==========================================================================
#   -Save: one scoreboard row, and nothing else, ever
# ==========================================================================

$when     = [DateTimeOffset]::Now
$whenText = $when.ToString('yyyy-MM-dd HH:mm zzz')

if (-not $Save) {
    Say "Nothing was written or changed by this check." DarkGray
    Say "Add one scoreboard row with:  -Save" DarkGray
    Say ""
} elseif ($gpus.Count -eq 0 -and $found.Count -eq 0) {
    # Nothing was read, so a row would say nothing - and an empty row in a
    # scoreboard is worse than no row, because it looks like a measurement.
    Say "Nothing could be read, so no scoreboard row was written." Yellow
    Say ""
} else {
    $gpuJson = @()
    foreach ($gpu in $gpus) {
        $gpuJson += [ordered] @{
            index    = $gpu.index
            name     = $gpu.name
            driver   = $gpu.driver
            total_mb = $gpu.total_mb
            used_mb  = $gpu.used_mb
            free_mb  = $gpu.free_mb
        }
    }
    $modelJson = @()
    foreach ($m in $found) {
        $modelJson += [ordered] @{
            name              = $m.name
            size_text         = $m.size_text
            size_mb           = $m.size_mb
            vram_mb           = $m.vram_mb
            on_gpu_percent    = $m.on_gpu_percent
            context           = $m.context
            until             = $m.until
            keep_alive_forever = $m.forever
            on_processor      = $m.spill
        }
    }
    $row = [ordered] @{
        v             = 1
        kind          = 'cards'
        at            = $when.ToUnixTimeSeconds()
        when          = $when.ToString('yyyy-MM-ddTHH:mm:sszzz')
        machine       = $machine
        os            = $osText
        ollama        = $ollamaVersion
        gpus          = $gpuJson
        models        = $modelJson
        context_now   = $(if ($everyday) { $everyday.context } else { $null })
        fits_16k      = $fits
        spare_16k_mb  = $(if ($null -ne $fits) { $spareMiB } else { $null })
        any_on_processor = $spill
    }
    $line = ""
    try { $line = ($row | ConvertTo-Json -Depth 6 -Compress) } catch { $line = "" }

    if (-not $Scoreboard) {
        # The same settings folder speed.jsonl uses: the framework's CONFIG_DIR,
        # else OPENJARVIS_CONFIG_DIR, else ~\.openjarvis.
        $settingsDir = $env:OPENJARVIS_CONFIG_DIR
        if (-not $settingsDir) { $settingsDir = Join-IfSet $env:USERPROFILE '.openjarvis' }
        if ($settingsDir) { $Scoreboard = Join-Path $settingsDir 'cards.jsonl' }
    }

    if (-not $Scoreboard) {
        Say "Could not work out where the Jarvis settings folder is, so no row was" Yellow
        Say "written. Give a path with:  -Save -Scoreboard `"D:\where\cards.jsonl`"" Yellow
        Say ""
    } elseif (-not $line) {
        Say "The scoreboard row could not be built, so nothing was written." Yellow
        Say ""
    } elseif (Add-ScoreboardRow -Path $Scoreboard -Line $line) {
        Say ("One scoreboard row was added to {0}" -f $Scoreboard) Green
        Say "  (one JSON line, append only - the same shape as speed.jsonl, a different" DarkGray
        Say "   file because it is about the cards, not about one answer)" DarkGray
        Say ""
        # The same row, as the markdown line docs\MEASURE-CARDS.md keeps.
        $mdModel = "(none loaded)"
        $mdSize = ""
        $mdProc = ""
        $mdCtx = ""
        $mdUntil = ""
        if ($found.Count -gt 0) {
            $mdModel = $found[0].name
            $mdSize  = $found[0].size_text
            $mdProc  = $found[0].processor
            $mdUntil = $found[0].until
            $mdCtx   = "-"
            if ($found[0].context -gt 0) { $mdCtx = $found[0].context.ToString('N0') }
        }
        $mdCards = @()
        foreach ($gpu in $gpus) {
            $mdCards += ("#{0} {1} {2} MiB" -f $gpu.index, (Short-CardName $gpu.name), $gpu.total_mb.ToString('N0'))
        }
        Say "  Paste this row into docs\MEASURE-CARDS.md (all measured, none calculated):" DarkGray
        Say ("  | {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} |" -f `
             $whenText, $machine, ($mdCards -join "; "), $mdModel, $mdSize, $mdProc, $mdCtx, $mdUntil) White
        Say ""
    } else {
        Say ("Could not write to {0} - nothing else was changed." -f $Scoreboard) Yellow
        Say ""
    }
}

if (-not $readSomething) {
    Say "Neither ollama nor nvidia-smi could be read, so this check has nothing to" Red
    Say "report. Check that both are installed and on PATH, then run it again." Red
    Say ""
    exit 1
}
exit 0
