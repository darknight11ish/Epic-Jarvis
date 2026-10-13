# Lists the icons inside the tray overflow window with their screen positions,
# using UI Automation (no clicking). Used to find the Jarvis tray icon.
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$auto = [System.Windows.Automation.AutomationElement]
$root = $auto::RootElement

# The overflow window has no stable class on this build; find it by title.
$cond = New-Object System.Windows.Automation.PropertyCondition($auto::NameProperty, "System tray overflow window.")
$ov = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)
if (-not $ov) {
  Write-Output "overflow window not found by title"
  return
}
Write-Output "overflow '$($ov.Current.Name)' class='$($ov.Current.ClassName)'"
$all = $ov.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                   [System.Windows.Automation.Condition]::TrueCondition)
Write-Output "elements: $($all.Count)"
foreach ($e in $all) {
  $n = ($e.Current.Name -replace "`r?`n", " / ")
  $ct = $e.Current.ControlType.ProgrammaticName -replace "ControlType\.", ""
  $r = $e.Current.BoundingRectangle
  $cls = $e.Current.ClassName
  Write-Output ("  {0} cls='{1}' name='{2}' at {3},{4} {5}x{6}" -f $ct, $cls, $n, [int]$r.X, [int]$r.Y, [int]$r.Width, [int]$r.Height)
}
