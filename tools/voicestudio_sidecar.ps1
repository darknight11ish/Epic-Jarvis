<#
.SYNOPSIS
    Start, stop or look at VoiceStudio - a SEPARATE voice program on this PC.

.DESCRIPTION
    VoiceStudio is not part of Jarvis and none of its code is in this
    repository (it is AGPL-3.0; see docs/VOICESTUDIO.md). It is an EXTERNAL
    program, installed where its owner put it, and Jarvis only ever talks to
    it over 127.0.0.1:11439. This script is the only thing that starts it.

    It starts it ON DEMAND and never on boot: there is no service, no
    scheduled task and no logon entry. It was measured at 32.06 s to be ready
    on a first start and 16.66 s on a later one, and it takes about 1.95 GB of
    the 8 GB graphics card - so it is started when it is needed, and `-Stop`
    releases it again.

    Three actions:

      -Status   read-only: is it listening, is it healthy, what has it loaded,
                which card has how much free graphics memory. The default.
      -Start    start it, pinned to the RTX 2080 SUPER, and wait for /health.
      -Stop     stop the process this script's -Start started. Nothing else.

    THE GRAPHICS CARD RULE, WHICH THIS SCRIPT ENFORCES. It pins the program to
    the RTX 2080 SUPER by UUID (found with `nvidia-smi -L`), so it can never
    end up on the RTX 2060 that holds the everyday model. It refuses to start
    while the 2080 has less than $VRAM_FLOOR_MIB of free memory, and it never
    unloads anything itself: when a Jarvis model is in the way it prints the
    one exact command for the 11435 lane that the OWNER can run, and stops.

    WHAT IT NEVER DOES: it does not touch Ollama, it does not unload a model,
    it does not install or download anything, it does not accept a model
    licence, and it never sets a machine-wide environment variable. Every
    environment value below is process-local, so nothing is left behind.

    Windows PowerShell 5.1 is the target (the owner's own shell): no `??`, no
    `?:`, ASCII only.

.PARAMETER VoiceStudioPath
    The external VoiceStudio install: the folder holding `backend\main.py`
    and `.venv\Scripts\python.exe`. Default D:\VoiceStudio. It must NOT be
    inside this repository: an AGPL-3.0 program is never committed here.

.PARAMETER DataPath
    Where VoiceStudio keeps its settings and database. Default
    <VoiceStudioPath>\data, which keeps everything in one external folder.

.PARAMETER CachePath
    Where its model weights live (needs about 4 GB free the first time).
    Default <VoiceStudioPath>\hf_cache.

.PARAMETER WaitSeconds
    How long -Start waits for /health before it reports where it is stuck.
    Default 60; a first start measured 32.06 s.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\voicestudio_sidecar.ps1 -Status

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\voicestudio_sidecar.ps1 -Start

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\voicestudio_sidecar.ps1 -Stop
#>
[CmdletBinding()]
param(
    [switch]$Start,
    [switch]$Stop,
    [switch]$Status,
    [string]$VoiceStudioPath = 'D:\VoiceStudio',
    [string]$DataPath = '',
    [string]$CachePath = '',
    [string]$PythonPath = '',
    [int]$WaitSeconds = 60
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# The measured numbers this script is built around (2026-11-04, this PC;
# docs/VOICESTUDIO.md carries the table and VOICESTUDIO-EVAL/MEASURE/RESULTS.md
# is the raw evidence).
#
# THE VRAM FLOOR, and where 5,200 comes from. It is a MEASURED floor, not a
# round guess:
#   * Measured CONTENTION state: with Jarvis's own two models resident, the
#     2080 SUPER had 2,245-2,335 MiB free before the start, the run paged
#     ~1.9 GB of the sidecar into system RAM, and the box peaked at 382 MiB
#     free (RESULTS.md sections 2 and 4). That state must be refused.
#   * Measured cost of the sidecar: 1,945.3 MB resident (1,855 MiB), a +1,750
#     to +1,900 MiB nvidia-smi delta, on an 8,192 MiB card.
#   * The card's own model in that baseline is qwen3.5:4b at 3,430 MiB
#     (RESULTS.md section 4). Unloading it - the owner's line, below - moves
#     the same measurement's baseline from 5,744-5,893 MiB USED to about
#     2,314-2,463 MiB used, which is roughly 5,729-5,878 MiB FREE.
#   * 5,200 MiB sits far above every figure the contention run recorded and
#     about 530 MiB below the serialised figure, so ordinary desktop use does
#     not block a start but a resident Jarvis model always does.
# So this floor enforces the measured verdict itself: VoiceStudio runs
# INSTEAD of the 2080's model, never beside it. It says which lane is in the
# way and prints the owner's own unload line; it never unloads anything.
# ---------------------------------------------------------------------------
$VRAM_FLOOR_MIB = 5200
$PRODUCT_PORT = 11439
$TARGET_GPU_MATCH = '2080'
$SECOND_CARD_LANE = 11435          # the only lane this script ever names
$EVERYDAY_LANE = 11436             # NEVER touched, not even named in a command
$MEASURED_FIRST_START = 32.06
$MEASURED_LATER_START = 16.66
$MEASURED_RESIDENT_MB = 1945.3

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO_ROOT = Split-Path -Parent $SCRIPT_DIR

# ---------------------------------------------------------------------------
# Small output helpers. Plain words, and the colour carries the meaning too.
# ---------------------------------------------------------------------------
function Say {
    param([string]$Text = '', [string]$Colour = 'Gray')
    Write-Host $Text -ForegroundColor $Colour
}

function Say-Head {
    param([string]$Text)
    Say ''
    Say ('= ' * 36) 'DarkGray'
    Say ('  ' + $Text) 'Cyan'
    Say ('= ' * 36) 'DarkGray'
}

function Refuse {
    param([string]$Text)
    Say ''
    Say 'REFUSED' 'Red'
    Say $Text 'Red'
}

# ---------------------------------------------------------------------------
# The cards. Everything is read with nvidia-smi; nothing is changed.
# ---------------------------------------------------------------------------
function Get-Gpus {
    $exe = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if ($null -eq $exe) {
        return @{ Ok = $false; Why = 'nvidia-smi was not found, so this PC''s cards cannot be read.'; Gpus = @() }
    }
    $lines = @(& nvidia-smi --query-gpu=index,uuid,name,memory.total,memory.used,memory.free --format=csv,noheader,nounits 2>$null)
    if ($LASTEXITCODE -ne 0 -or $lines.Count -eq 0) {
        return @{ Ok = $false; Why = 'nvidia-smi did not answer, so this PC''s cards cannot be read.'; Gpus = @() }
    }
    $gpus = @()
    foreach ($line in $lines) {
        $parts = @($line -split ',' | ForEach-Object { $_.Trim() })
        if ($parts.Count -lt 6) { continue }
        $gpus += [pscustomobject]@{
            Index = [int]$parts[0]
            Uuid  = [string]$parts[1]
            Name  = [string]$parts[2]
            Total = [int]$parts[3]
            Used  = [int]$parts[4]
            Free  = [int]$parts[5]
        }
    }
    return @{ Ok = $true; Why = ''; Gpus = $gpus }
}

function Get-TargetGpu {
    param($Gpus)
    # NOT $matches: that is a PowerShell automatic variable.
    $found = @($Gpus | Where-Object { $_.Name -like ('*' + $TARGET_GPU_MATCH + '*') })
    if ($found.Count -eq 1) {
        return @{ Ok = $true; Gpu = $found[0]; Why = '' }
    }
    if ($found.Count -eq 0) {
        $listing = (@(& nvidia-smi -L 2>$null) -join '; ')
        return @{ Ok = $false; Gpu = $null; Why = ('No card whose name contains "' + $TARGET_GPU_MATCH + '" is installed. `nvidia-smi -L` says: ' + $listing + '. This script will not fall back to another card: the RTX 2060 holds the everyday model and must never be touched.') }
    }
    return @{ Ok = $false; Gpu = $null; Why = ('More than one card matches "' + $TARGET_GPU_MATCH + '", so this script will not choose one. `nvidia-smi -L` says: ' + ((@(& nvidia-smi -L 2>$null)) -join '; ')) }
}

# ---------------------------------------------------------------------------
# The port and the program on it.
# ---------------------------------------------------------------------------
function Get-PortListener {
    $conn = @(Get-NetTCPConnection -LocalPort $PRODUCT_PORT -State Listen -ErrorAction SilentlyContinue)
    if ($conn.Count -eq 0) {
        return @{ Listening = $false; Pid = 0; Address = '' }
    }
    return @{ Listening = $true; Pid = [int]$conn[0].OwningProcess; Address = [string]$conn[0].LocalAddress }
}

function Get-ProcessWords {
    param([int]$ProcessId)
    if ($ProcessId -le 0) { return 'no process' }
    $proc = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $ProcessId) -ErrorAction SilentlyContinue
    if ($null -eq $proc) { return ('process ' + $ProcessId + ' (its command line could not be read)') }
    return ('process ' + $ProcessId + ': ' + $proc.CommandLine)
}

# ---------------------------------------------------------------------------
# Talk to it. Read-only requests only; 503 is an answer, not a failure.
# ---------------------------------------------------------------------------
function Invoke-LocalJson {
    param([string]$Path, [int]$TimeoutSec = 3)
    $uri = 'http://127.0.0.1:' + $PRODUCT_PORT + $Path
    try {
        $body = Invoke-RestMethod -Uri $uri -Method Get -TimeoutSec $TimeoutSec -UseBasicParsing
        return @{ Status = 200; Body = $body; Why = '' }
    }
    catch {
        $code = 0
        if ($null -ne $_.Exception.Response) {
            try { $code = [int]$_.Exception.Response.StatusCode } catch { $code = 0 }
        }
        $text = ''
        if ($null -ne $_.ErrorDetails -and $null -ne $_.ErrorDetails.Message) {
            $text = [string]$_.ErrorDetails.Message
        }
        if ($text -ne '') {
            try {
                $parsed = $text | ConvertFrom-Json
                return @{ Status = $code; Body = $parsed; Why = '' }
            }
            catch { }
        }
        return @{ Status = $code; Body = $null; Why = [string]$_.Exception.Message }
    }
}

# ---------------------------------------------------------------------------
# The refusal a person can act on: which model is in the way, and the ONE
# command for the 11435 lane. This script never runs that command.
# ---------------------------------------------------------------------------
function Show-VramRefusal {
    param($Gpu)

    Refuse ('VoiceStudio needs about 1,855 MiB of free graphics memory on the RTX 2080 SUPER (it reports ' + $MEASURED_RESIDENT_MB + ' MB resident, and a warm call measured a +1,750 to +1,900 MiB delta). This script will not start it with less than ' + $VRAM_FLOOR_MIB + ' MiB free, and the card has ' + $Gpu.Free + ' MiB free right now.')
    Say ''
    Say ('Measured on this PC on 2026-11-04: started with only 2,245-2,335 MiB free, it ran by paging ~1.9 GB into system RAM and left 382 MiB free at the peak. The verdict in the measurement is CONTENTION, so it is not started this way: it runs INSTEAD of a resident Jarvis model, never beside one.') 'Yellow'
    Say ''
    Say 'What is holding the card, and what to do:' 'Cyan'

    $lane = @()
    try {
        $laneResult = Invoke-RestMethod -Uri ('http://127.0.0.1:' + $SECOND_CARD_LANE + '/api/ps') -Method Get -TimeoutSec 2 -UseBasicParsing
        if ($null -ne $laneResult.models) { $lane = @($laneResult.models) }
    }
    catch {
        Say ('  The ' + $SECOND_CARD_LANE + ' lane did not answer, so its own list of loaded models could not be read.') 'Gray'
    }

    if ($lane.Count -eq 0) {
        Say ('  Nothing is loaded on the ' + $SECOND_CARD_LANE + ' lane right now, yet the card still has only ' + $Gpu.Free + ' MiB free - so something else on this PC holds it (a game, a browser with hardware acceleration, or another program). Close that program, then run -Start again.') 'Yellow'
    }
    else {
        $name = [string]$lane[0].name
        $sizeGb = [math]::Round(([double]$lane[0].size / 1GB), 2)
        Say ('  The ' + $SECOND_CARD_LANE + ' lane holds "' + $name + '" (' + $sizeGb + ' GB of the card), and Jarvis keeps it loaded forever.') 'Yellow'
        Say ''
        Say ('  If you want VoiceStudio to have the card, YOU run this one line. It unloads that model from the ' + $SECOND_CARD_LANE + ' lane and nothing else:') 'Cyan'
        $exact = 'Invoke-RestMethod -Uri http://127.0.0.1:' + $SECOND_CARD_LANE + '/api/generate -Method Post -Body (@{ model = ''' + $name + '''; prompt = ''''; keep_alive = 0 } | ConvertTo-Json) -ContentType ''application/json'''
        Say ('    ' + $exact) 'White'
        Say ''
        Say ('  This script does NOT run it, and it never unloads anything itself. The ' + $EVERYDAY_LANE + ' lane (the RTX 2060, the everyday model) is never queried, never unloaded and never named in a command this script prints.') 'Yellow'
    }
    Say ''
    Say 'Then run: powershell -NoProfile -ExecutionPolicy Bypass -File tools\voicestudio_sidecar.ps1 -Start' 'Cyan'
}

# ---------------------------------------------------------------------------
# -Status: read-only. Starts nothing, stops nothing, changes nothing.
# ---------------------------------------------------------------------------
function Show-Status {
    Say-Head 'VoiceStudio - status (read-only, nothing is started or stopped)'

    $gpuInfo = Get-Gpus
    if ($gpuInfo.Ok) {
        Say ''
        Say 'The cards, straight from nvidia-smi (MiB):' 'Cyan'
        foreach ($gpu in $gpuInfo.Gpus) {
            $marker = '        '
            if ($gpu.Name -like ('*' + $TARGET_GPU_MATCH + '*')) { $marker = '  <-- VoiceStudio runs here' }
            Say ('  GPU ' + $gpu.Index + '  ' + $gpu.Name + '  used ' + $gpu.Used + ' / ' + $gpu.Total + '  free ' + $gpu.Free + $marker) 'Gray'
        }
        $target = Get-TargetGpu -Gpus $gpuInfo.Gpus
        if ($target.Ok) {
            Say ''
            $verdict = 'below the ' + $VRAM_FLOOR_MIB + ' MiB floor, so -Start would refuse'
            if ($target.Gpu.Free -ge $VRAM_FLOOR_MIB) { $verdict = 'at or above the ' + $VRAM_FLOOR_MIB + ' MiB floor, so -Start would go ahead' }
            Say ('  ' + $TARGET_GPU_MATCH + ' SUPER free: ' + $target.Gpu.Free + ' MiB - ' + $verdict + '.') 'Yellow'
        }
        else {
            Say ('  ' + $target.Why) 'Red'
        }
    }
    else {
        Say ('  ' + $gpuInfo.Why) 'Red'
    }

    Say ''
    $health = Invoke-LocalJson -Path '/health' -TimeoutSec 3
    if ($null -ne $health.Body -and $health.Body.status -eq 'ok') {
        Say ('Running and ready. ' + $health.Body.device + ', VoiceStudio ' + $health.Body.version + '.') 'Green'
    }
    elseif ($health.Status -eq 503 -or ($null -ne $health.Body -and $health.Body.status -eq 'starting')) {
        $stepLabel = ''
        if ($null -ne $health.Body) {
            if ($null -ne $health.Body.label) { $stepLabel = [string]$health.Body.label }
            elseif ($null -ne $health.Body.step) { $stepLabel = [string]$health.Body.step }
        }
        Say ('Running, still starting: ' + $stepLabel + '. A first start measured ' + $MEASURED_FIRST_START + ' s; a later one ' + $MEASURED_LATER_START + ' s.') 'Yellow'
        $progress = Invoke-LocalJson -Path '/startup/progress' -TimeoutSec 3
        if ($null -ne $progress.Body) {
            if ($null -ne $progress.Body.elapsed_s) {
                Say ('  it says it has been starting for ' + $progress.Body.elapsed_s + ' s.') 'Gray'
            }
        }
    }
    elseif ($health.Status -eq 0) {
        Say ('Not running on 127.0.0.1:' + $PRODUCT_PORT + '. Start it with: powershell -NoProfile -ExecutionPolicy Bypass -File tools\voicestudio_sidecar.ps1 -Start') 'Yellow'
        Say ('  (' + $health.Why + ')') 'DarkGray'
    }
    else {
        Say ('Something is listening on ' + $PRODUCT_PORT + ' but /health answered HTTP ' + $health.Status + ', which is not a healthy answer.') 'Red'
    }

    $listener = Get-PortListener
    if ($listener.Listening) {
        Say ''
        Say ('Listening on ' + $listener.Address + ':' + $PRODUCT_PORT + ' - ' + (Get-ProcessWords -ProcessId $listener.Pid)) 'Gray'
        if ($listener.Address -ne '127.0.0.1') {
            Say '  WARNING: it is not bound to 127.0.0.1. This script only ever binds 127.0.0.1; something else started it.' 'Red'
        }
        $loaded = Invoke-LocalJson -Path '/model/loaded' -TimeoutSec 3
        if ($null -ne $loaded.Body) {
            $count = 0
            if ($null -ne $loaded.Body.count) { $count = [int]$loaded.Body.count }
            if ($count -gt 0) {
                Say ('  Holding ' + $count + ' model(s):') 'Gray'
                foreach ($model in @($loaded.Body.models)) {
                    Say ('    ' + $model.id + '  ' + $model.name + '  ' + $model.vram_mb + ' MB') 'Gray'
                }
            }
            else {
                Say '  Holding no model, so it is not using the card right now.' 'Gray'
            }
        }
    }

    Say ''
    Say ('The measured cost on this PC (2026-11-04): first start ' + $MEASURED_FIRST_START + ' s, later start ' + $MEASURED_LATER_START + ' s, warm call 1.70-1.98 s for ~2.5 s of audio, about 1,945 MB of the card resident, 546 MB of RAM idle, 3.043 GB of weights on disk. Verdict beside Jarvis''s own models: CONTENTION - demand-only, never resident.') 'DarkGray'
}

# ---------------------------------------------------------------------------
# -Start
# ---------------------------------------------------------------------------
function Start-Sidecar {
    Say-Head 'VoiceStudio - start'

    $root = [System.IO.Path]::GetFullPath($VoiceStudioPath)
    $mainPy = Join-Path $root 'backend\main.py'
    if ($PythonPath -eq '') {
        $python = Join-Path $root '.venv\Scripts\python.exe'
    }
    else {
        $python = [System.IO.Path]::GetFullPath($PythonPath)
    }

    if (-not (Test-Path -LiteralPath $root -PathType Container)) {
        Refuse ('There is no VoiceStudio folder at ' + $root + '. This script does not install it: install VoiceStudio yourself, outside this repository, and pass -VoiceStudioPath if it lives somewhere else.')
        return 1
    }
    if (-not (Test-Path -LiteralPath $mainPy -PathType Leaf)) {
        Refuse ('No backend\main.py under ' + $root + ', so that folder is not a VoiceStudio install. Pass -VoiceStudioPath with the folder that holds backend\main.py.')
        return 1
    }
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        Refuse ('There is no .venv\Scripts\python.exe under ' + $root + '. VoiceStudio''s own install document creates it (uv sync --locked); this script does not install or download anything.')
        return 1
    }
    if ($root.TrimEnd('\').ToLower().StartsWith($REPO_ROOT.TrimEnd('\').ToLower())) {
        Refuse ('That VoiceStudio folder is INSIDE this git repository (' + $REPO_ROOT + '). VoiceStudio is AGPL-3.0 and its code must never be committed here. Move it outside the repository, for example to D:\VoiceStudio, and run this again.')
        return 1
    }

    $listener = Get-PortListener
    if ($listener.Listening) {
        Say ('Something is already listening on ' + $PRODUCT_PORT + ' - ' + (Get-ProcessWords -ProcessId $listener.Pid)) 'Yellow'
        Say 'Nothing was started. Run -Status to see what it is, or -Stop if it is VoiceStudio.' 'Yellow'
        return 0
    }

    $gpuInfo = Get-Gpus
    if (-not $gpuInfo.Ok) {
        Refuse $gpuInfo.Why
        return 1
    }
    $target = Get-TargetGpu -Gpus $gpuInfo.Gpus
    if (-not $target.Ok) {
        Refuse $target.Why
        return 1
    }
    if ($target.Gpu.Free -lt $VRAM_FLOOR_MIB) {
        Show-VramRefusal -Gpu $target.Gpu
        return 1
    }

    $dataDir = $DataPath
    if ($dataDir -eq '') { $dataDir = Join-Path $root 'data' }
    $cacheDir = $CachePath
    if ($cacheDir -eq '') { $cacheDir = Join-Path $root 'hf_cache' }
    $dataDir = [System.IO.Path]::GetFullPath($dataDir)
    $cacheDir = [System.IO.Path]::GetFullPath($cacheDir)
    foreach ($pair in @(@('data', $dataDir), @('model cache', $cacheDir))) {
        try {
            if (-not (Test-Path -LiteralPath $pair[1] -PathType Container)) {
                New-Item -ItemType Directory -Path $pair[1] -Force | Out-Null
            }
        }
        catch {
            Refuse ('The ' + $pair[0] + ' folder could not be created at ' + $pair[1] + ' (' + $_.Exception.Message + '). Nothing was started.')
            return 1
        }
    }
    $log = Join-Path $dataDir 'voicestudio-start.log'
    $errLog = Join-Path $dataDir 'voicestudio-start.err.log'
    $tmpDir = Join-Path $dataDir 'tmp'
    $mplDir = Join-Path $tmpDir 'mpl'
    foreach ($dir in @($tmpDir, $mplDir)) {
        if (-not (Test-Path -LiteralPath $dir -PathType Container)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
    }

    Say ''
    Say ('Pinned to the ' + $TARGET_GPU_MATCH + ' SUPER (' + $target.Gpu.Uuid + '); ' + $target.Gpu.Free + ' MiB free, floor ' + $VRAM_FLOOR_MIB + ' MiB.') 'Gray'
    Say ('Bound to 127.0.0.1:' + $PRODUCT_PORT + ' only. Data: ' + $dataDir + '. Weights: ' + $cacheDir + '.') 'Gray'

    # PROCESS-LOCAL ONLY. None of these is saved anywhere: they exist for this
    # shell and the child it starts, exactly as the measurement did it.
    $env:CUDA_VISIBLE_DEVICES = $target.Gpu.Uuid
    $env:OMNIVOICE_HOST = '127.0.0.1'
    $env:OMNIVOICE_PORT = [string]$PRODUCT_PORT
    $env:OMNIVOICE_DATA_DIR = $dataDir
    $env:OMNIVOICE_CACHE_DIR = $cacheDir
    $env:OMNIVOICE_ENV_FILE = (Join-Path $dataDir 'omnivoice-env')
    $env:HF_HOME = $cacheDir
    $env:HF_HUB_CACHE = $cacheDir
    $env:TORCH_HOME = $cacheDir
    $env:MPLCONFIGDIR = $mplDir
    $env:TMP = $tmpDir
    $env:TEMP = $tmpDir
    $env:OMNIVOICE_TTS_BACKEND = 'omnivoice'

    $arguments = @('-m', 'uvicorn', 'main:app', '--app-dir', 'backend', '--host', '127.0.0.1', '--port', [string]$PRODUCT_PORT)
    try {
        $process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput $log -RedirectStandardError $errLog
    }
    catch {
        Refuse ('VoiceStudio could not be started (' + $_.Exception.Message + '). Nothing was changed; the log would have been ' + $log + '.')
        return 1
    }

    Say ''
    Say ('Started process ' + $process.Id + '. Waiting for it to be ready; a first start measured ' + $MEASURED_FIRST_START + ' s and a later one ' + $MEASURED_LATER_START + ' s.') 'Cyan'
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    $lastWords = ''
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 1
        $health = Invoke-LocalJson -Path '/health' -TimeoutSec 2
        if ($null -ne $health.Body -and $health.Body.status -eq 'ok') {
            Say ''
            Say ('Ready. ' + $health.Body.device + ', VoiceStudio ' + $health.Body.version + '.') 'Green'
            Say ('Still process-local: nothing was added to your environment, no service and no scheduled task was created, and nothing on the ' + $EVERYDAY_LANE + ' lane was touched.') 'Gray'            Say ''
            Say ('It is DEMAND-ONLY: use -Stop when you are done, or let it idle. Its own idle unload is meant to release about 1.9 GB after 900 s by its own setting - that path was NOT observed during the measurement, so -Stop is the one that is proved.') 'Cyan'
            Say ('Next start from a warm cache measured ' + $MEASURED_LATER_START + ' s.') 'DarkGray'
            return 0
        }
        if ($null -ne $health.Body) {
            $words = ''
            if ($null -ne $health.Body.label) { $words = [string]$health.Body.label }
            elseif ($null -ne $health.Body.step) { $words = [string]$health.Body.step }
            if ($words -ne '' -and $words -ne $lastWords) {
                Say ('  still starting: ' + $words) 'Yellow'
                $lastWords = $words
            }
        }
        if ($null -eq $health.Body -and $health.Status -eq 0) {
            $procNow = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
            if ($null -eq $procNow) {
                Refuse ('It exited before it was ready. Nothing is left running. The last lines of ' + $errLog + ' say why; run -Status for the rest.')
                return 1
            }
        }
    }

    Refuse ('It did not answer /health within ' + $WaitSeconds + ' s. Process ' + $process.Id + ' is still running. Check -Status, and read ' + $log + ' and ' + $errLog + '. If it must go, -Stop stops the process this script started.')
    return 1
}

# ---------------------------------------------------------------------------
# -Stop: only the process this script started, proved by its own command line.
# ---------------------------------------------------------------------------
function Stop-Sidecar {
    Say-Head 'VoiceStudio - stop'

    $listener = Get-PortListener
    if (-not $listener.Listening) {
        Say ('Nothing is listening on ' + $PRODUCT_PORT + ', so there is nothing to stop.') 'Green'
        return 0
    }

    $root = [System.IO.Path]::GetFullPath($VoiceStudioPath)
    $proc = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $listener.Pid) -ErrorAction SilentlyContinue
    $commandLine = ''
    if ($null -ne $proc) { $commandLine = [string]$proc.CommandLine }

    if ($commandLine -eq '' -or -not $commandLine.ToLower().Contains($root.TrimEnd('\').ToLower())) {
        Refuse ('Something is listening on ' + $PRODUCT_PORT + ' and its command line does not contain ' + $root + ', so it is not the VoiceStudio this script started. This script will not stop a program it did not start.')
        Say ('  ' + (Get-ProcessWords -ProcessId $listener.Pid)) 'Gray'
        Say '  Nothing was stopped. If it is VoiceStudio, close it from its own window.' 'Yellow'
        return 1
    }

    Say ('Stopping process ' + $listener.Pid + ' (started from ' + $root + ').') 'Cyan'
    try {
        Stop-Process -Id $listener.Pid -Force
    }
    catch {
        Refuse ('The process could not be stopped (' + $_.Exception.Message + ').')
        return 1
    }
    Start-Sleep -Seconds 1
    $after = Get-PortListener
    if ($after.Listening) {
        Refuse ('Something is still listening on ' + $PRODUCT_PORT + ' after the stop. Run -Status.')
        return 1
    }
    Say ''
    Say ('Stopped. ' + $PRODUCT_PORT + ' is free again, and the graphics card it was holding is released.') 'Green'
    Say 'Nothing else was touched: no Ollama lane was unloaded, no model on either card was changed, and no setting was written.' 'Gray'
    return 0
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
$actions = 0
if ($Start) { $actions = $actions + 1 }
if ($Stop) { $actions = $actions + 1 }
if ($Status) { $actions = $actions + 1 }
if ($actions -gt 1) {
    Refuse 'Choose ONE of -Start, -Stop or -Status.'
    exit 2
}

Say ''
Say ('VoiceStudio sidecar - a separate program on this PC, talked to at 127.0.0.1:' + $PRODUCT_PORT + ' only.') 'White'

if ($Start) {
    $code = Start-Sidecar
    exit $code
}
if ($Stop) {
    $code = Stop-Sidecar
    exit $code
}
if ($Status) {
    Show-Status
    exit 0
}

Say '(No action was given, so this is the read-only status. Add -Start or -Stop to change something.)' 'DarkGray'
Show-Status
exit 0
