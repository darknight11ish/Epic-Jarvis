<#
.SYNOPSIS
  Checks the Windows-only findings from docs/AUDIT.md that no Linux container
  could settle.

.DESCRIPTION
  Everything in this repo has been verified by cross-compilation type-checking,
  unit tests and a headless browser. None of that can tell you whether the
  Acrylic tint applies on YOUR build, whether Alt+Space is already taken, or
  whether a Job Object actually reaps a Python launcher's grandchildren.

  This does. It reads state and reports; it changes nothing.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\verify-windows.ps1
#>

$ErrorActionPreference = 'Continue'
$results = [System.Collections.Generic.List[object]]::new()
function Add-Result($area, $finding, $verdict, $detail) {
  $results.Add([pscustomobject]@{ Area = $area; Finding = $finding; Verdict = $verdict; Detail = $detail })
}

Write-Host "`nJarvis Desktop — Windows verification" -ForegroundColor Cyan
Write-Host "=====================================`n"

# --- 1. Windows build ------------------------------------------------------
# The Acrylic tint is honoured below build 22523 and silently dropped above it.
$build = [int](Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').CurrentBuildNumber
$ubr   = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').UBR
Add-Result 'Platform' 'Windows build' 'INFO' "$build.$ubr"
if ($build -ge 22523) {
  Add-Result 'Acrylic' 'Tint argument honoured?' 'NO' "build $build >= 22523, so window-vibrancy takes the DWM path and drops the colour. Contrast comes from CSS (10.7:1) so this is cosmetic."
} else {
  Add-Result 'Acrylic' 'Tint argument honoured?' 'YES' "build $build < 22523, so SetWindowCompositionAttribute is used and the tint applies."
}

# Transparency effects off in Settings makes every backdrop a no-op.
$tp = (Get-ItemProperty 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize' -ErrorAction SilentlyContinue).EnableTransparency
Add-Result 'Acrylic' 'Transparency effects enabled' $(if ($tp -eq 1) { 'YES' } elseif ($null -eq $tp) { 'UNKNOWN' } else { 'NO' }) `
  $(if ($tp -ne 1) { 'Settings > Personalisation > Colours. With this off there is no blur on any window, and apply_mica still returns Ok.' } else { '' })

# --- 2. Hotkey collisions --------------------------------------------------
# RegisterHotKey is system-wide and first-come-first-served.
$procs = Get-Process -ErrorAction SilentlyContinue | Select-Object -ExpandProperty ProcessName -Unique
$claimants = @{
  'PowerToys'    = 'PowerToys Run defaults to Alt+Space'
  'PowerToys.Run'= 'PowerToys Run defaults to Alt+Space'
  'Flow.Launcher'= 'Flow Launcher commonly binds Alt+Space'
  'Listary'      = 'Listary may bind Alt+Space'
  'Wox'          = 'Wox defaults to Alt+Space'
  'Keypirinha'   = 'Keypirinha may bind Alt+Space'
}
$found = $claimants.Keys | Where-Object { $procs -contains $_ }
Add-Result 'Hotkeys' 'Alt+Space contender running' $(if ($found) { 'YES' } else { 'none seen' }) `
  $(if ($found) { ($found | ForEach-Object { $claimants[$_] }) -join '; ' } else { 'Alt+Space is also the system window menu in every app while Jarvis holds it.' })

# Multiple keyboard layouts make Alt+Shift the layout toggle, which fights
# Alt+Shift+S / N / W.
$layouts = (Get-WinUserLanguageList).Count
Add-Result 'Hotkeys' 'Keyboard layouts installed' $layouts `
  $(if ($layouts -gt 1) { 'More than one layout: Alt+Shift is the layout switch, which competes with Alt+Shift+S/N/W.' } else { '' })

# --- 3. Displays -----------------------------------------------------------
# Mixed DPI is what broke the widget's saved position.
Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
$screens = [System.Windows.Forms.Screen]::AllScreens
$dpis = @()
foreach ($s in $screens) { $dpis += "$($s.Bounds.Width)x$($s.Bounds.Height)@$($s.Bounds.X),$($s.Bounds.Y)" }
Add-Result 'Display' 'Monitors' $screens.Count ($dpis -join ' | ')
Add-Result 'Display' 'Mixed DPI risk' $(if ($screens.Count -gt 1) { 'CHECK' } else { 'N/A' }) `
  $(if ($screens.Count -gt 1) { 'Drag the widget to each monitor, restart the app, and confirm it comes back where you left it.' } else { 'Single monitor: the DPI finding cannot bite.' })

# --- 4. WebView2 -----------------------------------------------------------
$wv = Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}' -ErrorAction SilentlyContinue
Add-Result 'WebView2' 'Runtime installed' $(if ($wv) { 'YES' } else { 'NO' }) $(if ($wv) { "v$($wv.pv)" } else { 'The installer bootstrapper will fetch it.' })

# --- 5. Python, and whether it hands off to a grandchild -------------------
# This is the one that decides whether the Job Object work matters.
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
  Add-Result 'Supervision' 'python on PATH' 'NO' 'Backend supervision cannot be tested without it.'
} else {
  $isAlias = $py.Source -like '*WindowsApps*'
  Add-Result 'Supervision' 'python resolves to' $(if ($isAlias) { 'STORE ALIAS' } else { 'real exe' }) $py.Source
  if ($isAlias) {
    Add-Result 'Supervision' 'Launcher hand-off risk' 'HIGH' 'An App Execution Alias re-execs or opens the Store. The pid we hold may not be the pid that binds the port, which is exactly the case the Job Object exists for.'
  }
  # Does the launched process stay the serving process?
  $p = Start-Process -FilePath $py.Source -ArgumentList '-c','import time; time.sleep(3)' -PassThru -WindowStyle Hidden
  Start-Sleep -Milliseconds 700
  $alive = -not $p.HasExited
  Add-Result 'Supervision' 'Launched pid still alive after 0.7s' $(if ($alive) { 'YES' } else { 'NO' }) `
    $(if ($alive) { "pid $($p.Id) is the interpreter itself" } else { 'It exited immediately — a launcher handing off. pid() must not treat that as "backend gone".' })
  Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
}

# --- 6. Toolchain ----------------------------------------------------------
foreach ($t in 'rustc','cargo','node','npm','git') {
  $c = Get-Command $t -ErrorAction SilentlyContinue
  Add-Result 'Toolchain' $t $(if ($c) { 'present' } else { 'MISSING' }) $(if ($c) { (& $t --version 2>&1 | Select-Object -First 1) } else { '' })
}
$msvc = (rustup target list --installed 2>$null) -match 'x86_64-pc-windows-msvc'
Add-Result 'Toolchain' 'x86_64-pc-windows-msvc target' $(if ($msvc) { 'present' } else { 'MISSING' }) ''

# --- Report ----------------------------------------------------------------
$results | Format-Table -AutoSize -Wrap
Write-Host "`nPaste the table above back into the Claude session.`n" -ForegroundColor Cyan
