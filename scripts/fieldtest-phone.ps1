# Field-test harness: drive the Jarvis phone app over adb and record what each screen says.
#
# Usage:
#   pwsh -File phone-lookup.ps1 -Targets @('attention|Attention budget|attention-budget', ...)
#
# Each target is  term | expected row text | tag
# For every target: go Home, open Find, search the term, tap the row whose text starts with
# the expected row text, then dump the screen we landed on and print its words.
#
# Every step is verified. A step that fails says it failed; it never silently produces a result.

param(
  [Parameter(Mandatory = $true)][string[]]$Targets
)

$ErrorActionPreference = 'Stop'
$adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
$tmp = $env:TEMP

function Snap([string]$name) {
  & $adb shell uiautomator dump /sdcard/ui.xml 2>&1 | Out-Null
  & $adb pull /sdcard/ui.xml "$tmp\$name.xml" 2>&1 | Out-Null
  if (-not (Test-Path "$tmp\$name.xml")) { return '' }
  return (Get-Content "$tmp\$name.xml" -Raw)
}

function Words([string]$xml) {
  return @([regex]::Matches($xml, 'text="([^"]{2,})"') | ForEach-Object { $_.Groups[1].Value })
}

function Box([string]$xml, [string]$want) {
  foreach ($m in [regex]::Matches($xml, '<node[^>]*>')) {
    $node = $m.Value
    if ($node -match 'text="([^"]*)"') {
      $t = $Matches[1]
      if ($t -eq $want -and $node -match 'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"') {
        return @([int]$Matches[1], [int]$Matches[2], [int]$Matches[3], [int]$Matches[4])
      }
    }
  }
  return $null
}

function BoxStarts([string]$xml, [string]$prefix) {
  foreach ($m in [regex]::Matches($xml, '<node[^>]*>')) {
    $node = $m.Value
    if ($node -match 'text="([^"]*)"') {
      $t = $Matches[1]
      if ($t.StartsWith($prefix) -and $node -match 'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"') {
        return @([int]$Matches[1], [int]$Matches[2], [int]$Matches[3], [int]$Matches[4])
      }
    }
  }
  return $null
}

function Press($box) {
  $x = [int](($box[0] + $box[2]) / 2)
  $y = [int](($box[1] + $box[3]) / 2)
  & $adb shell input tap $x $y 2>&1 | Out-Null
}

function GoHome {
  for ($k = 1; $k -le 6; $k++) {
    $s = Snap 'ft_home'
    $f = Box $s 'Find'
    if ($f) { return $f }
    $b = Box $s 'Back'
    if ($b) { Press $b } else { & $adb shell input keyevent KEYCODE_BACK 2>&1 | Out-Null }
    Start-Sleep -Seconds 3
  }
  return $null
}

function OpenFind {
  $fb = GoHome
  if (-not $fb) { return $null }
  Press $fb
  Start-Sleep -Seconds 6
  $fs = Snap 'ft_find'
  if ($fs -notmatch 'Find anything') { return $null }
  foreach ($m in [regex]::Matches($fs, '<node[^>]*>')) {
    $node = $m.Value
    if ($node -match 'class="android.widget.EditText"' -and $node -match 'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"') {
      return @([int]$Matches[1], [int]$Matches[2], [int]$Matches[3], [int]$Matches[4])
    }
  }
  return $null
}

foreach ($target in $Targets) {
  $parts = $target -split '\|'
  $term = $parts[0]
  $row = $parts[1]
  $tag = $parts[2]

  Write-Host "--- $tag  (search '$term', expect a row starting '$row')"
  $field = OpenFind
  if (-not $field) { Write-Host "    BLOCKED - could not open Find"; continue }

  Press $field
  Start-Sleep -Seconds 2
  & $adb shell input text $term 2>&1 | Out-Null
  Start-Sleep -Seconds 4
  $res = Snap 'ft_res'
  $found = BoxStarts $res $row
  if (-not $found) {
    $offered = Words $res
    Write-Host "    NOT FOUND as a row - Find offered: $(($offered | Select-Object -Skip 3 -First 6) -join ' / ')"
    continue
  }

  Press $found
  Start-Sleep -Seconds 12
  $dest = Snap 'ft_dest'
  $words = Words $dest
  Write-Host "    landed on: $(($words | Select-Object -First 12) -join ' | ')"
}
