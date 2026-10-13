# find-grey-regions.ps1 - the biggest CONTIGUOUS areas of flat-ish grey on screen,
# and the window on top of each. Run it with -Prove first; see below.
#
# WHY THIS EXISTS (2026-10-11). The owner keeps reporting "large grey areas when
# Jarvis on my desktop is running", and `find-flat-regions.ps1` cannot answer it:
# that tool takes the N most common EXACT colours and floods each one, so a grey is
# invisible twice over - a mid-grey is not common enough for the top of the list,
# and a soft grey (a gradient, a translucent overlay, a shadowed panel) has no
# single exact value to be common at all.
#
# AND THAT OTHER TOOL HAS A FAULT OF ITS OWN, MEASURED WHILE BUILDING THIS: it
# packed each pixel as `($px.R -shl 16) -bor ($px.G -shl 8) -bor $px.B`, and a
# known rgb(84,84,84) pixel came back as `key=84` -> r=0, g=0, b=84. The key
# carried the BLUE CHANNEL ONLY, so its "N most common colours" were really "N
# most common BLUE values" and each region flooded the union of every colour
# sharing a blue value. This file keeps the three channels in three arrays. The
# same fix belongs in `find-flat-regions.ps1`.
#
# WHAT IT DOES: the mask comes from the COLOUR RULE rather than a popularity list
# (channels within `-Tolerance` of each other, brightness in
# `-MinBrightness`..`-MaxBrightness`); ONE flood fill over that mask, so
# neighbouring shades are one area (what a gradient or overlay looks like); and
# every area says whether it is ONE flat colour or a RANGE, because "no grey
# found" must never again stand in for an answer it did not earn.
#
# DEFAULTS, and why: `-Tolerance 6` because the grey an earlier investigation
# found was exactly rgb(84,84,84) and a soft panel varies a few steps around its
# own value; brightness 40..220 because the regions the other tool did find were
# all below rgb(0,0,84) (near-black app backgrounds) and a white page is
# rgb(255,255,255) - neither is the grey the owner means.
#
# WHAT IT CANNOT SEE: the screen is read on a SAMPLED grid (every `-Step` px), so
# a grey band thinner than a step can be missed and pixel counts are estimates; an
# area is named with the window at its CENTRE only, so one spanning two windows
# names the middle one; a translucent wash over high-frequency texture is not
# contiguous under the channel test; and there is no vision provider on this
# machine, so the numbers and window names ARE the evidence.
#
# Read-only: it captures the screen and looks things up. Nothing is clicked,
# typed into or changed.

param(
  [int]$Step = 4,                 # sample every N pixels
  [int]$Tolerance = 6,            # channels within this of each other count as grey
  [int]$MinBrightness = 40,       # below this is a dark background, not the grey
  [int]$MaxBrightness = 220,      # above this is a white page
  [int]$MinArea = 20000,          # ignore areas smaller than this many pixels
  [int]$Top = 8,                  # how many areas to report
  [int]$MaxPieces = 6,            # how many loose areas to show when nothing is found
  [switch]$Prove                  # positive control: a known grey rectangle, not the screen
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

if ($Prove) {
  # THE POSITIVE CONTROL, and the reason this file can be trusted at all: it paints
  # a picture with a colour it knows and checks the tool finds it. A tool that
  # cannot find its own rectangle cannot report "no grey on screen" - and an
  # unproven detector already produced exactly that wrong answer once.
  $b = [pscustomobject]@{ Left = 0; Top = 0; Width = 400; Height = 300 }
  $bmp = New-Object System.Drawing.Bitmap(400, 300)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.Clear([System.Drawing.Color]::FromArgb(0, 0, 23))
  $brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(84, 84, 84))
  $g.FillRectangle($brush, 40, 30, 120, 80)
  $g.Dispose(); $brush.Dispose()
  Write-Output "PROVE: synthetic 400x300, rgb(84,84,84) rectangle at (40,30) 120x80"
  Write-Output "       expect: [40,30 120x80] ~9600 px rgb(84,84,84) exactly"
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
# Three channels in three arrays, NOT packed into one int: packing with
# `-shl`/`-bor` lost red and green and made the detector a blue-only test.
$chR = New-Object 'int[,]' $cols, $rows
$chG = New-Object 'int[,]' $cols, $rows
$chB = New-Object 'int[,]' $cols, $rows
for ($cy = 0; $cy -lt $rows; $cy++) {
  for ($cx = 0; $cx -lt $cols; $cx++) {
    $px = $bmp.GetPixel([Math]::Min($cx * $Step, $b.Width - 1), [Math]::Min($cy * $Step, $b.Height - 1))
    $chR[$cx, $cy] = [int]$px.R
    $chG[$cx, $cy] = [int]$px.G
    $chB[$cx, $cy] = [int]$px.B
  }
}
$bmp.Dispose()

Write-Output "virtual screen: $($b.Width)x$($b.Height) at ($($b.Left),$($b.Top)); sampled every $Step px"
Write-Output "grey = channels within $Tolerance of each other, brightness $MinBrightness..$MaxBrightness; areas over $MinArea px (estimated)"
Write-Output ""

function Test-Grey([int]$r, [int]$g, [int]$bl, [int]$tol, [int]$minB, [int]$maxB) {
  $br = [int](($r + $g + $bl) / 3)
  return (([Math]::Abs($r - $g) -le $tol) -and ([Math]::Abs($g - $bl) -le $tol) -and
          ([Math]::Abs($r - $bl) -le $tol) -and $br -ge $minB -and $br -le $maxB)
}

# One flood fill over the WHOLE mask, so neighbouring shades are one area. A box
# joining disjoint areas names the wrong window - the mistake the other tool's own
# header is about.
function Find-GreyAreas([int]$tol, [int]$minB, [int]$maxB) {
  $seen = New-Object 'bool[,]' $cols, $rows
  $areas = @()
  for ($sy = 0; $sy -lt $rows; $sy++) {
    for ($sx = 0; $sx -lt $cols; $sx++) {
      if ($seen[$sx, $sy]) { continue }
      if (-not (Test-Grey $chR[$sx, $sy] $chG[$sx, $sy] $chB[$sx, $sy] $tol $minB $maxB)) {
        $seen[$sx, $sy] = $true
        continue
      }
      $stack = New-Object System.Collections.Stack
      $stack.Push(@($sx, $sy))
      $seen[$sx, $sy] = $true
      $minX = $sx; $maxX = $sx; $minY = $sy; $maxY = $sy
      $n = 0
      $minR = 255; $maxR = 0; $minG = 255; $maxG = 0; $minBl = 255; $maxBl = 0
      while ($stack.Count -gt 0) {
        $p = $stack.Pop()
        $x = $p[0]; $y = $p[1]; $n++
        $pr = $chR[$x, $y]; $pg = $chG[$x, $y]; $pb = $chB[$x, $y]
        if ($pr -lt $minR) { $minR = $pr }; if ($pr -gt $maxR) { $maxR = $pr }
        if ($pg -lt $minG) { $minG = $pg }; if ($pg -gt $maxG) { $maxG = $pg }
        if ($pb -lt $minBl) { $minBl = $pb }; if ($pb -gt $maxBl) { $maxBl = $pb }
        if ($x -lt $minX) { $minX = $x }; if ($x -gt $maxX) { $maxX = $x }
        if ($y -lt $minY) { $minY = $y }; if ($y -gt $maxY) { $maxY = $y }
        foreach ($d in @(@(1,0), @(-1,0), @(0,1), @(0,-1))) {
          $nx = $x + $d[0]; $ny = $y + $d[1]
          if ($nx -lt 0 -or $ny -lt 0 -or $nx -ge $cols -or $ny -ge $rows) { continue }
          if ($seen[$nx, $ny]) { continue }
          if (-not (Test-Grey $chR[$nx, $ny] $chG[$nx, $ny] $chB[$nx, $ny] $tol $minB $maxB)) { continue }
          $seen[$nx, $ny] = $true
          $stack.Push(@($nx, $ny))
        }
      }
      $flat = ($minR -eq $maxR) -and ($minG -eq $maxG) -and ($minBl -eq $maxBl)
      $colour = if ($flat) { "rgb($minR,$minG,$minBl) exactly" }
                else { "NOT one colour - r $minR..$maxR, g $minG..$maxG, b $minBl..$maxBl" }
      $areas += [pscustomobject]@{
        X = $b.Left + $minX * $Step
        Y = $b.Top + $minY * $Step
        W = ($maxX - $minX + 1) * $Step
        H = ($maxY - $minY + 1) * $Step
        Pixels = $n * $Step * $Step
        Flat = $flat
        Colour = $colour
        Samples = $n
      }
    }
  }
  return $areas
}

function Show-Areas($areas, [int]$limit, [string]$why) {
  $big = @($areas | Where-Object { $_.Pixels -ge $MinArea } | Sort-Object -Property Pixels -Descending)
  if ($big.Count -eq 0) { return $false }
  Write-Output "$why - $($big.Count) contiguous area(s) over $MinArea px:"
  foreach ($reg in ($big | Select-Object -First $limit)) {
    $cx = [int]($reg.X + $reg.W / 2); $cy = [int]($reg.Y + $reg.H / 2)
    Write-Output ("  [{0},{1} {2}x{3}] ~{4} px  {5}" -f $reg.X, $reg.Y, $reg.W, $reg.H, $reg.Pixels, $reg.Colour)
    Write-Output ("      centre ({0},{1}) -> {2}" -f $cx, $cy, (Get-WindowAt $cx $cy))
  }
  Write-Output ""
  return $true
}

$areas = Find-GreyAreas $Tolerance $MinBrightness $MaxBrightness
$found = Show-Areas $areas $Top "grey: channels within $Tolerance, brightness $MinBrightness..$MaxBrightness"

if (-not $found) {
  Write-Output "No area of that grey was found over $MinArea px."
  Write-Output "That is NOT 'no grey on screen'. Here is the loosest reasonable look, so the"
  Write-Output "answer is a number rather than a word:"
  Write-Output ""
  $looseTol = $Tolerance * 3
  $looseMin = [Math]::Max(0, $MinBrightness - 20)
  $looseMax = [Math]::Min(255, $MaxBrightness + 20)
  $loose = Find-GreyAreas $looseTol $looseMin $looseMax
  $any = Show-Areas $loose $MaxPieces "loose pass: channels within $looseTol, brightness $looseMin..$looseMax"
  $biggest = @($areas | Sort-Object -Property Pixels -Descending | Select-Object -First 3)
  if ($biggest.Count -gt 0) {
    Write-Output "Largest areas at the TIGHT rule, at ANY size - so 'no grey' is a number:"
    foreach ($reg in $biggest) {
      $cx = [int]($reg.X + $reg.W / 2); $cy = [int]($reg.Y + $reg.H / 2)
      Write-Output ("  [{0},{1} {2}x{3}] ~{4} px  {5}" -f $reg.X, $reg.Y, $reg.W, $reg.H, $reg.Pixels, $reg.Colour)
      Write-Output ("      centre ({0},{1}) -> {2}" -f $cx, $cy, (Get-WindowAt $cx $cy))
    }
    Write-Output ""
  } else {
    Write-Output "Not one sampled pixel passed the tight grey rule - that itself is the finding."
    Write-Output ""
  }
  if (-not $any) {
    Write-Output "Even the loose pass found no contiguous grey over $MinArea px. If the owner still"
    Write-Output "sees a grey area it is textured (a wash over a picture), thinner than $Step px, or"
    Write-Output "not grey by this rule - say which before concluding it is not there."
  }
}
