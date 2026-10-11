# The one desktop install you do by hand (2026-10-11)

**Short version:** download one file from the release page below and run it once.
After that, Jarvis updates itself from inside the app, and you never do this again.

Your PC runs **0.2.129**. The release page now has a signed **0.2.134**.

## 1. What to do (about two minutes)

1. Open this page:
   <https://github.com/darknight11ish/Epic-Jarvis/releases/tag/desktop-latest>
2. Under **Assets**, click:
   `jarvis-desktop_0.2.134_x64-setup.exe` (about 4.5 MB)
   - Direct link:
     <https://github.com/darknight11ish/Epic-Jarvis/releases/download/desktop-latest/jarvis-desktop_0.2.134_x64-setup.exe>
3. **Quit Jarvis first** - right-click the Jarvis icon in the tray (next to the
   clock) and choose Quit, so the installer can replace the old copy.
4. **Double-click the downloaded file.** Two things to expect:
   - Windows may say **"Windows protected your PC"**. Choose **More info**,
     then **Run anyway**. This warning is about Windows' own paid publisher
     certificate, which this installer does not have; it is a *different*
     thing from the update signature described below.
   - There is **no administrator prompt**: this installs for your user only,
     into `C:\Users\pcadmin\AppData\Local\Jarvis Desktop`.
5. Start Jarvis again from the Start menu. Your settings, chats and saved
   memory stay as they are - the new version is written over the old one.

## 2. From then on, the button does it

In the Jarvis bar: **Settings → Updates → Check now**, then **Install**.

Every future version appears there. Jarvis never installs an update on its
own; it only offers it until you press Install.

## 3. Why this first one is by hand

Your installed 0.2.129 was built **before** the update signing key existed.

Checked directly on your PC: the installed `jarvis-desktop.exe` contains the
update address but **no public key at all**. Without a public key the app
cannot check a downloaded installer, so Settings → Updates could only ever say
it was "not set up". The 0.2.134 build has the public key inside it, which is
why this one install is needed and no later one is.

(The page is a "rolling" release: its tag never changes, but the version in
the file names goes up. If the page shows something newer than 0.2.134 by the
time you read this, download that file instead - the steps above are the same.)

## 4. What was verified from the files (2026-10-11), not from a green tick

- The `desktop-latest` release exists, is **not a draft**, and is titled
  "Jarvis Desktop - latest (0.2.134)", published 2026-10-11 07:41 UTC.
- `latest.json` is well-formed JSON and lists three entries
  (`windows-x86_64`, `windows-x86_64-nsis`, `windows-x86_64-msi`), each with a
  `version`, a `url` and a `signature`.
- Its version, **0.2.134**, is strictly greater than the installed **0.2.129**
  (read from the installed `jarvis-desktop.exe` itself and from the Windows
  uninstall entry, both 0.2.129).
- The `signature` in `latest.json` is **byte-identical** to the
  `...-setup.exe.sig` file published beside the installer (452 bytes each;
  same for the MSI).
- The signature **cryptographically verifies** against the public key inside
  `jarvis-desktop/src-tauri/tauri.conf.json` - an Ed25519 check over the real
  downloaded installer bytes, key id `CEB4FAE76D70E330`. Only the public key
  was needed; no private key was touched.
- The installer link in `latest.json` answers **HTTP 200**.
- **One honest gap:** `latest.json` has no `pubkey` field at all, so it cannot
  be compared against `tauri.conf.json`. That is deliberate, not a fault:
  `jarvis-desktop/scripts/updater-manifest.mjs` writes only `signature` and
  `url`, and the app checks downloads with the key compiled into it. The
  cryptographic check above is what actually proves the two keys match.

**Not verified, and why:** the 0.2.134 installer's insides could not be read on
this PC - it is a compressed NSIS archive and no unpacking tool (7-Zip or
similar) is installed - so the public key could not be seen *inside* the new
installer, only in the source config the builder used and in the signature
check above.
