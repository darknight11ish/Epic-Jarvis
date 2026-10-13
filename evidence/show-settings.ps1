# Finds the app's hidden Settings window, reveals it, moves it somewhere
# unobstructed and captures it. Showing and moving a window approves nothing.
param(
  [string]$Out = "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\.dsh-scratch\pairing\evidence\settings.png",
  [switch]$HideAgain
)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices; using System.Text; using System.Collections.Generic;
public class SW {
  public delegate bool Proc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(Proc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr h, int x, int y, int w, int ht, bool repaint);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  public struct RECT { public int L,T,R,B; }
  public static IntPtr Found = IntPtr.Zero;
  public static int W=0,H=0;
  public static string Title="";
  public static void Find(uint want, string title) {
    Found = IntPtr.Zero;
    EnumWindows((h,l)=>{
      uint pid; GetWindowThreadProcessId(h, out pid); if (pid != want) return true;
      var sb=new StringBuilder(300); GetWindowText(h,sb,300);
      if (sb.ToString() == title) {
        RECT r; GetWindowRect(h,out r);
        Found=h; W=r.R-r.L; H=r.B-r.T; Title=sb.ToString();
        return false;
      }
      return true; }, IntPtr.Zero);
  }
}
"@
$jp = (Get-Process jarvis-desktop | Select-Object -First 1).Id
[SW]::Find([uint32]$jp, "Jarvis Desktop — Settings")
if ([SW]::Found -eq [IntPtr]::Zero) { Write-Output "Settings window not found"; return }
Write-Output "found '$([SW]::Title)' handle=$([SW]::Found) size=$([SW]::W)x$([SW]::H) visible=$([SW]::IsWindowVisible([SW]::Found))"

$h = [SW]::Found
[SW]::ShowWindow($h, 9) | Out-Null                    # SW_RESTORE
[SW]::MoveWindow($h, 0, 0, [SW]::W, [SW]::H, $true) | Out-Null
Start-Sleep -Milliseconds 400
[SW]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 1500
[SW]::ShowWindow($h, 5) | Out-Null                    # SW_SHOW
Start-Sleep -Milliseconds 800

$bmp = New-Object System.Drawing.Bitmap([SW]::W, [SW]::H)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
$ok = [SW]::PrintWindow($h, $hdc, 2)
$g.ReleaseHdc($hdc); $g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output "saved $Out (PrintWindow ok: $ok) visible=$([SW]::IsWindowVisible($h))"
if ($HideAgain) { [SW]::ShowWindow($h, 0) | Out-Null; Write-Output "hidden again" }
