<#
measure-image-options.ps1 - the numbers the three picture options were missing.

Written for the owner's ask of 2026-10-10/11. Two independent things:

  -Section chat      A's price: seconds to unload the everyday chat off the
                     12 GB card and seconds to bring it back at 196,608
                     tokens. B's price: the largest num_ctx the same model
                     holds on the 8 GB card with NOTHING spilled.
  -Section pictures  Three draws per option, median seconds, peak VRAM, and
                     whether a picture really came out.

WHY THIS IS NOT THE SIBLING'S SCRIPT
  measure-picture-cards.ps1 decides "zero spill" from /api/ps alone
  (size_vram == size). Ollama's own note is not proof: on this machine a model
  has reported perfect VRAM residency while llama.cpp's own log showed a
  non-zero CUDA_Host model buffer size. So every load here also reads the
  runner's own log line and nvidia-smi, and both are written into the row.

WHY A PRIVATE SERVER AND NOT THE OWNER'S
  The owner's own second-card lanes (11435, 11436) are the live install's -
  this script never starts, stops or reconfigures them. It runs its own
  `ollama serve` on 11445 (12 GB card) / 11446 (8 GB card), each pinned by the
  card's UUID with OLLAMA_VULKAN=0, and stops it afterwards. Never by device
  number: the numbers are reversed on this PC and CUDA_VISIBLE_DEVICES alone
  silently falls back to Vulkan on the other card.

  Before every section it checks /api/ps on 11430-11460 and nvidia-smi's
  compute apps, and REFUSES to measure while a foreign model is resident - two
  models loading at once already produced a 7x-wrong number in this project.
#>
param(
  [ValidateSet('chat', 'pictures', 'cards')][string]$Section = 'chat',
  [ValidateSet('A', 'B', 'C')][string]$Option = 'A',
  [string]$Model = 'qwen3.5:9b',
  [string]$Store = 'D:\Jarvis Models\Ollama\store',
  [string]$LiveBackend = 'C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program',
  [string]$PyExe = 'C:\Users\pcadmin\AppData\Local\Programs\Python\Python312\python.exe',
  [string]$Out = 'D:\Jarvis\ImageGen\logs',
  [int]$BigPort = 11445,          # private, pinned to the 12 GB card (2060)
  [int]$SmallPort = 11446,        # private, pinned to the 8 GB card (2080S)
  [int]$LongCtx = 196608,
  [int[]]$Sweep = @(65536, 49152, 32768, 24576, 16384, 12288, 8192, 6144, 4096, 3072, 2048, 1536, 1024),
  [int]$Width = 1024, [int]$Height = 1024, [int]$Steps = 20, [int]$Seed = 12345,
  [string]$Prompt = 'a red panda sitting on a mossy rock, soft morning light',
  [string]$Negative = 'greyscale unfinished sketch, bad proportions, featureless, disfigured, blurry, ugly, watermarks, signatures, smudged, leaking colors',
  [int]$ResidentChatCtx = 0,      # for B: hold the everyday chat on the 8 GB card at this ctx while the picture is drawn
  [int]$Runs = 3
)
$ErrorActionPreference = 'Continue'
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$stamp = Get-Date -Format 'yyyy-MM-dd-HHmmss'
$rows = New-Object System.Collections.Generic.List[object]
$ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if (-not $ollama) { $ollama = 'C:\Users\pcadmin\AppData\Local\Programs\Ollama\ollama.exe' }
$py = 'D:\Jarvis\ImageGen\venv\Scripts\python.exe'

function Row($section, $what, $value, $note) {
  $script:rows.Add([pscustomobject]@{ section = $section; what = $what; value = $value; note = $note })
  Write-Host ("  {0,-9} {1,-48} {2,16}   {3}" -f $section, $what, $value, $note)
}
function Say($m) { Write-Host ("[{0:HH:mm:ss}] {1}" -f (Get-Date), $m) }

# ---------------------------------------------------------------- cards -----
function Get-Cards {
  $uuid = @{}
  foreach ($line in (nvidia-smi -L)) {
    if ($line -match 'GPU\s+(\d+):\s+(.*?)\s+\(UUID:\s*(GPU-[0-9a-fA-F-]+)\)') {
      $uuid[[int]$Matches[1]] = @{ name = $Matches[2].Trim(); uuid = $Matches[3] }
    }
  }
  $cards = @()
  foreach ($row in (nvidia-smi --query-gpu=index,memory.total,memory.used --format=csv,noheader,nounits)) {
    $p = $row -split ','
    $i = [int]$p[0].Trim()
    $cards += [pscustomobject]@{
      index = $i; name = $uuid[$i].name; uuid = $uuid[$i].uuid
      total_mb = [int]$p[1].Trim(); used_mb = [int]$p[2].Trim()
    }
  }
  return ($cards | Sort-Object total_mb)
}
function Used-On($card) {
  $r = nvidia-smi --query-gpu=index,memory.used --format=csv,noheader,nounits | Where-Object { $_ -match "^$($card.index)," }
  if ($r) { return [int](($r -split ',')[1].Trim()) }
  return -1
}

# --------------------------------------------------- is a foreign model on? -
$script:MyPorts = @()
function Get-Resident {
  $resident = @()
  foreach ($port in 11430..11460) {
    try {
      $ps = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/ps" -TimeoutSec 1 -ErrorAction Stop
      foreach ($m in $ps.models) {
        $resident += [pscustomobject]@{
          port = $port; name = $m.name; size = $m.size; vram = $m.size_vram
          ctx = $m.context_length; spill = ($m.size - $m.size_vram)
        }
      }
    } catch { }
  }
  return $resident
}
function Show-Resident($label) {
  $r = Get-Resident
  if ($r.Count -eq 0) { Row 'state' "${label}: models resident" 'none' 'every model port is empty' }
  else {
    foreach ($m in $r) {
      Row 'state' "${label}: port $($m.port)" $m.name ("ctx $($m.ctx); vram $($m.vram); size $($m.size); /api/ps spill $($m.spill) bytes")
    }
  }
  $apps = nvidia-smi --query-compute-apps=pid,process_name,used_memory,gpu_uuid --format=csv,noheader |
    Where-Object { $_ -match 'llama|ollama|python|comfy' }
  if ($apps) { foreach ($a in $apps) { Row 'state' "${label}: nvidia-smi compute app" (($a -split ',')[0].Trim()) ($a.Trim()) } }
  else { Row 'state' "${label}: nvidia-smi compute apps" 'none of ours' 'no llama/ollama/python process on a card' }
}
function Assert-Quiet {
  $busy = Get-Resident | Where-Object { $script:MyPorts -notcontains $_.port }
  if ($busy) {
    Write-Host ""
    Write-Host "  REFUSING TO MEASURE: a foreign model is resident on a card." -ForegroundColor Red
    $busy | ForEach-Object { Write-Host ("    port {0}  {1}  ctx {2}  spill {3:N0} bytes" -f $_.port, $_.name, $_.ctx, $_.spill) -ForegroundColor Red }
    return $false
  }
  return $true
}

# ------------------------------------------------------- private ollama -----
# The environment is not guessed: it is the live product's own lane_env(), from
# the live backend folder, so the private server sees exactly what a real
# second-card lane sees - OLLAMA_KV_CACHE_TYPE=q8_0 (the cache format the whole
# model topology is budgeted in), one model at a time, one parallel slot, the
# lane's own context, Vulkan off, the card pinned by UUID.
function Get-LaneEnv($uuid, $port, $ctx) {
  $code = "import json,sys,os;sys.path.insert(0,r'$LiveBackend');os.environ['OLLAMA_MODELS']=r'$Store';" +
          "import jarvis_second_card as sc;" +
          "print(json.dumps(sc.lane_env('$uuid',port=$port,num_ctx=$ctx,base=os.environ,flash=sc._flash_setting())))"
  $out = ($code | & $PyExe -) 2>&1
  try { return ($out | ConvertFrom-Json) } catch { return $null }
}
function Apply-LaneEnv($dict) {
  foreach ($k in (Get-ChildItem Env: | Where-Object { $_.Name -like 'OLLAMA_*' } | Select-Object -ExpandProperty Name)) {
    Remove-Item "Env:\$k" -ErrorAction SilentlyContinue
  }
  if (-not $dict) { return }
  foreach ($prop in $dict.PSObject.Properties) {
    if ($prop.Name -like 'OLLAMA_*' -or $prop.Name -like 'CUDA_*') {
      Set-Item -Path "Env:\$($prop.Name)" -Value ([string]$prop.Value)
    }
  }
  Set-Item -Path 'Env:\OLLAMA_DEBUG' -Value '1'   # measurement only: so the runner's own lines are written down
}
function Start-Private($card, $port, $tag, $ctxForServer) {
  if (-not $card) { return $null }
  $envDict = Get-LaneEnv $card.uuid $port $ctxForServer
  if (-not $envDict) { Write-Host "  could not build the lane env for $port" -ForegroundColor Red; return $null }
  Apply-LaneEnv $envDict
  Row 'env' "private server $tag (port $port)" ("OLLAMA_KV_CACHE_TYPE=" + $envDict.OLLAMA_KV_CACHE_TYPE) `
    ("CUDA_VISIBLE_DEVICES=$($envDict.CUDA_VISIBLE_DEVICES); flash=$(if ($envDict.OLLAMA_FLASH_ATTENTION) { $envDict.OLLAMA_FLASH_ATTENTION } else { 'auto (unset)' })")
  $log = Join-Path $Out "private-$tag-$port.log"
  Remove-Item $log -Force -ErrorAction SilentlyContinue
  Remove-Item (Join-Path $Out "private-$tag-$port.err.log") -Force -ErrorAction SilentlyContinue
  $proc = Start-Process -FilePath $ollama -ArgumentList 'serve' -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput $log -RedirectStandardError (Join-Path $Out "private-$tag-$port.err.log")
  $script:MyPorts += $port
  for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 500
    try { Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/version" -TimeoutSec 2 | Out-Null; return $proc } catch { }
  }
  return $proc
}
function Stop-Private($proc, $port) {
  try {
    $r = Get-Resident | Where-Object { $_.port -eq $port -and $_.name -eq $Model }
    if ($r) {
      Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/generate" -Method Post -TimeoutSec 180 `
        -Body (@{ model = $Model; prompt = ''; keep_alive = 0 } | ConvertTo-Json) -ContentType 'application/json' | Out-Null
      Start-Sleep -Seconds 3
    }
  } catch { }
  if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
  Write-Host "  (private ollama on $port stopped)" -ForegroundColor Gray
}
# the runner's own word on spill, out of the server's log
function Runner-SpillLine($port, $tag) {
  foreach ($f in @("private-$tag-$port.log", "private-$tag-$port.err.log")) {
    $p = Join-Path $Out $f
    if (Test-Path $p) {
      $m = Select-String -Path $p -Pattern 'CUDA_Host model buffer size' -ErrorAction SilentlyContinue | Select-Object -Last 1
      if ($m) { return $m.Line.Trim() }
    }
  }
  return '(no CUDA_Host model buffer size line in the runner log)'
}
function Runner-GpuLines($port, $tag) {
  $lines = @()
  foreach ($f in @("private-$tag-$port.log", "private-$tag-$port.err.log")) {
    $p = Join-Path $Out $f
    if (Test-Path $p) {
      $lines += (Select-String -Path $p -Pattern 'model buffer size|offloaded|n_ctx  ' -ErrorAction SilentlyContinue |
        ForEach-Object { $_.Line.Trim() })
    }
  }
  return ($lines | Select-Object -Last 14)
}
# the runner's own layer count: "offloaded 37/37 layers to GPU" means nothing was
# left on the host; "offloaded 21/33" means it was not all on the card.
function Runner-Layers($port, $tag) {
  $last = $null
  foreach ($f in @("private-$tag-$port.log", "private-$tag-$port.err.log")) {
    $p = Join-Path $Out $f
    if (Test-Path $p) {
      $m = Select-String -Path $p -Pattern 'offloaded (\d+)/(\d+) layers' -ErrorAction SilentlyContinue | Select-Object -Last 1
      if ($m) { $last = $m }
    }
  }
  if (-not $last) { return @{ on = -1; of = -1; text = '(no layers line)' } }
  if ($last.Line -match 'offloaded (\d+)/(\d+) layers') {
    return @{ on = [int]$Matches[1]; of = [int]$Matches[2]; text = $last.Line.Trim() }
  }
  return @{ on = -1; of = -1; text = $last.Line.Trim() }
}
# the CUDA_Host model buffer, in MiB. NOTE, measured here 2026-10-10: this line
# is NOT zero even for a load Ollama calls perfect (qwen3:8b on the 12 GB card,
# 37/37 layers offloaded, size_vram == size, still 333.84 MiB host). So it is
# read as a number and judged against a known-resident reference, never as
# "zero or it spilled".
function Runner-HostMiB($port, $tag) {
  $last = $null
  foreach ($f in @("private-$tag-$port.log", "private-$tag-$port.err.log")) {
    $p = Join-Path $Out $f
    if (Test-Path $p) {
      $m = Select-String -Path $p -Pattern 'CUDA_Host model buffer size\s*=\s*([0-9.]+)\s*MiB' -ErrorAction SilentlyContinue | Select-Object -Last 1
      if ($m) { $last = $m }
    }
  }
  if (-not $last) { return -1 }
  if ($last.Line -match 'CUDA_Host model buffer size\s*=\s*([0-9.]+)\s*MiB') { return [double]$Matches[1] }
  return -1
}
function Ps-Row($port) {
  try {
    $ps = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/ps" -TimeoutSec 3 -ErrorAction Stop
    return ($ps.models | Where-Object { $_.name -eq $Model } | Select-Object -First 1)
  } catch { return $null }
}
# one load: returns @{ ok; wall; resident; ps; spillLine; hostMiB; layers; cardUsed }
function Load-At($port, $card, $tag, $ctx) {
  $before = Used-On $card
  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  $ok = $true; $err = ''
  try {
    Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/generate" -Method Post -TimeoutSec 900 `
      -Body (@{ model = $Model; prompt = 'hi'; stream = $false; keep_alive = '5m'
                 options = @{ num_ctx = $ctx; num_predict = 1 } } | ConvertTo-Json -Depth 5) `
      -ContentType 'application/json' | Out-Null
  } catch { $ok = $false; $err = $_.Exception.Message }
  $wall = $sw.Elapsed.TotalSeconds
  $sw2 = [System.Diagnostics.Stopwatch]::StartNew()
  $row = $null
  while ($sw2.Elapsed.TotalSeconds -lt 300) {
    $row = Ps-Row $port
    if ($row -and $row.size_vram -gt 0) { break }
    Start-Sleep -Milliseconds 500
  }
  $resident = $sw2.Elapsed.TotalSeconds
  $after = Used-On $card
  $rec = @{
    ok = $ok; err = $err; wall = [math]::Round($wall, 1); resident = [math]::Round($resident, 1)
    ps = $row; before = $before; after = $after; hostMiB = -1; layers = $null
    spillLine = '(not read)'; gpuLines = @()
  }
  try { $rec.spillLine = (Runner-SpillLine $port $tag) } catch { }
  try { $rec.layers = (Runner-Layers $port $tag) } catch { }
  if (-not $rec.layers) { $rec.layers = @{ on = -1; of = -1; text = '(no layers line)' } }
  try { $rec.hostMiB = (Runner-HostMiB $port $tag) } catch { }
  try { $rec.gpuLines = (Runner-GpuLines $port $tag) } catch { }
  return $rec
}
function Unload($port) {
  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  try {
    Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/generate" -Method Post -TimeoutSec 300 `
      -Body (@{ model = $Model; prompt = ''; keep_alive = 0 } | ConvertTo-Json) -ContentType 'application/json' | Out-Null
  } catch { }
  $req = $sw.Elapsed.TotalSeconds
  while ($sw.Elapsed.TotalSeconds -lt 300) {
    if (-not (Ps-Row $port)) { break }
    Start-Sleep -Milliseconds 500
  }
  return @{ request = [math]::Round($req, 1); gone = [math]::Round($sw.Elapsed.TotalSeconds, 1) }
}
function Report-Load($section, $label, $card, $ctx, $r) {
  $ps = $r.ps
  if (-not $ps) {
    Row $section $label 'NO /api/ps entry' ("ok={0} wall={1}s err={2}" -f $r.ok, $r.wall, $r.err)
    return $false
  }
  $psSpill = $ps.size - $ps.size_vram
  $layers = $r.layers
  $allOn = ($layers -and $layers.on -ge 1 -and $layers.on -eq $layers.of)
  Row $section ("$label : granted ctx") $ps.context_length ("asked $ctx")
  Row $section ("$label : /api/ps vram / size") ("{0:N0} / {1:N0}" -f $ps.size_vram, $ps.size) ("/api/ps says the spill is {0:N0} bytes" -f $psSpill)
  Row $section ("$label : nvidia-smi on $($card.name)") ("{0:N0} -> {1:N0} MiB" -f $r.before, $r.after) ("card total {0:N0} MiB" -f $card.total_mb)
  Row $section ("$label : layers really on the card") $layers.text ("all of them: {0}" -f $allOn)
  Row $section ("$label : runner CUDA_Host model buffer") ("{0:N2} MiB" -f $r.hostMiB) $r.spillLine
  $ctxLine = ($r.gpuLines | Where-Object { $_ -match 'n_ctx ' } | Select-Object -Last 1)
  Row $section ("$label : the runner's own n_ctx") $(if ($ctxLine) { ($ctxLine -replace '.*n_ctx\s+=\s*', '') } else { '?' }) ("what llama.cpp was actually started with; asked $ctx")
  Row $section ("$label : load wall / resident") ("{0:N1} s / {1:N1} s" -f $r.wall, $r.resident) 'wall = the API call; resident = until /api/ps saw it on the card'
  # Zero spill means BOTH: Ollama's own account agrees, AND no layer was left
  # on the host. The CUDA_Host figure is printed either way - see the note on
  # Runner-HostMiB for why it is never the test by itself.
  return ($r.ok -and $psSpill -eq 0 -and $allOn)
}

# ----------------------------------------------------------------- chat -----
function Section-Chat($cards) {
  Write-Host "`n== chat: A's unload/reload cost and B's price ==" -ForegroundColor Cyan
  $big = $cards[-1]; $small = $cards[0]
  Show-Resident 'before chat section'

  # ---- the reference load: what a load that certainly fits really logs -----
  # qwen3.5:9b at a small ctx on the 12 GB card cannot spill. Its CUDA_Host
  # figure is the irreducible one, and is what everything else is read against.
  Write-Host "`n  reference: $Model at ctx 8192 on $($big.name) - this one cannot spill" -ForegroundColor Gray
  $procBig = Start-Private $big $BigPort 'big' $LongCtx
  $script:HostRefMiB = -1
  try {
    if (-not $procBig) { Row 'chat' "A: private server on $($big.name)" 'did not start' '' }
    else {
      $ref = Load-At $BigPort $big 'big' 8192
      Report-Load 'ref' 'ctx 8192 on the 12 GB card' $big 8192 $ref | Out-Null
      $script:HostRefMiB = $ref.hostMiB
      Row 'ref' 'what the runner logs when nothing spills' ("CUDA_Host {0:N2} MiB" -f $ref.hostMiB) 'a NON-zero host figure is normal: it is not zero even for a perfect load'

      # ---- A's cost: the 12 GB card, 196,608 tokens ------------------------
      Write-Host "`n  A's cost: unloading the long everyday chat off $($big.name) and bringing it back" -ForegroundColor Gray
      $u = Unload $BigPort
      Row 'A' 'A: unload (keep_alive 0) request returned in' ("{0:N1} s" -f $u.request) 'through the API only; no server was stopped'
      Row 'A' 'A: chat is GONE from the card after' ("{0:N1} s" -f $u.gone) 'polled /api/ps until the model disappeared'
      Start-Sleep -Seconds 3
      $r2 = Load-At $BigPort $big 'big' $LongCtx
      Row 'A' 'A: reload wall time' ("{0:N1} s" -f $r2.wall) 'the API call, load + one token'
      Row 'A' 'A: reload, back on the card in' ("{0:N1} s" -f $r2.resident) 'until /api/ps saw it resident'
      Row 'A' 'A: the 196,608-token conversation came back' $(if ($r2.ps -and $r2.ps.context_length -eq $LongCtx) { 'yes' } else { 'NO' }) ("granted {0}" -f $(if ($r2.ps) { $r2.ps.context_length } else { 'nothing' }))
      Row 'A' 'A: unload+reload cost per draw' ("{0:N1} s" -f ($u.gone + $r2.wall)) 'the chat is unavailable for this long around every picture (reload = the API call)'
      Row 'A' 'reload: /api/ps vram / size' ("{0:N0} / {1:N0}" -f $r2.ps.size_vram, $r2.ps.size) ("/api/ps spill {0:N0} bytes" -f ($r2.ps.size - $r2.ps.size_vram))
      Row 'A' 'reload: layers really on the card' $r2.layers.text ("all of them: {0}" -f ($r2.layers.on -eq $r2.layers.of))
      Row 'A' 'reload: runner CUDA_Host model buffer' ("{0:N2} MiB" -f $r2.hostMiB) ("reference, nothing spilled: {0:N2} MiB" -f $script:HostRefMiB)
      Row 'A' 'reload: nvidia-smi on the card' ("{0:N0} MiB" -f $r2.after) ("{0:N0} MiB of {1:N0} MiB" -f $r2.after, $big.total_mb)
    }
  } finally { Stop-Private $procBig $BigPort }

  # ---- B's price: the 8 GB card, nothing spilled -------------------------
  Write-Host "`n  B's price: the largest ctx $Model holds on $($small.name) with nothing spilled" -ForegroundColor Gray
  $cands = $Sweep | Sort-Object
  $proc = Start-Private $small $SmallPort 'small' $cands[-1]
  $foundB = $null
  $tried = @()
  try {
    if (-not $proc) { Row 'chat' "B: private server on $($small.name)" 'did not start' '' }
    else {
      # binary search: the model is 6.1 GB of weights and the card has ~6.8 GB
      # free, so the answer is near the bottom and this costs ~4 loads, not 11.
      $lo = 0; $hi = $cands.Count - 1
      while ($lo -le $hi) {
        $mid = [int](($lo + $hi) / 2)
        $ctx = $cands[$mid]
        $r = Load-At $SmallPort $small 'small' $ctx
        $zero = Report-Load 'B' "ctx $ctx" $small $ctx $r
        $tried += [pscustomobject]@{ ctx = $ctx; zero = $zero; host = $r.hostMiB
          layers = $r.layers.text; psSpill = $(if ($r.ps) { $r.ps.size - $r.ps.size_vram } else { 'none' }) }
        if ($zero) { $foundB = $ctx; $lo = $mid + 1 } else { $hi = $mid - 1 }
        Unload $SmallPort | Out-Null
        Start-Sleep -Seconds 2
      }
      foreach ($t in ($tried | Sort-Object ctx)) {
        Row 'B' ("  tried ctx {0}" -f $t.ctx) $(if ($t.zero) { 'ZERO SPILL' } else { 'spilled' }) ("CUDA_Host {0:N2} MiB; {1}; /api/ps spill {2}" -f $t.host, $t.layers, $t.psSpill)
      }
      if ($foundB) {
        Row 'B' "B'S PRICE: $($small.name) holds" ("$foundB tokens") 'no layer left on the host AND /api/ps agrees'
        Row 'B' 'of the everyday 196,608-token conversation' ("{0:N1}% kept" -f ($foundB / $LongCtx * 100)) ("{0} tokens lost" -f ($LongCtx - $foundB))
      } else {
        Row 'B' "B'S PRICE: $($small.name) holds" 'nothing' 'no ctx in the sweep put every layer on the card with /api/ps agreeing'
      }
    }
  } finally { Stop-Private $proc $SmallPort }
  Show-Resident 'after chat section'
}

# ------------------------------------------------------------- pictures -----
function Section-Pictures($cards, $option) {
  Write-Host "`n== pictures: $option ==" -ForegroundColor Cyan
  $big = $cards[-1]; $small = $cards[0]
  if ($option -eq 'C') { $card = $small } else { $card = $big }
  $comfy = 'D:\Jarvis\ImageGen\ComfyUI'
  if ($option -eq 'C') {
    $modelFile = 'qwen-image-2.1-UC-Q4_K_M.gguf'; $loader = 'UnetLoaderGGUF'
    $clipName = 'qwen3vl_8b_int8_convrot.safetensors'; $vaeName = 'qwen_image_2.1_vae_bf16.safetensors'; $clipType = 'qwen_image'
    $unetDir = 'D:\Jarvis Models\AI-Models'
  } else {
    $modelFile = 'Chroma1-HD-int8-convrot-simple.safetensors'; $loader = 'UNETLoader'
    $clipName = 't5xxl_fp8_e4m3fn_scaled.safetensors'; $vaeName = 'ae.safetensors'; $clipType = 'chroma'
    $unetDir = 'D:\Jarvis Models\AI-Models'
  }
  $need = @(
    (Join-Path $comfy "models\text_encoders\$clipName"),
    (Join-Path $comfy "models\vae\$vaeName"),
    (Join-Path $unetDir $modelFile)
  )
  $missing = $need | Where-Object { -not (Test-Path $_) }
  if ($missing) {
    foreach ($m in $missing) { Row 'pictures' "option $option missing" 'not on disk' $m }
    return
  }
  # The owner's two picture models live in D:\Jarvis Models\AI-Models. Tell
  # ComfyUI that, instead of copying 12.9 GB into its own tree.
  $extra = Join-Path $comfy 'extra_model_paths.yaml'
  $yaml = @"
# Written by scripts/measure-image-options.ps1 - so ComfyUI can see the owner's
# own picture models where they already live.
jarvis_ai_models:
    base_path: D:/Jarvis Models/AI-Models
    diffusion_models: |
        .
    unet: |
        .
    checkpoints: |
        .
"@
  if (-not (Test-Path $extra) -or ((Get-Content $extra -Raw) -notmatch 'Jarvis Models/AI-Models')) {
    Set-Content -Path $extra -Value $yaml -Encoding UTF8
    Row 'pictures' 'extra_model_paths.yaml written' 'D:/Jarvis Models/AI-Models' 'so the models need no copying'
  }
  $custom = Join-Path $comfy 'custom_nodes'
  $fork = Get-ChildItem $custom -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'GGUF' } | Select-Object -First 1
  Row 'pictures' 'GGUF custom node' $(if ($fork) { $fork.Name } else { 'NONE' }) $(if ($fork) { (git -C $fork.FullName remote -v 2>&1 | Select-Object -First 1) } else { 'qwen_image21 needs leejet/ComfyUI-GGUF' })

  # The recipes are the publishers' own, read out of
  # D:\Jarvis\ImageGen\workflows\<model>-t2i.json on this PC - not invented here.
  if ($option -eq 'C') {
    # Comfy-Org/Qwen-Image-2.1's own text-to-image graph: UnetLoaderGGUF (the
    # owner's file is an sd.cpp GGUF export), CLIPLoader type qwen_image,
    # TextEncodeQwenImage21 - which hands out its OWN 64-channel latent, so
    # EmptyLatentImage would be the wrong shape - and KSampler 25 steps,
    # cfg 1, euler, simple.
    $wf = @{
      '1' = @{ class_type = 'UnetLoaderGGUF'; inputs = @{ unet_name = $modelFile } }
      '2' = @{ class_type = 'CLIPLoader'; inputs = @{ clip_name = $clipName; type = $clipType; device = 'default' } }
      '3' = @{ class_type = 'VAELoader'; inputs = @{ vae_name = $vaeName } }
      '4' = @{ class_type = 'TextEncodeQwenImage21'; inputs = @{ clip = @('2', 0); prompt = $Prompt
                   negative_prompt = $Negative; resolution = $Width } }
      '5' = @{ class_type = 'KSampler'; inputs = @{ model = @('1', 0); positive = @('4', 0); negative = @('4', 1)
                   latent_image = @('4', 2); seed = $Seed; steps = 25; cfg = 1.0
                   sampler_name = 'euler'; scheduler = 'simple'; denoise = 1.0 } }
      '6' = @{ class_type = 'VAEDecode'; inputs = @{ samples = @('5', 0); vae = @('3', 0) } }
      '7' = @{ class_type = 'SaveImage'; inputs = @{ images = @('6', 0); filename_prefix = "jarvis-option$option" } }
    }
  } else {
    # The Chroma1-HD publisher's own graph: T5TokenizerOptions min_padding 1,
    # ModelSamplingAuraFlow shift 1.0 (their note: "intended shift by the
    # creator"), a real negative prompt, CFGGuider 3.8, euler,
    # BetaSamplingScheduler 26 steps at alpha/beta 0.45, 1152x1152.
    $wf = @{
      '1'  = @{ class_type = 'UNETLoader'; inputs = @{ unet_name = $modelFile; weight_dtype = 'default' } }
      '2'  = @{ class_type = 'CLIPLoader'; inputs = @{ clip_name = $clipName; type = $clipType; device = 'default' } }
      '3'  = @{ class_type = 'VAELoader'; inputs = @{ vae_name = $vaeName } }
      '4'  = @{ class_type = 'T5TokenizerOptions'; inputs = @{ clip = @('2', 0); min_padding = 1; min_length = 0 } }
      '5'  = @{ class_type = 'CLIPTextEncode'; inputs = @{ text = $Prompt; clip = @('4', 0) } }
      '6'  = @{ class_type = 'CLIPTextEncode'; inputs = @{ text = $Negative; clip = @('4', 0) } }
      '7'  = @{ class_type = 'ModelSamplingAuraFlow'; inputs = @{ model = @('1', 0); shift = 1.0 } }
      '8'  = @{ class_type = 'EmptySD3LatentImage'; inputs = @{ width = $Width; height = $Height; batch_size = 1 } }
      '9'  = @{ class_type = 'RandomNoise'; inputs = @{ noise_seed = $Seed } }
      '10' = @{ class_type = 'CFGGuider'; inputs = @{ model = @('7', 0); positive = @('5', 0); negative = @('6', 0); cfg = 3.8 } }
      '11' = @{ class_type = 'KSamplerSelect'; inputs = @{ sampler_name = 'euler' } }
      '12' = @{ class_type = 'BetaSamplingScheduler'; inputs = @{ model = @('7', 0); steps = 26; alpha = 0.45; beta = 0.45 } }
      '13' = @{ class_type = 'SamplerCustomAdvanced'; inputs = @{ noise = @('9', 0); guider = @('10', 0)
                   sampler = @('11', 0); sigmas = @('12', 0); latent_image = @('8', 0) } }
      '14' = @{ class_type = 'VAEDecode'; inputs = @{ samples = @('13', 0); vae = @('3', 0) } }
      '15' = @{ class_type = 'SaveImage'; inputs = @{ images = @('14', 0); filename_prefix = "jarvis-option$option" } }
    }
  }

  # Option B is "the chat lives on the 8 GB card while the picture is drawn".
  # So for B the chat really is resident there during the draws - otherwise the
  # measurement would be option A wearing B's name.
  $procChat = $null
  if ($option -eq 'B' -and $ResidentChatCtx -gt 0) {
    Write-Host "`n  B: putting the everyday chat on $($small.name) at ctx $ResidentChatCtx first" -ForegroundColor Gray
    $procChat = Start-Private $small $SmallPort 'small' $ResidentChatCtx
    if ($procChat) {
      $rc = Load-At $SmallPort $small 'small' $ResidentChatCtx
      Report-Load 'B' "the chat holding $($small.name)" $small $ResidentChatCtx $rc | Out-Null
    } else { Row 'pictures' 'B: the chat could not be put on the 8 GB card' 'no' 'the picture numbers below are then option A numbers' }
  }

  $env:CUDA_VISIBLE_DEVICES = $card.uuid
  $env:OLLAMA_VULKAN = '0'
  $log = Join-Path $Out "comfy-$option-$stamp.log"
  $comfyArgs = @('main.py', '--port', '8188', '--listen', '127.0.0.1', '--cuda-device', '0')
  if ($option -eq 'C') { $comfyArgs += '--lowvram' }
  $proc = Start-Process -FilePath $py -ArgumentList $comfyArgs -WorkingDirectory $comfy -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput $log -RedirectStandardError (Join-Path $Out "comfy-$option-$stamp.err.log")
  Row 'pictures' 'ComfyUI started' 'yes' ("pid $($proc.Id); pinned $($card.uuid); log $log")
  try {
    $up = $false
    for ($i = 0; $i -lt 180; $i++) {
      Start-Sleep -Seconds 2
      try { Invoke-RestMethod -Uri 'http://127.0.0.1:8188/system_stats' -TimeoutSec 3 | Out-Null; $up = $true; break } catch { }
      if ($proc.HasExited) { break }
    }
    if (-not $up) {
      Row 'pictures' 'ComfyUI answered on 8188' 'NO' ((Get-Content $log -Tail 6 -ErrorAction SilentlyContinue) -join ' | ')
      return
    }
    $st = Invoke-RestMethod -Uri 'http://127.0.0.1:8188/system_stats' -TimeoutSec 10
    Row 'pictures' 'ComfyUI device it thinks it has' $st.devices[0].name ("vram total {0:N0} MB, free {1:N0} MB" -f ($st.devices[0].vram_total/1MB), ($st.devices[0].vram_free/1MB))
    $apps = nvidia-smi --query-compute-apps=pid,used_memory,gpu_uuid --format=csv,noheader | Where-Object { $_ -match "^$($proc.Id)," }
    Row 'pictures' 'nvidia-smi says the work is on' $(if ($apps) { ($apps -split ',')[2].Trim() } else { 'NOT FOUND' }) "expected $($card.uuid)"

    $times = @()
    for ($run = 1; $run -le $Runs; $run++) {
      $peak = 0
      $body = @{ prompt = $wf; client_id = 'jarvis-measure' } | ConvertTo-Json -Depth 12 -Compress
      $sw = [System.Diagnostics.Stopwatch]::StartNew()
      try { $q = Invoke-RestMethod -Uri 'http://127.0.0.1:8188/prompt' -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 60 }
      catch { Row 'pictures' "run $run" 'could not queue' $_.Exception.Message; break }
      $done = $false; $files = @(); $bad = ''
      while (-not $done -and $sw.Elapsed.TotalSeconds -lt 3600) {
        Start-Sleep -Milliseconds 400
        $used = Used-On $card
        if ($used -gt $peak) { $peak = $used }
        try {
          $h = Invoke-RestMethod -Uri "http://127.0.0.1:8188/history/$($q.prompt_id)" -TimeoutSec 10
          if ($h.$($q.prompt_id)) {
            $entry = $h.$($q.prompt_id)
            $done = $true
            $files = $entry.outputs.PSObject.Properties.Value.images | ForEach-Object { $_.filename }
            if ($entry.status -and $entry.status.status_str -ne 'success') {
              $bad = (($entry.status.messages | ForEach-Object { ($_ | ForEach-Object { "$_" }) -join ' ' }) -join ' | ')
            }
          }
        } catch { }
      }
      $secs = [math]::Round($sw.Elapsed.TotalSeconds, 1)
      $times += $secs
      Row 'pictures' "run $run at ${Width}x${Height}, seed $Seed" ("{0:N1} s" -f $secs) ("peak on $($card.name): $peak MiB of $($card.total_mb); output: $(($files -join ', '))")
      if ($bad) { Row 'pictures' "run ${run}: ComfyUI said" 'FAILED' $bad }
    }
    if ($times.Count -ge 1) {
      $sorted = $times | Sort-Object
      $median = if ($sorted.Count % 2 -eq 1) { $sorted[[int]($sorted.Count/2)] } else { ($sorted[$sorted.Count/2 - 1] + $sorted[$sorted.Count/2]) / 2 }
      Row 'pictures' "median of $($times.Count) runs" ("{0:N1} s per picture" -f $median) ("runs: {0}" -f (($times | ForEach-Object { '{0:N1}' -f $_ }) -join ', '))
      $outs = Get-ChildItem (Join-Path $comfy 'output') -Filter "jarvis-option$option*" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 6
      foreach ($o in $outs) { Row 'pictures' 'picture saved' $o.Name ("{0}; {1:N0} bytes; {2}" -f $o.FullName, $o.Length, $o.LastWriteTime) }
      # keep the owner's copy
      $keep = Join-Path $Out 'owner-pictures'
      New-Item -ItemType Directory -Force -Path $keep | Out-Null
      foreach ($o in $outs) { Copy-Item $o.FullName $keep -Force -ErrorAction SilentlyContinue }
      Row 'pictures' 'copies for the owner' $keep "$($outs.Count) file(s)"
    }
    Show-Resident "option $option after the draw"
  } finally {
    try { Invoke-RestMethod -Uri 'http://127.0.0.1:8188/interrupt' -Method Post -TimeoutSec 5 | Out-Null } catch { }
    if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
    Remove-Item Env:\CUDA_VISIBLE_DEVICES -ErrorAction SilentlyContinue
    Write-Host "  (the measuring ComfyUI was stopped)" -ForegroundColor Gray
    if ($procChat) { Stop-Private $procChat $SmallPort }
    Show-Resident "option $option at the end"
  }
}

# ------------------------------------------------------------------ main ----
$cards = Get-Cards
Write-Host "`nCards (ranked by their own memory, never by index):" -ForegroundColor Cyan
$cards | ForEach-Object { Write-Host ("  {0,-26} {1,6} MiB total, {2,6} MiB used   {3}" -f $_.name, $_.total_mb, $_.used_mb, $_.uuid) }

if ($Section -eq 'cards') {
  foreach ($c in $cards) { Row 'cards' "$($c.name) memory" ("$($c.total_mb) MiB total") "$($c.used_mb) MiB used, uuid $($c.uuid)" }
  Show-Resident 'now'
}
if ($Section -eq 'chat') { if (Assert-Quiet) { Section-Chat $cards } }
if ($Section -eq 'pictures') {
  if (Assert-Quiet) { Section-Pictures $cards $Option }
}

$csv = Join-Path $Out "image-options-$Section-$stamp.csv"
$rows | Export-Csv -Path $csv -NoTypeInformation -Encoding UTF8
Write-Host "`n  written: $csv" -ForegroundColor Green
$rows | Format-Table -AutoSize -Wrap
