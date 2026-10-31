<#
.SYNOPSIS
  Makes a NEW signing key for the phone app, outside this repository, for the
  one-time "uninstall and pair again" ceremony - and prints every step after it.

.DESCRIPTION
  The app on the phone is signed with one shared key. Android only lets a build
  replace the installed app if BOTH carry the same certificate, so replacing
  that key means uninstalling the app once, which deletes its data, and pairing
  the phone again. That is why this is a deliberate ceremony and not a routine
  step: the owner decided on 2026-10-30 to KEEP the current key while the app is
  sideloaded onto his own phone only, and to rotate it only when he chooses to.

  This script does the first half of that ceremony and nothing else:

    1. makes a brand-new keystore OFF the repository (default
       %USERPROFILE%\.jarvis\keys\debug.keystore), with the same alias and the
       same password the Android build already uses - both READ from
       `jarvis-client/app/build.gradle.kts`, never typed in here and never
       printed;
    2. reads the new certificate's SHA-256 fingerprint back OUT of the new key
       and prints it, because every step after this needs that one value;
    3. writes the base64 text of the new keystore next to it, also outside the
       repository, ready to be pasted into the GitHub secret;
    4. prints the exact remaining steps (the secret, the two code pins, the
       release banner flag, the uninstall warning and the re-pair) and stops.

  What it deliberately does NOT do: it does not touch the repository, the
  GitHub secret, CI, the phone, the backend or any running program; it does not
  publish anything; and it does not delete or overwrite a key. It refuses unless
  `-Rotate` is given, and it refuses if a keystore or base64 file is already at
  the target, so a second run can never silently replace the key you are still
  using. Moving the old files away is the only way past that refusal, and that
  is the point: it makes the loss of the old key a thing you did on purpose.

  `-SelfTest` runs the safety checks without making a key: the refusal paths,
  the "outside the repository" rule, and the rule that the password never
  reaches a command line. It is what CI runs.

  READ FIRST: `docs/DEPLOY.md` section 5 (the accepted boundary and the whole
  ceremony) and `docs/LOCAL-APK-SIGNING.md` (where a key must live and how to
  check an APK before installing it).

.PARAMETER Rotate
  Required. Without it the script explains itself and exits 1, so a key is
  never made by a stray double-click or a copy-paste slip.

.PARAMETER OutDir
  Where the new keystore and its base64 text go. Defaults to
  `%USERPROFILE%\.jarvis\keys`. It MUST be outside this repository, and the
  script refuses if it is not.

.PARAMETER ValidityDays
  How long the new certificate is valid, in days. Default 10000 (about 27
  years), the same order as the Android tools' own debug key.

.PARAMETER SelfTest
  Run the safety checks and exit. Writes only inside a temporary folder and
  makes no key.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\rotate-android-signing-key.ps1 -Rotate

.NOTES
  ONE key material rule: the new keystore is a private key. It must never be
  committed, pasted into a chat or a report, or copied into this repository.
  The FINGERPRINT this script prints is public (it is inside every APK) and is
  safe to quote; the key file and its base64 are not.
#>

[CmdletBinding()]
param(
    [switch] $Rotate,
    [string] $OutDir,
    [int] $ValidityDays = 10000,
    [switch] $SelfTest
)

# 'Stop' so a real PowerShell error (an unwritable path, say) ends the script.
# Native tools are handled by the helpers below instead: under 'Stop', keytool
# writing an ordinary line to the error stream would abort the script before its
# exit code could be read.
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$GradleFile = Join-Path $RepoRoot 'jarvis-client\app\build.gradle.kts'
$ScriptPath = $PSCommandPath

function Say  ([string] $m) { Write-Host $m }
function Good ([string] $m) { Write-Host $m -ForegroundColor Green }
function Warn ([string] $m) { Write-Host $m -ForegroundColor Yellow }
function Bad  ([string] $m) { Write-Host $m -ForegroundColor Red }

function Die ([string] $m) {
    Bad ""
    Bad "STOPPING: $m"
    exit 1
}

# Every native tool call goes through here.
#
# $ErrorActionPreference is local to this function, so setting it to 'Continue'
# does not weaken the script. keytool writes ordinary output to the error
# stream, so `2>&1` is required to see it at all - and under the script's
# 'Stop', the first such line would throw "NativeCommandError" and lose the exit
# code that says what actually happened.
#
# The password is fed in on STDIN, never as an argument, so it never appears in
# a process command line, in this script's output, or in a log.
function Invoke-Keytool ([string[]] $arguments, [string] $stdinText) {
    $ErrorActionPreference = 'Continue'
    $output = $stdinText | & $script:Keytool @arguments 2>&1 | ForEach-Object { "$_" }
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

# Is $Path inside this repository (or any git work tree)? A signing key must
# live outside one: `.gitignore` protects `*.keystore`, but an ignore rule is
# the only thing standing between the key and `git add -A`.
function Test-InsideRepository ([string] $Path) {
    $full = [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    $root = [System.IO.Path]::GetFullPath($RepoRoot).TrimEnd('\', '/')
    if ($full -eq $root) { return $true }
    if ($full.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) { return $true }
    # Another checkout or worktree is still a repository. Ask git about the
    # nearest folder that EXISTS yet, so a folder about to be created inside one
    # is caught before anything is written into it.
    $probe = $full
    while ($probe -and -not (Test-Path -LiteralPath $probe -PathType Container)) {
        $parent = Split-Path -Parent $probe
        if (-not $parent -or $parent -eq $probe) { break }
        $probe = $parent
    }
    if ($probe -and (Test-Path -LiteralPath $probe -PathType Container)) {
        $ErrorActionPreference = 'Continue'
        $top = & git -C $probe rev-parse --show-toplevel 2>$null
        if ($LASTEXITCODE -eq 0 -and $top) { return $true }
    }
    return $false
}

# The alias and password the Android build itself uses for the shared debug key.
#
# This script does not carry either value. They are READ from the build file, so
# the two can never drift apart: a key made with a different password would be
# one CI cannot open, and that failure would only show up on a build machine.
# Exactly one of each must be present; anything else is refused rather than
# guessed.
function Get-BuildSigningValues ([string] $Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return [pscustomobject]@{ Ok = $false; Reason = "there is no build file at $Path"; Alias = $null; Password = $null }
    }
    $text = Get-Content -LiteralPath $Path -Raw
    $passwords = @([regex]::Matches($text, '(?m)^\s*storePassword\s*=\s*"([^"]*)"'))
    $aliases = @([regex]::Matches($text, '(?m)^\s*keyAlias\s*=\s*"([^"]*)"'))
    if ($passwords.Count -ne 1 -or $aliases.Count -ne 1) {
        return [pscustomobject]@{
            Ok = $false
            Reason = ("the build file must name exactly one storePassword and one keyAlias " +
                      "(found $($passwords.Count) and $($aliases.Count))")
            Alias = $null
            Password = $null
        }
    }
    $password = $passwords[0].Groups[1].Value
    $alias = $aliases[0].Groups[1].Value
    if (-not $password -or -not $alias) {
        return [pscustomobject]@{ Ok = $false; Reason = 'the build file names an empty password or alias'; Alias = $null; Password = $null }
    }
    if ($password.Length -lt 6) {
        return [pscustomobject]@{ Ok = $false; Reason = 'a keystore password must be at least 6 characters'; Alias = $null; Password = $null }
    }
    return [pscustomobject]@{ Ok = $true; Reason = $null; Alias = $alias; Password = $password }
}

# The certificate's SHA-256, as 64 lowercase hex characters with no separators -
# the form CI compares, the form `UpdateCheck.SIGNER_SHA256` holds, and the only
# form worth quoting.
function Get-KeystoreFingerprint ([string] $KeyStorePath, [string] $Password, [string] $Alias) {
    $result = Invoke-Keytool @('-list', '-v', '-keystore', $KeyStorePath, '-alias', $Alias) $Password
    if ($result.ExitCode -ne 0) {
        return [pscustomobject]@{ Ok = $false; Fingerprint = $null; Output = $result.Output }
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
        Ok          = (($fingerprint) -and ($fingerprint.Length -eq 64))
        Fingerprint = $fingerprint
        Output      = $result.Output
    }
}

function Show-Grouped ([string] $hex) {
    return (($hex -split '(.{2})' | Where-Object { $_ }) -join ':')
}

# ---------------------------------------------------------------------------
# What the two target files are called, given the folder.
# ---------------------------------------------------------------------------
function Get-TargetPaths ([string] $Folder) {
    return [pscustomobject]@{
        Keystore = Join-Path $Folder 'debug.keystore'
        Base64   = Join-Path $Folder 'debug-keystore.b64'
    }
}

# ---------------------------------------------------------------------------
# -SelfTest: the guards, without making a key.
# ---------------------------------------------------------------------------
function Invoke-SelfTest {
    $script:Failures = 0

    function Test-Ok ([string] $m) { Write-Host "  ok    $m" -ForegroundColor Green }
    function Test-No ([string] $m) {
        Write-Host "  FAIL  $m" -ForegroundColor Red
        $script:Failures = $script:Failures + 1
    }

    Say "Self-test: the rotation script's safety guards. No key is made, and"
    Say "nothing is written outside a temporary folder."
    Say ""

    # 1. "Outside the repository" is decided correctly.
    if (Test-InsideRepository $RepoRoot) { Test-Ok 'the repository root counts as inside' }
    else { Test-No 'the repository root was not recognised as inside' }

    if (Test-InsideRepository (Join-Path $RepoRoot 'keystore\debug.keystore')) {
        Test-Ok 'a path inside the repository counts as inside'
    } else { Test-No 'a path inside the repository was not recognised' }

    $outside = Join-Path ([System.IO.Path]::GetTempPath()) 'jarvis-rotation-selftest-outside'
    if (-not (Test-InsideRepository $outside)) { Test-Ok 'a temporary folder counts as outside' }
    else { Test-No 'a temporary folder was wrongly counted as inside the repository' }

    # A folder that does not exist yet, inside ANOTHER git repository, is still
    # inside a repository - proved with a real one, not by looking at the name.
    $otherRepo = Join-Path ([System.IO.Path]::GetTempPath()) ("jarvis-rotation-other-" + [guid]::NewGuid().ToString('N'))
    try {
        New-Item -ItemType Directory -Path $otherRepo -Force | Out-Null
        $ErrorActionPreference = 'Continue'
        $null = & git -C $otherRepo init --quiet 2>&1
        $ErrorActionPreference = 'Stop'
        if (Test-InsideRepository (Join-Path $otherRepo 'keys')) {
            Test-Ok 'a not-yet-created folder inside another repository counts as inside'
        } else {
            Test-No 'a folder that does not exist yet inside another repository was not recognised'
        }
    } finally {
        $ErrorActionPreference = 'Stop'
        if (Test-Path -LiteralPath $otherRepo) {
            Remove-Item -LiteralPath $otherRepo -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    # 2. The alias and password come from the build file, not from here.
    $build = Get-BuildSigningValues $GradleFile
    if ($build.Ok) { Test-Ok 'the build file names exactly one alias and one password' }
    else { Test-No "the build file could not be read for the alias and password: $($build.Reason)" }

    # ...and an ambiguous build file is refused, not guessed.
    $ambiguous = Join-Path ([System.IO.Path]::GetTempPath()) ("jarvis-rotation-" + [guid]::NewGuid().ToString('N') + '.kts')
    try {
        [System.IO.File]::WriteAllText($ambiguous, "storePassword = `"one`"`nstorePassword = `"two`"`nkeyAlias = `"a`"`n")
        $bad = Get-BuildSigningValues $ambiguous
        if (-not $bad.Ok) { Test-Ok 'two storePassword lines are refused, not guessed' }
        else { Test-No 'an ambiguous build file was accepted' }
    } finally {
        if (Test-Path -LiteralPath $ambiguous) { Remove-Item -LiteralPath $ambiguous -Force -ErrorAction SilentlyContinue }
    }

    # 3. The password never reaches a command line, and is never asked for.
    #    This is a check on the mechanism, not a claim that a key is safe: with
    #    no password argument and no prompt, the only way keytool can receive it
    #    is the stdin pipe in Invoke-Keytool.
    $self = Get-Content -LiteralPath $ScriptPath -Raw
    # Split, so this check cannot find its own list instead of the script.
    $forbidden = @('-store' + 'pass', '-key' + 'pass', 'Read-' + 'Host', 'ConvertTo-' + 'SecureString')
    $present = @($forbidden | Where-Object { $self.Contains($_) })
    if ($present.Count -eq 0) {
        Test-Ok 'no password argument and no password prompt anywhere in this script'
    } else {
        Test-No ("the script contains a password-carrying token: " + ($present -join ', '))
    }

    # 4. The refusal paths, proved by running the script as a child process.
    #    Every one of these stops BEFORE keytool is needed, so this runs on a
    #    machine with no JDK.
    $exe = (Get-Process -Id $PID).Path
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("jarvis-rotation-selftest-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    try {
        function Invoke-Child ([string[]] $arguments) {
            $ErrorActionPreference = 'Continue'
            $out = & $exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath @arguments 2>&1 |
                   ForEach-Object { "$_" }
            return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Text = (@($out) -join "`n") }
        }

        $noFlag = Invoke-Child @()
        if ($noFlag.ExitCode -eq 1 -and $noFlag.Text -match 'Rotate') {
            Test-Ok 'without -Rotate it exits 1 and names the flag'
        } else {
            Test-No "without -Rotate it did not refuse as expected (exit $($noFlag.ExitCode))"
        }

        $existsDir = Join-Path $tempRoot 'existing'
        New-Item -ItemType Directory -Path $existsDir -Force | Out-Null
        $existingKey = Join-Path $existsDir 'debug.keystore'
        [System.IO.File]::WriteAllText($existingKey, 'this must not be replaced')
        $before = (Get-FileHash -LiteralPath $existingKey -Algorithm SHA256).Hash
        $exists = Invoke-Child @('-Rotate', '-OutDir', $existsDir)
        $after = (Get-FileHash -LiteralPath $existingKey -Algorithm SHA256).Hash
        if ($exists.ExitCode -eq 1 -and $before -eq $after) {
            Test-Ok 'an existing keystore is refused and left byte-for-byte alone'
        } else {
            Test-No "an existing keystore was not refused and left alone (exit $($exists.ExitCode))"
        }

        $b64Dir = Join-Path $tempRoot 'b64-exists'
        New-Item -ItemType Directory -Path $b64Dir -Force | Out-Null
        [System.IO.File]::WriteAllText((Join-Path $b64Dir 'debug-keystore.b64'), 'not a key, just a marker')
        $b64 = Invoke-Child @('-Rotate', '-OutDir', $b64Dir)
        if ($b64.ExitCode -eq 1) { Test-Ok 'an existing base64 file is refused, not overwritten' }
        else { Test-No "an existing base64 file was not refused (exit $($b64.ExitCode))" }

        $inside = Invoke-Child @('-Rotate', '-OutDir', (Join-Path $RepoRoot 'scripts'))
        if ($inside.ExitCode -eq 1 -and $inside.Text -match 'repository') {
            Test-Ok 'an output folder inside the repository is refused'
        } else {
            Test-No "a folder inside the repository was not refused (exit $($inside.ExitCode))"
        }
    } finally {
        if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue }
    }

    Say ""
    if ($script:Failures -gt 0) {
        Bad "$($script:Failures) self-test check(s) FAILED."
        exit 1
    }
    Good "All self-test checks passed. Nothing was generated and no key was touched."
    exit 0
}

if ($SelfTest) { Invoke-SelfTest }

# ---------------------------------------------------------------------------
# From here on, a key is made. Nothing happens without the flag.
# ---------------------------------------------------------------------------
if (-not $Rotate) {
    Say ""
    Say "This script makes a NEW signing key for the phone app. That is a"
    Say "one-time ceremony, not a routine step: replacing the key means"
    Say "uninstalling the app on the phone once (which deletes its pairing"
    Say "token, approval key, widget slots and settings) and pairing again."
    Say ""
    Say "Nothing has been done. To go ahead, run it with -Rotate:"
    Say ""
    Say "  powershell -ExecutionPolicy Bypass -File .\scripts\rotate-android-signing-key.ps1 -Rotate"
    Say ""
    Say "Read docs/DEPLOY.md section 5 first - it is the whole ceremony, and"
    Say "it says why the key is being kept until you choose otherwise."
    exit 1
}

if (-not $OutDir) {
    $home_ = [Environment]::GetFolderPath('UserProfile')
    if (-not $home_) { Die "Could not find your user folder, so there is no safe default place for the key. Pass -OutDir with a folder outside this repository." }
    $OutDir = Join-Path $home_ '.jarvis\keys'
}

$outFull = [System.IO.Path]::GetFullPath($OutDir)
if (Test-InsideRepository $outFull) {
    Die @"
The output folder is inside this repository (or another git work tree):

    $outFull

A signing key must NEVER be committed. Put it outside every repository - the
default is `$env:USERPROFILE\.jarvis\keys - and run again with -OutDir if you
want a different folder.
"@
}

$targets = Get-TargetPaths $outFull

foreach ($path in @($targets.Keystore, $targets.Base64)) {
    if (Test-Path -LiteralPath $path) {
        Warn ""
        Warn "There is already a file at:"
        Warn "  $path"
        Warn ""
        Warn "This script will not replace it. Replacing a key is exactly the"
        Warn "one-time ceremony it exists for, so the old file has to be moved"
        Warn "away by you, on purpose, before a new one can be made:"
        Warn ""
        Warn "  Move-Item -LiteralPath '$path' -Destination '$path.old'"
        Warn ""
        Warn "Nothing was changed."
        exit 1
    }
}

$script:Keytool = Find-Tool 'keytool'
if (-not $script:Keytool) {
    Die "Could not find keytool, so no key can be made. It ships with the JDK; set JAVA_HOME, or add the JDK's bin folder to PATH."
}

$build = Get-BuildSigningValues $GradleFile
if (-not $build.Ok) { Die "Cannot tell which alias and password the Android build uses: $($build.Reason). Nothing was written." }

Say ""
Say "Making a new keystore. The alias and the password are the ones"
Say "jarvis-client/app/build.gradle.kts already gives the build - they are"
Say "read from that file and are not printed here."
Say ""

if (-not (Test-Path -LiteralPath $outFull -PathType Container)) {
    try {
        New-Item -ItemType Directory -Path $outFull -Force | Out-Null
    } catch {
        Die "Could not create the folder '$outFull': $($_.Exception.Message)"
    }
}

# The password reaches keytool on stdin, twice: once as the new keystore
# password and once as its confirmation. Never as an argument.
$stdin = "$($build.Password)`n$($build.Password)`n`n"
$generated = Invoke-Keytool @(
    '-genkeypair',
    '-keystore', $targets.Keystore,
    '-alias', $build.Alias,
    '-keyalg', 'RSA',
    '-keysize', '2048',
    '-sigalg', 'SHA256withRSA',
    '-validity', "$ValidityDays",
    '-dname', 'CN=Android Debug,O=Android,C=US'
) $stdin

if ($generated.ExitCode -ne 0) {
    if (Test-Path -LiteralPath $targets.Keystore) { Remove-Item -LiteralPath $targets.Keystore -Force -ErrorAction SilentlyContinue }
    Warn ($generated.Output -join [Environment]::NewLine)
    Die "keytool could not make the keystore (exit $($generated.ExitCode)). Nothing usable was left behind."
}

# Read the new certificate back OUT of the new key. The fingerprint is printed
# from the key itself, never assumed, and a key that cannot be read back is
# removed rather than handed over.
$check = Get-KeystoreFingerprint $targets.Keystore $build.Password $build.Alias
if (-not $check.Ok) {
    if (Test-Path -LiteralPath $targets.Keystore) { Remove-Item -LiteralPath $targets.Keystore -Force -ErrorAction SilentlyContinue }
    Warn ($check.Output -join [Environment]::NewLine)
    Die "The new keystore was made but could not be read back with the build's alias and password, so it would not be usable. It was removed."
}

$fingerprint = $check.Fingerprint

# The base64 text for the GitHub secret. Written next to the key, outside the
# repository; never echoed, because it IS the private key.
$bytes = [System.IO.File]::ReadAllBytes($targets.Keystore)
$b64 = [Convert]::ToBase64String($bytes)
[System.IO.File]::WriteAllText($targets.Base64, $b64, [System.Text.Encoding]::ASCII)

Good ""
Good "The new keystore is at:"
Good "  $($targets.Keystore)"
Good ""
Good "Its base64 text (for the GitHub secret) is at:"
Good "  $($targets.Base64)"
Good ""
Say "The certificate's SHA-256 fingerprint is:"
Say ""
Say "  $(Show-Grouped $fingerprint)"
Say ""
Say "and in the lowercase, no-colons form the code holds:"
Say ""
Say "  $fingerprint"
Say ""
Warn "The two files above are a PRIVATE KEY and its copy. Never commit them,"
Warn "never paste them into a chat or a report, and do not copy them into this"
Warn "repository. The fingerprint above is public and is safe to quote."
Say ""
Say "NOTHING has been published, changed or deleted. The app on the phone is"
Say "untouched and still works with the old key."
Say ""
Say "NEXT STEPS - in this order."
Say ""
Say "1. Put the new key in the GitHub secret, which is the only copy CI can read:"
Say "     GitHub > this repository > Settings > Secrets and variables > Actions"
Say "     > DEBUG_KEYSTORE_B64 > Update"
Say "   Paste from the file WITHOUT printing it:"
Say "     Get-Content -LiteralPath '$($targets.Base64)' -Raw | Set-Clipboard"
Say ""
Say "2. Change the two code pins, in the same commit:"
Say "     jarvis-client/app/src/main/java/com/jarvis/client/net/UpdateCheck.kt"
Say "       SIGNER_SHA256 = `"$fingerprint`""
Say "     jarvis-client/app/src/test/java/com/jarvis/client/UpdateCheckTest.kt"
Say "       private val expectedSigner = `"$fingerprint`""
Say "   Those are the two places the app checks a downloaded APK against."
Say ""
Say "3. Add the checked-in flag so the first release says the truth:"
Say "     jarvis-client/RELEASE-KEY-ROTATION   (an empty file)"
Say "   The release workflow reads it and puts a REQUIRED one-time-uninstall"
Say "   banner at the top of the release notes. Delete it in a later PR, after"
Say "   that one release is out."
Say ""
Say "4. Build and publish as usual (GitHub Actions does both)."
Say ""
Say "5. Then the one-time ceremony on the phone. This is the destructive part:"
Say "   a. Download the new APK in the phone's BROWSER from the release page."
Say "      The app already on the phone pins the OLD fingerprint, so its own"
Say "      Download button will refuse this one - that is the pin working."
Say "   b. Uninstall:  adb uninstall com.jarvis.client"
Say "      (or long-press the app > Uninstall). This deletes the app's data."
Say "   c. Install the new APK:  adb install -r <the apk>"
Say "      (or open the downloaded file on the phone)."
Say "   d. Pair again: on the PC, Settings > Connection > Show the token for my"
Say "      phone; then enter the address and that token on the phone."
Say ""
Say "WHAT THE UNINSTALL DELETES (verified in the app's own code, not guessed):"
Say "  - the pairing token, which also carries the device id"
Say "    (TokenStore: Keystore alias 'jarvis_token_key', encrypted blob in the"
Say "    'jarvis_secure' preferences);"
Say "  - the fingerprint/PIN approval key (Keystore alias 'jarvis_approval_key_v1'),"
Say "    so signed approvals are registered again on the next pairing;"
Say "  - the three home-screen widget slots' saved choices ('home_widget_' keys in"
Say "    the 'jarvis_client' preferences), and any widget already on the home"
Say "    screen becomes a dead tile to remove;"
Say "  - every local preference: the saved address, appearance, menu order,"
Say "    notification watch list, update settings and so on;"
Say "  - the captured-notifications key and its preferences."
Say "The PC's own records are untouched: pairing again does not delete memory,"
Say "notes, chat history or approvals on the PC."
Say ""
Say "docs/DEPLOY.md section 5 is the same ceremony in writing, with why the key"
Say "is being kept until you choose otherwise."
exit 0
