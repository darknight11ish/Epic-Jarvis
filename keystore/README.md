# Debug signing key

`debug.keystore` is the key both apps are signed with for sideloading. It is
committed deliberately, and it is not a secret: it uses the standard Android
debug credentials (`android` / `android`, alias `androiddebugkey`), which are
published in Google's own documentation.

## Why it is here

Without it, AGP generates `~/.android/debug.keystore` on first use, and a
GitHub runner is a fresh machine every time — so every CI run signed the APK
with a **different** key. `adb install -r` of a new build over an old one then
fails with `INSTALL_FAILED_UPDATE_INCOMPATIBLE`, and the only way through is
`adb uninstall`, which wipes app data.

App data here is the pairing secret, the auth token, the device id and any
queued notes or approval decisions. So every upgrade cost a re-pair, and any
decision still sitting in the offline queue was lost. A fixed key makes
upgrades install in place and keeps all of it.

## What it is not

It is not a release key and there is no release build — the app is sideloaded
over adb and never listed, so there is nothing for a release key to sign. Do
not reuse this key if that ever changes: anyone who can read this repository
can sign an APK with it.

Fingerprint (SHA-256):

    A5:8C:14:56:F9:4C:C3:E2:84:06:CC:D6:FD:0A:67:5F:32:F8:CE:5C:70:28:E0:7B:0B:F9:97:05:8F:48:29:00

Valid until 2056-09-06.
