# Epic-Jarvis
Epic Javis based on openjarvis  and greatly enhanced . 

## Building the Android APK

APKs are built in CI, since the Android SDK is not vendored in this repo.

Two apps live here, and each has its own workflow and its own Gradle root:

| App | Workflow | Artifact |
| --- | --- | --- |
| `jarvis-android/` — the full companion (approvals, duplex audio, widgets, assistant role) | **Build Android APK** | `jarvis-android-debug-apk` |
| `jarvis-client/` — the rewrite against `ANDROID-BUILD.md`, currently step 0 | **Jarvis client** | `jarvis-client-debug-apk` |

### Getting the APK onto a phone

**Easiest — the Releases page.** Every `jarvis-android` build publishes to a
rolling prerelease tagged `android-latest`:

> https://github.com/darknight111/Epic-Jarvis/releases/tag/android-latest

That is a plain `.apk` at a stable URL. Open it on the phone, tap the file, and
allow your browser to install unknown apps — or download it on a computer and
`adb install -r jarvis-android-<sha>.apk`.

**The other way — run artifacts.** Actions → the workflow → a run → the
**Artifacts** box at the bottom. This gives a `.zip` that has to be unpacked
first, and note that **the GitHub mobile app cannot download run artifacts at
all** — that path needs a browser.

Builds are signed with the committed debug key (`keystore/`), so a new build
installs over an old one in place and the pairing secret survives.

Unit tests gate both builds, and the workflows assert that the test task
actually matched sources: Gradle reports `NO-SOURCE` and exits 0 for a module
with no tests, so a green check is otherwise compatible with nothing having run.

**Debug builds only, and deliberately.** The app is sideloaded over adb and is
never listed on Play, so there is no channel a release build would serve. CI
used to decode a keystore and export four `SIGNING_*` variables into a build
that contained no `signingConfig` to read them — the result was an unsigned APK
that cannot be installed, uploaded under a name that called it signed. That
plumbing is gone rather than completed.
