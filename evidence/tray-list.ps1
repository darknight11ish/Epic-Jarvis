# Lists every clickable element in the Windows tray overflow ("hidden icons")
# window, so the Jarvis tray menu can be opened without guessing coordinates.
# Read-only: it inspects the UI tree and prints it. It clicks nothing.
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes

$auto = [System.Windows.Automation.AutomationElement]
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
$root = $auto::RootElement

# Find the overflow window (class name NotifyIconOverflowWindow), else the tray bar.
$cond = New-Object System.Windows.Automation.PropertyCondition(
  $auto::ClassNameProperty, "NotifyIconOverflowWindow")
$overflow = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)

if (-not $overflow) {
  Write-Output "overflow window not found (it may be closed). Tray bar instead:"
  $trayCond = New-Object System.Windows.Automation.PropertyCondition(
    $auto::ClassNameProperty, "Shell_TrayWnd")
  $tray = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $trayCond)
  if ($tray) {
    $all = $tray.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                         [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($e in $all) {
      $n = $e.Current.Name
      if ($n) { Write-Output ("  [{0}] '{1}'" -f $e.Current.ControlType.ProgrammaticName, $n) }
    }
  } else { Write-Output "no Shell_TrayWnd" }
  return
}

Write-Output "overflow window found: '$($overflow.Current.Name)'"
$all = $overflow.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                         [System.Windows.Automation.Condition]::TrueCondition)
Write-Output "elements: $($all.Count)"
foreach ($e in $all) {
  $n = $e.Current.Name
  $ct = $e.Current.ControlType.ProgrammaticName
  if ($n -or $ct -match "Button|ListItem") {
    Write-Output ("  [{0}] '{1}'" -f $ct, $n)
  }
}
