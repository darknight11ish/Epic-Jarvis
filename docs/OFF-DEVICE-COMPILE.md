# Compiling and running a few Kotlin files off-device, 2026-10-08

**There is no Android SDK on the owner's PC and virtualisation is off in its
firmware, so `./gradlew testDebugUnitTest` cannot run here at all.** The phone's
unit tests are otherwise only ever run by CI, five minutes after a push. This is
the one committed way to compile a few of those files, and run their JUnit
tests, on this machine.

- **Where:** `tools/offdevice/Invoke-OffDeviceKotlin.ps1` (the driver) and
  `tools/offdevice/SelfCheck.ps1` (proof that the driver can fail).
- **Nothing machine-specific is written in either one.** See "How it finds the
  compiler" below.
- **It is wired into nothing.** No workflow, no `backend/test_*.py`, no
  `tools/check_*.py`. CI does not run it. See "What this does not replace".

## Why this exists, and why it is committed

On 2026-10-08 three separate agents, working on three different branches,
independently rediscovered the same trick: the pinned Kotlin compiler is already
sitting in this machine's Gradle cache, because the Android build downloaded it
before the SDK was ever needed. Each of them hand-rolled a script to compile a
few files and run their JUnit tests off-device:

- `.dsh-scratch/approve-freeze/.ktcheck/run-approval-tests.ps1`
- `%TEMP%\captcha-ktcheck-preserved\run-handoff-tests.ps1` and
  `run-places-tests.ps1` (preserved from `.dsh-scratch/captcha/.ktcheck/`)
- a third in `.dsh-scratch/retrieve-port/.ktcheck/`, which **no longer exists on
  disk**, was never committed, and has no copy in this repository's history
  (`git log --all --name-only -- "*ktcheck*"` prints nothing)

Each took roughly an hour, and each hardcoded one machine's absolute jar paths,
one worktree, and the exact file list of the moment. The trick is also what
caught two real things that day:

- a Compose-generated `$stable` field breaking a reflective test
  (`RetrieveCountTest` and `NotificationIdsTest` both name it), and
- four failing menu-contract tests on the phone, found and fixed before CI had
  to say so.

So the trick is worth keeping. Doing it a fourth time, by hand, is not.

## What it proves, and what it does not

**It proves** that the files you name compile with the same Kotlin the app is
built with, and that the tests you name pass on a plain JVM, against the same
contract fixtures Gradle would have handed them.

**It does not prove** any of the following, and a green run here is not a
substitute for any of them:

- that Gradle can build the app - the Android plugin, the Compose plugin, the
  serialization plugin, R8, the manifest, the resources and the resource merger
  are all absent here;
- that the other ~1900 phone tests pass - only the files you named ran;
- anything about the phone itself. **CI remains the judge**, and
  `jarvis-client.yml`'s `./gradlew testDebugUnitTest` step is the only thing
  that runs the whole suite the way it ships;
- anything about a stand-in being the real type. Every shim below is documented
  as one, because a test compiled against a stand-in can be satisfied by a
  stand-in that has drifted from the real file. The `-Extract` and `-Const`
  modes exist to make that drift hard: the stand-in is *generated from the real
  file at run time*, not typed a second time.

## How to run it

Give it real sources, real test files, and - when the real file cannot be
compiled on its own - the declaration to lift out of it. Every recipe below is
one line, ready to paste, run from the top of the checkout.

### 1. A test that only reads source files as text (no shim of any kind)

`ApprovalDecisionTest` reads `MainActivity.kt` as text, so it needs no source
files and no stand-ins at all:

```powershell
pwsh -File tools/offdevice/Invoke-OffDeviceKotlin.ps1 -Test jarvis-client/app/src/test/java/com/jarvis/client/ApprovalDecisionTest.kt
```

Real output (2026-10-08):

```
offdevice: checked out:   C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\.dsh-scratch\offdevice
offdevice: Gradle cache:  C:\Users\pcadmin\.gradle\caches\modules-2\files-2.1
offdevice: pinned Kotlin: 2.4.20   JUnit: 4.13.2
offdevice: work dir:      C:\Users\pcadmin\AppData\Local\Temp\offdevice-wnvbq5prw2p
offdevice: compiling:     1 Kotlin file(s)
offdevice:   ApprovalDecisionTest.kt
offdevice:   org.jetbrains.kotlin:kotlin-compiler-embeddable:2.4.20 C:\Users\pcadmin\.gradle\caches\...\kotlin-compiler-embeddable-2.4.20.jar
offdevice:   org.jetbrains.kotlin:kotlin-stdlib:2.4.20            C:\Users\pcadmin\.gradle\caches\...\kotlin-stdlib-2.4.20.jar
offdevice:   junit:junit:4.13.2                                   C:\Users\pcadmin\.gradle\caches\...\junit-4.13.2.jar
offdevice:   org.hamcrest:hamcrest-core:1.3                       C:\Users\pcadmin\.gradle\caches\...\hamcrest-core-1.3.jar
offdevice:   org.jetbrains:annotations:23.0.0                     C:\Users\pcadmin\.gradle\caches\...\annotations-23.0.0.jar
offdevice:   org.jetbrains.kotlinx:kotlinx-coroutines-core-jvm:1.9.0 C:\Users\pcadmin\.gradle\caches\...\kotlinx-coroutines-core-jvm-1.9.0.jar
offdevice: compiled OK:   1 class file(s)
offdevice: running:       com.jarvis.client.ApprovalDecisionTest
offdevice: working dir:   ...\.dsh-scratch\offdevice  (tests that walk up for repo files start here)
JUnit version 4.13.2
....
Time: 0.1

OK (4 tests)
offdevice: RESULT: 4 test(s) ran, 0 failed - the named files compile and the named tests pass
```

### 2. The menu-contract tests - the four the day's incidents were about

`MenuVisibilityTest`, `OpenPlaceTest` and `SettingsJumpTest` are pure JVM, but
the files they read are not: `Screen` lives in a `Nav.kt` that is mostly
`@Composable` navigation, `JarvisJson` lives in `ApiModels.kt` among
`@Serializable` wire shapes, and `ForgetRange.PLACE` / `Topics.PLACE` live in
files that drag in `ChatLog`, `ApiError` and `DesktopWrite`. Those three things
are the stand-ins, and each is **generated from its own real file** by
`-Extract` (a whole declaration) and `-Const` (one constant, inside the object
that declares it):

```powershell
pwsh -File tools/offdevice/Invoke-OffDeviceKotlin.ps1 -Source "jarvis-client/app/src/main/java/com/jarvis/client/net/MenuCatalog.kt,jarvis-client/app/src/main/java/com/jarvis/client/net/MenuState.kt,jarvis-client/app/src/main/java/com/jarvis/client/net/MenuVisibility.kt,jarvis-client/app/src/main/java/com/jarvis/client/ui/MenuPlaces.kt,jarvis-client/app/src/main/java/com/jarvis/client/ui/SettingsJump.kt,jarvis-client/app/src/main/java/com/jarvis/client/ui/OpenPlace.kt" -Extract "jarvis-client/app/src/main/java/com/jarvis/client/net/ApiModels.kt::val JarvisJson = Json {;jarvis-client/app/src/main/java/com/jarvis/client/ui/Nav.kt::enum class Screen {" -Const "jarvis-client/app/src/main/java/com/jarvis/client/net/ForgetRange.kt::PLACE;jarvis-client/app/src/main/java/com/jarvis/client/net/Topics.kt::PLACE" -Jar "org.jetbrains.kotlinx:kotlinx-serialization-json-jvm,org.jetbrains.kotlinx:kotlinx-serialization-core-jvm" -Test "jarvis-client/app/src/test/java/com/jarvis/client/MenuVisibilityTest.kt,jarvis-client/app/src/test/java/com/jarvis/client/OpenPlaceTest.kt,jarvis-client/app/src/test/java/com/jarvis/client/SettingsJumpTest.kt" -Resources "jarvis-client/app/src/test/resources"
```

Real output (2026-10-08):

```
offdevice: compiling:     13 Kotlin file(s)
offdevice:   Extracted1.kt
offdevice:   Extracted2.kt
offdevice:   Extracted3.kt
offdevice:   Extracted4.kt
offdevice:   MenuCatalog.kt
offdevice:   MenuPlaces.kt
offdevice:   MenuState.kt
offdevice:   MenuVisibility.kt
offdevice:   MenuVisibilityTest.kt
offdevice:   OpenPlace.kt
offdevice:   OpenPlaceTest.kt
offdevice:   SettingsJump.kt
offdevice:   SettingsJumpTest.kt
...src\MenuState.kt:72:29: warning: unnecessary non-null assertion (!!) on a non-null receiver of type 'String'.
offdevice: compiled OK:   24 class file(s)
offdevice: running:       com.jarvis.client.MenuVisibilityTest, com.jarvis.client.OpenPlaceTest, com.jarvis.client.SettingsJumpTest
JUnit version 4.13.2
.............................
Time: 0.395

OK (29 tests)
offdevice: RESULT: 29 test(s) ran, 0 failed - the named files compile and the named tests pass
```

### 3. `RetrieveCountTest`, which needs the real `ApiError`

`RetrieveCount.kt` refers to `ApiError`, which is declared in `net/JarvisApi.kt`
- a file full of OkHttp and coroutine plumbing. One more `-Extract` lifts the
sealed interface itself, word for word:

```powershell
pwsh -File tools/offdevice/Invoke-OffDeviceKotlin.ps1 -Source jarvis-client/app/src/main/java/com/jarvis/client/net/RetrieveCount.kt -Extract "jarvis-client/app/src/main/java/com/jarvis/client/net/ApiModels.kt::val JarvisJson = Json {;jarvis-client/app/src/main/java/com/jarvis/client/net/JarvisApi.kt::sealed interface ApiError {" -Jar "org.jetbrains.kotlinx:kotlinx-serialization-json-jvm,org.jetbrains.kotlinx:kotlinx-serialization-core-jvm" -Test jarvis-client/app/src/test/java/com/jarvis/client/RetrieveCountTest.kt
```

```
offdevice: compiling:     4 Kotlin file(s)
offdevice: compiled OK:   16 class file(s)
offdevice: running:       com.jarvis.client.RetrieveCountTest
JUnit version 4.13.2
............
Time: 0.132

OK (12 tests)
offdevice: RESULT: 12 test(s) ran, 0 failed - the named files compile and the named tests pass
```

## The shims, named, and what each stands in for

The three hand-rolled scripts each needed these, and this is the honest list of
what is *not* the real thing in the runs above:

| Stand-in | Lifted out of | What it stands in for, and what is missing |
|---|---|---|
| `JarvisJson` | `net/ApiModels.kt` (`val JarvisJson = Json { ... }`) | The real `Json` instance, with its four options, word for word. The rest of `ApiModels.kt` - every `@Serializable` wire shape - is not there; those need the serialization compiler plugin and a classpath this machine cannot assemble. |
| `Screen` | `ui/Nav.kt` (`enum class Screen { ... }`) | The real enum, all constants, word for word. The rest of `Nav.kt` - the `@Composable` back stack - is not there. |
| `ForgetRange` / `Topics` | `net/ForgetRange.kt`, `net/Topics.kt` (their `const val PLACE`) | Two string constants in the objects that declare them. Every other member of both objects, and the whole of both files, is not there. |
| `ApiError` | `net/JarvisApi.kt` (`sealed interface ApiError { ... }`) | The real error type, word for word. `JarvisApi.kt`'s HTTP layer is not there. |
| `-Shim <file>` | hand-written | For anything the two modes above cannot generate. `decideAndReset`'s "lift one function into a stub holder" trick (from `run-approval-tests.ps1`) is done this way: the stub holder is a hand-written `-Shim` file and the function is pasted into it. Not automated, and it is the one thing the old scripts did that this tool does not do for you. |

Two rules keep a stand-in from lying quietly:

- the generated file carries a header saying which real file it came from, which
  declaration was kept, and that everything else in that file is missing;
- the **value** is read from the real file at run time, so a constant added to
  `Nav.kt` cannot go missing here (the old scripts' hand-typed `JarvisJson` stub
  could, and one of them says so in its own comment).

## Proof that the driver can fail

A checker that cannot fail is a green tick over nothing - this repository has
`tools/check_vacuous_checks.py` because that has happened. So
`tools/offdevice/SelfCheck.ps1` runs the driver five times against throwaway
files and insists on all five answers:

```powershell
pwsh -File tools/offdevice/SelfCheck.ps1
```

Real output (2026-10-08), trimmed to the lines that matter:

```
===== CASE 1  a source file that does not compile  (exit 2)
  offdevice: STOPPED - the Kotlin compiler REJECTED the sources (exit 1). The diagnostics above

===== CASE 2  a JUnit test asserting something false  (exit 2)
  1) twiceIsNotWhatItIs(com.jarvis.client.selfcheck.FalseTest)
  FAILURES!!!
  Tests run: 1,  Failures: 1
  offdevice: STOPPED - 1 test(s) ran and at least one FAILED (JUnit exit 1).

===== CASE 3  a good source and a good test  (exit 0)
  OK (1 test)
  offdevice: RESULT: 1 test(s) ran, 0 failed - the named files compile and the named tests pass

===== CASE 4  nothing named to compile  (exit 2)
  offdevice: STOPPED - nothing was named to compile or run - refusing to report a pass having done

===== CASE 5  a test class that does not exist  (exit 2)
  offdevice: STOPPED - the test class com.jarvis.client.selfcheck.NoSuchTest was not produced by this compile, so NOTHING would have been

SELF-CHECK: OK - the driver fails on a file that does not compile, fails on a test that asserts
something false, fails on a run that named nothing and on a test class that does not exist, and
passes a good source with its test.
```

Case 5 exists for a reason worth writing down: **JUnit answers a class it cannot
find with one synthetic `initializationError` test**, so a count-only check
would read that as "1 test ran" and pass. The driver checks that the compile
actually produced each test class before it runs anything.

### The two intentional failures, run directly, as a future agent would

```
########## A. a source file that does not compile
C:\Users\pcadmin\AppData\Local\Temp\offdevice-xdxcjjtoy2n\src\Broken.kt:4:32: error: none of the following candidates is applicable:
fun times(other: Int): Int:
  Argument type mismatch: actual type is 'String', but 'Int' was expected.
    fun twice(n: Int): Int = n * "two"
                               ^

offdevice: STOPPED - the Kotlin compiler REJECTED the sources (exit 1). The diagnostics above
are the real ones, from the same compiler the app is built with.
exit=2

########## B. a JUnit test that asserts something false
JUnit version 4.13.2
.E
There was 1 failure:
1) twiceIsNotWhatItIs(com.jarvis.client.selfcheck.FalseTest)
java.lang.AssertionError: two times twenty-one is forty-three expected:<43> but was:<42>
	at com.jarvis.client.selfcheck.FalseTest.twiceIsNotWhatItIs(FalseTest.kt:9)

FAILURES!!!
Tests run: 1,  Failures: 1

offdevice: STOPPED - 1 test(s) ran and at least one FAILED (JUnit exit 1). The failure
and its stack trace are above.
exit=2

########## C. a good source and its test
JUnit version 4.13.2
.

OK (1 test)
offdevice: RESULT: 1 test(s) ran, 0 failed - the named files compile and the named tests pass
exit=0
```

### Proving the self-check itself is sensitive

The self-check is only worth having if it goes red when the tool loses its
teeth. It was proved by neutering the driver's two failure guards
(`if ($code -ne 0)` and `if ($runCode -ne 0)` changed to `if ($false)`),
running the self-check, and restoring them. With them neutered, the driver
reported a failing test as a pass - and the self-check said so:

```
SELF-CHECK: NOT OK - the driver does not have the teeth it claims:
  * the driver failed a source file that does not compile for another reason (exit 2, wanted 'Kotlin compiler REJECTED')
  * the driver PASSED a JUnit test that asserts something false
```

Note the second line: JUnit really did print `Tests run: 1, Failures: 1`, and the
neutered driver still printed `0 failed`. That is the exact shape of vacuous
check this whole page is written against. Restored, the self-check is green
again and `ApprovalDecisionTest` is back to `4 test(s) ran, 0 failed`.

## How it finds the compiler, the stdlib and JUnit

Nothing machine-specific is typed into either script. In order:

1. **The cache root** is `%GRADLE_USER_HOME%\caches\modules-2\files-2.1`, or
   `%USERPROFILE%\.gradle\caches\modules-2\files-2.1`. `-GradleCache` overrides
   it. If it is not there, the tool stops and says so - it never reports a pass
   because it compiled nothing.
2. **The versions** are read from the build files the app itself is pinned by:
   Kotlin from `jarvis-client/build.gradle.kts`
   (`org.jetbrains.kotlin.plugin.compose") version "2.4.20"`), JUnit from
   `jarvis-client/app/build.gradle.kts` (`junit:junit:4.13.2`). A dependency
   asked for with `-Jar group:artifact` takes its version from those same
   dependency lines where they name it - including the `-jvm` suffix the cache
   uses and the build file does not - and otherwise the newest in the cache. The
   table it prints says which was used, every time.
3. **The jar** is found under
   `<cache>\<group>\<artifact>\<version>\<hash>\<artifact>-<version>.jar`, so the
   cache's own hash directory is never written down. Gradle keeps the group id
   whole (`org.jetbrains.kotlin`), which is the layout this tool looks for
   first; a Maven-shaped cache is looked for too.
4. If a jar is missing, the message names the coordinate, the path it looked in,
   **and what versions are actually present** - so the next reader knows whether
   the dependency was never fetched here or whether the pin has moved.

Three jars are not the tests' dependencies but the *compiler's own*:
`org.jetbrains:annotations` (code generation fails without it:
`NoClassDefFoundError: org/jetbrains/annotations/Nullable`) and
`kotlinx-coroutines-core-jvm` (the compiler fails before it reads a single file
without it: `NoClassDefFoundError: kotlinx/coroutines/CoroutineScope`), plus the
stdlib. All three are found the same way as everything else.

## The desktop counterpart: checking the Rust without a full release build

The Rust half has the same problem in reverse - a full `npm run tauri build`
takes minutes and links an installer nobody asked for. The four checks CI's
`rust` job runs can be run here in about two minutes warm. **Run them from a
worktree with `CARGO_TARGET_DIR` pointed at the main checkout's target
directory**, which already holds about 2 GB of compiled debug output: a worktree
built into its own `target/` starts cold and recompiles every crate.

```powershell
$env:CARGO_TARGET_DIR = "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\jarvis-desktop\src-tauri\target"; cd jarvis-desktop\src-tauri; cargo fmt --check; cargo check --all-targets; cargo clippy --all-targets -- -D warnings; cargo test --lib
```

Real output (2026-10-08, from a fresh worktree at `origin/main`, rustc 1.98.1 -
the same newest-stable CI uses, nothing changed to take these):

```
##### cargo fmt --check
exit=0

##### cargo check --all-targets
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 1m 20s
exit=0

##### cargo clippy --all-targets -- -D warnings
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 38.91s
exit=0

##### cargo test --lib
test result: FAILED. 717 passed; 2 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.49s
error: test failed, to rerun pass `--lib`
exit=101
```

**Two of the 719 fail on this machine, and neither is caused by the Kotlin
tool.** Both write inside `%TEMP%` from inside the test process, and both pass
when the temp directory is pointed somewhere else:

```
##### cargo test --lib, with $env:TEMP (and $env:TMP) pointed at a folder inside the checkout
test result: ok. 719 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.53s
```

- `commands::wiki_tests::only_a_real_jarvis_wiki_folder_is_opened` panics with
  `temp folder: Os { code: 5, kind: PermissionDenied }` from
  `create_dir_all` in `%TEMP%`, although that same folder is created without
  complaint from PowerShell in the same session. Why the test process is refused
  is not known; it is an environment answer, not a code answer, and it is
  written down rather than guessed at.
- `crash_notes::tests::record_and_read_round_trip_and_keep_only_the_newest`
  fails `assert_eq!(loaded.len(), MAX_NOTES + 3)` (`left: 0, right: 13`). Its
  `scratch_path` builds a filename out of `{:?}` of a `SystemTime`, and that
  debug formatting contains a colon - **not a legal character in a Windows file
  name**. On this machine the file that appears in `%TEMP%` is truncated at that
  colon and is 0 bytes long, so the JSON never round-trips. On CI's Linux
  runner a colon is an ordinary character, which is why CI has never seen it.
  Fixing it is a one-line change to the test helper, and it is **not** fixed
  here: it is a desktop source change, this work is the Kotlin tool, and the
  owner's call on what to do with a test that cannot pass on the machine the app
  ships to.

So: `cargo fmt`, `cargo check` and `cargo clippy` are clean on `origin/main` as
of 2026-10-08, and `cargo test --lib` is 717/719 with the machine's `%TEMP%`,
719/719 with `%TEMP%` pointed inside the checkout. Anyone re-running the recipe
above should expect the same two names.

## What this does not replace, and where it is deliberately not wired in

**CI is still the only judge.** A green run here means the files you named
compile and the tests you named pass; it says nothing about the other ~1900
tests, the Gradle build, R8, the APK, or the phone.

This tool is wired into nothing on purpose:

- it added **no workflow**;
- it is **not** a `backend/test_*.py` suite, because `backend/run_suites.py`
  collects those and CI runs the runner - that would put an off-device Kotlin
  check in CI by accident, which is the owner's decision and not this script's;
- `tools/check_vacuous_checks.py` reads `backend/test_*.py` and
  `backend/eval_*.py` only, so it neither sees nor needs to see
  `tools/offdevice/`.

**Where it would belong, if the owner wants it in a check:** the natural home is
CI's phone job, as a step before `./gradlew testDebugUnitTest` that runs
`tools/offdevice/SelfCheck.ps1` (on a Linux runner that would need the same
jars from a Gradle cache, so it is not free), or a local `preflight` line beside
`tools/check_parity.py`. Neither is done here.

## The risk

- **A stand-in can drift from the real type.** `-Extract` and `-Const` read the
  real file at run time, which removes the hand-typing class of drift, but a
  test that compiles against `ApiError` lifted out of `JarvisApi.kt` is still
  not the app's own compile: anything in that file which the declaration needs
  but which was not lifted shows up as a compile error, and anything the *test*
  needs which the declaration only appears to provide shows up as a passing test
  that the real build would fail.
- **A pass here can be mistaken for a pass from CI.** The driver prints what it
  proves and what it does not on every green run, and this page says it again,
  because that mistake is the whole risk.
- **It reads `%USERPROFILE%\.gradle`.** That cache is a build artefact of the
  Android project, not part of this repository; if it is emptied, the tool
  cannot run on this machine until Gradle fetches the pinned jars again. It
  stops loudly when that happens rather than reporting a pass.
