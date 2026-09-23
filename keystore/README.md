# Debug signing key

**The key is not in this folder, and must never be committed.** This folder
is where CI puts it, for the length of one build.

## How it works

Both Android apps are signed with one shared debug key. It lives in the
repository secret **`DEBUG_KEYSTORE_B64`** (GitHub: Settings → Secrets and
variables → Actions), as base64 text. At the start of every build,
`.github/workflows/jarvis-client.yml` and `android-apk.yml` decode it to
`keystore/debug.keystore`, which is where `app/build.gradle.kts` looks for it.
If the secret is missing, the build **stops on purpose** rather than quietly
signing with a random key (see "Why one fixed key", below).

`.gitignore` refuses `*.keystore` everywhere, with no exceptions.

## Why one fixed key

Without it, the Android build tools make a new `~/.android/debug.keystore` on
first use, and a GitHub runner is a fresh machine every time - so every CI
run signed the APK with a **different** key. Android only lets an app update
another if both are signed with the same key, so `adb install -r` of a new
build over an old one failed with `INSTALL_FAILED_UPDATE_INCOMPATIBLE`, and
the only way through was uninstalling, which wipes the app's data: the
pairing token, the device id and any queued notes or approval decisions.
One fixed key makes updates install in place and keeps all of that.

## The key was replaced on 2026-09-19

The first shared key **was** committed here, deliberately, in a repository
that was public at the time. Anyone who copied it could build an app the
phone would accept as an update to Jarvis, and that app would inherit
Jarvis's stored pairing token. So it was treated as compromised, removed from
the history, and replaced by a new key kept only in the secret.

**What that means on your phone, once:** a copy of the app installed before
the change was signed with the old key, so installing a newer build over it
fails with `INSTALL_FAILED_UPDATE_INCOMPATIBLE`. To get past it:

1. Uninstall the old app: long-press it → **Uninstall**, or from the PC
   `adb uninstall com.jarvis.client`
2. Install the new APK (`adb install jarvis-client-<commit>.apk`, or open it
   on the phone).
3. Pair again: host and port as before, and the token from
   `%USERPROFILE%\.openjarvis\token` on the PC.

Uninstalling deletes the old pairing and anything still waiting in the
phone's offline queue. Every build after that installs over the last one
normally.

## What it is not

Not a release key, and there is no Play listing for one to sign: the app is
sideloaded and never listed. The key uses the standard Android debug
passwords (`android` / `android`, alias `androiddebugkey`), which are public;
what keeps it private is that the file itself is only in the secret.

Rotating it again (for example if the secret leaks) costs the same one
uninstall and re-pair as above: make a new keystore, put its base64 in
`DEBUG_KEYSTORE_B64`, and say so in the next release notes.
