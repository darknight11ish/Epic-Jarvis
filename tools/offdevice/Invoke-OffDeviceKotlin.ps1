<#
.SYNOPSIS
Compile a few Kotlin files - and RUN their JUnit tests - off-device, with the
pinned Kotlin compiler and JUnit already sitting in this machine's Gradle cache.

.DESCRIPTION
WHY THIS EXISTS (2026-10-08)

There is no Android SDK on this machine and virtualisation is off in its
firmware, so `./gradlew testDebugUnitTest` cannot run here at all: the phone's
~1900 unit tests are only ever run by CI. Three separate agents rediscovered on
2026-10-08 that the pinned compilers are already in the local Gradle cache and
hand-rolled a script to compile and run a few files plus their JUnit tests
off-device - one in `.dsh-scratch/retrieve-port/.ktcheck/`, one in
`.dsh-scratch/approve-freeze/.ktcheck/`, one preserved at
`%TEMP%\captcha-ktcheck-preserved`. Each took about an hour and each hardcoded
one machine's absolute jar paths, one machine's worktree, and the exact file
list of the moment. This is that trick, once, committed.

WHAT IT PROVES: the files you name compile, with the same Kotlin the app is
built with, and the tests you name pass on a plain JVM.

WHAT IT DOES NOT PROVE: anything Gradle does. The Android/Compose plugin, the
serialization plugin, R8, the manifest, resources, another ~1900 tests, and the
phone itself - none of them are here. See docs/OFF-DEVICE-COMPILE.md.

HOW IT FINDS THINGS. Nothing machine-specific is typed in:

  * the GRADLE CACHE root is `%GRADLE_USER_HOME%` (or `%USERPROFILE%\.gradle`),
    then `caches\modules-2\files-2.1`;
  * the KOTLIN version is read out of `jarvis-client/build.gradle.kts`, and the
    JUnit version out of `jarvis-client/app/build.gradle.kts` - the same files
    the build itself is pinned by;
  * a jar is found under `<cache>\<group as path>\<artifact>\<version>\<hash>\`,
    so the cache's own hash directory is never named here;
  * `-Jar group:artifact` takes its version from the app's own dependency
    lines when they name it, and otherwise takes the newest in the cache - and
    the table it prints says which, every time.

IT FAILS LOUDLY. If the compiler, the stdlib, JUnit or the annotations jar are
not in the cache, it stops with the path it looked in and what it wanted. If
nothing was named to compile, if every named file was empty of declarations, if
the compiler produced no class files, or if JUnit printed no test count, it
stops too - a run that compiled nothing must never look like a pass.

.PARAMETER Source
Real Kotlin sources to compile (files or directories; a directory is read
recursively for *.kt). These are the app's own files, unmodified.

.PARAMETER Test
JUnit test sources. Each one's test class is derived from its own
`package` line and file name and RUN, unless -Class names the classes instead.

.PARAMETER Shim
Extra Kotlin to compile alongside - a hand-written stand-in for something that
cannot be compiled here. Each file says in its own header what it stands for.
The recipes in docs/OFF-DEVICE-COMPILE.md need none of these: -Extract and
-Const generate the stand-ins they need straight from the real file, so a
constant added to the real file cannot quietly go missing from the stand-in.

.PARAMETER Extract
`<file>::<declaration>` - lift ONE whole declaration (word for word) out of a
file that cannot be compiled off-device, with the import lines from that file
that the declaration needs. Example:
`-Extract "ui/Nav.kt::enum class Screen {"` (the real file is mostly @Composable
navigation). The generated file carries a header saying where it came from.

.PARAMETER Const
`<file>::<name>` - lift ONE `const val <name>` out of a file that cannot be
compiled off-device, keeping it inside the `object`/`class` that declares it.
Example: `-Const "net/ForgetRange.kt::PLACE"`. Only that constant is kept; the
rest of the object (and of the file) is not here, which is the limitation the
doc names.

.PARAMETER Jar
An extra dependency from the cache, as `group:artifact` or
`group:artifact:version` (a version of `any` means "newest in the cache").
Example: `-Jar org.jetbrains.kotlinx:kotlinx-serialization-json-jvm`.

.PARAMETER Resources
Directories (or files) put on the test classpath, so
`getResource("contract/menu-cases.json")` finds the fixture Gradle would have
handed it.

.PARAMETER Class
Test classes to run, fully qualified. Default: derived from -Test.

.PARAMETER RepoRoot
The checkout the paths are relative to, and the working directory the tests run
in (several tests walk UP from it looking for repo files). Default: this
script's own repository.

.PARAMETER WorkDir
Where the copied sources and class files go. Default: a fresh directory under
%TEMP%. -Keep leaves it there and prints the path.

.PARAMETER GradleCache
The `caches\modules-2\files-2.1` directory to read. Default: %GRADLE_USER_HOME%,
else %USERPROFILE%\.gradle.

.PARAMETER KotlinVersion
The compiler and stdlib version to look for. Default: read out of
jarvis-client/build.gradle.kts.

.PARAMETER JunitVersion
The JUnit version to look for. Default: read out of
jarvis-client/app/build.gradle.kts.

.PARAMETER CompileOnly
Compile and stop. Nothing is run, so the result says NOTHING about behaviour -
which is exactly what it prints.

.PARAMETER Keep
Leave the work directory (the copied sources, the compiler log, the JUnit log)
in place and print its path, for when a run needs reading rather than repeating.

.NOTES
LISTS. `pwsh -File` hands an array parameter over as ONE string and refuses the
same parameter twice, so every list here is split by the script: paths, jars and
class names on a comma or a semicolon, and an -Extract/-Const spec on a
SEMICOLON only (a declaration can contain a comma; a Windows path cannot
contain either). So:

    -Source "a.kt,b.kt"      -Jar "g:a,g:b"      -Test "X.kt,Y.kt"
    -Extract "A.kt::val x = {;B.kt::enum class Y {"

.EXAMPLE
pwsh -File tools/offdevice/Invoke-OffDeviceKotlin.ps1 -Test jarvis-client/app/src/test/java/com/jarvis/client/ApprovalDecisionTest.kt

.EXAMPLE
pwsh -File tools/offdevice/Invoke-OffDeviceKotlin.ps1 -Source jarvis-client/app/src/main/java/com/jarvis/client/net/RetrieveCount.kt -Extract "jarvis-client/app/src/main/java/com/jarvis/client/net/ApiModels.kt::val JarvisJson = Json {;jarvis-client/app/src/main/java/com/jarvis/client/net/JarvisApi.kt::sealed interface ApiError {" -Jar "org.jetbrains.kotlinx:kotlinx-serialization-json-jvm,org.jetbrains.kotlinx:kotlinx-serialization-core-jvm" -Test jarvis-client/app/src/test/java/com/jarvis/client/RetrieveCountTest.kt

.NOTES
docs/OFF-DEVICE-COMPILE.md has the recipes for the real tests, what each
stand-in stands for, and what none of this proves.
#>
[CmdletBinding()]
param(
    [string[]] $Source = @(),
    [string[]] $Test = @(),
    [string[]] $Shim = @(),
    [string[]] $Extract = @(),
    [string[]] $Const = @(),
    [string[]] $Jar = @(),
    [string[]] $Resources = @(),
    [string[]] $Class = @(),
    [string] $RepoRoot,
    [string] $WorkDir,
    [string] $GradleCache,
    [string] $KotlinVersion,
    [string] $JunitVersion,
    [switch] $CompileOnly,
    [switch] $Keep
)

$ErrorActionPreference = 'Stop'

# Every way out of this script goes through Fail, so a reader never has to work
# out whether an odd exit code meant "no" or "broken".
function Fail([string] $Message) {
    Write-Host ''
    Write-Host "offdevice: STOPPED - $Message" -ForegroundColor Red
    exit 2
}

function Step([string] $Message) { Write-Host "offdevice: $Message" }

# ---------------------------------------------------------------- the checkout

# `pwsh -File` hands an array parameter over as ONE string (and refuses the same
# parameter twice), so every list is split here rather than trusting the binder.
# Paths, jars and class names split on a comma or a semicolon; an -Extract or
# -Const spec splits on a semicolon ONLY, because a declaration can contain a
# comma (`class Bar(val a: Int, val b: Int)`) and a Windows path cannot contain
# either. A path with a comma in it would have to be passed by calling this
# script in-process; none in this repository has one.
function Split-List([string[]] $Values, [string] $Separator = '[,;]') {
    $out = New-Object System.Collections.Generic.List[string]
    foreach ($v in $Values) {
        foreach ($piece in ($v -split $Separator)) {
            $p = $piece.Trim().Trim('"')
            if ($p) { $out.Add($p) }
        }
    }
    return $out
}

$Source = Split-List $Source
$Test = Split-List $Test
$Shim = Split-List $Shim
$Jar = Split-List $Jar
$Resources = Split-List $Resources
$Class = Split-List $Class
$Extract = Split-List $Extract ';'
$Const = Split-List $Const ';'

if (-not $RepoRoot) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}
if (-not (Test-Path -LiteralPath $RepoRoot)) { Fail "the repository root does not exist: $RepoRoot" }
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path

$appBuild = Join-Path $RepoRoot 'jarvis-client\app\build.gradle.kts'
$rootBuild = Join-Path $RepoRoot 'jarvis-client\build.gradle.kts'

# A path as written in a recipe, resolved against the checkout first (so the
# command works from anywhere) and then against the current directory.
function Resolve-Input([string] $Path, [string] $What) {
    if (-not $Path) { Fail "$What was given an empty path" }
    $tries = @()
    if ([System.IO.Path]::IsPathRooted($Path)) { $tries += $Path }
    else {
        $tries += (Join-Path $RepoRoot $Path)
        $tries += (Join-Path (Get-Location).Path $Path)
    }
    foreach ($t in $tries) {
        if (Test-Path -LiteralPath $t) { return (Resolve-Path -LiteralPath $t).Path }
    }
    Fail ("$What was not found. Tried:`n    " + ($tries -join "`n    "))
}

function Expand-Kotlin([string[]] $Paths, [string] $What) {
    $files = New-Object System.Collections.Generic.List[string]
    foreach ($p in $Paths) {
        $resolved = Resolve-Input $p $What
        if (Test-Path -LiteralPath $resolved -PathType Container) {
            $found = @(Get-ChildItem -LiteralPath $resolved -Recurse -File -Filter '*.kt' |
                       Sort-Object FullName | ForEach-Object { $_.FullName })
            if ($found.Count -eq 0) { Fail "$What '$p' is a directory with no *.kt under it" }
            foreach ($f in $found) { $files.Add($f) }
        } else {
            if ([System.IO.Path]::GetExtension($resolved) -ne '.kt') { Fail "$What '$p' is not a .kt file" }
            $files.Add($resolved)
        }
    }
    return $files
}

# ------------------------------------------------------- the pinned versions

function Read-Pinned([string] $File, [string] $Pattern, [string] $What) {
    if (-not (Test-Path -LiteralPath $File)) { return $null }
    $text = Get-Content -LiteralPath $File -Raw
    $m = [regex]::Match($text, $Pattern)
    if ($m.Success) { return $m.Groups[1].Value }
    return $null
}

# The dependency lines the app is pinned by, as `group:artifact` -> version.
# Read from the build files, not typed in here, so bumping the app bumps this.
function Read-Dependencies() {
    $map = @{}
    foreach ($f in @($appBuild, $rootBuild)) {
        if (-not (Test-Path -LiteralPath $f)) { continue }
        foreach ($m in [regex]::Matches((Get-Content -LiteralPath $f -Raw),
                                        '([A-Za-z][\w.\-]*):([A-Za-z][\w.\-]*):([0-9][\w.\-]*)')) {
            $map["$($m.Groups[1].Value):$($m.Groups[2].Value)"] = $m.Groups[3].Value
        }
    }
    return $map
}

$deps = Read-Dependencies

# Which version of an artifact this repository is pinned to, where it can be
# told: the exact coordinate from the build files, then the same coordinate
# without the `-jvm` suffix the cache uses, then any other artifact of the same
# FAMILY (`kotlinx-coroutines-core-jvm` follows the version the app declares for
# `kotlinx-coroutines-android`; the family - not the group - because
# kotlinx.serialization and kotlinx.coroutines share a group and do not share a
# version). 'any' means "newest in the cache", which the printed table shows.
function Get-CachedVersion([string] $Group, [string] $Artifact) {
    if ($deps.ContainsKey("$Group`:$Artifact")) { return $deps["$Group`:$Artifact"] }
    if ($Artifact.EndsWith('-jvm')) {
        $base = $Artifact.Substring(0, $Artifact.Length - 4)
        if ($deps.ContainsKey("$Group`:$base")) { return $deps["$Group`:$base"] }
    }
    $parts = @($Artifact -split '-')
    if ($parts.Count -ge 2) {
        $family = "$($parts[0])-$($parts[1])"
        $sameFamily = @($deps.Keys | Where-Object { $_ -like "$Group`:$family*" } |
                        ForEach-Object { $deps[$_] } | Sort-Object -Unique)
        if ($sameFamily.Count -gt 0) {
            return @($sameFamily | Sort-Object -Property @{ Expression = {
                        try { [version] $_ } catch { [version] '0.0' } } })[-1]
        }
    }
    return 'any'
}
if (-not $KotlinVersion) {
    $KotlinVersion = Read-Pinned $rootBuild 'org\.jetbrains\.kotlin\.plugin\.compose"\)\s+version\s+"([^"]+)"' 'the Kotlin version'
    if (-not $KotlinVersion) {
        Fail "the pinned Kotlin version could not be read from $rootBuild - pass -KotlinVersion <version>"
    }
}
if (-not $JunitVersion) {
    $JunitVersion = $deps['junit:junit']
    if (-not $JunitVersion) {
        $JunitVersion = Read-Pinned $appBuild 'junit:junit:([0-9][^")\s]*)' 'the JUnit version'
    }
    if (-not $JunitVersion) {
        Fail "the pinned JUnit version could not be read from $appBuild - pass -JunitVersion <version>"
    }
}

# ------------------------------------------------------------- the Gradle cache

if ($GradleCache) {
    $cache = $GradleCache
} elseif ($env:GRADLE_USER_HOME) {
    $cache = Join-Path $env:GRADLE_USER_HOME 'caches\modules-2\files-2.1'
} else {
    $cache = Join-Path $env:USERPROFILE '.gradle\caches\modules-2\files-2.1'
}
if (-not (Test-Path -LiteralPath $cache)) {
    Fail @"
the Gradle cache is not here: $cache
  Override it with -GradleCache <path to ...\caches\modules-2\files-2.1>.
  Without the cache there is no pinned Kotlin compiler on this machine and
  nothing can be compiled off-device; CI remains the only judge.
"@
}
$cache = (Resolve-Path -LiteralPath $cache).Path

$resolved = New-Object System.Collections.Generic.List[object]

# The hash directory under <version> is the cache's own, so it is globbed and
# never written down. -Version 'any' takes the newest version present.
function Resolve-CacheJar([string] $Group, [string] $Artifact, [string] $Version, [string] $Why) {
    # Gradle keeps the group id whole, dots and all:
    #   <cache>\org.jetbrains.kotlin\kotlin-stdlib\2.4.20\<hash>\kotlin-stdlib-2.4.20.jar
    # A Maven-shaped cache (the dots as directories) is looked for too, because
    # guessing the layout is cheaper than telling the next reader their cache is
    # "wrong" when it is merely laid out the other way.
    $dir = Join-Path (Join-Path $cache $Group) $Artifact
    if (-not (Test-Path -LiteralPath $dir)) {
        $mavenish = Join-Path $cache ((($Group -replace '\.', '\')) + '\' + $Artifact)
        if (Test-Path -LiteralPath $mavenish) { $dir = $mavenish }
    }
    if (-not (Test-Path -LiteralPath $dir)) {
        Fail @"
$Why is not in the Gradle cache.
  wanted:   ${Group}:${Artifact} $(if ($Version) { $Version } else { '(any version)' })
  looked in: $dir
  The cache holds what the Android build has already downloaded. If this jar
  has never been fetched on this machine, it is not here - and this check
  cannot be run off-device without it. CI is the judge.
"@
    }
    $versions = @(Get-ChildItem -LiteralPath $dir -Directory | Sort-Object Name)
    if ($versions.Count -eq 0) { Fail "$Why has no version directory under $dir" }
    if ($Version -and $Version -ne 'any') {
        $want = $versions | Where-Object { $_.Name -eq $Version }
        if (-not $want) {
            $have = ($versions | ForEach-Object { $_.Name }) -join ', '
            Fail @"
$Why is in the cache, but not at the pinned version.
  wanted:   ${Group}:${Artifact}:$Version
  present:  $have
  looked in: $dir
  A different version than the app is built with is not the same dependency, so
  this stops rather than quietly compiling against something else. Pass the
  version yourself (`-Jar ${Group}:${Artifact}:<version>`) if a different one is
  wanted on purpose.
"@
        }
        $vdir = @($want)[0]
    } else {
        # Newest by version where the names are versions, else newest by name.
        $numbered = @($versions | Where-Object { $_.Name -match '^[0-9]+(\.[0-9]+)*' })
        if ($numbered.Count -gt 0) {
            $vdir = @($numbered | Sort-Object -Property @{ Expression = {
                        $v = ($_.Name -split '-')[0]
                        try { [version] $v } catch { [version] '0.0' } } })[-1]
        } else {
            $vdir = $versions[-1]
        }
    }
    $jar = @(Get-ChildItem -LiteralPath $vdir.FullName -Recurse -File -Filter "$Artifact-*.jar" |
             Where-Object { $_.Name -notlike '*-sources.jar' -and $_.Name -notlike '*-javadoc.jar' } |
             Sort-Object Name)
    if ($jar.Count -eq 0) { Fail "$Why has no jar under $($vdir.FullName)" }
    $chosen = $jar[0]
    $resolved.Add([pscustomobject]@{ What = $Why; Coordinate = "$Group`:$Artifact`:$($vdir.Name)"; Path = $chosen.FullName })
    return $chosen.FullName
}

Step "checked out:   $RepoRoot"
Step "Gradle cache:  $cache"
Step "pinned Kotlin: $KotlinVersion   JUnit: $JunitVersion"

$compilerJar = Resolve-CacheJar 'org.jetbrains.kotlin' 'kotlin-compiler-embeddable' $KotlinVersion 'the Kotlin compiler'
$stdlibJar = Resolve-CacheJar 'org.jetbrains.kotlin' 'kotlin-stdlib' $KotlinVersion 'the Kotlin standard library'
$junitJar = Resolve-CacheJar 'junit' 'junit' $JunitVersion 'JUnit'
$hamcrestJar = Resolve-CacheJar 'org.hamcrest' 'hamcrest-core' 'any' 'Hamcrest (JUnit needs it to assert)'
# The compiler itself generates code that references org.jetbrains.annotations,
# so it needs that jar on its own classpath: without it codegen dies with
# "NoClassDefFoundError: org/jetbrains/annotations/Nullable". It also needs
# kotlinx-coroutines at STARTUP ("NoClassDefFoundError:
# kotlinx/coroutines/CoroutineScope" before a single file is read) - both are
# the compiler's own dependencies, not the sources'.
$annotationsJar = Resolve-CacheJar 'org.jetbrains' 'annotations' 'any' 'org.jetbrains:annotations (the compiler needs it to generate code)'
$coroutinesJar = Resolve-CacheJar 'org.jetbrains.kotlinx' 'kotlinx-coroutines-core-jvm' (Get-CachedVersion 'org.jetbrains.kotlinx' 'kotlinx-coroutines-core-jvm') 'kotlinx-coroutines-core-jvm (the compiler needs it to start)'

foreach ($spec in $Jar) {
    $parts = $spec.Split(':')
    if ($parts.Count -lt 2 -or $parts.Count -gt 3) { Fail "-Jar '$spec' is not group:artifact or group:artifact:version" }
    $group = $parts[0]
    $artifact = $parts[1]
    if ($parts.Count -eq 3) { $version = $parts[2] } else { $version = Get-CachedVersion $group $artifact }
    $null = Resolve-CacheJar $group $artifact $version "-Jar $spec"
}

# ------------------------------------------------------------------ the work

$sources = Expand-Kotlin $Source '-Source'
$tests = Expand-Kotlin $Test '-Test'
$shims = Expand-Kotlin $Shim '-Shim'
$extracted = New-Object System.Collections.Generic.List[object]

# The body of one declaration, from its needle to its matching close brace -
# skipping braces inside strings, chars and comments, so a Kotlin string that
# holds a `}` does not end the declaration early.
function Get-Declaration([string] $Text, [string] $Needle, [string] $Where) {
    $at = $Text.IndexOf($Needle, [System.StringComparison]::Ordinal)
    if ($at -lt 0) { Fail "-Extract $Where`: '$Needle' was not found in that file" }
    $lineEnd = $Text.IndexOf("`n", $at)
    if ($lineEnd -lt 0) { $lineEnd = $Text.Length }
    $head = $Text.Substring($at, $lineEnd - $at)
    $braceInHead = $head.IndexOf([char] 0x7B)
    if ($braceInHead -lt 0) { return $head.TrimEnd("`r", "`n", " ", "`t") }

    $open = $at + $braceInHead
    $depth = 0
    $i = $open
    $len = $Text.Length
    $mode = 'code'
    while ($i -lt $len) {
        $c = $Text[$i]
        if ($mode -eq 'line') { if ($c -eq [char] 0x0A) { $mode = 'code' }; $i++; continue }
        if ($mode -eq 'block') {
            if ($c -eq [char] 0x2A -and $i + 1 -lt $len -and $Text[$i + 1] -eq [char] 0x2F) { $mode = 'code'; $i += 2; continue }
            $i++; continue
        }
        if ($mode -eq 'dq') {
            if ($c -eq [char] 0x5C) { $i += 2; continue }
            if ($c -eq [char] 0x22) { $mode = 'code' }
            $i++; continue
        }
        if ($mode -eq 'raw') {
            if ($c -eq [char] 0x22 -and $i + 2 -lt $len -and $Text[$i + 1] -eq [char] 0x22 -and $Text[$i + 2] -eq [char] 0x22) {
                $mode = 'code'; $i += 3; continue
            }
            $i++; continue
        }
        if ($mode -eq 'char') {
            if ($c -eq [char] 0x5C) { $i += 2; continue }
            if ($c -eq [char] 0x27) { $mode = 'code' }
            $i++; continue
        }
        if ($c -eq [char] 0x2F) {                                   # /
            if ($i + 1 -lt $len -and $Text[$i + 1] -eq [char] 0x2F) { $mode = 'line'; $i += 2; continue }
            if ($i + 1 -lt $len -and $Text[$i + 1] -eq [char] 0x2A) { $mode = 'block'; $i += 2; continue }
        } elseif ($c -eq [char] 0x22) {                             # "
            if ($i + 2 -lt $len -and $Text[$i + 1] -eq [char] 0x22 -and $Text[$i + 2] -eq [char] 0x22) { $mode = 'raw'; $i += 3; continue }
            $mode = 'dq'; $i++; continue
        } elseif ($c -eq [char] 0x27) { $mode = 'char'; $i++; continue }   # '
        elseif ($c -eq [char] 0x7B) { $depth++; $i++; continue }           # {
        elseif ($c -eq [char] 0x7D) {                                      # }
            $depth--
            if ($depth -eq 0) { return $Text.Substring($at, $i - $at + 1) }
            $i++; continue
        }
        $i++
    }
    Fail "-Extract $Where`: the braces never balanced - is '$Needle' a whole declaration?"
}

function Get-Package([string] $Text) {
    $m = [regex]::Match($Text, '(?m)^package\s+([\w.]+)')
    if (-not $m.Success) { Fail "that file has no package line, so a stand-in lifted from it has nowhere to live" }
    return $m.Groups[1].Value
}

# Only the import lines whose own name is used by the lifted text. A missing one
# shows up as a compile error naming the symbol, which is the right way round.
function Get-NeededImports([string] $Text, [string] $Body) {
    $kept = New-Object System.Collections.Generic.List[string]
    foreach ($m in [regex]::Matches($Text, '(?m)^import\s+([\w.]+)\s*$')) {
        $fqn = $m.Groups[1].Value
        $simple = ($fqn -split '\.')[-1]
        if ([regex]::IsMatch($Body, "\b$([regex]::Escape($simple))\b")) { $kept.Add($fqn) }
    }
    return $kept
}

$n = 0
foreach ($spec in $Extract) {
    $split = $spec.IndexOf('::')
    if ($split -lt 1) { Fail "-Extract '$spec' is not <file>::<declaration>" }
    $file = Resolve-Input $spec.Substring(0, $split) '-Extract'
    $needle = $spec.Substring($split + 2)
    $text = Get-Content -LiteralPath $file -Raw
    $body = Get-Declaration $text $needle $file
    $package = Get-Package $text
    $imports = Get-NeededImports $text $body
    $n++
    $extracted.Add([pscustomobject]@{
        Name = "Extracted$n.kt"; Package = $package; Body = $body; Imports = $imports
        Where = $file; What = $needle
        Why = "ONE declaration lifted, word for word, out of that file. Everything ELSE in the file is missing, and would be in the real build."
    })
}

foreach ($spec in $Const) {
    $split = $spec.IndexOf('::')
    if ($split -lt 1) { Fail "-Const '$spec' is not <file>::<name>" }
    $file = Resolve-Input $spec.Substring(0, $split) '-Const'
    $name = $spec.Substring($split + 2)
    $text = Get-Content -LiteralPath $file -Raw
    $m = [regex]::Match($text, "(?m)^([ \t]*)const val\s+$([regex]::Escape($name))\b[^\r\n]*")
    if (-not $m.Success) { Fail "-Const $file`: 'const val $name' was not found" }
    $line = $m.Value.Trim()
    $before = $text.Substring(0, $m.Index)
    $owner = $null
    foreach ($o in [regex]::Matches($before, '(?m)^([ \t]*)(?:private\s+|internal\s+)?(?:object|class)\s+(\w+)\s*\{')) { $owner = $o }
    if ($owner) {
        $body = "$($owner.Groups[1].Value)object $($owner.Groups[2].Value) {`n    $line`n}"
        $why = "ONLY the constant '$name' is kept, inside the object that declares it. The other members of that object - and the rest of the file - are not here."
    } else {
        $body = $line
        $why = "ONLY the constant '$name' is kept. The rest of the file is not here."
    }
    $package = Get-Package $text
    $n++
    $extracted.Add([pscustomobject]@{
        Name = "Extracted$n.kt"; Package = $package; Body = $body; Imports = @()
        Where = $file; What = "const val $name"
        Why = $why
    })
}

if ($sources.Count + $tests.Count + $shims.Count + $extracted.Count -eq 0) {
    Fail @"
nothing was named to compile or run - refusing to report a pass having done
nothing. Name at least one -Source, -Test, -Shim, -Extract or -Const.
"@
}

if (-not $WorkDir) {
    $WorkDir = Join-Path $env:TEMP ('offdevice-' + [System.IO.Path]::GetRandomFileName().Replace('.', ''))
}
$srcDir = Join-Path $WorkDir 'src'
$classesDir = Join-Path $WorkDir 'classes'
if (Test-Path -LiteralPath $WorkDir) { Remove-Item -LiteralPath $WorkDir -Recurse -Force }
$null = New-Item -ItemType Directory -Force -Path $srcDir, $classesDir

function Copy-In([string] $From, [string] $What) {
    $name = [System.IO.Path]::GetFileName($From)
    $to = Join-Path $srcDir $name
    if ((Test-Path -LiteralPath $to) -and
        ((Get-FileHash -LiteralPath $to -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $From -Algorithm SHA256).Hash)) {
        Fail @"
two different files are both called ${name}:
    $to
    $From   ($What)
  Give them different names, or compile them in two runs. Silent one-wins
  copying is how a check ends up testing a file nobody named.
"@
    }
    Copy-Item -LiteralPath $From -Destination $to -Force
}

foreach ($f in $sources) { Copy-In $f '-Source' }
foreach ($f in $tests) { Copy-In $f '-Test' }
foreach ($f in $shims) { Copy-In $f '-Shim' }

foreach ($e in $extracted) {
    $head = @(
        '// GENERATED by tools/offdevice/Invoke-OffDeviceKotlin.ps1 - do not edit, and',
        '// do not commit as source. It is a STAND-IN, not a copy of the real file.',
        '//',
        "// lifted from : $($e.Where)",
        "// kept        : $($e.What)",
        "// limitation  : $($e.Why)",
        "package $($e.Package)"
    )
    foreach ($i in $e.Imports) { $head += "import $i" }
    $body = ($head -join "`n") + "`n`n" + $e.Body.TrimEnd() + "`n"
    Set-Content -LiteralPath (Join-Path $srcDir $e.Name) -Value $body -Encoding UTF8
}

$ktFiles = @(Get-ChildItem -LiteralPath $srcDir -File -Filter '*.kt' | Sort-Object Name | ForEach-Object { $_.FullName })
if ($ktFiles.Count -eq 0) { Fail "no .kt file reached the work directory ($srcDir) - nothing would be compiled" }

Step "work dir:      $WorkDir"
Step "compiling:     $($ktFiles.Count) Kotlin file(s)"
foreach ($f in $ktFiles) { Write-Host ("offdevice:   " + [System.IO.Path]::GetFileName($f)) }

foreach ($r in $resolved) {
    Write-Host ("offdevice:   {0,-52} {1}" -f $r.Coordinate, $r.Path)
}

# ------------------------------------------------------------------ compile

$compilerCp = @($compilerJar, $stdlibJar, $annotationsJar, $coroutinesJar) -join ';'
$extra = @($resolved | Where-Object { $_.What -like '-Jar *' } | ForEach-Object { $_.Path })
$runtimeCp = @($stdlibJar, $junitJar, $hamcrestJar) + $extra
$compileCp = ($runtimeCp) -join ';'

$log = Join-Path $WorkDir 'kotlin.log'
$cliArgs = @('-cp', $compilerCp, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
             '-no-stdlib', '-jvm-target', '17', '-cp', $compileCp, '-d', $classesDir) + $ktFiles
& java @cliArgs > $log 2>&1
$code = $LASTEXITCODE
$out = Get-Content -LiteralPath $log -Raw
if ($out) { $out.TrimEnd() | Write-Host }

if ($code -ne 0) {
    Fail @"
the Kotlin compiler REJECTED the sources (exit $code). The diagnostics above
are the real ones, from the same compiler the app is built with.
  full log: $log
"@
}

$classFiles = @(Get-ChildItem -LiteralPath $classesDir -Recurse -File -Filter '*.class')
if ($classFiles.Count -eq 0) {
    Fail "the compiler reported success but produced no class file in $classesDir - that is not a pass"
}
Step "compiled OK:   $($classFiles.Count) class file(s)"

# --------------------------------------------------------------------- run

if ($CompileOnly) {
    Step "RESULT: the named files compile (-CompileOnly: no test was run, so this says NOTHING about behaviour)"
    if (-not $Keep) { Remove-Item -LiteralPath $WorkDir -Recurse -Force -ErrorAction SilentlyContinue }
    exit 0
}

$testClasses = New-Object System.Collections.Generic.List[string]
foreach ($c in $Class) { $testClasses.Add($c) }
if ($testClasses.Count -eq 0) {
    foreach ($f in $tests) {
        $text = Get-Content -LiteralPath $f -Raw
        $m = [regex]::Match($text, '(?m)^package\s+([\w.]+)')
        if (-not $m.Success) { Fail "$f has no package line, so its test class cannot be named" }
        $testClasses.Add("$($m.Groups[1].Value).$([System.IO.Path]::GetFileNameWithoutExtension($f))")
    }
}
if ($testClasses.Count -eq 0) {
    Fail "no test was named and none could be derived from -Test - refusing to report a pass having run nothing"
}

# JUnit answers a class it cannot find with one synthetic "initializationError"
# test, which would otherwise be counted here as "1 test ran". A class this
# compile did not produce is not a test that ran, so it is checked for first.
foreach ($c in $testClasses) {
    $classFile = Join-Path $classesDir (($c -replace '\.', '\') + '.class')
    if (-not (Test-Path -LiteralPath $classFile)) {
        Fail @"
the test class $c was not produced by this compile, so NOTHING would have been
run. Wanted:
    $classFile
  Check the class name (its package and file name must match), or that the -Test
  file really declares it.
"@
    }
}

$resCp = @($Resources | ForEach-Object { Resolve-Input $_ '-Resources' })
$runCp = (@($classesDir) + $runtimeCp + $resCp) -join ';'

Step "running:       $($testClasses -join ', ')"
Step "working dir:   $RepoRoot  (tests that walk up for repo files start here)"

$runLog = Join-Path $WorkDir 'junit.log'
$runArgs = @('-cp', $runCp, 'org.junit.runner.JUnitCore') + $testClasses
Push-Location $RepoRoot
try { & java @runArgs > $runLog 2>&1; $runCode = $LASTEXITCODE } finally { Pop-Location }
$runOut = Get-Content -LiteralPath $runLog -Raw
if ($runOut) { $runOut.TrimEnd() | Write-Host }

$okCounts = [regex]::Matches($runOut, 'OK \((\d+) tests?\)')
$ranCounts = [regex]::Matches($runOut, 'Tests run: (\d+)')
$total = 0
foreach ($m in $okCounts) { $total += [int] $m.Groups[1].Value }
foreach ($m in $ranCounts) { $total += [int] $m.Groups[1].Value }
if ($okCounts.Count -eq 0 -and $ranCounts.Count -eq 0) {
    Fail @"
JUnit printed no test count, so NOTHING was run - this is not a pass. The
output above says why (a class it could not find, a classpath problem, or a
test class that does not exist).
  full log: $runLog
"@
}
if ($total -eq 0) { Fail "JUnit ran 0 tests - this is not a pass" }

if ($runCode -ne 0) {
    Fail @"
$total test(s) ran and at least one FAILED (JUnit exit $runCode). The failure
and its stack trace are above.
  full log: $runLog
"@
}

Step "RESULT: $total test(s) ran, 0 failed - the named files compile and the named tests pass"
Step "        this proves the touched files compile and the touched tests pass. It does NOT prove Gradle's whole-app build, the other tests, or the phone. See docs/OFF-DEVICE-COMPILE.md."
if ($Keep) { Step "work dir kept: $WorkDir" } else { Remove-Item -LiteralPath $WorkDir -Recurse -Force -ErrorAction SilentlyContinue }
exit 0
