# Opens the tray overflow, clicks the Jarvis tray icon, and captures what
# appears. It clicks ONLY that one icon. Nothing in the resulting menu is
# clicked - this script never presses Approve, Pair or any action.
param([switch]$NoClick)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public class M {
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, IntPtr e);
  public const uint LEFTDOWN = 0x02, LEFTUP = 0x04;
  public static void Click(int x, int y) {
    SetCursorPos(x, y);
    System.Threading.Thread.Sleep(250);
    mouse_event(LEFTDOWN, 0, 0, 0, IntPtr.Zero);
    System.Threading.Thread.Sleep(60);
    mouse_event(LEFTUP, 0, 0, 0, IntPtr.Zero);
  }
}
"@
$auto = [System.Windows.Automation.AutomationElement]
$root = $auto::RootElement

function Get-Overflow {
  $c = New-Object System.Windows.Automation.PropertyCondition($auto::NameProperty, "System tray overflow window.")
  return $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $c)
}

$ov = Get-Overflow
if (-not $ov) {
  # Open it: the "Show Hidden Icons" button in the tray bar.
  $trayCond = New-Object System.Windows.Automation.PropertyCondition($auto::ClassNameProperty, "Shell_TrayWnd")
  $tray = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $trayCond)
  $btnCond = New-Object System.Windows.Automation.PropertyCondition($auto::NameProperty, "Show Hidden Icons")
  $btn = $tray.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $btnCond)
  if ($btn) {
    $btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    Start-Sleep -Milliseconds 1200
    $ov = Get-Overflow
  }
}
if (-not $ov) { Write-Output "overflow unavailable"; return }
Write-Output "overflow open"

# The Jarvis icon, by its accessible name.
$all = $ov.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                   [System.Windows.Automation.Condition]::TrueCondition)
$jarvis = $null
foreach ($e in $all) {
  if ($e.Current.ClassName -eq "SystemTray.NormalButton" -and $e.Current.Name -match "Jarvis") { $jarvis = $e; break }
}
if (-not $jarvis) { Write-Output "Jarvis tray icon not found"; return }
$r = $jarvis.Current.BoundingRectangle
$cx = [int]($r.X + $r.Width / 2); $cy = [int]($r.Y + $r.Height / 2)
Write-Output "Jarvis tray icon: '$($jarvis.Current.Name -replace "`r?`n", ' | ')' centre $cx,$cy"
if ($NoClick) { return }

[M]::Click($cx, $cy)
Start-Sleep -Milliseconds 1500

# Capture everything, then the bottom-left region where the tray menu lands.
$b = [System.Windows.Forms.SystemInformation]::VirtualScreen
Add-Type -AssemblyName System.Windows.Forms
$b = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.X, $b.Y, 0, 0, (New-Object System.Drawing.Size($b.Width, $b.Height)))
$g.Dispose()
$out1 = "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\.dsh-scratch\pairing\evidence\20-after-tray-click.png"
$bmp.Save($out1, [System.Drawing.Imaging.ImageFormat]::Png)
# Also crop the bottom strip, where a tray menu usually appears.
$menW = 420; $menH = 420
$mx = [Math]::Max(0, $b.X + $b.Width - $menW); $my = [Math]::Max(0, $b.Y + $b.Height - $menH)
$crop = New-Object System.Drawing.Bitmap($menW, $menH)
$g2 = [System.Drawing.Graphics]::FromImage($crop)
$g2.DrawImage($bmp, (New-Object System.Drawing.Rectangle(0,0,$menW,$menH)), (New-Object System.Drawing.Rectangle($mx,$my,$menW,$menH)), [System.Drawing.GraphicsUnit]::Pixel)
$g2.Dispose()
$out2 = "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\.dsh-scratch\pairing\evidence\21-tray-menu-crop.png"
$crop.Save($out2, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose(); $crop.Dispose()
Write-Output "saved $out1 and $out2"
