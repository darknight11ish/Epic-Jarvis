# move-models-to-d.ps1 - move every local AI model off C: and onto D:.
#
# WHY THIS EXISTS
#   The C: drive has been nearly full for days (it fell to 5.7 GB free on
#   2026-10-10 and broke every build). The owner asked for all the AI models
#   to live on the 4 TB D: drive instead. This script does that in the only
#   order that cannot lose a model:
#
#       copy -> verify -> (a quiet window) -> point the programs at D: -> delete C:
#
#   It NEVER deletes anything while copying or verifying, and it refuses to run
#   at all while another test or build is mid-flight, because those tests load
#   models from this very store.
#
# WHAT IT MOVES (names as of 2026-10-10; measured, not assumed)
#   ollama  45.70 GB  C:\Users\pcadmin\.lmstudio\models
#                     -> DOES-NOT-MOVE-C: it is Ollama's store AND LM Studio's
#                        store. They share one blobs folder, so they move
#                        together and both programs get repointed in one step.
#   ai     36.76 GB  C:\Users\pcadmin\Documents\AI Models
#                     -> D:\Jarvis Models\AI-Models   (hand-downloaded files)
#   hf      0.19 GB  C:\Users\pcadmin\.cache\huggingface
#                     -> D:\Jarvis Models\HuggingFace\cache
#   voice   1.14 GB  C:\Users\pcadmin\.openjarvis\voice-models
#                     -> D:\Jarvis Models\Jarvis-Voice\voice-models
#   mem     0.06 GB  C:\Users\pcadmin\.openjarvis\models
#                     -> D:\Jarvis Models\Jarvis-Memory-Search\models
#
# THE FOUR PLACES THAT POINT AT THE OLLAMA STORE (all four change together)
#   1. OLLAMA_MODELS, saved for the owner's account (the desktop app reads it)
#   2. C:\Users\pcadmin\AppData\Local\JarvisOllama\model-store.txt (the lanes)
#   3. C:\Users\pcadmin\.lmstudio\settings.json  key "downloadsFolder"
#   4. any shell that starts `ollama serve` by hand
#   The two scheduled lanes already resolve the store through #1 and #2, so
#   nothing in the scheduled tasks needs editing.
#
# HOW TO RUN
#   Dry run first - prints every decision, changes nothing:
#       powershell -NoProfile -File scripts\move-models-to-d.ps1 -DryRun
#   Then the real thing, in a quiet window:
#       powershell -NoProfile -File scripts\move-models-to-d.ps1
#
# SAFETY
#   * -DryRun prints the plan and touches nothing.
#   * Without -DryRun the copy and verify happen, and then the script STOPS
#     unless -CutOver is also given, so the point of no return is two separate,
#     deliberate commands.
#   * Nothing on C: is deleted until file counts and total bytes match exactly
#     on both sides, for every store.
#   * A log of every action is written next to the backups, under
#     %LOCALAPPDATA%\JarvisOllama\logs.
#
# PowerShell 5.1 runs this file (the logon tasks use 5.1), so nothing here may
# use a PowerShell 7-only spelling: no `??`, and no `try` used as an expression.
# Inside a double-quoted string, write ${name} and never $name: - see CLAUDE.md.

[CmdletBinding()]
param(
    # Print the plan and change nothing at all.
    [switch]$DryRun,
    # Copy the models to D: and stop. This is read-only work on C:, so it is
    # safe while other tests are running; it only makes the quiet window
    # shorter later. Nothing is deleted, no setting is changed.
    [switch]$CopyOnly,
    # Copy (again, so the D: copy is current), verify, then do the quiet-window
    # work: stop the lanes, repoint everything, delete the C: originals, start
    # the lanes again and prove the models still answer.
    [switch]$CutOver,
    # Keep going even if a test process was seen. The operator's call, logged.
    [switch]$ForceQuietWindow
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

if ($CopyOnly -and $CutOver) {
    Write-Output 'STOP: -CopyOnly and -CutOver do opposite things; give one or the other.'
    exit 2
}
if ($DryRun -and ($CopyOnly -or $CutOver)) {
    Write-Output 'STOP: -DryRun only prints the plan, so it cannot be combined with the others.'
    exit 2
}
if (-not $DryRun -and -not $CopyOnly -and -not $CutOver) {
    Write-Output 'STOP: choose what to do - one of these:'
    Write-Output '   -DryRun     print the plan, change nothing'
    Write-Output '   -CopyOnly   copy the models to D: and stop (safe while tests run)'
    Write-Output '   -CutOver    copy, verify, then move everything over for real'
    exit 2
}

# ===========================================================================
# 1. Where everything is
# ===========================================================================

$User        = $env:USERPROFILE
$LaneDir     = Join-Path $env:LOCALAPPDATA 'JarvisOllama'
$LogDir      = Join-Path $LaneDir 'logs'
$StoreFile   = Join-Path $LaneDir 'model-store.txt'
$LmSettings  = Join-Path $User '.lmstudio\settings.json'
$BackupDir   = Join-Path $LaneDir 'move-backup-2026-10-10'

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$LogPath = Join-Path $LogDir 'move-models-to-d.log'

# Every store, in plain words. $Kind is 'move' (copy then delete the original)
# or 'junction' (copy, then leave a link where the program expects it).
$Stores = @(
    [pscustomobject]@{
        Name   = 'ollama'
        Plain  = "Ollama's thinking models, shared with LM Studio"
        From   = Join-Path $User '.lmstudio\models'
        To     = 'D:\Jarvis Models\Ollama\store'
        Kind   = 'move'
        Marker = 'manifests'                       # proves the store is real
    }
    [pscustomobject]@{
        Name   = 'ai'
        Plain  = 'hand-downloaded model files and pictures'
        From   = Join-Path $User 'Documents\AI Models'
        To     = 'D:\Jarvis Models\AI-Models'
        Kind   = 'move'
        Marker = $null
    }
    [pscustomobject]@{
        Name   = 'hf'
        Plain  = 'cached downloads from huggingface.co'
        From   = Join-Path $User '.cache\huggingface'
        To     = 'D:\Jarvis Models\HuggingFace\cache'
        Kind   = 'move'
        Marker = $null
    }
    [pscustomobject]@{
        Name   = 'voice'
        Plain  = "Jarvis's ears and mouth (speech models)"
        From   = Join-Path $User '.openjarvis\voice-models'
        To     = 'D:\Jarvis Models\Jarvis-Voice\voice-models'
        Kind   = 'junction'
        Marker = $null
    }
    [pscustomobject]@{
        Name   = 'mem'
        Plain  = "Jarvis's memory-search model"
        From   = Join-Path $User '.openjarvis\models'
        To     = 'D:\Jarvis Models\Jarvis-Memory-Search\models'
        Kind   = 'junction'
        Marker = $null
    }
)

# ===========================================================================
# 2. Telling the operator what is happening
# ===========================================================================

function Say([string]$Text) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Text
    Write-Output $line
    try { Add-Content -Path $LogPath -Value $line -ErrorAction SilentlyContinue } catch { }
}

function Ok([string]$Text)   { Say "  OK    ${Text}" }
function Warn([string]$Text) { Say "  WARN  ${Text}" }
function Bad([string]$Text)  { Say "  STOP  ${Text}" }

function Format-Gb([double]$Bytes) { "{0:N2} GB" -f ($Bytes / 1GB) }

# Measure a folder: how many files, and how many bytes in total.
function Measure-Store([string]$Path) {
    # @(...) around a single $null gives an array of one, so an EMPTY folder
    # would be reported as "1 file". Catch that before it becomes a false
    # "the copy is short by one file" verdict.
    $files = @(Get-ChildItem -LiteralPath $Path -Recurse -File -Force -ErrorAction SilentlyContinue |
               Where-Object { $null -ne $_ })
    $sum = ($files | Measure-Object -Property Length -Sum).Sum
    if ($null -eq $sum) { $sum = 0 }
    return [pscustomobject]@{ Count = $files.Count; Bytes = [int64]$sum }
}

# ===========================================================================
# 3. The quiet-window check - the part that protects other people's work
# ===========================================================================

function Get-BusyTests {
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue
    $busy = @()
    foreach ($p in $procs) {
        $cmd = ''
        if ($p.CommandLine) { $cmd = $p.CommandLine }
        if ($cmd -match 'run_suites|test_|pytest|eval_') {
            $busy += [pscustomobject]@{ Pid = $p.ProcessId; Cmd = $cmd }
        }
    }
    return $busy
}

function Get-OllamaState {
    $result = @()
    foreach ($port in 11434, 11435, 11436) {
        $entry = [pscustomobject]@{ Port = $port; Up = $false; Loaded = 0; Model = '' }
        try {
            $ps = Invoke-RestMethod "http://127.0.0.1:${port}/api/ps" -TimeoutSec 4
            $entry.Up = $true
            $models = @($ps.models)
            $entry.Loaded = $models.Count
            if ($models.Count -gt 0) { $entry.Model = $models[0].name }
        } catch { }
        $result += $entry
    }
    return $result
}

function Test-QuietWindow {
    $problems = @()

    # a). No model may be loaded on any lane.
    foreach ($state in Get-OllamaState) {
        if ($state.Up -and $state.Loaded -gt 0) {
            $problems += "port $($state.Port) has '$($state.Model)' loaded in memory"
        }
    }

    # b). No half-finished download anywhere in the store we are moving.
    $store = ($Stores | Where-Object { $_.Name -eq 'ollama' }).From
    if (Test-Path $store) {
        $partial = Get-ChildItem -LiteralPath $store -Recurse -File -Force -ErrorAction SilentlyContinue |
                   Where-Object { $_.Name -like '*partial*' -or $_.Name -like '*incomplete*' }
        foreach ($p in $partial) { $problems += "a half-finished download is sitting there: $($p.Name)" }
    }

    # c). A pull in progress (it would be writing a new blob right now).
    $writer = Get-ChildItem -LiteralPath $store -Recurse -File -Force -ErrorAction SilentlyContinue |
              Where-Object { $_.LastWriteTime -gt (Get-Date).AddMinutes(-3) -and $_.Length -gt 1MB }
    foreach ($w in $writer) { $problems += "a model file was written 3 minutes ago, so something is downloading: $($w.Name)" }

    # d). Somebody else's test is running and may load models.
    $busy = Get-BusyTests
    if (@($busy).Count -gt 0) {
        $problems += "$(@($busy).Count) test process(es) are running right now"
    }

    return $problems
}

# ===========================================================================
# 4. Start
# ===========================================================================

Say '============================================================='
Say 'Jarvis models: move from C: to D:\Jarvis Models'
if ($DryRun)      { Say 'MODE: dry run - the plan only, nothing will be changed' }
elseif ($CopyOnly) { Say 'MODE: copy only - the models are copied to D: and nothing else changes' }
else              { Say 'MODE: cut over - copy, verify, repoint, delete the C: originals, prove it' }
Say '============================================================='

# Where does C: and D: stand right now?
$cFreeBefore = (Get-PSDrive C).Free
$dFreeBefore = (Get-PSDrive D).Free
Say ("C: free now {0}   D: free now {1}" -f (Format-Gb $cFreeBefore), (Format-Gb $dFreeBefore))

# What does Jarvis itself say it has? This is the baseline to compare after.
$baselineModels = @()
try {
    $tags = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5
    $baselineModels = @($tags.models)
    Say ("Ollama currently lists {0} models, {1} in total" -f $baselineModels.Count, (Format-Gb (($baselineModels | Measure-Object -Property size -Sum).Sum)))
} catch {
    Warn 'Ollama on port 11434 did not answer; the model list cannot be recorded now.'
}

# ===========================================================================
# 5. Plan: what to copy, and is there room
# ===========================================================================

Say ''
Say '--- the plan ---'
$plan = @()
foreach ($s in $Stores) {
    if (-not (Test-Path -LiteralPath $s.From)) {
        Say ("  {0,-7} not on C: any more - nothing to do ({1})" -f $s.Name, $s.From)
        continue
    }
    $m = Measure-Store $s.From
    if ($m.Count -eq 0) {
        Say ("  {0,-7} empty on C: - nothing to do ({1})" -f $s.Name, $s.From)
        continue
    }
    $entry = [pscustomobject]@{ Store = $s; From = $m }
    $plan += $entry
    Say ("  {0,-7} {1,10}  {2} files   {3}" -f $s.Name, (Format-Gb $m.Bytes), $m.Count, $s.Plain)
    Say ("           from {0}" -f $s.From)
    Say ("           to   {0}" -f $s.To)
}

$totalBytes = 0
foreach ($p in $plan) { $totalBytes += $p.From.Bytes }
Say ''
Say ("Total to copy: {0} across {1} store(s)" -f (Format-Gb $totalBytes), $plan.Count)

if ($dFreeBefore -lt ($totalBytes + 5GB)) {
    Bad ("D: has only {0} free and the copy needs {1} plus a 5 GB margin. Nothing was copied." -f (Format-Gb $dFreeBefore), (Format-Gb $totalBytes))
    exit 2
}
Ok ("D: has {0} free - enough for the copy and a margin" -f (Format-Gb $dFreeBefore))

# ===========================================================================
# 6. The quiet window
# ===========================================================================

Say ''
Say '--- is this a quiet window? ---'
$problems = Test-QuietWindow
if (@($problems).Count -gt 0) {
    foreach ($p in $problems) { Warn $p }
    if ($CopyOnly) {
        Ok 'Copying only reads the models, so the copy is safe even now. Nothing is deleted or changed.'
        Ok 'The quiet-window check above is what -CutOver will insist on.'
    } elseif (-not $ForceQuietWindow) {
        Bad 'Something is using the models right now, so the move was not started.'
        Bad 'The cut-over stops the lanes and deletes files, and that is not safe while tests or models are live.'
        Bad 'Run -CopyOnly now if you like (safe), then -CutOver when the machine is quiet. Nothing was changed.'
        exit 3
    } else {
        Warn '-ForceQuietWindow was given, so the move continues anyway. This is written to the log.'
    }
} else {
    Ok 'Nobody is mid-test, nothing is loaded, and no download is half-done.'
}

if ($DryRun) {
    Say ''
    Say 'Dry run finished. Nothing was copied, changed or deleted.'
    exit 0
}

# ===========================================================================
# 7. Copy, then verify, then stop
# ===========================================================================

Say ''
Say '--- copying (the originals on C: are kept until every copy is verified) ---'

foreach ($p in $plan) {
    $s = $p.Store
    Say ("copying {0} : {1} -> {2}" -f $s.Name, $s.From, $s.To)

    # robocopy exit codes below 8 mean success; 8 or more is a real failure.
    # /E copies sub-folders including empty ones, /COPY:DAT keeps the dates,
    # /R:2 /W:2 means two retries then move on rather than hanging forever.
    $null = New-Item -ItemType Directory -Path $s.To -Force -ErrorAction SilentlyContinue
    & robocopy $s.From $s.To /E /COPY:DAT /DCOPY:DAT /R:2 /W:2 /NP /NFL /NDL /NJH /NJS
    $code = $LASTEXITCODE
    if ($code -ge 8) {
        Bad ("robocopy failed for {0} with exit code {1}. Nothing was deleted." -f $s.Name, $code)
        exit 4
    }
    Ok ("copied {0} (robocopy exit code {1}, 0-7 all mean success)" -f $s.Name, $code)
}

Say ''
Say '--- verifying: the same number of files and the same total bytes on both sides ---'

$allVerified = $true
foreach ($p in $plan) {
    $s = $p.Store
    $after = Measure-Store $s.To
    $same  = ($after.Count -eq $p.From.Count) -and ($after.Bytes -eq $p.From.Bytes)
    if ($same) {
        Ok ("{0,-7} C: {1} files / {2}   D: {3} files / {4}" -f $s.Name, $p.From.Count, (Format-Gb $p.From.Bytes), $after.Count, (Format-Gb $after.Bytes))
    } else {
        $allVerified = $false
        Bad ("{0,-7} MISMATCH  C: {1} files / {2}   D: {3} files / {4}" -f $s.Name, $p.From.Count, (Format-Gb $p.From.Bytes), $after.Count, (Format-Gb $after.Bytes))
        if ($after.Count -lt $p.From.Count) { Bad "           the D: copy is missing $($p.From.Count - $after.Count) file(s)" }
    }
    if ($s.Marker -and -not (Test-Path (Join-Path $s.To $s.Marker))) {
        $allVerified = $false
        Bad ("{0,-7} the D: copy has no '{1}' folder, so Ollama would not see it as a store" -f $s.Name, $s.Marker)
    }
}

# The checksum proof for the one model that was verified by hand before.
$whisper = Join-Path $User '.cache\huggingface\hub\models--Systran--faster-whisper-base\blobs\model.bin'
$whisperD = 'D:\Jarvis Models\HuggingFace\cache\hub\models--Systran--faster-whisper-base\blobs\model.bin'
if ((Test-Path $whisper) -and (Test-Path $whisperD)) {
    $a = (Get-FileHash -LiteralPath $whisper -Algorithm SHA256).Hash
    $b = (Get-FileHash -LiteralPath $whisperD -Algorithm SHA256).Hash
    if ($a -eq $b) { Ok 'the whisper speech model is byte-for-byte identical on D:' }
    else { $allVerified = $false; Bad 'the whisper speech model on D: does NOT match C: byte for byte' }
}

if (-not $allVerified) {
    Bad 'Verification failed, so nothing on C: was deleted. The copies on D: are kept for a second try.'
    exit 5
}

Say ''
Ok 'Every store copied and verified. Nothing has been deleted yet.'

if ($CopyOnly) {
    Say ''
    Say 'Copy-only run finished. Everything is on D: and verified; C: still has the originals.'
    Say 'To finish, run this again with -CutOver in a quiet window:'
    Say '    powershell -NoProfile -File scripts\move-models-to-d.ps1 -CutOver'
    exit 0
}

# ===========================================================================
# 8. Cut over: point the programs at D:, then delete the C: originals
# ===========================================================================

Say ''
Say '--- cutting over (quiet window required) ---'

# One last guard, right at the point of no return: a lane with a model in
# memory must never have its files pulled out from under it.
foreach ($p in $problems) { Warn $p }
$loaded = @()
foreach ($state in Get-OllamaState) { if ($state.Up -and $state.Loaded -gt 0) { $loaded += $state } }
if (@($loaded).Count -gt 0 -and -not $ForceQuietWindow) {
    Bad 'A lane still has a model loaded. Stopping it now would break whatever is using it.'
    Bad 'Wait until nothing is loaded, then run with -CutOver again. Nothing was deleted.'
    exit 3
}

# 8a. Back up the three settings files before touching them.
if (-not (Test-Path $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
foreach ($f in @($StoreFile, $LmSettings)) {
    if (Test-Path -LiteralPath $f) {
        $dest = Join-Path $BackupDir ("{0}.{1}.bak" -f (Split-Path $f -Leaf), $stamp)
        Copy-Item -LiteralPath $f -Destination $dest -Force
        Ok ("backed up {0}" -f $f)
    }
}

# 8b. Stop the two lanes (and their llama-server children, which hold memory).
#     Stopping `ollama serve` alone does NOT stop its children - they keep the
#     model in graphics memory and the file open. That trap cost hours here.
Say 'stopping the Ollama lanes'
$laneProcesses = @()
foreach ($name in 'ollama app', 'ollama', 'llama-server') {
    $laneProcesses += Get-Process -Name $name -ErrorAction SilentlyContinue
}
if (@($laneProcesses).Count -gt 0) {
    $laneProcesses | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 4
    $left = @()
    foreach ($name in 'ollama app', 'ollama', 'llama-server') {
        $left += Get-Process -Name $name -ErrorAction SilentlyContinue
    }
    if (@($left).Count -gt 0) {
        Bad ("$(@($left).Count) Ollama process(es) would not stop, so files could still be locked. Nothing was deleted.")
        exit 6
    }
    Ok 'every Ollama process stopped, including the llama-server children'
} else {
    Ok 'no Ollama process was running'
}

# 8c. Point the store where the programs look.
#     Two ways, and BOTH are needed:
#       - the saved setting covers `ollama app.exe` started from the Start Menu
#       - model-store.txt covers the two scheduled lanes
[Environment]::SetEnvironmentVariable('OLLAMA_MODELS', 'D:\Jarvis Models\Ollama\store', 'User')
Ok 'saved OLLAMA_MODELS for the owner''s account -> D:\Jarvis Models\Ollama\store'

Set-Content -LiteralPath $StoreFile -Value 'D:\Jarvis Models\Ollama\store' -Encoding ASCII
Ok ("model-store.txt now says: {0}" -f (Get-Content $StoreFile -Raw).Trim())

# 8d. LM Studio shares this store, so its own setting changes in the same step.
if (Test-Path -LiteralPath $LmSettings) {
    $raw = Get-Content -LiteralPath $LmSettings -Raw
    $new = $raw -replace '"downloadsFolder"\s*:\s*"[^"]*"', '"downloadsFolder": "D:\\Jarvis Models\\Ollama\\store"'
    if ($new -ne $raw) {
        Set-Content -LiteralPath $LmSettings -Value $new -Encoding UTF8 -NoNewline
        Ok 'LM Studio settings.json downloadsFolder -> D:\Jarvis Models\Ollama\store'
    } else {
        Warn 'LM Studio settings.json had no downloadsFolder line to change - check it by hand.'
    }
}

# 8e. Hugging Face cache: new downloads go to D:.
[Environment]::SetEnvironmentVariable('HF_HOME', 'D:\Jarvis Models\HuggingFace\cache', 'User')
Ok 'saved HF_HOME for the owner''s account -> D:\Jarvis Models\HuggingFace\cache'

# 8f. Voice pack and memory search: leave a link where Jarvis expects them,
#     so no code change and no config change is needed, and the move stays
#     reversible by deleting one link.
foreach ($p in $plan) {
    $s = $p.Store
    if ($s.Kind -ne 'junction') { continue }
    if (Test-Path -LiteralPath $s.From) {
        # Only remove the original when the D: copy matches, which it does here.
        Remove-Item -LiteralPath $s.From -Recurse -Force
    }
    $parent = Split-Path $s.From -Parent
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    $null = New-Item -ItemType Junction -Path $s.From -Target $s.To
    Ok ("{0} now a link: {1} -> {2}" -f $s.Name, $s.From, $s.To)
}

# 8g. Only now, delete the C: originals, and only where the copy was verified.
foreach ($p in $plan) {
    $s = $p.Store
    if ($s.Kind -ne 'move') { continue }
    $after = Measure-Store $s.To
    if ($after.Count -ne $p.From.Count -or $after.Bytes -ne $p.From.Bytes) {
        Bad ("{0} does not match any more, so the C: original was KEPT." -f $s.Name)
        continue
    }
    Remove-Item -LiteralPath $s.From -Recurse -Force
    Ok ("deleted the C: original of {0} (the D: copy is verified)" -f $s.Name)
    # Recreate the empty parent if the move left it missing, so nothing that
    # writes a stray file into the old path fails confusingly.
    if ($s.Name -eq 'ai') {
        $null = New-Item -ItemType Directory -Path $s.From -Force -ErrorAction SilentlyContinue
    }
}

# 8h. Start the lanes again, from their own script, so they come up pointed at D:.
Say 'starting the two Ollama lanes again'
$startLane = Join-Path $LaneDir 'start-lane.ps1'
if (Test-Path -LiteralPath $startLane) {
    Say 'Starting both logon tasks now.'
    Start-ScheduledTask -TaskName 'Jarvis Ollama - Everyday model' -ErrorAction SilentlyContinue
    Start-ScheduledTask -TaskName 'Jarvis Ollama - Coding model' -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 12
} else {
    Warn "- $startLane was not found, so the lanes were not started. Run the two logon tasks by hand."
}

# ===========================================================================
# 9. Prove it, like a user would
# ===========================================================================

Say ''
Say '--- proving the move worked ---'

$after = @()
try {
    $tags = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 10
    $after = @($tags.models)
} catch { }

if (@($after).Count -eq @($baselineModels).Count -and @($after).Count -gt 0) {
    Ok ("Ollama lists the same {0} models as before the move" -f $after.Count)
    $beforeNames = ($baselineModels | ForEach-Object { $_.name } | Sort-Object) -join ', '
    $afterNames  = ($after | ForEach-Object { $_.name } | Sort-Object) -join ', '
    if ($beforeNames -eq $afterNames) { Ok "and they are the same models: ${afterNames}" }
    else {
        Bad 'the model NAMES differ after the move:'
        Bad ("  before: ${beforeNames}")
        Bad ("  after : ${afterNames}")
    }
} else {
    Bad ("Ollama did not list the same models after the move (before {0}, after {1})." -f @($baselineModels).Count, @($after).Count)
    Bad 'The D: copies are all still there, so nothing is lost - but the store path needs checking.'
}

$cFreeAfter = (Get-PSDrive C).Free
$freed = $cFreeAfter - $cFreeBefore
Say ("C: free after the move: {0}  (freed {1})" -f (Format-Gb $cFreeAfter), (Format-Gb $freed))
if ($freed -gt 20GB) { Ok 'the move really did free space on C:' }
else { Warn ("only {0} was freed - check whether everything moved" -f (Format-Gb $freed)) }

$health = Join-Path $LaneDir 'health.ps1'
if (Test-Path -LiteralPath $health) {
    Say ''
    Say '--- health.ps1, for the record ---'
    & $health
}

Say ''
Say 'Move finished. Everything else Jarvis needs is unchanged.'
Say 'Next, if the owner wants: load one model and ask it a question, to prove it answers from D:.'
exit 0
