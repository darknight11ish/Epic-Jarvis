# Signing a phone app build on this PC

**Read this before you install a build you made yourself.** A locally built APK
is **not upgrade-compatible** with the app on your phone until the project's
signing key is in place on this PC.

This page: what goes wrong, where the key must go, and the check to run before
you install. The key itself is never in this repository - see
[`keystore/README.md`](../keystore/README.md) for what the key is and what a
key rotation costs.

## The problem, in plain words

Android will only let an app update another app if **both were signed with the
same key**. Signing is how Android knows an update really comes from the same
source.

The key this project uses is not in the repository, on purpose: it was once
committed to a public repository, so it is treated as compromised and was
replaced with a new one kept only in a GitHub secret. That is fine on GitHub,
where the build machine gets the key from the secret. **On your own PC nobody
has put it back.**

So when you build here, the Android build tools notice there is no key and
quietly make a new one, once per machine, at
`C:\Users\<you>\.android\debug.keystore`. Your build is then signed with *that*
key - a different key from the one on your phone.

What you see when you install it:

```
adb: failed to install app-debug.apk: Failure
[INSTALL_FAILED_UPDATE_INCOMPATIBLE: Package com.jarvis.client signatures do
not match previously installed version; ignoring!]
```

**Why this matters more than an inconvenient error.** The only way past it is
to uninstall the app first, and uninstalling deletes the app's data:

- the **pairing token** - you have to pair the phone again;
- the **device id**;
- anything still waiting in the **offline queue** (notes you wrote while the PC
  was asleep, and approval decisions).

None of that is recoverable. So the check below exists to stop you reaching for
an uninstall "just this once".

## Why CI stops instead of carrying on

`.github/workflows/jarvis-client.yml` deliberately **fails the build** if the
`DEBUG_KEYSTORE_B64` secret is missing, rather than building anyway. The comment
in that step says exactly why: `build.gradle.kts` guards the keystore on
`exists()`, so a build with no key would *not* fail - it would silently sign
with a throwaway key, and the APK would be unusable as an update. CI would
rather stop than publish that.

`jarvis-client/app/build.gradle.kts` has a second guard,
`verifyReleaseSigningKey`: a **release** build in CI without the key stops too.
A **debug** build does not - which is why the local foot-gun described here is
still open.

## Where the key must go

**This is the part that is easy to get wrong.**

```
<repository root>\keystore\debug.keystore
```

Say the repository is at `C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main`.
Then the file goes at:

```
C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\keystore\debug.keystore
```

**Not** `jarvis-client\keystore\debug.keystore`. There is no `keystore` folder
inside `jarvis-client` and one put there would be ignored: the build reads
`rootProject.file("../keystore/debug.keystore")`, and `rootProject` for this
module *is* `jarvis-client/`, so `../keystore` is the **repository's** root
folder. (`jarvis-client/app/build.gradle.kts` line 130 for the debug build,
line 249 for the release guard.)

A key in the wrong place fails the same way as no key at all: the build falls
back to the throwaway key, and nothing warns you. The `-VerifyApk` check below
is what catches that.

### Is that path gitignored? Yes - verified

`.gitignore` line 18, in the block headed *"Signing keys. NOTHING is excepted
here any more."*:

```
*.keystore
```

The pattern has no slash in it, so git matches it **at any depth**, including
`keystore/debug.keystore`. Run from the repository root, this prints the rule
that matches and exits 0:

```powershell
git check-ignore -v keystore/debug.keystore
# .gitignore:18:*.keystore	keystore/debug.keystore
```

`git ls-files keystore` lists only `keystore/README.md`, so no key is tracked
today either.

**So the claim holds: the key is ignored, and cannot be committed by accident.**
Two things to know anyway:

- The ignore rule is the *only* thing protecting it. It covers `*.keystore`,
  `*.jks`, `*.p12`, `*.pfx`, `*.pem` and `*.key`. If the file were renamed to
  something without one of those endings, `git add -A` would happily stage it.
- **Never commit a signing key.** The block above says why in its own words: a
  key that was committed here, while the repository was public, had to be
  thrown away and replaced, and the replacement cost a real uninstall and
  re-pair on the phone.

## Do this once on this PC

### 1. Get the secret

On GitHub: **Settings → Secrets and variables → Actions → `DEBUG_KEYSTORE_B64`**.
GitHub never shows a secret again, so if you cannot read it there, it has to be
regenerated - see the end of `keystore/README.md`.

Copy it to one of these places. **Neither is inside this repository.**

- an environment variable, for this one PowerShell window:

  ```powershell
  $env:DEBUG_KEYSTORE_B64 = '<paste the secret here>'
  ```

- or a file outside the repository, e.g.
  `C:\Users\<you>\Downloads\debug-keystore.b64`

Whichever you use, it is the *same base64 text* CI decodes with
`printf '%s' "$KEY" | base64 -d > keystore/debug.keystore` - the script below
does the same thing in PowerShell, so local and CI agree.

### 2. Put the key in place

From the repository root:

```powershell
# from an environment variable
powershell -ExecutionPolicy Bypass -File .\scripts\import-debug-keystore.ps1

# or from a file
powershell -ExecutionPolicy Bypass -File .\scripts\import-debug-keystore.ps1 `
  -Base64File "$env:USERPROFILE\Downloads\debug-keystore.b64"
```

It prints the certificate's SHA-256 fingerprint, and says plainly whether git
ignores the path it wrote to. **The script writes nothing at all** unless the
decoded bytes are a Java keystore it can actually open - see
[The helper script](#the-helper-script-interface-and-failure-paths) below.

### 3. Build

```powershell
cd jarvis-client
.\gradlew.bat assembleDebug
```

### 4. Check the APK before you install it

```powershell
powershell -ExecutionPolicy Bypass -File ..\scripts\import-debug-keystore.ps1 `
  -VerifyApk app\build\outputs\apk\debug\app-debug.apk
```

Only install if it says **MATCH**. If it says **MISMATCH**, the key was not in
place in time or is not the right key - **do not install, and do not uninstall
to get past it.** Fix the key and build again.

## The helper script: interface and failure paths

**`scripts/import-debug-keystore.ps1`** - one script, two modes. It never
contains the secret, reads it only from outside the repository, and only
`-Force` replaces a keystore that is already there.

| Parameter | What it does |
|---|---|
| *(none)* | Reads base64 from `$env:DEBUG_KEYSTORE_B64` and writes `keystore\debug.keystore`. |
| `-Base64File <path>` | Reads the base64 from that file instead (whitespace and newlines trimmed, so a copy-paste with line breaks works). |
| `-Target <path>` | Write somewhere else. Defaults to the repository's `keystore\debug.keystore`. |
| `-Force` | Replace a keystore that is already there. Without it, an existing file is left alone and the script says so. |
| `-VerifyApk <apk>` | **Reads only.** Compares the APK's signer against the keystore. Changes nothing. |

**It fails loudly, writes no keystore, and exits 1** for each of these - all
of them exercised:

| Input | What it says |
|---|---|
| `DEBUG_KEYSTORE_B64` unset and no `-Base64File` | *"No base64 text in ..."* plus both ways to supply it. |
| Text that is not base64 | *"That is not valid base64 ... Nothing was written."* |
| Valid base64 of something that is not a keystore | *"not a Java keystore: the file starts with 68656C6C, where a keystore starts with FEEDFEED ... or 3082"*. |
| A damaged keystore (right header, unreadable) | *"cannot be opened as one with the project's password and alias ... Nothing was written to ..."*. |
| `-Base64File` pointing at nothing | *"There is no file at ..."*. |
| `-VerifyApk` pointing at nothing | *"There is no APK at ... Build one first: cd jarvis-client; .\gradlew.bat assembleDebug"*. |
| `-VerifyApk` with no keystore to compare against | *"There is no keystore at ..., so there is nothing to compare against."* |
| A file that is not an APK | *"... is not a signed APK that apksigner accepts, so it could not be installed at all."* |
| No `keytool` anywhere | *"Could not find keytool ... It ships with the JDK; set JAVA_HOME, or add the JDK's bin folder to PATH."* |

The write is all-or-nothing. The bytes are decoded in memory, written to a
temporary file in the target folder, **read back with `keytool`**, and only
then renamed into place. Anything wrong before that point removes the
temporary file and leaves whatever was already there untouched.

**Both keystore formats are accepted, and that was a real trap.** Java has two
keystore formats and both are normal: JKS (starts `FEEDFEED`) and PKCS#12
(starts `3082`). `keytool` has written **PKCS#12 by default since JDK 9**, and
the Android tools' `~/.android/debug.keystore` is PKCS#12 too - measured on this
machine, where that file starts `3082`. So a script that demanded the JKS header
would have rejected a perfectly good project key. `keytool` is the thing that
decides whether the file is usable; the header check only catches a wrong paste.

## The fingerprint comparison

A fingerprint is a short, public summary of a certificate. It is printed from
any APK by anyone who has the APK, so comparing and quoting it leaks nothing.

**What to compare: the SHA-256 fingerprint, and only that one.**

- **The key in the keystore.** `-VerifyApk` prints it and computes it the same
  way CI does (`keytool -list -v`), as 64 lowercase hex characters with no
  separators.
- **The APK you actually built.** `apksigner verify --print-certs` prints it
  from the APK itself.

`-VerifyApk` does the comparison for you:

```
Key the keystore holds: 0000000000000000000000000000000000000000000000000000000000000000
APK is signed by:      0000000000000000000000000000000000000000000000000000000000000000
```

Those two lines are a **made-up placeholder**, not a fingerprint from this
project or from any machine - so that nobody ever compares against the example
by mistake. Yours will be 64 real hex characters, and the two lines must be
**identical to each other**.

**To do it by hand instead** (the SDK path on this PC is
`%LOCALAPPDATA%\Android\Sdk\build-tools\36.0.0\`):

```powershell
# the certificate inside the APK
& "$env:LOCALAPPDATA\Android\Sdk\build-tools\36.0.0\apksigner.bat" `
    verify --print-certs .\jarvis-client\app\build\outputs\apk\debug\app-debug.apk

# the certificate in the keystore
& "$env:JAVA_HOME\bin\keytool.exe" -list -v `
    -keystore .\keystore\debug.keystore -storepass android -alias androiddebugkey
```

`keytool` prints `SHA256: AB:CD:EF:...` with colons; `apksigner` prints
lowercase hex with none. **Strip the colons and compare the 64 characters.**

`keytool` ships with the JDK. If `$env:JAVA_HOME` is empty (measured: it is on
this PC), either use the `-VerifyApk` mode above, which finds the JDK for you,
or point at it directly, e.g.
`& "C:\Program Files\Microsoft\jdk-17.0.20.101-hotspot\bin\keytool.exe" -list -v ...`.

### What each answer means

- **The same 64 characters** → this APK will install over the copy already on
  the phone, and the phone keeps its pairing token, device id and offline queue.
- **Different** → this APK was signed with a different key. Android will refuse
  it with `INSTALL_FAILED_UPDATE_INCOMPATIBLE`, and an uninstall is the only way
  past, which wipes the app's data. **Do not install it. Do not uninstall to
  make room for it.** Put the right key in place and build again.
- **More than one different signer in the APK** → not a build of this project.
  Treat it as broken, not as a phone problem.
- **A fingerprint from CI** is the project key. If yours differs from CI's, you
  do not have the project key, whatever the file is called. If it differs from
  **the phone's** copy, you need the older key, or one uninstall and re-pair -
  `keystore/README.md` has those three steps.

`keystore/README.md` records the last time this went wrong: from 19 September
2026 a second CI job rebuilt the release on a machine with no key, so every
release in that window shipped with a different throwaway certificate. That is
why CI now compares the certificate itself before publishing, and why the same
comparison is worth one line here.

## If the app already on the phone was signed with the old key

Nothing on this page fixes that - the old key was destroyed on purpose. You need
the one uninstall and re-pair. The three steps are at the end of
[`keystore/README.md`](../keystore/README.md), and
[`INSTALL.md`](INSTALL.md) mentions it where `adb install -r` is described.

## What is deliberately not in this repository

No keystore, no password and no base64 blob - not in this document, not in the
script, not in a comment, not in a test. The placeholders above are the
interface. The keystore's password and alias are the standard Android debug
ones (`android` / `androiddebugkey`) and are public; what keeps the key private
is that the file itself exists only in the secret and on machines that put it
there.
