<#
.SYNOPSIS
  Add one plug-and-play module to Jarvis, or switch one off.

.DESCRIPTION
  A "drop-in" module is a feature whose only wiring was a single line in
  jarvis_hud.py calling the module's own install(). jarvis_plugins.py makes
  that call for you, so the feature becomes a FOLDER:

      <your backend folder>\jarvis_plugins\<name>\plugin.json

  This copies one such folder in (or out). It never edits jarvis_hud.py,
  never touches the module file itself, and never re-runs the patch script.
  Restart Jarvis afterwards and the feature is on (or off).

  The module file it calls is one this repository already ships, and
  scripts\apply-patches.ps1 copies those in. If it is missing, this says so
  and stops rather than adding a folder that cannot load.

.PARAMETER Name
  The module to add or switch off, as listed by list-plugins.ps1
  (for example: news, media, goals).

.PARAMETER All
  Add or switch off every drop-in module this repository ships.

.PARAMETER Disable
  Switch the module off without deleting it: the folder stays, with a
  "disabled" marker beside its plugin.json, so turning it back on is one
  run with -Enable and nothing is re-copied.

.PARAMETER Enable
  Remove a "disabled" marker.

.PARAMETER BackendPath
  The folder holding jarvis_hud.py. Defaults to the path in backend\README.md.

.PARAMETER Revert
  Take this repository's copy back out again. Anything the folder did not
  come from here is left alone.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\add-plugin.ps1 -Name news
  powershell -ExecutionPolicy Bypass -File .\scripts\add-plugin.ps1 -All
  powershell -ExecutionPolicy Bypass -File .\scripts\add-plugin.ps1 -Name news -Disable
  powershell -ExecutionPolicy Bypass -File .\scripts\add-plugin.ps1 -Name news -Revert
#>
[CmdletBinding()]
param(
    [string] $BackendPath = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program",
    [string] $Name,
    [switch] $All,
    [switch] $Disable,
    [switch] $Enable,
    [switch] $Revert
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ReadyDir = Join-Path $RepoRoot 'plugins\ready'
$Registry = Join-Path $RepoRoot 'plugins\registry.json'
$PluginsFolderName = 'jarvis_plugins'

function Write-Step($text) { Write-Host "  $text" }
function Fail($text) { Write-Host ""; Write-Host "  $text" -ForegroundColor Red; exit 1 }

if (-not (Test-Path $Registry)) {
    Fail "plugins\registry.json is not there. Run: py -3 tools\gen_plugin_catalogue.py"
}

$data = Get-Content $Registry -Raw | ConvertFrom-Json
$dropIns = @($data.entries | Where-Object { $_.bucket -eq 'plug-in' })

if (-not (Test-Path $BackendPath)) {
    Fail "No backend folder at:`n    $BackendPath`n  Pass the real one: -BackendPath ""D:\your\backend"""
}
$hud = Join-Path $BackendPath 'jarvis_hud.py'
if (-not (Test-Path $hud)) {
    Fail "That folder has no jarvis_hud.py:`n    $BackendPath"
}

$pluginsDir = Join-Path $BackendPath $PluginsFolderName
$loader = Join-Path $BackendPath 'jarvis_plugins.py'

$targets = @()
if ($All) {
    $targets = $dropIns
} elseif ($Name) {
    $one = @($dropIns | Where-Object { $_.name -eq $Name })
    if ($one.Count -eq 0) {
        $known = ($dropIns | ForEach-Object { $_.name }) -join ', '
        Fail "'$Name' is not a drop-in module.`n  Drop-in modules: $known`n  Run scripts\list-plugins.ps1 for the full picture."
    }
    $targets = $one
} else {
    Fail "Say which one: -Name news, or -All.`n  scripts\list-plugins.ps1 lists them."
}

if ($Disable -and $Enable) { Fail "-Disable and -Enable do opposite things; pick one." }

# The loader must be in the backend, or a folder here would be read by nobody.
if (-not $Revert) {
    if (-not (Test-Path $loader)) {
        Write-Host ""
        Write-Host "  jarvis_plugins.py is not in your backend folder yet." -ForegroundColor Yellow
        Write-Host "  It is the thing that reads these folders. Copy it in with:"
        Write-Host ""
        Write-Host "      powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1"
        Write-Host ""
        Write-Host "  (that also adds the one startup call it needs - backend\plugin-loader.patch)."
        Write-Host "  Adding the folder anyway, so nothing is lost; it will load on the next run"
        Write-Host "  of apply-patches.ps1."
        Write-Host ""
    }
}

$stamp = Get-Date -Format 'yyyy-MM-dd-HHmmss'

foreach ($entry in $targets) {
    $name = $entry.name
    $src = Join-Path $ReadyDir $name
    $dst = Join-Path $pluginsDir $name

    if ($Revert) {
        if (Test-Path $dst) {
            $backup = Join-Path $BackendPath "_jarvis-plugin-backup-$stamp"
            New-Item -ItemType Directory -Path $backup -Force | Out-Null
            Copy-Item $dst (Join-Path $backup $name) -Recurse -Force
            Remove-Item $dst -Recurse -Force
            Write-Step "removed   $name  (kept a copy in _jarvis-plugin-backup-$stamp)"
        } else {
            Write-Step "not there $name"
        }
        continue
    }

    if (-not (Test-Path $src)) {
        Write-Step "SKIP      $name - plugins\ready\$name is not there"
        continue
    }

    $marker = Join-Path $dst 'disabled'
    if ($Disable) {
        if (-not (Test-Path $dst)) {
            Write-Step "SKIP      $name - not added yet, so there is nothing to switch off"
            continue
        }
        New-Item -ItemType File -Path $marker -Force | Out-Null
        Write-Step "off       $name  (restart Jarvis)"
        continue
    }
    if ($Enable) {
        if (Test-Path $marker) {
            Remove-Item $marker -Force
            Write-Step "on        $name  (restart Jarvis)"
        } else {
            Write-Step "already on $name"
        }
        continue
    }

    # Adding: the module the loader will call has to be in the backend.
    $moduleFile = Join-Path $BackendPath "$($entry.module).py"
    if (-not (Test-Path $moduleFile)) {
        Write-Step "SKIP      $name - $($entry.module).py is not in your backend folder"
        Write-Step "          run apply-patches.ps1 first: it copies the modules in"
        continue
    }

    New-Item -ItemType Directory -Path $pluginsDir -Force | Out-Null
    if (Test-Path $dst) {
        Remove-Item $dst -Recurse -Force
        Write-Step "replaced  $name"
    } else {
        Write-Step "added     $name"
    }
    Copy-Item $src $dst -Recurse -Force
    if (Test-Path $marker) { Remove-Item $marker -Force }

    $summary = $entry.summary
    Write-Host "            $summary" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "  Restart Jarvis, then look at the start-up banner: it prints one line per"
Write-Host "  module it loaded, and names any that would not load."
Write-Host ""
