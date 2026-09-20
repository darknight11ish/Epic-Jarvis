# Jarvis Desktop - Windows verification
#
# Checks the Windows-only findings from docs/AUDIT.md that no Linux container
# could settle. Reads state and reports; changes nothing.
#
#   powershell -ExecutionPolicy Bypass -File scripts\verify-windows.ps1
#
# Written deliberately flat for Windows PowerShell 5.1: no angle brackets in
# strings, no backtick continuations, no inline if-expressions as arguments.
# The previous version used all three and would not parse.

$ErrorActionPreference = 'Continue'
$rows = New-Object System.Collections.ArrayList

function Add-Row([string]$Area, [string]$Check, [string]$Verdict, [string]$Detail) {
    $null = $rows.Add((New-Object psobject -Property ([ordered]@{
        Area    = $Area
        Check   = $Check
        Verdict = $Verdict
        Detail  = $Detail
    })))
}

Write-Host ''
Write-Host 'Jarvis Desktop - Windows verification' -ForegroundColor Cyan
Write-Host '====================================='
Write-Host ''

# --- Platform -------------------------------------------------------------
$cv = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
$build = [int]$cv.CurrentBuildNumber
Add-Row 'Platform' 'Windows build' ("$build." + $cv.UBR) $cv.ProductName

# window-vibrancy passes the tint only below build 22523; above it, the DWM
# backdrop path is used and the colour is dropped.
if ($build -ge 22523) {
    $v = 'NO'
    $d = 'Build is at or above 22523, so the DWM path is used and the tint colour is dropped. Cosmetic only: contrast comes from CSS at 10.7 to 1.'
} else {
    $v = 'YES'
    $d = 'Build is below 22523, so SetWindowCompositionAttribute is used and the tint applies.'
}
Add-Row 'Acrylic' 'Tint argument honoured' $v $d

$tp = (Get-ItemProperty 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize' -ErrorAction SilentlyContinue).EnableTransparency
if ($tp -eq 1) { $v = 'YES'; $d = '' }
elseif ($null -eq $tp) { $v = 'UNKNOWN'; $d = 'Key not present.' }
else { $v = 'NO'; $d = 'Settings, Personalisation, Colours. With this off there is no blur on any window and apply_mica still returns Ok.' }
Add-Row 'Acrylic' 'Transparency effects on' $v $d

# --- Hotkeys --------------------------------------------------------------
$names = Get-Process -ErrorAction SilentlyContinue | Select-Object -ExpandProperty ProcessName -Unique
$contenders = @('PowerToys', 'PowerToys.Run', 'Flow.Launcher', 'Listary', 'Wox', 'Keypirinha')
$hits = @()
foreach ($n in $contenders) { if ($names -contains $n) { $hits += $n } }
if ($hits.Count -gt 0) {
    Add-Row 'Hotkeys' 'Alt+Space contender running' 'YES' ($hits -join ', ')
} else {
    Add-Row 'Hotkeys' 'Alt+Space contender running' 'none seen' 'Alt+Space is also the system window menu in every app while Jarvis holds it.'
}

$layouts = (Get-WinUserLanguageList).Count
if ($layouts -gt 1) { $d = 'More than one layout, so Alt+Shift is the layout switch and competes with Alt+Shift+S, N and W.' } else { $d = '' }
Add-Row 'Hotkeys' 'Keyboard layouts' $layouts $d

# --- Displays -------------------------------------------------------------
Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
$screens = [System.Windows.Forms.Screen]::AllScreens
$desc = @()
foreach ($s in $screens) {
    $desc += ('{0}x{1} at {2},{3}' -f $s.Bounds.Width, $s.Bounds.Height, $s.Bounds.X, $s.Bounds.Y)
}
Add-Row 'Display' 'Monitors' $screens.Count ($desc -join ' | ')
if ($screens.Count -gt 1) {
    Add-Row 'Display' 'Mixed DPI check' 'TODO' 'Drag the widget to each monitor, restart the app, confirm it returns to the same place.'
} else {
    Add-Row 'Display' 'Mixed DPI check' 'N/A' 'Single monitor, so the DPI finding cannot bite.'
}

# --- WebView2 -------------------------------------------------------------
$wvKeys = @(
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
)
$wv = $null
foreach ($k in $wvKeys) {
    $p = Get-ItemProperty $k -ErrorAction SilentlyContinue
    if ($p) { $wv = $p; break }
}
if ($wv) { Add-Row 'WebView2' 'Runtime installed' 'YES' ('v' + $wv.pv) }
else { Add-Row 'WebView2' 'Runtime installed' 'NO' 'The installer bootstrapper will fetch it.' }

# --- Supervision ----------------------------------------------------------
# This decides whether the Job Object work was worth doing.
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Add-Row 'Supervision' 'python on PATH' 'NO' 'Backend supervision cannot be tested without it.'
} else {
    $isAlias = $py.Source -like '*WindowsApps*'
    if ($isAlias) { $v = 'STORE ALIAS' } else { $v = 'real exe' }
    Add-Row 'Supervision' 'python resolves to' $v $py.Source
    if ($isAlias) {
        Add-Row 'Supervision' 'Launcher hand-off risk' 'HIGH' 'An App Execution Alias re-execs or opens the Store, so the pid we launch may not be the pid that binds the port. That is the case the Job Object exists for.'
    }
    $proc = Start-Process -FilePath $py.Source -ArgumentList '-c', 'import time; time.sleep(3)' -PassThru -WindowStyle Hidden
    Start-Sleep -Milliseconds 700
    if ($proc.HasExited) {
        Add-Row 'Supervision' 'Launched pid alive after 0.7s' 'NO' 'It exited immediately, so it is a launcher handing off. pid() must not read that as backend gone.'
    } else {
        Add-Row 'Supervision' 'Launched pid alive after 0.7s' 'YES' ('pid ' + $proc.Id + ' is the interpreter itself')
    }
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}

# --- Toolchain ------------------------------------------------------------
foreach ($t in @('rustc', 'cargo', 'node', 'npm', 'git')) {
    $c = Get-Command $t -ErrorAction SilentlyContinue
    if ($c) {
        $ver = (& $t --version 2>&1 | Select-Object -First 1)
        Add-Row 'Toolchain' $t 'present' "$ver"
    } else {
        Add-Row 'Toolchain' $t 'MISSING' ''
    }
}
$targets = rustup target list --installed 2>$null
if ($targets -match 'x86_64-pc-windows-msvc') { $v = 'present' } else { $v = 'MISSING' }
Add-Row 'Toolchain' 'msvc target' $v ''

# --- Report ---------------------------------------------------------------
$rows | Format-Table -AutoSize -Wrap
Write-Host ''
Write-Host 'Paste the table above back into the Claude session.' -ForegroundColor Cyan
Write-Host ''
