# ============================================================================
#  TRACKED COPY - THIS IS NOT THE FILE THE OWNER'S PC RUNS.
#
#  The launcher the owner's Windows logon tasks actually run lives outside this
#  repository, at:
#      C:\Users\pcadmin\AppData\Local\JarvisOllama\start-lane.ps1
#
#  This file is a copy of it, kept in the repository so a pull request can SEE
#  what that launcher decides. Before this copy existed, two lines no test could
#  read decided how every preset behaved:
#      $env:CUDA_VISIBLE_DEVICES = $GpuUuid   (which graphics card(s) the lane gets)
#      $env:OLLAMA_MAX_LOADED_MODELS = '1'    (one model at a time)
#  The card itself is not written in this file: each logon task passes it as
#  -GpuUuid, so the task table below is the half of the machine the repository
#  has to record as well.
#
#  EDITING THIS FILE ALONE CHANGES NOTHING ON THE MACHINE. The live copy is a
#  separate file on the owner's Windows profile, and each task names it by
#  absolute path. To change the machine: change the live file or the logon task,
#  and update this copy in the same pull request. tools/check_lane_launcher.py
#  FAILS loudly when the repository copy and the live file differ, and
#  tools/reconcile_live_backend.py refuses a one-step deploy when the
#  repository's lane table asks for more cards than the live logon task grants,
#  printing "2-step deploy: update the lane task" and the exact -GpuUuid value.
#
#  WHY THIS EXISTS (2026-11-18): a pull request changed the repository's lane
#  table to say the everyday lane (port 11436) runs across all three cards. CI
#  was green, but this PC's task passes ONE -GpuUuid, so the launcher sets
#  CUDA_VISIBLE_DEVICES to one card and the lane can never spread a model.
#  Measured that night: loading on 11436 grew the RTX 2060 by 3,713 MiB and the
#  other two cards by 0 MiB each. Nothing in the tree could see it. This copy
#  and its checker are that visibility.
#
#  Everything below the END marker is the live file verbatim. The comparison
#  ignores line-ending style only (git stores this file with LF endings and the
#  live file is LF today). The two TASK and GPU blocks below are compared with
#  the live machine too: keep them a copy of the live truth, never a wish.
#
#  rows: TASK|<task name>|<lane>|<port>|-GpuUuid (comma-separated, in order)|<context>
#  TASK|Jarvis Ollama - Everyday model (RTX 2060)|main|11436|GPU-1ba04124-85de-3b44-bacc-7b7d9f0d8bee|196608
#  TASK|Jarvis Ollama - Coding model (RTX 2080 Super)|coding|11435|GPU-e4283ff2-b412-4e8c-9bae-7e433139e7d6|16384
#
#  rows: GPU|<nvidia-smi index>|<name>|<UUID>   (nvidia-smi -L on this PC, 2026-11-18)
#  GPU|0|NVIDIA GeForce RTX 2060|GPU-1ba04124-85de-3b44-bacc-7b7d9f0d8bee
#  GPU|1|NVIDIA GeForce RTX 2080 SUPER|GPU-1f7e38f5-3447-97fc-0c13-c8c7eaf83313
#  GPU|2|NVIDIA GeForce RTX 2080 SUPER|GPU-e4283ff2-b412-4e8c-9bae-7e433139e7d6
# ============================================================================
# <<< END OF TRACKED-COPY HEADER - EVERYTHING BELOW IS THE LIVE FILE >>>
# start-lane.ps1 - start ONE Ollama server, pinned to ONE graphics card.
#
# Written 2026-10-10 for the owner's Option B pairing:
#   * the everyday model runs on the RTX 2060 12 GB, with a very large context
#   * the coding model runs on the RTX 2080 Super 8 GB, at 16,384
#
# WHY THIS FILE EXISTS RATHER THAN A ONE-LINE COMMAND
#   The two settings that actually pin a model to a card cannot be put on the
#   task's command line as plain variables, and one of them is easy to get
#   wrong in a way that silently uses the OTHER card:
#
#   1. OLLAMA_VULKAN=0 is MANDATORY. CUDA_VISIBLE_DEVICES alone does NOT pin a
#      model: it hides the card from Ollama's CUDA engine, and Ollama then
#      happily loads the model onto the other card through Vulkan instead.
#      Measured on this PC, 2026-10-10.
#   2. CUDA_VISIBLE_DEVICES takes a card UUID (from `nvidia-smi -L`), never an
#      index. Ollama's own device numbering is the REVERSE of nvidia-smi's
#      order on this machine, so an index silently means the other card.
#
#   Run this file again with the same -Port and it does nothing, so a logon
#   task that fires twice can never start two servers fighting over one port.
#
# To see what is running:  C:\Users\pcadmin\AppData\Local\JarvisOllama\health.ps1

[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('main', 'coding')][string]$Lane,
    [Parameter(Mandatory)][int]$Port,
    # nvidia-smi -L  ->  GPU 0: NVIDIA GeForce RTX 2060 (UUID: GPU-1ba04124-...)
    [Parameter(Mandatory)][string]$GpuUuid,
    [Parameter(Mandatory)][int]$ContextLength
)

$ErrorActionPreference = 'Stop'

$Exe        = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
$DefaultSrc = Join-Path $env:USERPROFILE '.lmstudio\models'   # the store in use on 2026-10-10
$StoreFile  = Join-Path $PSScriptRoot 'model-store.txt'
$LogDir     = Join-Path $PSScriptRoot 'logs'

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

function Say([string]$m) {
    Write-Output ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m)
}

# -- 1. already running on this port? then there is nothing to do -----------
try {
    $null = Invoke-RestMethod "http://127.0.0.1:$Port/api/version" -TimeoutSec 3
    Say "$Lane lane already answering on port $Port - leaving it alone."
    exit 0
} catch { }

# -- 2. where are the models? ----------------------------------------------
# Order: whatever the PC says now, then the pinned file, then the known store.
# This is what lets the whole setup survive the model store being moved to
# D:\Jarvis Models\ - a moved store stays found.
# Windows PowerShell 5.1 runs this file (the logon task uses it), so nothing
# here may use a PowerShell 7-only spelling: no `??`, no `?:`, and an `if`
# cannot stand in as an expression inside an array.
$PinnedSrc = ''
if (Test-Path $StoreFile) { $PinnedSrc = (Get-Content $StoreFile -Raw).Trim() }

$models = $null
foreach ($candidate in @($env:OLLAMA_MODELS, $PinnedSrc, $DefaultSrc)) {
    if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
    if (Test-Path (Join-Path $candidate 'manifests')) { $models = $candidate; break }
}
if (-not $models) {
    Say "FATAL: no Ollama model store found. Looked at OLLAMA_MODELS, $StoreFile and $DefaultSrc."
    Say "Nothing was started, so the other lane is untouched."
    exit 1
}
Say "model store: $models"

# -- 3. the settings that pick the card ------------------------------------
$env:OLLAMA_MODELS         = $models
$env:OLLAMA_HOST           = "127.0.0.1:$Port"
$env:CUDA_VISIBLE_DEVICES  = $GpuUuid
$env:OLLAMA_VULKAN         = '0'          # the line that makes the pin real

# One model per card, held in memory, always this card's lane.
$env:OLLAMA_CONTEXT_LENGTH = "$ContextLength"
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:OLLAMA_KV_CACHE_TYPE  = 'q8_0'
$env:OLLAMA_KEEP_ALIVE     = '-1'
$env:OLLAMA_NUM_PARALLEL   = '1'
$env:OLLAMA_NO_CLOUD       = '1'          # rule 1: the local model never leaves this PC
$env:LLAMA_ARG_CACHE_RAM   = '3072'       # Q3 2026-11-09: cap the engine prompt cache in system RAM at 3 GB

Say "starting '$Lane': port=$Port gpu=$GpuUuid ctx=$ContextLength vulkan=$($env:OLLAMA_VULKAN)"
Say "logging to $LogDir\$Lane.log"

# Ollama writes its INFO log lines to STDERR, not stdout. With
# $ErrorActionPreference = 'Stop', PowerShell treats the first of those lines
# as a terminating NativeCommandError and kills this script - the server dies
# before it can even bind the port, leaving an empty log and exit code 1.
# That is exactly what happened on the first two runs of this file, so the
# redirection below merges both streams into the log file and the strict
# preference is relaxed for the one call that is SUPPOSED to keep running.
$ErrorActionPreference = 'Continue'
& $Exe serve *> (Join-Path $LogDir "$Lane.log")
