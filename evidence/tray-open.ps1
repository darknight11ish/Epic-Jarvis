# Opens the tray overflow ("Show Hidden Icons") and lists what is inside, so the
# Jarvis tray icon can be located. It clicks only the overflow button - the
# "Show Hidden Icons" control - and nothing else.
param([switch]$KeepOpen)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes

$auto = [System.Windows.Automation.AutomationElement]
$root = $auto::RootElement

function Find-ByName($parent, $name) {
  $c = New-Object System.Windows.Automation.PropertyCondition($auto::NameProperty, $name)
  return $parent.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $c)
}

$trayCond = New-Object System.Windows.Automation.PropertyCondition($auto::ClassNameProperty, "Shell_TrayWnd")
$tray = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $trayCond)

$btn = Find-ByName $tray "Show Hidden Icons"
if (-not $btn) { Write-Output "no 'Show Hidden Icons' button"; return }

$inv = $btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
$inv.Invoke()
Start-Sleep -Milliseconds 1200

$ovCond = New-Object System.Windows.Automation.PropertyCondition($auto::ClassNameProperty, "NotifyIconOverflowWindow")
$ov = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $ovCond)
if (-not $ov) { Write-Output "overflow window did not appear"; return }

Write-Output "overflow: '$($ov.Current.Name)'"
$all = $ov.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                   [System.Windows.Automation.Condition]::TrueCondition)
foreach ($e in $all) {
  $n = ($e.Current.Name -replace "`r?`n", " / ")
  $ct = $e.Current.ControlType.ProgrammaticName
  $r = $e.Current.BoundingRectangle
  if ($n -or $ct -match "Button") {
    Write-Output ("  [{0}] '{1}'  at {2},{3} {4}x{5}" -f $ct, $n, [int]$r.X, [int]$r.Y, [int]$r.Width, [int]$r.Height)
  }
}
