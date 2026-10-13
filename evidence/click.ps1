# Clicks a point on screen and optionally sends keystrokes. Used to put the
# caret in the Jarvis bar and open its command palette with "/".
# It only clicks where told and types what it is told - it never presses an
# approval button.
param(
  [Parameter(Mandatory=$true)][int]$X,
  [Parameter(Mandatory=$true)][int]$Y,
  [string]$Keys = "",
  [int]$WaitMs = 700
)
Add-Type @"
using System; using System.Runtime.InteropServices;
public class Mk {
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, IntPtr e);
  public static void Click(int x, int y) {
    SetCursorPos(x, y);
    System.Threading.Thread.Sleep(200);
    mouse_event(0x02, 0, 0, 0, IntPtr.Zero);
    System.Threading.Thread.Sleep(60);
    mouse_event(0x04, 0, 0, 0, IntPtr.Zero);
  }
}
"@
[Mk]::Click($X, $Y)
Start-Sleep -Milliseconds $WaitMs
Write-Output "clicked $X,$Y"
if ($Keys -ne "") {
  $ws = New-Object -ComObject WScript.Shell
  $ws.SendKeys($Keys)
  Write-Output "sent '$Keys'"
}
