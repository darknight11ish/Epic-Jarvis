# find-flat-regions.ps1 - the biggest FLAT, CONTIGUOUS screen regions, and the
# window on top of each.
#
# WHY THIS EXISTS (2026-10-11). `find-grey-zone.ps1` reported "the box all pixels
# of one colour occupy", and a box can join DISJOINT regions: it reported
# rgb(84,84,84) as a single 1520x792 box at (400,152), but the Jarvis window it
# was blamed on only reaches x=1214, so the box was at least two separate areas
# added together. A rectangle that spans disjoint areas names the wrong window.
# This reports each CONTIGUOUS region on its own, by flood fill over a sampled
# grid, so the rectangle is the real one.
#
# FIXED 2026-10-11, AND IT IS WHY EVERY COLOUR THIS TOOL EVER PRINTED WAS WRONG.
# Each sampled pixel was packed as
#   `$key = ($px.R -shl 16) -bor ($px.G -shl 8) -bor $px.B`
# and that does not pack an RGB value. Measured with this tool's own `-Prove`
# control: a pixel that is exactly rgb(84,84,84) stored `key=84`, which decodes to
# **r=0, g=0, b=84**. The key carried the BLUE CHANNEL ONLY, so "the N most common
# colours" were really "the N most common BLUE values", and each region flooded
# every colour that shared a blue value - different colours added together, which
# is the very fault this file was written to fix, wearing the other hat. The
# corroboration is in its own past output: rgb(0,0,23), rgb(0,0,0), rgb(0,0,28),
# rgb(0,0,84) - every one with r=0 and g=0.
# Now the three channels live in three arrays and the key is built with
# arithmetic, not shifts.
#
# RUN `-Prove` FIRST. It paints a picture with a colour it knows and checks this
# tool finds exactly that rectangle, and prints `CONTROL PASS` or `CONTROL FAIL`
# from the RESULT - never from the words above. A tool that cannot find its own
# rectangle cannot be believed about the screen.
#
# Read-only: it captures the screen and looks things up. Nothing is clicked,
# typed into or changed. What it cannot see: the screen is sampled every `-Step`
# px, so a band thinner than a step can be missed and pixel counts are estimates;
# a region is named with the window at its CENTRE only.

param(
  [int]$Step = 4,                 # sample every N pixels
  [int]$Top = 6,                  # how many colours to examine
  [int]$MinArea = 20000,          # ignore regions smaller than this many pixels
  [switch]$Prove                  # positive control: a known rectangle, not the screen
)

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class W {
  [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
  [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h, uint f);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, System.Text.StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, System.Text.StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
}
"@

function Get-WindowAt([int]$x, [int]$y) {
  $pt = New-Object W+POINT
  $pt.X = $x; $pt.Y = $y
  $h = [W]::WindowFromPoint($pt)
  if ($h -eq [IntPtr]::Zero) { return "(nothing)" }
  $top = [W]::GetAncestor($h, 2)   # GA_ROOT
  $sb = New-Object System.Text.StringBuilder 512
  [void][W]::GetWindowTextW($top, $sb, 512)
  $cn = New-Object System.Text.StringBuilder 512
  [void][W]::GetClassNameW($top, $cn, 512)
  $pid_ = 0
  [void][W]::GetWindowThreadProcessId($top, [ref]$pid_)
  $name = try { (Get-Process -Id $pid_ -ErrorAction Stop).ProcessName } catch { "?" }
  return "title='$($sb.ToString())' class='$($cn.ToString())' pid=$pid_ ($name)"
}

# The control's own rectangle, in one place so the picture and the check cannot
# drift apart.
$ProveX = 40; $ProveY = 30; $ProveW = 120; $ProveH = 80; $ProveV = 84

if ($Prove) {
  $b = [pscustomobject]@{ Left = 0; Top = 0; Width = 400; Height = 300 }
  $bmp = New-Object System.Drawing.Bitmap(400, 300)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.Clear([System.Drawing.Color]::FromArgb(0, 0, 23))
  $brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb($ProveV, $ProveV, $ProveV))
  $g.FillRectangle($brush, $ProveX, $ProveY, $ProveW, $ProveH)
  $g.Dispose(); $brush.Dispose()
  Write-Output "PROVE: synthetic 400x300 picture, rgb($ProveV,$ProveV,$ProveV) at ($ProveX,$ProveY) ${ProveW}x${ProveH}"
  Write-Output ""
} else {
  $b = [System.Windows.Forms.SystemInformation]::VirtualScreen
  $bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($b.Left, $b.Top, 0, 0, $bmp.Size)
  $g.Dispose()
}

$cols = [int][Math]::Ceiling($b.Width / $Step)
$rows = [int][Math]::Ceiling($b.Height / $Step)
# Three channels in three arrays. The key below is built with ARITHMETIC: the
# shifts that used to be here lost red and green (see the header).
$chR = New-Object 'int[,]' $cols, $rows
$chG = New-Object 'int[,]' $cols, $rows
$chB = New-Object 'int[,]' $cols, $rows
$keys = New-Object 'int[,]' $cols, $rows
$counts = @{}
for ($cy = 0; $cy -lt $rows; $cy++) {
  for ($cx = 0; $cx -lt $cols; $cx++) {
    $px = $bmp.GetPixel([Math]::Min($cx * $Step, $b.Width - 1), [Math]::Min($cy * $Step, $b.Height - 1))
    $r = [int]$px.R; $gg = [int]$px.G; $bb = [int]$px.B
    $chR[$cx, $cy] = $r; $chG[$cx, $cy] = $gg; $chB[$cx, $cy] = $bb
    $key = ($r * 65536) + ($gg * 256) + $bb
    $keys[$cx, $cy] = $key
    if ($counts.ContainsKey($key)) { $counts[$key]++ } else { $counts[$key] = 1 }
  }
}
$bmp.Dispose()

Write-Output "virtual screen: $($b.Width)x$($b.Height) at ($($b.Left),$($b.Top)); sampled every $Step px"
Write-Output ""

$found = @()
$topColours = $counts.GetEnumerator() | Sort-Object -Property Value -Descending | Select-Object -First $Top

foreach ($entry in $topColours) {
  $key = [int]$entry.Key
  $r = [int]($key / 65536)
  $gg = [int](($key % 65536) / 256)
  $bb = [int]($key % 256)
  # Flood fill, 4-connected, over this colour only.
  $seen = New-Object 'bool[,]' $cols, $rows
  $regions = @()
  for ($sy = 0; $sy -lt $rows; $sy++) {
    for ($sx = 0; $sx -lt $cols; $sx++) {
      if ($seen[$sx, $sy] -or $keys[$sx, $sy] -ne $key) { continue }
      $stack = New-Object System.Collections.Stack
      $stack.Push(@($sx, $sy))
      $seen[$sx, $sy] = $true
      $minX = $sx; $maxX = $sx; $minY = $sy; $maxY = $sy; $n = 0
      while ($stack.Count -gt 0) {
        $p = $stack.Pop()
        $x = $p[0]; $y = $p[1]; $n++
        if ($x -lt $minX) { $minX = $x }; if ($x -gt $maxX) { $maxX = $x }
        if ($y -lt $minY) { $minY = $y }; if ($y -gt $maxY) { $maxY = $y }
        foreach ($d in @(@(1,0), @(-1,0), @(0,1), @(0,-1))) {
          $nx = $x + $d[0]; $ny = $y + $d[1]
          if ($nx -lt 0 -or $ny -lt 0 -or $nx -ge $cols -or $ny -ge $rows) { continue }
          if ($seen[$nx, $ny] -or $keys[$nx, $ny] -ne $key) { continue }
          $seen[$nx, $ny] = $true
          $stack.Push(@($nx, $ny))
        }
      }
      $regions += [pscustomobject]@{
        X = $b.Left + $minX * $Step
        Y = $b.Top + $minY * $Step
        W = ($maxX - $minX + 1) * $Step
        H = ($maxY - $minY + 1) * $Step
        Pixels = $n * $Step * $Step
        R = $r; G = $gg; B = $bb
      }
    }
  }
  $big = $regions | Where-Object { $_.Pixels -ge $MinArea } | Sort-Object -Property Pixels -Descending
  if (-not $big) { continue }
  Write-Output "rgb($r,$gg,$bb) - $($big.Count) contiguous region(s) over $MinArea px:"
  foreach ($reg in ($big | Select-Object -First 4)) {
    $cx = [int]($reg.X + $reg.W / 2); $cy = [int]($reg.Y + $reg.H / 2)
    Write-Output ("  [{0},{1} {2}x{3}] {4} px  centre ({5},{6}) -> {7}" -f `
      $reg.X, $reg.Y, $reg.W, $reg.H, $reg.Pixels, $cx, $cy, (Get-WindowAt $cx $cy))
    $found += $reg
  }
  Write-Output ""
}

if ($Prove) {
  # The verdict is computed from the RESULT. Never from the words printed above:
  # a harness that matched this tool's own "expect" text once declared a control
  # passed while the tool had found nothing at all.
  $hit = @($found | Where-Object {
    $_.X -eq $ProveX -and $_.Y -eq $ProveY -and $_.W -eq $ProveW -and $_.H -eq $ProveH -and
    $_.R -eq $ProveV -and $_.G -eq $ProveV -and $_.B -eq $ProveV -and
    $_.Pixels -eq ($ProveW * $ProveH)
  })
  if ($hit.Count -eq 1) {
    Write-Output "CONTROL PASS: found [$ProveX,$ProveY ${ProveW}x${ProveH}] $($hit[0].Pixels) px rgb($ProveV,$ProveV,$ProveV) exactly"
  } else {
    Write-Output "CONTROL FAIL: the painted rgb($ProveV,$ProveV,$ProveV) rectangle at ($ProveX,$ProveY) ${ProveW}x${ProveH} was NOT found; regions found: $($found.Count)"
  }
}
