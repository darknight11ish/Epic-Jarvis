# Desktop field-test harness: read and drive the Jarvis desktop app through Windows UI Automation.
#
# The Tauri app is a WebView2 window, and WebView2 exposes its whole page to UI Automation,
# so this reads the app's real text and clicks its real controls - no screenshots, no vision.
#
# Usage:
#   pwsh -File desktop.ps1 -List                 # print every readable element
#   pwsh -File desktop.ps1 -Click 'Jarvis settings'
#   pwsh -File desktop.ps1 -Click -Id 'hud-settings'
#   pwsh -File desktop.ps1 -Text                 # just the text, in order, as one line per string

param(
  [switch]$List,
  [switch]$Text,
  [string]$Click,
  [string]$Id,
  # Which top-level window to read or drive. The app has two:
  #   'Jarvis'                      - the HUD (conversation, lanes, rails)
  #   'Jarvis Desktop - Settings'   - the Settings window, once the gear has been clicked
  # The em-dash matters: it is what the window is really called.
  [string]$Window = 'Jarvis',
  # Which match to take when several windows share a name. The app can have TWO windows
  # called 'Jarvis': the HUD and the quickbar (the Jarvis bar). 1 = the first found.
  [int]$Nth = 1,
  [switch]$Windows
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

function Get-Window([string]$name, [int]$nth = 1) {
  $p = Get-Process jarvis-desktop -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $p) { throw 'jarvis-desktop is not running' }
  $root = [System.Windows.Automation.AutomationElement]::RootElement
  $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $p.Id)
  $wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)
  $seen = 0
  for ($i = 0; $i -lt $wins.Count; $i++) {
    if ($wins.Item($i).Current.Name -eq $name) {
      $seen++
      if ($seen -ge $nth) { return $wins.Item($i) }
    }
  }
  throw "no window named '$name' at match $nth"
}

function Show-Windows {
  $p = Get-Process jarvis-desktop -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $p) { throw 'jarvis-desktop is not running' }
  $root = [System.Windows.Automation.AutomationElement]::RootElement
  $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $p.Id)
  $wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)
  for ($i = 0; $i -lt $wins.Count; $i++) {
    $w = $wins.Item($i)
    $all = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    "window '{0}' class='{1}' descendants={2}" -f $w.Current.Name, $w.Current.ClassName, $all.Count
  }
}

function Get-Elements($win) {
  return $win.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
}

function Find-ByName($win, [string]$name) {
  $all = Get-Elements $win
  # Exact first. Then startswith, then contains: a settings row's accessible name is often its
  # label AND its one-line description joined together, so an exact match misses it.
  for ($i = 0; $i -lt $all.Count; $i++) {
    if ($all.Item($i).Current.Name -eq $name) { return $all.Item($i) }
  }
  for ($i = 0; $i -lt $all.Count; $i++) {
    $n = $all.Item($i).Current.Name
    if ($n -and $n.StartsWith($name)) { return $all.Item($i) }
  }
  for ($i = 0; $i -lt $all.Count; $i++) {
    $n = $all.Item($i).Current.Name
    if ($n -and $n.Contains($name)) { return $all.Item($i) }
  }
  return $null
}

function Find-ById($win, [string]$id) {
  $all = Get-Elements $win
  for ($i = 0; $i -lt $all.Count; $i++) {
    if ($all.Item($i).Current.AutomationId -eq $id) { return $all.Item($i) }
  }
  return $null
}

function Invoke-Element($el) {
  # Try the patterns in the order a real click would: Invoke, then Toggle, then Select.
  $patterns = @(
    [System.Windows.Automation.InvokePattern]::Pattern,
    [System.Windows.Automation.TogglePattern]::Pattern,
    [System.Windows.Automation.SelectionItemPattern]::Pattern
  )
  foreach ($pat in $patterns) {
    $obj = $null
    if ($el.TryGetCurrentPattern($pat, [ref]$obj)) {
      switch ($pat.ProgrammaticName) {
        'InvokePatternIdentifiers.Pattern'        { $obj.Invoke();               return "invoked" }
        'TogglePatternIdentifiers.Pattern'        { $obj.Toggle();               return "toggled to $($obj.Current.ToggleState)" }
        'SelectionItemPatternIdentifiers.Pattern' { $obj.Select();               return "selected" }
      }
    }
  }
  return 'no clickable pattern on that element'
}

if ($Windows) {
  Show-Windows
  exit 0
}

$win = Get-Window $Window $Nth

if ($List) {
  $all = Get-Elements $win
  Write-Host "=== $($all.Count) elements ==="
  for ($i = 0; $i -lt $all.Count; $i++) {
    $e = $all.Item($i)
    $type = $e.Current.ControlType.ProgrammaticName.Replace('ControlType.', '')
    if ($e.Current.Name -or $e.Current.AutomationId) {
      "[{0,-12}] name='{1}' id='{2}'" -f $type, $e.Current.Name, $e.Current.AutomationId
    }
  }
  exit 0
}

if ($Text) {
  $all = Get-Elements $win
  for ($i = 0; $i -lt $all.Count; $i++) {
    $e = $all.Item($i)
    if ($e.Current.Name) { Write-Output $e.Current.Name }
  }
  exit 0
}

if ($Click) {
  $el = Find-ByName $win $Click
  if (-not $el) { Write-Host "NOT FOUND by name: '$Click'"; exit 2 }
  $what = Invoke-Element $el
  Write-Host "clicked '$Click': $what"
  exit 0
}

if ($Id) {
  $el = Find-ById $win $Id
  if (-not $el) { Write-Host "NOT FOUND by id: '$Id'"; exit 2 }
  $what = Invoke-Element $el
  Write-Host "clicked id '$Id': $what"
  exit 0
}

Write-Host 'nothing to do - pass -List, -Text, -Click or -Id'
