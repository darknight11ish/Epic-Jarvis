<#
.SYNOPSIS
    Builds libjarvis_llama.so (arm64-v8a by default) from the vendored llama.cpp
    source in this folder and the standalone Android toolchain.

.DESCRIPTION
    Everything this script needs is already on disk:
      * vendor\llama.cpp   - MIT llama.cpp 0.5.0-dev, copied from the PrivateLM
                             Android plugin (see PROVENANCE.json)
      * jni\jarvis_llama_jni.cpp - the JNI bridge for com.jarvis.client.localai.LlamaNative
      * CMakeLists.txt     - CPU-only, single-library build options
      * the NDK, CMake and Ninja named by the toolchain marker file

    No network access, no git, no FetchContent: the build is reproducible from
    this folder plus the toolchain.

    The toolchain marker is read for NDK_DIR, CMAKE_EXE and NINJA_EXE. It must
    end with DONE=1 (the Lead's download writes it). Individual paths can be
    overridden with -NdkDir / -CMakeExe / -NinjaExe.

.PARAMETER ToolchainFile
    Marker file written by the toolchain download. Default D:\Android\tools\TOOLCHAIN-READY.txt

.PARAMETER Abi
    Android ABI to build. arm64-v8a is the phone target; x86_64 is only useful
    for an emulator smoke test and is not required by E1.

.PARAMETER Clean
    Delete build\<abi> first. The delete is refused unless the path is inside
    this script's own folder.

.PARAMETER KeepDebugSymbols
    Do not llvm-strip the published .so. The default strips it: an unstripped
    Release build carries ~33 MB of .debug_* sections (47.1 MB -> 4.4 MB for
    arm64) that neither JNI nor the app needs. The unstripped library stays in
    build\<abi>\lib\ if it is ever needed for a native debugger.

.PARAMETER Jobs
    Parallel compile jobs. Default: number of logical processors.

.EXAMPLE
    pwsh -NoProfile -File .\build-native.ps1

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File .\build-native.ps1 -Clean
#>
[CmdletBinding()]
param(
    [string]$ToolchainFile = 'D:\Android\tools\TOOLCHAIN-READY.txt',
    [string]$NdkDir,
    [string]$CMakeExe,
    [string]$NinjaExe,
    [ValidateSet('arm64-v8a', 'x86_64')]
    [string]$Abi = 'arm64-v8a',
    [string]$ApiLevel = 'android-33',
    [switch]$Clean,
    [switch]$KeepDebugSymbols,
    [int]$Jobs = 0
)

$ErrorActionPreference = 'Stop'
$scriptRoot = $PSScriptRoot

function Read-ToolchainMarker {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Toolchain marker not found: $Path. Wait for the download to finish (the file ends with DONE=1) or pass -NdkDir/-CMakeExe/-NinjaExe."
    }
    $text = Get-Content -LiteralPath $Path -Raw
    if ($text -notmatch 'DONE\s*=\s*1') {
        throw "Toolchain marker does not contain DONE=1 yet: $Path`n--- marker contents ---`n$text"
    }

    $values = @{}
    foreach ($line in ($text -split "`r?`n")) {
        # NDK_DIR=..., CMAKE_EXE = "...", export NINJA_EXE: ...
        if ($line -match '^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*[=:]\s*(.+?)\s*$') {
            $key = $matches[1].ToUpperInvariant()
            $value = $matches[2].Trim().Trim('"').Trim("'")
            $values[$key] = $value
        }
    }
    return $values
}

function Resolve-ExistingPath {
    param([string]$Label, [string]$Path)
    if (-not $Path) { throw "$Label is not set." }
    if (-not (Test-Path -LiteralPath $Path)) { throw "$Label does not exist: $Path" }
    return (Resolve-Path -LiteralPath $Path).Path
}

# --- toolchain --------------------------------------------------------------
if (-not $NdkDir -or -not $CMakeExe -or -not $NinjaExe) {
    $marker = Read-ToolchainMarker -Path $ToolchainFile
    if (-not $NdkDir -and $marker.ContainsKey('NDK_DIR')) { $NdkDir = $marker['NDK_DIR'] }
    if (-not $CMakeExe -and $marker.ContainsKey('CMAKE_EXE')) { $CMakeExe = $marker['CMAKE_EXE'] }
    if (-not $NinjaExe -and $marker.ContainsKey('NINJA_EXE')) { $NinjaExe = $marker['NINJA_EXE'] }
}

$ndk = Resolve-ExistingPath -Label 'NDK_DIR' -Path $NdkDir
$cmake = Resolve-ExistingPath -Label 'CMAKE_EXE' -Path $CMakeExe
$ninja = Resolve-ExistingPath -Label 'NINJA_EXE' -Path $NinjaExe

$toolchain = Join-Path $ndk 'build\cmake\android.toolchain.cmake'
if (-not (Test-Path -LiteralPath $toolchain)) {
    throw "The NDK at $ndk has no build\cmake\android.toolchain.cmake - is this a full NDK?"
}

$vendorLlama = Join-Path $scriptRoot 'vendor\llama.cpp'
$jniSource = Join-Path $scriptRoot 'jni\jarvis_llama_jni.cpp'
foreach ($required in @($vendorLlama, $jniSource, (Join-Path $scriptRoot 'CMakeLists.txt'))) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Vendored source is incomplete, missing: $required"
    }
}

# --- build directory --------------------------------------------------------
$rootPath = (Resolve-Path -LiteralPath $scriptRoot).Path
$buildDir = Join-Path $rootPath ("build\" + $Abi)
if ($Clean -and (Test-Path -LiteralPath $buildDir)) {
    # Refuse to delete anything that is not inside this script's own folder.
    $fullBuild = [System.IO.Path]::GetFullPath($buildDir)
    if (-not $fullBuild.StartsWith($rootPath + [System.IO.Path]::DirectorySeparatorChar,
                                   [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to delete a build folder outside the script root: $fullBuild"
    }
    Write-Host "Removing $fullBuild"
    Remove-Item -LiteralPath $fullBuild -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

if ($Jobs -le 0) { $Jobs = [Environment]::ProcessorCount }
if ($Jobs -lt 1) { $Jobs = 1 }

# --- configure --------------------------------------------------------------
Write-Host "== cmake configure =="
Write-Host "  NDK       : $ndk"
Write-Host "  CMake     : $cmake"
Write-Host "  Ninja     : $ninja"
Write-Host "  ABI       : $Abi"
Write-Host "  Platform  : $ApiLevel"
Write-Host "  Build type: Release"

$configureArguments = @(
    '-S', $rootPath,
    '-B', $buildDir,
    '-G', 'Ninja',
    "-DCMAKE_TOOLCHAIN_FILE=$toolchain",
    "-DANDROID_ABI=$Abi",
    "-DANDROID_PLATFORM=$ApiLevel",
    "-DANDROID_STL=c++_static",
    '-DCMAKE_BUILD_TYPE=Release',
    "-DCMAKE_MAKE_PROGRAM=$ninja"
)
& $cmake @configureArguments
if ($LASTEXITCODE -ne 0) {
    throw "cmake configure failed with exit code $LASTEXITCODE"
}

# --- build ------------------------------------------------------------------
Write-Host "== cmake build (jarvis_llama, $Jobs jobs) =="
& $cmake --build $buildDir --target jarvis_llama --parallel $Jobs
if ($LASTEXITCODE -ne 0) {
    throw "cmake build failed with exit code $LASTEXITCODE"
}

$built = Join-Path $buildDir 'lib\libjarvis_llama.so'
if (-not (Test-Path -LiteralPath $built)) {
    throw "Build reported success but $built does not exist."
}

# --- publish + evidence -----------------------------------------------------
$distDir = Join-Path $rootPath ("dist\" + $Abi)
New-Item -ItemType Directory -Force -Path $distDir | Out-Null
$dist = Join-Path $distDir 'libjarvis_llama.so'
Copy-Item -LiteralPath $built -Destination $dist -Force

$toolBin = Join-Path $ndk 'toolchains\llvm\prebuilt\windows-x86_64\bin'
$llvmNm = Join-Path $toolBin 'llvm-nm.exe'
$llvmReadelf = Join-Path $toolBin 'llvm-readelf.exe'
$llvmStrip = Join-Path $toolBin 'llvm-strip.exe'
$clang = Join-Path $toolBin 'clang.exe'

$unstrippedSize = (Get-Item -LiteralPath $dist).Length
$stripped = $false
if (-not $KeepDebugSymbols) {
    if (-not (Test-Path -LiteralPath $llvmStrip)) {
        throw "llvm-strip not found at $llvmStrip (pass -KeepDebugSymbols to publish unstripped)."
    }
    & $llvmStrip --strip-unneeded $dist
    if ($LASTEXITCODE -ne 0) { throw "llvm-strip failed with exit code $LASTEXITCODE" }
    $stripped = $true
}

$sha256 = (Get-FileHash -LiteralPath $dist -Algorithm SHA256).Hash.ToLowerInvariant()
$size = (Get-Item -LiteralPath $dist).Length

$ndkRevision = 'unknown'
$sourceProperties = Join-Path $ndk 'source.properties'
if (Test-Path -LiteralPath $sourceProperties) {
    $line = Get-Content -LiteralPath $sourceProperties | Where-Object { $_ -match '^Pkg\.Revision' } | Select-Object -First 1
    if ($line) { $ndkRevision = ($line -split '=', 2)[1].Trim() }
}
$cmakeVersion = (& $cmake --version | Select-Object -First 1)
$ninjaVersion = (& $ninja --version | Select-Object -First 1)
$clangVersion = 'unknown'
if (Test-Path -LiteralPath $clang) {
    $clangVersion = (& $clang --version | Select-Object -First 1)
}

$jniSymbols = @()
if (Test-Path -LiteralPath $llvmNm) {
    $jniSymbols = & $llvmNm -D --defined-only $dist |
        Select-String -Pattern 'Java_com_jarvis_client_localai_LlamaNative_' |
        ForEach-Object { $_.Line.Trim() }
}

$loadSegments = @()
if (Test-Path -LiteralPath $llvmReadelf) {
    $loadSegments = & $llvmReadelf -lW $dist |
        Select-String -Pattern '^\s*LOAD' |
        ForEach-Object { $_.Line.Trim() }
}

$info = New-Object System.Collections.Generic.List[string]
$info.Add("jarvis_llama native build")
$info.Add("built_at_utc      : $([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))")
$info.Add("abi               : $Abi")
$info.Add("platform          : $ApiLevel")
$info.Add("build_type        : Release")
$info.Add("stl               : c++_static")
$info.Add("output            : $dist")
$info.Add("size_bytes        : $size")
$info.Add("size_before_strip_bytes : $unstrippedSize")
$info.Add("stripped          : $stripped")
$info.Add("sha256            : $sha256")
$info.Add("ndk               : $ndk")
$info.Add("ndk_revision      : $ndkRevision")
$info.Add("cmake             : $cmakeVersion")
$info.Add("ninja             : $ninjaVersion")
$info.Add("clang             : $clangVersion")
$info.Add("jni_symbols       : $($jniSymbols.Count)")
foreach ($symbol in $jniSymbols) { $info.Add("  $symbol") }
$info.Add("load_segments     : $($loadSegments.Count)")
foreach ($segment in $loadSegments) { $info.Add("  $segment") }
$infoText = ($info -join [Environment]::NewLine) + [Environment]::NewLine
$infoPath = Join-Path $distDir 'BUILD-INFO.txt'
Set-Content -LiteralPath $infoPath -Value $infoText -Encoding UTF8

Write-Host ""
Write-Host "== done =="
Write-Host "  output : $dist"
Write-Host "  size   : $size bytes (before strip: $unstrippedSize, stripped: $stripped)"
Write-Host "  sha256 : $sha256"
Write-Host "  info   : $infoPath"
if ($jniSymbols.Count -ne 8) {
    Write-Warning "Expected 8 Java_* JNI symbols, found $($jniSymbols.Count). See $infoPath"
}
