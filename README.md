# Epic-Jarvis
Epic Javis based on openjarvis  and greatly enhanced . 

## Building the Android APK

APKs are built in CI, since the Android SDK is not vendored in this repo.

Two apps live here, and each has its own workflow and its own Gradle root:

| App | Workflow | Artifact |
| --- | --- | --- |
| `jarvis-android/` — the full companion (approvals, duplex audio, widgets, assistant role) | **Build Android APK** | `jarvis-android-debug-apk` |
| `jarvis-client/` — the rewrite against `ANDROID-BUILD.md`, currently step 0 | **Jarvis client** | `jarvis-client-debug-apk` |

Go to **Actions**, pick the workflow, and run it — or just push; each is scoped
to its own directory. Download the APK from the run's **Artifacts** section and
install it with `adb install -r <file>.apk`.

Unit tests gate both builds, and the workflows assert that the test task
actually matched sources: Gradle reports `NO-SOURCE` and exits 0 for a module
with no tests, so a green check is otherwise compatible with nothing having run.

**Debug builds only, and deliberately.** The app is sideloaded over adb and is
never listed on Play, so there is no channel a release build would serve. CI
used to decode a keystore and export four `SIGNING_*` variables into a build
that contained no `signingConfig` to read them — the result was an unsigned APK
that cannot be installed, uploaded under a name that called it signed. That
plumbing is gone rather than completed.
