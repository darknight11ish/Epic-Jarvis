# Reveals the app's hidden Settings window and captures it with PrintWindow.
# It only shows/moves a window and takes a picture - it clicks nothing and
# approves nothing.
param(
  [string]$Title = "Jarvis Desktop — Settings",
  [string]$Out = "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\.dsh-scratch\pairing\evidence\settings.png",
  [switch]$NoMove
)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices; using System.Text;
public class SW2 {
  public delegate bool Proc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(Proc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr h, int x, int y, int w, int ht, bool repaint);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  public struct RECT { public int L,T,R,B; }
  public static IntPtr F = IntPtr.Zero;
  public static int W=0,H=0;
  public static void Find(uint want, string title) {
    F = IntPtr.Zero;
    EnumWindows((h,l)=>{
      uint pid; GetWindowThreadProcessId(h, out pid); if (pid != want) return true;
      var sb=new StringBuilder(300); GetWindowText(h,sb,300);
      if (sb.ToString() == title) { RECT r; GetWindowRect(h,out r); F=h; W=r.R-r.L; H=r.B-r.T; return false; }
      return true; }, IntPtr.Zero);
  }
}
"@
$jp = (Get-Process jarvis-desktop | Select-Object -First 1).Id
[SW2]::Find([uint32]$jp, $Title)
if ([SW2]::F -eq [IntPtr]::Zero) { Write-Output "window '$Title' not found"; return }
$h = [SW2]::F
Write-Output "found handle=$h size=$([SW2]::W)x$([SW2]::H) visible=$([SW2]::IsWindowVisible($h))"

[SW2]::ShowWindow($h, 9) | Out-Null      # SW_RESTORE
if (-not $NoMove) { [SW2]::MoveWindow($h, 0, 0, [SW2]::W, [SW2]::H, $true) | Out-Null }
Start-Sleep -Milliseconds 1200
[SW2]::ShowWindow($h, 5) | Out-Null      # SW_SHOW
Start-Sleep -Milliseconds 1500
Write-Output "visible now = $([SW2]::IsWindowVisible($h))"

$bmp = New-Object System.Drawing.Bitmap([SW2]::W, [SW2]::H)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
$ok = [SW2]::PrintWindow($h, $hdc, 2)
$g.ReleaseHdc($hdc); $g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output "saved $Out (PrintWindow ok: $ok)"
