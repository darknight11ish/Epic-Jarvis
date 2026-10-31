# android-builder - build an app and sideload it onto your phone

This folder is the whole wiring for the app builder's last two steps
(`jarvis_android_builder.py`, 2026-10-30, `docs/JARVIS-API.md` section 166).
There is no patch: the loader finds this folder, imports the module it names
and calls that module's own `install()`, exactly as the patch would have.

## What it does

1. **The template.** `POST /api/projects/<id>/app/tasks/<task>/android/template`
   writes a FIXED, minimal Android project into that task's copy: the Gradle
   files, the manifest, one WebView activity and the owner's own
   `assets/index.html`, `app.js` and `app.css`. Jarvis writes no Gradle file,
   no Kotlin file and no manifest of its own: the model supplies three web
   files and a name, and nothing else. No card - the files land in a task's
   copy and nothing runs them.
2. **The build.** `POST .../android/build` raises ONE risky card
   (`app_build_android`) naming the exact command
   (`<task copy>/gradlew.bat assembleDebug`), the exact folder, the toolchain
   it found, and that a first build downloads Gradle and the Android Gradle
   plugin. A yes runs exactly that, with the allowlisted environment, a time
   limit and the log kept at `build/jarvis-build.log` inside the task's copy.
3. **The install.** `POST .../android/install` raises ONE risky card
   (`app_install_android`) naming the exact `adb install -r <apk>`. There is
   no other adb subcommand in the module: no shell, no uninstall, no serial.

`GET .../android` answers with what the project is, what the toolchain has,
and the two commands a card would run.

## What it never does

No release signing, no Play Store (rule 5), no `adb shell`, no arbitrary
command, no npm, no Capacitor, and no network call of its own. The app it
makes declares **no permission at all** - not even INTERNET - so what the
owner sideloads cannot reach the internet or Jarvis's own routes.

## Taking it out

Remove this folder and restart. The routes go with it; the projects already
built stay where they are, and nothing else changes.
