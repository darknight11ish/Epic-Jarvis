# Focuses one of the running Jarvis app's windows by index (see -ListOnly in
# focus-and-key.ps1) and optionally sends keys. Read-only: it only sets focus
# and synthesises keystrokes the owner could type.
param(
  [int]$Index = 0,
  [string]$Keys = "",
  [switch]$ListOnly,
  [int]$Pid_ = 0
)
Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public class Win2 {
  public delegate bool Proc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(Proc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  public struct RECT { public int L, T, R, B; }
  public static List<string> Found = new List<string>();
  public static List<IntPtr> Handles = new List<IntPtr>();
  public static void Scan(uint want) {
    Found.Clear(); Handles.Clear();
    EnumWindows((h, l) => {
      uint pid; GetWindowThreadProcessId(h, out pid);
      if (pid != want || !IsWindowVisible(h)) return true;
      var sb = new StringBuilder(256); GetWindowText(h, sb, 256);
      RECT r; GetWindowRect(h, out r);
      Found.Add(sb.ToString() + "  [" + (r.R-r.L) + "x" + (r.B-r.T) + " at " + r.L + "," + r.T + "]");
      Handles.Add(h);
      return true;
    }, IntPtr.Zero);
  }
}
"@
if ($Pid_ -eq 0) { $Pid_ = (Get-Process jarvis-desktop -ErrorAction SilentlyContinue | Select-Object -First 1).Id }
[Win2]::Scan([uint32]$Pid_)
Write-Output "windows of pid ${Pid_}:"
for ($i = 0; $i -lt [Win2]::Found.Count; $i++) { Write-Output ("  {0}: {1}" -f $i, [Win2]::Found[$i]) }
if ($ListOnly) { return }
if ($Index -ge [Win2]::Handles.Count) { Write-Output "no such window index $Index"; return }
$h = [Win2]::Handles[$Index]
[Win2]::ShowWindow($h, 9) | Out-Null   # SW_RESTORE
[Win2]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 800
Write-Output "focused: $([Win2]::Found[$Index])"
if ($Keys -ne "") {
  $ws = New-Object -ComObject WScript.Shell
  $ws.SendKeys($Keys)
  Write-Output "sent $Keys"
}
