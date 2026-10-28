<#
.SYNOPSIS
  What can be added to Jarvis as a plug-and-play module, and what is in there now.

.DESCRIPTION
  Reads plugins\registry.json (written by tools\gen_plugin_catalogue.py from
  apply-patches.ps1's own patch list) and your backend folder, and prints:

    1. the drop-in modules, and which are in your backend right now;
    2. the core patches - the things that are not optional, and why.

  Nothing is changed. This only reads.

.PARAMETER BackendPath
  The folder holding jarvis_hud.py. Defaults to the path in backend\README.md.

.PARAMETER Core
  Also list every core patch, one per line, with its reason.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\list-plugins.ps1
  powershell -ExecutionPolicy Bypass -File .\scripts\list-plugins.ps1 -Core
#>
[CmdletBinding()]
param(
    [string] $BackendPath = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program",
    [switch] $Core
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Registry = Join-Path $RepoRoot 'plugins\registry.json'

if (-not (Test-Path $Registry)) {
    Write-Host "plugins\registry.json is not there. Run: py -3 tools\gen_plugin_catalogue.py"
    exit 1
}
$data = Get-Content $Registry -Raw | ConvertFrom-Json
$dropIns = @($data.entries | Where-Object { $_.bucket -eq 'plug-in' } | Sort-Object stack_order)
# NOT `$core`: `-Core` is a [switch] parameter, and PowerShell keeps a
# parameter's type, so assigning this array to it failed every run of this
# script - in 5.1 and in 7 alike - with "Cannot convert value
# "System.Object[]" to type "System.Management.Automation.SwitchParameter"".
# The powershell-5 CI job only PARSES the scripts, so nothing caught it. Found
# and fixed 2026-10-14 while adding the patch-less folder below; recorded as
# DEF-013 in docs/defect-register.tsv.
$coreRows = @($data.entries | Where-Object { $_.bucket -ne 'plug-in' })

# A drop-in folder that replaces NO patch has no row in `entries`: the patch
# rows come from the patch stack, and there is no patch for it. The generator
# reads its own plugin.json into `folders` now, so this list and
# plugins\README.md's count cannot disagree. (plugins\ready\receipts was the
# first one, 2026-10-14; ten of them by 2026-10-28.)
if ($null -eq $data.folders) {
    Write-Host "plugins\registry.json has no 'folders' list - it was written before 2026-10-28."
    Write-Host "Run: py -3 tools\gen_plugin_catalogue.py"
    exit 1
}
$folderRows = @($data.folders | ForEach-Object {
    [pscustomobject]@{
        name        = [string]$_.name
        module      = [string]$_.module
        summary     = [string]$_.summary
        stack_order = [int]$_.stack_order
    }
})
$dropIns = @(@($dropIns) + @($folderRows) | Sort-Object stack_order)

$pluginsDir = Join-Path $BackendPath 'jarvis_plugins'
$loader = Join-Path $BackendPath 'jarvis_plugins.py'

Write-Host ""
Write-Host "Epic Jarvis - plug-and-play modules"
Write-Host ("=" * 60)
Write-Host ""
if (Test-Path $loader) {
    Write-Host "  The loader is installed in this backend." -ForegroundColor Green
} else {
    Write-Host "  The loader is NOT in this backend yet - no folder would be read." -ForegroundColor Yellow
    Write-Host "  Run scripts\apply-patches.ps1 once to put it there."
}
if (-not (Test-Path $pluginsDir)) {
    Write-Host "  No jarvis_plugins\ folder yet - every drop-in module is off."
}
Write-Host ""
Write-Host ("  {0,-18} {1,-9} {2}" -f 'module', 'in backend', 'what it does')
Write-Host ("  " + ("-" * 76))
foreach ($entry in $dropIns) {
    $dst = Join-Path $pluginsDir $entry.name
    $state = 'no'
    if (Test-Path (Join-Path $dst 'disabled')) { $state = 'off' }
    elseif (Test-Path $dst) { $state = 'YES' }
    $summary = $entry.summary
    if ($summary.Length -gt 60) { $summary = $summary.Substring(0, 57) + '...' }
    Write-Host ("  {0,-18} {1,-9} {2}" -f $entry.name, $state, $summary)
}

Write-Host ""
Write-Host ("  {0} drop-in modules, {1} core patches." -f $dropIns.Count, $coreRows.Count)
Write-Host "  Add one:    scripts\add-plugin.ps1 -Name <module>"
Write-Host "  Add all:    scripts\add-plugin.ps1 -All"
Write-Host "  Switch off: scripts\add-plugin.ps1 -Name <module> -Disable"
Write-Host ""

if ($Core) {
    Write-Host "Core patches - not optional, and why"
    Write-Host ("  " + ("-" * 76))
    foreach ($entry in ($coreRows | Sort-Object stack_order)) {
        Write-Host ("  {0,-34} {1}" -f $entry.patch, $entry.why)
    }
    Write-Host ""
} else {
    Write-Host "  (scripts\list-plugins.ps1 -Core explains why each of the core patches"
    Write-Host "   is not a drop-in module.)"
    Write-Host ""
}
