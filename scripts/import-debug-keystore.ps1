<#
.SYNOPSIS
  Puts the phone app's shared signing key where the build looks for it, so an
  APK you build on this PC can be installed over the app already on the phone.

.DESCRIPTION
  `jarvis-client/app/build.gradle.kts` looks for the key at
  `keystore/debug.keystore`, measured from the top of this repository - NOT
  inside `jarvis-client/`. That file is not committed (`.gitignore` refuses
  `*.keystore` everywhere, with no exceptions) and it is not in the repository
  history either. On GitHub's build machines it is put back from the
  `DEBUG_KEYSTORE_B64` repository secret; this script does the same thing here.

  The base64 text is read from the `DEBUG_KEYSTORE_B64` environment variable,
  or from a file you point at with `-Base64File`. It is NEVER a literal in this
  script or anywhere else in the repository.

  It writes nothing until the decoded bytes have been read back as a JKS
  keystore and checked for the expected key. So a wrong environment variable, a
  truncated paste or a file that is not a keystore fails with a clear message
  and leaves the disk exactly as it was.

  Nothing secret is ever printed. The certificate FINGERPRINT is printed, which
  is public: it is printed from any APK by anyone who has the APK.

.PARAMETER Base64File
  A file holding the base64 text - for example the value of the
  `DEBUG_KEYSTORE_B64` secret, copied with GitHub's "Copy" button in
  Settings -> Secrets and variables -> Actions. Leading and trailing
  whitespace and newlines are trimmed.

.PARAMETER Target
  Where to write the keystore. Defaults to `keystore\debug.keystore` at the top
  of this repository, which is where the build reads it from.

.PARAMETER Force
  Overwrite a keystore that is already there. Without this, an existing file is
  left alone and the script says so.

.PARAMETER VerifyApk
  Instead of importing anything, check whether an APK was signed with the
  project key. Reads only. Give it the path of the APK.

.PARAMETER StorePassword
  The keystore's password. Defaults to the project's standard debug password.

.PARAMETER KeyAlias
  The key's name inside the keystore. Defaults to the project's standard debug
  alias.

.EXAMPLE
  Read the secret from an environment variable and check it before installing:

  $env:DEBUG_KEYSTORE_B64 = '<paste the secret here>'
  powershell -ExecutionPolicy Bypass -File .\scripts\import-debug-keystore.ps1

.EXAMPLE
  Read the secret from a file (never commit that file):

  powershell -ExecutionPolicy Bypass -File .\scripts\import-debug-keystore.ps1 `
    -Base64File "$env:USERPROFILE\Downloads\debug-keystore.b64"

.EXAMPLE
  Check an APK against the keystore without changing anything:

  powershell -ExecutionPolicy Bypass -File .\scripts\import-debug-keystore.ps1 `
    -VerifyApk .\jarvis-client\app\build\outputs\apk\debug\app-debug.apk

.NOTES
  Read `docs/LOCAL-APK-SIGNING.md` first if you have not. It says what the
  problem is, why the CI secret exists, and what a fingerprint mismatch means.
#>

[CmdletBinding()]
param(
    [string] $Base64File,
    [string] $Target,
    [switch] $Force,
    [string] $VerifyApk,
    [string] $StorePassword = 'android',
    [string] $KeyAlias = 'androiddebugkey'
)

# 'Stop' so a real PowerShell error (an unwritable path, say) ends the script.
# Native tools are handled by two helpers below instead: under 'Stop', keytool
# writing its warnings to the error stream would abort the script before its
# exit code could be read.
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot

function Say  ([string] $m) { Write-Host $m }
function Good ([string] $m) { Write-Host $m -ForegroundColor Green }
function Warn ([string] $m) { Write-Host $m -ForegroundColor Yellow }
function Bad  ([string] $m) { Write-Host $m -ForegroundColor Red }

function Die ([string] $m) {
    Bad "STOPPING: $m"
    exit 1
}

# Every native tool goes through here.
#
# $ErrorActionPreference is local to this function, so setting it to 'Continue'
# does not weaken the script. keytool writes ordinary output (and its "storing
# ... certificate" preamble) to the ERROR stream, so `2>&1` is required to see
# it at all - and under the script's 'Stop', the first such line would throw
# "NativeCommandError" and lose the exit code that says what actually happened.
function Invoke-Native ([string] $exe, [string[]] $arguments) {
    $ErrorActionPreference = 'Continue'
    $output = & $exe @arguments 2>&1 | ForEach-Object { "$_" }
    return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = @($output) }
}

function Find-Tool ([string] $exeName) {
    if ($env:JAVA_HOME) {
        $candidate = Join-Path $env:JAVA_HOME "bin\$exeName.exe"
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    $onPath = Get-Command $exeName -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    # A JDK installed but not on PATH, and JAVA_HOME unset.
    $jdk = Get-ChildItem 'C:\Program Files\*\*\bin' -Filter "$exeName.exe" -ErrorAction SilentlyContinue |
           Select-Object -First 1
    if ($jdk) { return $jdk.FullName }
    return $null
}

function Find-ApkSigner {
    $bases = @()
    if ($env:LOCALAPPDATA) { $bases += (Join-Path $env:LOCALAPPDATA 'Android\Sdk\build-tools') }
    if ($env:ANDROID_HOME) { $bases += (Join-Path $env:ANDROID_HOME 'build-tools') }
    if ($env:ANDROID_SDK_ROOT) { $bases += (Join-Path $env:ANDROID_SDK_ROOT 'build-tools') }
    foreach ($base in $bases) {
        if (-not (Test-Path -LiteralPath $base)) { continue }
        # Newest build-tools first, the same "sort -V | tail" CI does.
        $versions = Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue |
                    Sort-Object -Property @{ Expression = { try { [version]$_.Name } catch { [version]'0.0' } } } -Descending
        foreach ($version in $versions) {
            $candidate = Join-Path $version.FullName 'apksigner.bat'
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
        }
    }
    $onPath = Get-Command 'apksigner' -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    return $null
}

# The certificate's SHA-256, as 64 lowercase hex characters with no separators.
# That is the form the workflow compares, and the only form worth comparing.
function Get-KeystoreFingerprint ([string] $KeyStorePath) {
    $keytool = Find-Tool 'keytool'
    if (-not $keytool) {
        Die "Could not find keytool, so the keystore cannot be checked. It ships with the JDK; set JAVA_HOME, or add the JDK's bin folder to PATH."
    }

    $result = Invoke-Native $keytool @(
        '-list', '-v', '-keystore', $KeyStorePath,
        '-storepass', $StorePassword, '-alias', $KeyAlias
    )
    if ($result.ExitCode -ne 0) {
        return [pscustomobject]@{
            Ok          = $false
            Fingerprint = $null
            Output      = $result.Output
            Tool        = $keytool
        }
    }

    $fingerprint = $null
    foreach ($line in $result.Output) {
        $match = [regex]::Match($line, '^\s*SHA256:\s*([0-9A-Fa-f:]+)\s*$')
        if ($match.Success) {
            $fingerprint = ($match.Groups[1].Value -replace '[^0-9A-Fa-f]', '').ToLowerInvariant()
            break
        }
    }
    return [pscustomobject]@{
        Ok          = ($fingerprint -and $fingerprint.Length -eq 64)
        Fingerprint = $fingerprint
        Output      = $result.Output
        Tool        = $keytool
    }
}

function Show-Grouped ([string] $hex) {
    # AB:CD:EF... - the way keytool and CI print it, easier to read in pairs.
    return (($hex -split '(.{2})' | Where-Object { $_ }) -join ':')
}

# ---------------------------------------------------------------------------
# Mode 1: is this APK signed with the key in the keystore? Reads only.
# ---------------------------------------------------------------------------
if ($VerifyApk) {
    if (-not $Target) { $Target = Join-Path $RepoRoot 'keystore\debug.keystore' }

    if (-not (Test-Path -LiteralPath $VerifyApk -PathType Leaf)) {
        Die "There is no APK at '$VerifyApk'. Build one first: cd jarvis-client; .\gradlew.bat assembleDebug"
    }
    $apkItem = Get-Item -LiteralPath $VerifyApk
    $apkPath = $apkItem.FullName
    if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) {
        Die "There is no keystore at '$Target', so there is nothing to compare against. Put it there first - see docs/LOCAL-APK-SIGNING.md."
    }

    Say "Keystore: $Target"
    $key = Get-KeystoreFingerprint $Target
    if (-not $key.Ok) {
        Warn ($key.Output -join [Environment]::NewLine)
        Die "Could not read a SHA-256 fingerprint from '$Target'. Either it is not a keystore this keytool can open, or the alias '$KeyAlias' is not in it."
    }
    Say "Key the keystore holds: $($key.Fingerprint)"

    $apksigner = Find-ApkSigner
    if (-not $apksigner) {
        Die "Could not find apksigner. It comes with the Android SDK's build-tools. Set ANDROID_HOME, or check that %LOCALAPPDATA%\Android\Sdk\build-tools exists."
    }

    $result = Invoke-Native $apksigner @('verify', '--print-certs', $apkPath)
    $text = $result.Output
    if ($result.ExitCode -ne 0) {
        Warn ($text -join [Environment]::NewLine)
        Die "'$apkPath' is not a signed APK that apksigner accepts, so it could not be installed at all."
    }

    # Newer build-tools print "V2 Signer: certificate SHA-256 digest: ..." once
    # per signing scheme; older ones print "Signer #1 certificate SHA-256
    # digest: ...". So collect every DISTINCT digest, whatever the prefix - the
    # same rule the workflow uses.
    $digests = @()
    foreach ($line in $text) {
        $match = [regex]::Match($line, 'signer.*certificate SHA-256 digest:\s*([0-9A-Fa-f]+)', 'IgnoreCase')
        if ($match.Success) {
            $digests += ($match.Groups[1].Value -replace '[^0-9A-Fa-f]', '').ToLowerInvariant()
        }
    }
    $distinct = @($digests | Sort-Object -Unique)

    if ($distinct.Count -eq 0) {
        Warn ($text -join [Environment]::NewLine)
        Die "apksigner printed no certificate SHA-256 digest for '$apkPath', so it cannot be compared."
    }
    if ($distinct.Count -gt 1) {
        Die "'$apkPath' carries $($distinct.Count) different signers. That is not a build of this project."
    }

    $apkFingerprint = $distinct[0]
    Say "APK is signed by:      $apkFingerprint"

    if ($apkFingerprint -eq $key.Fingerprint) {
        Good ""
        Good "MATCH. This APK was signed with the key in the keystore above."
        Say  "  (match on: $(Show-Grouped $key.Fingerprint))"
        Say  ""
        Say  "So it will install over any copy of Jarvis already signed with that same"
        Say  "key. If that keystore is the project's own - the fingerprint is the one CI"
        Say  "prints - the app on the phone keeps its pairing token, device id and"
        Say  "offline queue."
        exit 0
    }

    Bad ""
    Bad "MISMATCH - do NOT install this expecting your data to survive."
    Bad "  The APK was signed with a different key from the one in the keystore."
    Bad "  Attempting to install it over the app on the phone fails with"
    Bad "  INSTALL_FAILED_UPDATE_INCOMPATIBLE, and the only way past is an"
    Bad "  uninstall - which wipes the pairing token, the device id and anything"
    Bad "  still queued offline."
    Say ""
    Say "  Most likely cause: the keystore was not in place when this APK was built,"
    Say "  so the build tools signed it with the throwaway key they make per machine"
    Say "  at `$env:USERPROFILE\.android\debug.keystore. Put the project key in place"
    Say "  and build again - see docs/LOCAL-APK-SIGNING.md."
    exit 1
}

# ---------------------------------------------------------------------------
# Mode 2 (default): decode the base64 and put the keystore in place.
# ---------------------------------------------------------------------------
if (-not $Target) { $Target = Join-Path $RepoRoot 'keystore\debug.keystore' }

if ($Base64File) {
    if (-not (Test-Path -LiteralPath $Base64File -PathType Leaf)) {
        Die "There is no file at '$Base64File'."
    }
    $base64 = (Get-Content -LiteralPath $Base64File -Raw).Trim()
    $origin = "the file '$Base64File'"
} else {
    $base64 = "$env:DEBUG_KEYSTORE_B64".Trim()
    $origin = 'the DEBUG_KEYSTORE_B64 environment variable'
}

if (-not $base64) {
    Die @"
No base64 text in $origin.

Either set the environment variable first:

    `$env:DEBUG_KEYSTORE_B64 = '<paste the secret here>'

or point at a file holding it:

    ... -Base64File '<path to the file>'

The text is the value of the DEBUG_KEYSTORE_B64 repository secret on GitHub
(Settings -> Secrets and variables -> Actions), copied with its Copy button.
Never commit it, and never paste it into a file inside this repository.
"@
}

Say "Reading the keystore from $origin."

# Decoded to bytes in memory first. Nothing is written to disk until those bytes
# have been read back as a keystore below.
try {
    $bytes = [Convert]::FromBase64String(($base64 -replace '\s', ''))
} catch {
    Die "That is not valid base64, so it cannot be the keystore. Nothing was written. Check that the whole secret was copied - extra spaces or a missing character are enough to do this."
}

if ($bytes.Length -lt 1024) {
    Die "That decoded to only $($bytes.Length) bytes. A keystore is a few kilobytes - this is not one. Nothing was written."
}

# A Java keystore is one of two formats, and BOTH are normal - do not reject
# one of them:
#   FEEDFEED  the older JKS format
#   3082      PKCS#12, which keytool has made by DEFAULT since JDK 9
#             (measured: JDK 17's plain -genkeypair writes 3082), and which the
#             Android build tools also make as ~/.android/debug.keystore
# So this only rules out "this is not a keystore at all"; keytool below is what
# decides whether the file is really usable. Checking this BEFORE anything is
# written is what makes a wrong paste harmless.
$magic = ($bytes[0..3] | ForEach-Object { $_.ToString('X2') }) -join ''
# StartsWith, not -eq: $magic is all FOUR bytes in hex, so only the first two
# bytes are the format marker (a JKS file's first four bytes are all FEEDFEED,
# but a PKCS#12 file's are 3082 followed by whatever its length is).
if ($magic.StartsWith('FEEDFEED')) {
    $format = 'JKS'
} elseif ($magic.StartsWith('3082')) {
    $format = 'PKCS#12'
} else {
    $format = $null
}
if (-not $format) {
    Die @"
The text decoded, but it is not a Java keystore: the file starts with $magic,
where a keystore starts with FEEDFEED (the older JKS format) or 3082 (PKCS#12,
what modern keytool writes by default). Nothing was written.

Check that you copied the DEBUG_KEYSTORE_B64 secret, and not some other file.
"@
}
Say "Looks like a $format keystore."

$targetFull = [System.IO.Path]::GetFullPath($Target)
$targetDirectory = Split-Path -Parent $targetFull
if ($targetDirectory -and -not (Test-Path -LiteralPath $targetDirectory)) {
    New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
}

if ((Test-Path -LiteralPath $targetFull -PathType Leaf) -and -not $Force) {
    Warn "A keystore is already at $targetFull. Leaving it alone."
    Warn "Run again with -Force to replace it (that changes the certificate and costs one uninstall and re-pair)."
    exit 0
}

# A temporary file in the target folder, named so it cannot be mistaken for the
# keystore. Different folder, so the move below is a same-volume rename.
$temporary = Join-Path $targetDirectory ("debug.keystore.importing-" + [System.IO.Path]::GetRandomFileName())

try {
    [System.IO.File]::WriteAllBytes($temporary, $bytes)

    $check = Get-KeystoreFingerprint $temporary
    if (-not $check.Ok) {
        Warn ($check.Output -join [Environment]::NewLine)
        Die @"
The text decoded to something that has a keystore's header, but it cannot be
opened as one with the project's password and alias - so it is damaged, or it
is not this project's key.

    alias:    $KeyAlias
    password: (the project's standard debug password)

Nothing was written to $targetFull.
"@
    }

    if (Test-Path -LiteralPath $targetFull -PathType Leaf) {
        Remove-Item -LiteralPath $targetFull -Force
    }
    Move-Item -LiteralPath $temporary -Destination $targetFull -Force
    $temporary = $null
} finally {
    if ($temporary -and (Test-Path -LiteralPath $temporary)) {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
}

$ignored = $null
try { $ignored = & git -C $RepoRoot check-ignore -v -- $targetFull 2>$null } catch { }

Good "The keystore is in place at:"
Good "  $targetFull"
Say  ""
Say  "It holds alias '$KeyAlias', and the certificate's SHA-256 is:"
Say  "  $($check.Fingerprint)"
Say  ""
if ($ignored) {
    Good "git ignores that path, so it cannot be committed by accident:"
    Say  "  $ignored"
} else {
    Warn "WARNING: git does NOT ignore $targetFull."
    Warn "Do not run 'git add -A' until you have added an ignore rule - committing a signing key is a serious mistake."
}
Say ""
Say "This must be the SAME fingerprint CI prints for a release build. If it is not,"
Say "you have a different key from the one the app on the phone was signed with, and"
Say "installing over it will fail with INSTALL_FAILED_UPDATE_INCOMPATIBLE."
Say ""
Say "Next: build, then check the APK before installing -"
Say "  cd jarvis-client"
Say "  .\gradlew.bat assembleDebug"
Say "  powershell -ExecutionPolicy Bypass -File ..\scripts\import-debug-keystore.ps1 ``"
Say "    -VerifyApk app\build\outputs\apk\debug\app-debug.apk"
Say ""
Say "docs/LOCAL-APK-SIGNING.md has the whole runbook."
