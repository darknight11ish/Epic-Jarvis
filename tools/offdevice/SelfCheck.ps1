<#
.SYNOPSIS
Prove tools/offdevice/Invoke-OffDeviceKotlin.ps1 is not vacuous.

.DESCRIPTION
A checker that cannot fail is worse than no checker: it is a green tick over
nothing (tools/check_vacuous_checks.py exists because this repository has been
bitten by exactly that). So this runs the driver four times against throwaway
files and insists on all four answers:

  1. a source file that does NOT compile        -> the run must STOP, non-zero
  2. a JUnit test asserting something FALSE     -> the run must STOP, non-zero
  3. a good source and a good test              -> the run must PASS, 0 failed,
                                                   with a test count above zero
  4. nothing named to compile at all            -> the run must STOP rather
                                                   than report a pass having
                                                   compiled nothing
  5. a test class that does not exist           -> the run must STOP rather
                                                   than report a pass having
                                                   run nothing

It also prints, for each case, the exact exit code and the line the driver
stopped on, so "it failed" can be told apart from "it failed for the reason I
meant".

    pwsh -File tools/offdevice/SelfCheck.ps1

Exit 0 means the driver passed all five. Exit 1 means at least one answer was
wrong, and says which.

WHY THIS FILE IS HERE AND NOT IN backend/. backend/test_*.py is collected by
backend/run_suites.py and therefore by CI's backend job. Wiring an off-device
Kotlin check into CI is the owner's call, not this tool's, so nothing here is
named in a way CI picks up on its own.
#>
[CmdletBinding()]
param(
    [string] $Driver,
    [switch] $Keep
)

$ErrorActionPreference = 'Stop'

if (-not $Driver) { $Driver = Join-Path $PSScriptRoot 'Invoke-OffDeviceKotlin.ps1' }
if (-not (Test-Path -LiteralPath $Driver)) { throw "the driver is not here: $Driver" }
$Driver = (Resolve-Path -LiteralPath $Driver).Path

$pwshExe = (Get-Process -Id $PID).Path
$case = Join-Path $env:TEMP ('offdevice-selfcheck-' + [System.IO.Path]::GetFileNameWithoutExtension([System.IO.Path]::GetRandomFileName()))
$null = New-Item -ItemType Directory -Force -Path $case

# The package matches the app's, so these are compiled exactly the way a real
# file would be. The sources are throwaway; none of them is in the repository.
$good = @'
package com.jarvis.client.selfcheck

/** The control: this compiles and its one behaviour is asserted below. */
object Good {
    fun twice(n: Int): Int = n * 2
}
'@

$goodTest = @'
package com.jarvis.client.selfcheck

import org.junit.Assert.assertEquals
import org.junit.Test

class GoodTest {
    @Test
    fun twiceDoubles() {
        assertEquals(42, Good.twice(21))
    }
}
'@

# A type error the compiler must refuse: Int times String.
$broken = @'
package com.jarvis.client.selfcheck

object Broken {
    fun twice(n: Int): Int = n * "two"
}
'@

# Compiles, runs, and fails on its own assertion.
$falseTest = @'
package com.jarvis.client.selfcheck

import org.junit.Assert.assertEquals
import org.junit.Test

class FalseTest {
    @Test
    fun twiceIsNotWhatItIs() {
        assertEquals("two times twenty-one is forty-three", 43, Good.twice(21))
    }
}
'@

Set-Content -LiteralPath (Join-Path $case 'Good.kt') -Value $good -Encoding UTF8
Set-Content -LiteralPath (Join-Path $case 'GoodTest.kt') -Value $goodTest -Encoding UTF8
Set-Content -LiteralPath (Join-Path $case 'Broken.kt') -Value $broken -Encoding UTF8
Set-Content -LiteralPath (Join-Path $case 'FalseTest.kt') -Value $falseTest -Encoding UTF8

function Invoke-Driver([string[]] $DriverArgs) {
    $out = (& $pwshExe -NoProfile -File $Driver @DriverArgs 2>&1 | Out-String)
    return [pscustomobject]@{ Out = $out; Code = $LASTEXITCODE }
}

function Show([string] $Label, $Run) {
    Write-Host ''
    Write-Host "===== $Label  (exit $($Run.Code))" -ForegroundColor Cyan
    foreach ($line in ($Run.Out -split "`r?`n")) {
        if ($line -match '^offdevice: (STOPPED|RESULT)|^offdevice: +this proves|^Tests run:|^OK \(|^FAILURES|^[0-9]+\) ' ) {
            Write-Host "  $line"
        }
    }
}

$problems = New-Object System.Collections.Generic.List[string]

# "It failed" and "it failed for the reason I meant" are different answers, so
# each case is checked in both directions - and the pass case is checked for a
# test count, because a pass that ran no test is the exact failure this whole
# self-check exists to catch.
function Expect-Stop([string] $What, $Run, [string] $Marker) {
    if ($Run.Code -eq 0) { $problems.Add("the driver PASSED $What") }
    elseif ($Run.Out -notmatch [regex]::Escape($Marker)) {
        $problems.Add("the driver failed $What for another reason (exit $($Run.Code), wanted '$Marker')")
    }
}
function Expect-Pass([string] $What, $Run, [string] $Marker) {
    if ($Run.Code -ne 0) { $problems.Add("the driver FAILED $What (exit $($Run.Code))") }
    elseif ($Run.Out -notmatch [regex]::Escape($Marker)) {
        $problems.Add("the driver passed $What without reporting what it ran (wanted '$Marker')")
    }
}

# 1. a source file that does not compile
$r1 = Invoke-Driver @('-Source', (Join-Path $case 'Broken.kt'))
Show 'CASE 1  a source file that does not compile' $r1
Expect-Stop 'a source file that does not compile' $r1 'Kotlin compiler REJECTED'

# 2. a JUnit test that asserts something false
$r2 = Invoke-Driver @('-Source', (Join-Path $case 'Good.kt'), '-Test', (Join-Path $case 'FalseTest.kt'))
Show 'CASE 2  a JUnit test asserting something false' $r2
Expect-Stop 'a JUnit test that asserts something false' $r2 'at least one FAILED'

# 3. a good source and a good test
$r3 = Invoke-Driver @('-Source', (Join-Path $case 'Good.kt'), '-Test', (Join-Path $case 'GoodTest.kt'))
Show 'CASE 3  a good source and a good test' $r3
Expect-Pass 'a good source and a good test' $r3 'OK (1 test)'

# 4. nothing named at all
$r4 = Invoke-Driver @()
Show 'CASE 4  nothing named to compile' $r4
Expect-Stop 'a run that named nothing to compile' $r4 'nothing was named to compile'

# 5. a test class that does not exist - the anti-vacuity guard. JUnit answers a
#    class it cannot find with ONE synthetic "initializationError" test, which a
#    count-only check would read as "1 test ran"; the driver must say instead
#    that the class was not produced at all.
$r5 = Invoke-Driver @('-Source', (Join-Path $case 'Good.kt'), '-Test', (Join-Path $case 'GoodTest.kt'),
                     '-Class', 'com.jarvis.client.selfcheck.NoSuchTest')
Show 'CASE 5  a test class that does not exist' $r5
Expect-Stop 'a run whose test class does not exist' $r5 'was not produced by this compile'

if (-not $Keep) { Remove-Item -LiteralPath $case -Recurse -Force -ErrorAction SilentlyContinue }

Write-Host ''
if ($problems.Count -gt 0) {
    Write-Host 'SELF-CHECK: NOT OK - the driver does not have the teeth it claims:' -ForegroundColor Red
    foreach ($p in $problems) { Write-Host "  * $p" -ForegroundColor Red }
    exit 1
}
Write-Host 'SELF-CHECK: OK - the driver fails on a file that does not compile, fails on a test that asserts something false, fails on a run that named nothing and on a test class that does not exist, and passes a good source with its test.' -ForegroundColor Green
exit 0
