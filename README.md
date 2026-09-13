# Epic-Jarvis
Epic Javis based on openjarvis  and greatly enhanced . 

## Building the Android APK

APKs are built in CI, since the Android SDK is not vendored in this repo.

1. Import the app source (a Gradle Android project at the repo root or under
   `android/`, or a Flutter / React Native / Capacitor project — the workflow
   detects which and builds accordingly).
2. Go to **Actions → Build Android APK → Run workflow**, pick `debug` or
   `release`, and run it. Pushes to any branch also build automatically.
3. Download the APK from the run's **Artifacts** section.

Release signing is optional. Set the repository secrets
`ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`
and `ANDROID_KEY_PASSWORD` to get a signed release APK; without them a release
build still runs and produces an unsigned one.
