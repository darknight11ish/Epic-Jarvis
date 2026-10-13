# Full evaluation: the Jarvis phone app on a Pixel 9 running GrapheneOS

**Date:** 2026-10-12
**App evaluated:** `jarvis-client` (the Android app that actually talks to the backend), at
commit `9a31591592b7dac287cc20db817bea3efd1af98`.
**Device evaluated against:** Google Pixel 9 (`tokay`), GrapheneOS **2026100600** (2026-10-06),
which is based on **Android 17**.
**Supersedes / extends:** `docs/GRAPHENEOS.md` (2026-09-27), which asked this question before
the app had grown the features it now has.

---

## 1. The short answer

**Yes — the app will work on a Pixel 9 running GrapheneOS, and no code change, no rebuild and no
second APK is needed.** It is one of the better-suited apps for GrapheneOS there is, because it
was built to avoid Google's services on purpose (that is rule 1 of the project), not by accident.

**But "fully compatible" is not quite the right word.** Three things behave differently, and two
of them are real, visible gaps the owner will meet on day one:

1. **GrapheneOS ships no text-to-speech engine.** The phone's own fallback voice goes silent.
   The normal voice (the PC's Kokoro voice) is unaffected — this only bites if the PC's voice
   module is not installed.
2. **GrapheneOS ships no calendar app.** Half of "Also on my phone" (the reminder → calendar
   half) has nothing to hand the event to, and the app says so in words.
3. **Face unlock does not exist on GrapheneOS**, so risky approvals rest on the fingerprint or
   the PIN. The app is already built for exactly that, so it works — the owner just should not
   expect to use their face.

Everything else is either identical to stock Android, or a normal Android setting the owner
flips once (the most important being **"Allow restricted settings"**, which the app's notification
reading needs and which the current `GRAPHENEOS.md` does not mention).

**One forward-looking item has teeth:** Android 17 blocks local-network access for apps that
raise `targetSdk` to 37. Jarvis targets 36, so it is **safe today**, but the day anyone bumps
that number the app must also declare and request `ACCESS_LOCAL_NETWORK` or the link to the PC
breaks. §6 says exactly what to do, and it is a five-line change nobody has made yet.

### Verdict at a glance

| Area | Verdict | Notes |
|---|---|---|
| Installs and starts | **Yes** | `adb install`, arm64-v8a, minSdk 33 / targetSdk 36 on Android 17 |
| Google Play Services needed | **No** | Zero GMS / Firebase / ML Kit / Play Integrity anywhere |
| Play Integrity / attestation checks | **No** | Deliberately deferred (`PAIRING-DESIGN.md` §9); nothing to fail |
| Pairing, chat, approvals, event stream | **Yes** | Ordinary HTTPS/HTTP sockets + Android Keystore |
| Fingerprint / PIN gate for risky approvals | **Yes** | `BIOMETRIC_STRONG or DEVICE_CREDENTIAL`; StrongBox with TEE fallback |
| "Hey Jarvis" wake word (ONNX Runtime) | **Probably** | The one thing only a real GrapheneOS phone can prove |
| Phone's own fallback voice (TTS) | **No (degrades)** | GrapheneOS has no TTS engine; the app goes silent, by design |
| PC's voice over the network | **Yes** | Plays a WAV through `AudioTrack`; no TTS engine involved |
| Reading phone notifications | **Yes, after one setup tap** | "Allow restricted settings" (Android 13+ rule) |
| Floating avatar (overlay) | **Yes** | Plus a 1-second delay before the allow button works |
| Floating avatar (bubble) | **No — but unrelated to GrapheneOS** | Still missing `MessagingStyle`; broken on any phone |
| Quick Settings tiles | **Yes, after unlocking** | GrapheneOS requires unlock for system tiles by default |
| "Also on my phone" (alarm) | **Yes** | GrapheneOS has a Clock app |
| "Also on my phone" (calendar) | **No (degrades)** | GrapheneOS has no calendar app; the app says so |
| Watch with me (screen share) | **Yes** | MediaProjection + usage access, both standard |
| App lock / screenshot blocking | **Yes** | `FLAG_SECURE` behaves as on stock |
| Auto-reboot (18 h default) | **Works, with a caveat** | The link returns when the owner next unlocks |
| Native library hardening | **Probably** | `hardened_malloc` / secure app spawning are the risk; per-app toggle exists |
| 16 KB page size | **Cleared for the future** | Verified: every `.so` in the shipped ABIs is 16 KB-aligned |

---

## 2. How this was evaluated, and what it is not

**What was done:**

- **The app's source was read**, not summarised from other docs: the whole manifest, the Gradle
  dependency list, and the specific files that decide every GrapheneOS-sensitive behaviour
  (Keystore, biometrics, TTS, notifications, screen capture, network, GPU probe, TTS fallback).
- **The native libraries were measured**, not trusted: every `.so` that ends up in the APK was
  read with a small ELF parser to check 16 KB page alignment (§8).
- **The platform side was researched** against grapheneos.org, the Android developer
  documentation, and real-world reports of apps breaking — every claim in §4–§7 carries its URL.

**What this is not — said plainly, because it is the difference between a paper answer and a
proven one:**

- **It is not a run on a GrapheneOS phone.** Nothing in this workspace has one. The app has
  been proven to install, start and stay up on a real Android 15 phone (a OnePlus, see
  `docs/ANDROID-DEVICE-AUDIT-2026-10-09.md`), and the emulator smoke job in CI proves the
  release APK installs, starts and survives, but **a GrapheneOS Pixel 9 has never run this
  app**.
- **Two claims are therefore "expected", not "proven"**: that the ONNX Runtime wake-word
  library loads under GrapheneOS's memory hardening (§7), and that the mesh link to the PC is
  unaffected by Android 17's network changes while `targetSdk` stays at 36 (§6).

Everything else in the table above is a property of the app's own code, or a documented
platform behaviour, and is as solid as a paper evaluation gets.

---

## 3. Why this app is a good fit for GrapheneOS

The two things that break ordinary apps on GrapheneOS are **needing Google Play Services** and
**needing Firebase push**. This app needs neither, and that was a deliberate rule, not luck.

Checked against the real dependency list and source, not assumed:

| Common GrapheneOS dealbreaker | Found in `jarvis-client`? | Evidence |
|---|---|---|
| `com.google.android.gms` (Play Services) | **No match anywhere** | grep over the whole source tree |
| Firebase / FCM push | **No** | Live events arrive over the app's own always-on `EventService` socket |
| Google ML Kit (barcode/QR) | **No** — deliberately avoided | ZXing core (plain Java) + CameraX instead, chosen *because* of the GrapheneOS plan (`PAIRING-DESIGN.md` §8.3) |
| Play Integrity / SafetyNet | **No** | Key attestation was consciously deferred (`PAIRING-DESIGN.md` §9) — partly *because* a GrapheneOS phone reports "self-signed" boot state |
| Google TTS (network voice) | **No** — the app *refuses* network voices | `Speaker.speakOnDevice` filters out any voice with `isNetworkConnectionRequired` |
| Google's WebView / Chrome | **No** | The app has no WebView at all |
| Play Store distribution | **No** | Sideloaded by `adb` (rule 5), which is the normal GrapheneOS way |
| ONNX Runtime telemetry | **No** | Pinned to 1.22.0 specifically to avoid a phone-home added in 1.30.0 |

The one dependency that is a *positive* on GrapheneOS: approval signing uses the **Android
Keystore**, so the phone's own security chip holds the key. It tries StrongBox (which GrapheneOS
requires of supported devices, and the Pixel 9 is one) and **falls back cleanly to the ordinary
TEE keystore** if `setIsStrongBoxBacked(true)` fails, catching `ProviderException`. That is
exactly the resilience a device-different Android needs.

---

## 4. Setup steps that are different on GrapheneOS

These are not incompatibilities — they are one-time taps that stock Android either does not ask
for or asks for differently. The installer's instructions (`docs/INSTALL.md` §3.3) do not
mention them, which is the gap to close.

### 4.1 "Allow restricted settings" — needed for reading phone notifications

**What it is:** since Android 13, an app that was **not installed by the Play Store's own
installer** (so: every `adb install`, and every F-Droid install) cannot be given
**Notification access** or **Accessibility access** until the owner deliberately allows it.
GrapheneOS behaves exactly the same as AOSP here.

**Why it matters for Jarvis:** the "reading phone notifications" feature (off by default) needs
Notification access. Without this step, the switch simply cannot be turned on, and the app's
own explanation screen will lead to a settings page where the toggle cannot be enabled.

**What to do, in order:**
1. Settings → Apps → Jarvis → the **three-dot menu** (top right) → **Allow restricted settings**.
2. Then Settings → Apps → Special app access → **Notification access** → enable Jarvis.
3. Then turn on the feature inside Jarvis's own settings.

Sources: [GrapheneOS forum, restricted settings](https://discuss.grapheneos.org/api/discussions/825).

### 4.2 The USB-C port starts in "charging only when locked"

GrapheneOS's default USB-C mode blocks new USB connections while the phone is locked, at the
hardware and OS level. **`adb install` therefore does nothing until the phone is unlocked**, and
`adb` can drop out again when the screen locks. If the install "just sits there", this is why.

Source: [GrapheneOS usage — USB-C port control](https://grapheneos.org/usage#usb-c-port-and-pogo-pins-control).

### 4.3 The "allow" button on a permission dialog is inert for one second

GrapheneOS disables the allow action on permission prompts and the adb authorisation prompt for
one second, to defeat tapjacking. This is by design; a fast tap simply does nothing.

Source: [GrapheneOS features](https://grapheneos.org/features).

### 4.4 Two GrapheneOS toggles must be left alone

GrapheneOS adds a per-app **Network** toggle and a per-app **Sensors** toggle. Both default to
allowed, which is what the app needs. If the Network toggle is switched off, the app does not
see a permission error — it sees **"the network is down"**, which the app reports as *"Your PC
isn't answering."* Worth knowing before chasing a phantom backend fault.

Sources: [Network permission toggle](https://grapheneos.org/features#network-permission-toggle),
[Sensors permission toggle](https://grapheneos.org/features#sensors-permission-toggle).

### 4.5 A user-installed app can be disabled outright

GrapheneOS lets the owner fully *disable* a user-installed app, which is stricter than the
normal force-stop. If Jarvis goes completely inert one day, check that it is still enabled.

Source: [GrapheneOS features](https://grapheneos.org/features#user-installed-apps-can-be-disabled).

---

## 5. The three real gaps, in detail

### 5.1 The phone's own fallback voice is silent

**What happens:** `Speaker.speakOnDevice` asks Android for a TTS engine and **refuses to speak
through any voice that needs the network** — a deliberate rule 1 protection, because on a stock
handset the default engine is Google's and can synthesise in the cloud, which would upload
Jarvis's reply. On GrapheneOS there is **no TTS engine in the base OS at all**, so
`TextToSpeech(context)` initialises with an error, the app logs "no local text-to-speech
engine", and the reply **stays on screen** instead of being spoken.

**What the owner will actually see**, verbatim (it is a tested string, `SpeechText.kt`):

> "No offline voice on this phone, so it was not spoken aloud. The reply is on screen."

So this is a **handled, explained degradation — not a crash and not a silent failure**. That is
worth knowing before the first run, because on GrapheneOS this is the message that appears, and
it looks like a fault until you know why.

**How bad is this?** Smaller than it first looks:
- The **normal** voice is the PC's Kokoro voice, delivered as a WAV and played by `AudioTrack`.
  That path does not involve TTS at all and is completely unaffected.
- The fallback only runs when the PC answers `/api/voice/say` with 503 — i.e. the desktop's
  speech module is not installed. So this bites only on a PC with no voice engine.

**What to do:** either install the PC's voice pack (the intended path), or install a TTS engine
on the phone if the fallback is wanted. GrapheneOS's own documentation names **RHVoice** and
**eSpeak NG** as the usual choices, and warns that installing one is not enough — it must be
selected and set up, because GrapheneOS deliberately does not use any TTS engine as an OS
backend.

Sources: [GrapheneOS usage — accessibility](https://grapheneos.org/usage#accessibility);
the app's own behaviour is `audio/Speaker.kt`.

### 5.2 Half of "Also on my phone" has nothing to talk to

**What happens:** "Also on my phone" hands an alarm to the phone's Clock app
(`AlarmClock.ACTION_SET_ALARM`) or a reminder to a calendar app (`ACTION_INSERT` on
`CalendarContract.Events`). GrapheneOS ships **no calendar app** — answered directly on
GrapheneOS's own forum: *"The AOSP calendar is broken so it's not in the apps list, and
maintaining a separate calendar app isn't a priority"* — and its FAQ's bundling policy
("minimal bundled apps… only essential apps") means one is unlikely to appear.

**How bad is this?** The app already handles it correctly and says so in words —
`AlsoOnPhone.NO_CALENDAR` = *"This phone has no calendar app that takes events from other
apps."* So it is a missing feature, not a broken one. The alarm half works: GrapheneOS keeps the
AOSP alarm/clock and calculator apps, precisely because they are AOSP
(*"The only reason those exist is because they are part of AOSP"*, same thread).

**What to do:** install a calendar app if the reminder half is wanted. Note the row's own
warning, which becomes more pointed here: a third-party calendar may sync the event to a cloud
account — which is the owner's own choice to make, and the app's note already says it.

### 5.3 There is no face unlock

**What happens:** GrapheneOS does not support face unlock on the Pixel 9 (the Pixel 5-and-later
face unlock is camera-only, which GrapheneOS rejects as insecure). Fingerprint and PIN/pattern/
password work normally and are the strong factors.

**How bad is this?** **None — the app is already built for it.** `BiometricGate` asks for
`BIOMETRIC_STRONG or DEVICE_CREDENTIAL` by default and explicitly excludes weak biometrics,
with a comment saying "Face unlock on many devices falls into that class and can be satisfied by
a photograph". So GrapheneOS simply removes an option the app never wanted. The "Fingerprint
only" mode also works.

**One thing to expect:** GrapheneOS limits the fingerprint sensor to **5 total attempts** (stock
allows 20 with delays). A Keystore key created with `setUserAuthenticationRequired(true)` and
`setInvalidatedByBiometricEnrollment(true)` — which is what `ApprovalKey` does — is bound to
that policy, so a run of wrong fingers can invalidate the approval key sooner than on stock. The
app already detects this (`KeyPermanentlyInvalidatedException` → `SignedApproval.Local.INVALID`)
and offers to re-create the key, so this is a re-enrol nuisance, not a lockout.

Sources: [GrapheneOS forum — face scan biometric](https://discuss.grapheneos.org/api/discussions/27213),
[GrapheneOS features — more secure fingerprint unlock](https://grapheneos.org/features#more-secure-fingerprint-unlock).

---

## 6. The forward-looking risk: Android 17's local-network block

**This is the single most important item in this report**, because it is the one that will
silently break the app later and looks like a backend fault when it does.

**What changed:** Android 16 introduced "Local Network Protections" in stages; **Android 17 makes
them mandatory for apps that target API 37 or higher**:

> "Starting in Android 17, local network protections are mandatory and enforced for apps
> targeting Android 17 or higher. Local network is blocked by default for all apps that update
> their target SDK."

**Where Jarvis stands today:** `jarvis-client` sets `compileSdk = 36` and **`targetSdk = 36`**.
Enforcement is keyed to `targetSdk 37+`, so **the app is not affected today** — apps targeting 36
keep the existing implicit `INTERNET` access. A real-world report of this biting confirms the
mechanism: Kodi, with `targetSdk=37` and no `ACCESS_LOCAL_NETWORK`, is **blocked from the LAN on
GrapheneOS/Android 17**, and the app-compat override cannot be disabled for a non-debuggable app
on a user build (i.e. there is no workaround).

**Why it would matter to Jarvis when it does apply:** Android's local-network definition
**includes CGNAT `100.64.0.0/10`** — which is exactly the range Tailscale and NordVPN Meshnet
use. Jarvis's whole transport is "dial the PC's `*.ts.net` / `*.nord` name". If the rule applies,
the app would see connection timeouts and report *"Your PC isn't answering"*, with nothing
anywhere saying "permission".

**There is a genuine ambiguity, and it should be resolved by testing rather than assuming:**
Android's own guidance says a local network "excludes cellular and **VPN** connections", and
Jarvis's traffic to the PC goes out over the VPN interface (Tailscale/Meshnet are `VpnService`
apps). If the classification follows the interface, Jarvis is exempt even at `targetSdk 37`. If
it follows the address range, it is not. Both statements are in the official material; the two
reconcile most naturally as "CGNAT addresses are the LAN class *unless* the traffic is over a
VPN", but that reading is an inference.

**What to do, before anyone raises `targetSdk` to 37** (five lines, no design change):

1. Declare `<uses-permission android:name="android.permission.ACCESS_LOCAL_NETWORK" />`.
2. Request it at runtime from the **pairing screen** — the moment the owner types a desktop
   address — not at app start, so the prompt has context.
3. On denial, fall back to the existing plain-language message plus a "Try again" action, rather
   than a silent timeout.
4. Add it to `PlatformReadiness` as its own row, next to "Desktop address", so the Checks screen
   explains it the way it explains cleartext.
5. Test on the real GrapheneOS Pixel 9 with `targetSdk 37`, both mesh paths (Tailscale and
   Meshnet), before shipping that bump.

> **Update, 2026-10-13 — steps 1-4 are now BUILT, and only step 5 is left.** PR
> [#348](https://github.com/darknight11ish/Epic-Jarvis/pull/348) declares the permission
> (`jarvis-client/app/src/main/AndroidManifest.xml:24`), asks for it at the pairing screen
> (`PairingScreen.kt`), handles the refusal with a **Try again**, and adds the
> `PlatformReadiness` row — and on that PR its own CI passed `build`, `smoke` and
> `phone-unit-tests`. `targetSdk` is still 36, so the app is safe today. **This list is left
> exactly as the evaluation wrote it, because a record of what was believed then is evidence;
> `docs/GRAPHENEOS.md` carries the live state of play**, with a `file:line` for each step.

**Do not bump `targetSdk` to 37 for any other reason without doing the above first.** The app
would install, start, pair and then fail to reach the PC — the worst possible failure shape.

Sources: [Android — local network permission](https://developer.android.com/privacy-and-security/local-network-permission),
[Flutter issue 184859](https://github.com/flutter/flutter/issues/184859),
[Kodi issue 28557 (GrapheneOS, Android 17, real failure)](https://github.com/xbmc/xbmc/issues/28557),
[GrapheneOS forum — local network permission and CGNAT](https://discuss.grapheneos.org/d/22215-questions-regarding-android-16-getting-separate-local-network-permission/5).

---

## 7. Watch items: the things GrapheneOS's hardening does to native code

GrapheneOS is not just "Android without Google" — it adds exploit mitigations that, in rare
cases, turn a latent bug in a native library into a crash:

- **`hardened_malloc`** is the default allocator for apps; it aborts on detected memory
  corruption instead of continuing. GrapheneOS documents that this "uncovers latent memory
  corruption bugs in apps" and crashes them.
- **Secure app spawning** replaces Zygote with `exec`, adds ~200 ms to a cold start, and has
  broken real apps (WhatsApp, notably) until GrapheneOS worked around it.

**The one place this app has native code is ONNX Runtime 1.22.0**, which runs the "Hey Jarvis"
spotter and the Smart Turn model. Those libraries are well-tested and use ordinary allocation,
so a failure is unlikely — but it is exactly the class of thing that can only be proven on the
device.

**What to do if "Hey Jarvis" crashes or stops responding:** GrapheneOS exposes per-app switches
at **Settings → Security & privacy → Exploit protection** (secure app spawning, MTE, native code
debugging, dynamic code loading, and a hardened-allocator compatibility mode). Turning off
**Secure app spawning for Jarvis only** is the first thing to try, and is a known-good remedy
for this shape of failure. Record which switch fixed it.

The app also runs a one-time GPU probe that reads `GL_RENDERER` and treats unknown answers as
"normal GPU", so GrapheneOS's driver reporting (the same Mali vendor blobs as stock, since
GrapheneOS is built from the stock firmware's vendor partition) changes nothing here.

Sources: [GrapheneOS exploit mitigations](https://grapheneos.org/features#exploit-mitigations),
[GrapheneOS usage — bugs uncovered by security features](https://grapheneos.org/usage#bugs-uncovered-by-security-features),
[GrapheneOS usage — exec spawning](https://grapheneos.org/usage#exec-spawning).

---

## 8. Checked and cleared (so nobody re-checks them)

These were each a plausible GrapheneOS problem, checked against the code, and are **not**:

| Question | Finding |
|---|---|
| Does anything gate on Play Integrity / SafetyNet? | **No.** No `IntegrityManager`, no attestation code in the app *or* in the Python backend (grepped for `attestation`, `RootOfTrust`, `KeyDescription`). The deferral in `PAIRING-DESIGN.md` §9 held. |
| Does the approval key need Google's attestation roots? | **No.** `ApprovalKey` sends only the public key (SPKI DER) to the PC. No `setAttestationChallenge` anywhere. The GrapheneOS "self-signed boot state" problem the design doc worried about never became real code. |
| Is the APK missing an ABI the Pixel 9 needs? | **No.** `abiFilters = arm64-v8a, x86_64`. The Pixel 9 is 64-bit-only ARM, and GrapheneOS has no 32-bit support to rely on. |
| 16 KB page size — are the `.so` files aligned? | **Yes, verified by measurement.** Every `PT_LOAD` segment in `libonnxruntime.so`, `libonnxruntime4j_jni.so`, `libimage_processing_util_jni.so`, `libsurface_util_jni.so` and `libandroidx.graphics.path.so` for **arm64-v8a** and **x86_64** is aligned to `0x4000` (16 KB). Only the 32-bit copies are 4 KB-aligned, and those ABIs are filtered out of the APK. *(GrapheneOS runs 4 KB pages today, so this is future-proofing rather than a live need — but it is future-proofing that already holds.)* |
| Does StrongBox break the approval key? | **No.** `ApprovalKey.create` tries StrongBox and falls back once on `ProviderException` (which `StrongBoxUnavailableException` is). GrapheneOS lists StrongBox in its device requirements and the Pixel 9 meets them. |
| Does the notification listener or the OTP redaction depend on Google? | **No.** OTP hiding is the app's own regex (`NotificationRedactor`), which is *necessary* here because GrapheneOS has no Android System Intelligence to do it at the platform level. The listener is a plain `NotificationListenerService`. |
| Any WebView, Custom Tabs or Chrome dependency? | **No.** None in the source. |
| Does the assistant/`VoiceInteractionService` path depend on a Google assistant? | **No.** It is the AOSP `RoleManager.ROLE_ASSISTANT` role plus a plain `ACTION_ASSIST` intent-filter, and `PlatformReadiness` already reports "This phone has no assistant setting to give Jarvis" gracefully if the role is unavailable. *(Whether GrapheneOS's own Launcher exposes the role is not documented by GrapheneOS — treat the assist gesture as unverified, not broken.)* |
| Will `FLAG_SECURE` / App lock still block screenshots? | **Yes.** `FLAG_SECURE` behaves as on stock. GrapheneOS's own change here is only about *screenshot metadata* (it strips EXIF), which this app never reads. |
| Does the app open any Settings screen GrapheneOS might lack? | **No.** Every special-access screen it opens (`ACTION_NOTIFICATION_LISTENER_SETTINGS`, `ACTION_MANAGE_OVERLAY_PERMISSION`, `ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS`, `ACTION_USAGE_ACCESS_SETTINGS`, `ACTION_APP_NOTIFICATION_BUBBLE_SETTINGS`) is AOSP, and each call has a `runCatching` fallback to general Settings. |
| Does the always-on link survive? | **By design, yes.** `EventService` is a `specialUse` foreground service (deliberately not `dataSync`, which Android 15 caps at 6 h/day), with `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` and a `BOOT_COMPLETED` receiver. GrapheneOS imposes no extra background restriction; its own FAQ names foreground service + battery exemption as the supported pattern for exactly this. |
| Widgets, tiles, shortcuts, share targets | **Yes.** Glance app widgets, `BIND_QUICK_SETTINGS_TILE` services and app shortcuts are all standard; GrapheneOS ships its own AOSP-based Launcher and SystemUI. |
| Developer verification (Google, 2026→2027) | **Not applicable.** It applies to Google-**certified** devices; GrapheneOS has stated it does not apply to GrapheneOS. `adb install` — the path this project already uses — is unaffected either way. |

---

## 9. Ranked risk

| # | Risk | Likelihood | Impact | Action |
|---|---|---|---|---|
| 1 | `targetSdk` raised to 37 without `ACCESS_LOCAL_NETWORK` | Certain if someone bumps it | App cannot reach the PC; looks like a backend fault | Add the permission + request flow **before** any bump (§6) |
| 2 | "Hey Jarvis" breaks under hardened_malloc / secure app spawning | Low | Wake word stops; rest of app fine | Try the per-app Exploit protection toggle first (§7) |
| 3 | Phone's fallback voice does not speak | Medium (only if the PC has no voice engine) | Reply is on screen instead of spoken | Install the PC voice pack, or a phone TTS engine (§5.1) |
| 4 | Notification reading cannot be enabled | Medium — easy to miss | The feature looks broken | Do the "Allow restricted settings" step (§4.1) |
| 5 | Calendar half of "Also on my phone" unavailable | Certain | One feature degrades with a clear message | Install a calendar app (§5.2) |
| 6 | `adb install` appears to hang | Medium | Confusing first-time setup | Unlock the phone; check USB-C port mode (§4.2) |
| 7 | Approval key invalidated by the 5-attempt fingerprint cap | Low | Re-enrol the key (the app offers to) | Expected behaviour; nothing to fix (§5.3) |
| 8 | Bubble mode never appears | Certain — **but unrelated to GrapheneOS** | A known, already-recorded blocker | Fix `MessagingStyle` first; it fails on every phone |

---

## 10. What to actually do on the Pixel 9 — the first-run list

Written as the order to do them. The five steps in `docs/GRAPHENEOS.md` are still right; they
just omit the USB-C unlock (step 2 here), the "Allow restricted settings" tap (step 4), and the
voice, fingerprint and auto-reboot checks (steps 8–10):

1. **Install GrapheneOS as usual**, then enable Developer options → USB debugging.
2. **Unlock the phone before plugging in** (GrapheneOS's USB-C default blocks data while
   locked), then `adb install -r jarvis-client-<commit>.apk`.
3. **Open Jarvis and pair** exactly as `docs/INSTALL.md` §3 says (`*.ts.net` or `*.nord`
   address, then the token or QR code). If a permission dialog appears, wait one second before
   tapping Allow.
4. **Allow restricted settings** (App info → three-dot menu), then grant Notification access —
   only if the owner wants the reading-notifications feature.
5. **Say "Hey Jarvis" a few times** with the app in the background. This is the one real
   unknown. If it crashes or stops responding, try Settings → Security & privacy → Exploit
   protection → **Secure app spawning off for Jarvis**, and note which switch fixed it.
6. **Enable the floating avatar** and allow "draw over other apps" (a normal AOSP special
   access on GrapheneOS). Then check a notification arrives for an approval card and that
   tapping it opens the app.
7. **Leave the app in the background** for a while, then send a chat message from it — this
   exercises the always-on link.
8. **Check the two voice behaviours**: ask a question while the PC has its voice pack installed
   (should speak), and confirm the phone fallback is silent rather than reaching for a network
   voice (expected on GrapheneOS).
9. **Set the screen lock, then enrol a fingerprint**, and approve one risky card to confirm the
   biometric gate and the signed-approval key both work.
10. **Consider GrapheneOS's auto-reboot** (18 h by default). It reboots while locked, so Jarvis
    comes back when the owner next unlocks — expect the link to be absent until then, not lost.

If all ten hold, the app is working as designed and nothing further needs to change.

---

## 11. What would change this verdict

Re-check these before relying on this document:

1. **`jarvis-client`'s `targetSdk`.** If it becomes 37, §6 stops being a future risk and becomes
   an active incompatibility.
2. **GrapheneOS's page size.** It runs 4 KB pages on the Pixel 9 today; the Pixel 9 firmware
   supports 16 KB and GrapheneOS is actively adding Pixel kernel branches. The app's libraries
   are already 16 KB-aligned, so this is a "no action needed" item — but re-check
   [grapheneos.org/releases](https://grapheneos.org/releases).
3. **Whether GrapheneOS ships a TTS engine.** It says including one is planned "when a suitable
   option is available"; if that lands, §5.1 disappears.
4. **Whether GrapheneOS ships or recommends a calendar app**, which would soften §5.2.
5. **The result of the first real device run.** Steps 5, 8 and 9 of §10 are the ones a phone can
   answer and this document cannot.

---

## Sources

**GrapheneOS (official):** [releases](https://grapheneos.org/releases) ·
[FAQ](https://grapheneos.org/faq) · [features](https://grapheneos.org/features) ·
[usage guide](https://grapheneos.org/usage) · [attestation compatibility guide](https://grapheneos.org/articles/attestation-compatibility-guide) ·
[contact / reporting](https://grapheneos.org/contact)

**GrapheneOS forum / issue tracker:** [restricted settings for sideloaded apps](https://discuss.grapheneos.org/api/discussions/825) ·
[why there is no calendar app](https://discuss.grapheneos.org/d/29361-why-does-gos-not-have-a-calendar) ·
[face unlock on the Pixel 9](https://discuss.grapheneos.org/api/discussions/27213) ·
[local network permission and CGNAT](https://discuss.grapheneos.org/d/22215-questions-regarding-android-16-getting-separate-local-network-permission/5) ·
[16 KB page support](https://discuss.grapheneos.org/d/40757-16kb-page-file-support) ·
[Play Integrity `MEETS_DEVICE_INTEGRITY`](https://discuss.grapheneos.org/d/35360-meets-device-integrity-not-passing-in-second-profile-pixel-10pro) ·
[developer verification does not apply](https://discuss.grapheneos.org/d/26337-android-developer-verification-are-we-screwed-no-doesnt-apply-to-gos) ·
[hardened_malloc / spawning crash report](https://github.com/GrapheneOS/os-issue-tracker/issues/7899)

**Android:** [local network permission](https://developer.android.com/privacy-and-security/local-network-permission) ·
[Android 17 behaviour changes](https://developer.android.com/about/versions/17/behavior-changes-17)

**Real-world reports of the Android 17 network change:** [Kodi blocked on GrapheneOS/Android 17](https://github.com/xbmc/xbmc/issues/28557) ·
[Flutter's tracking issue](https://github.com/flutter/flutter/issues/184859) ·
[AppManager audit](https://github.com/SysAdminDoc/AppManagerNG/blob/main/docs/audits/2026-06-13-android17-access-local-network.md)

**This repository:** `docs/GRAPHENEOS.md` · `docs/PAIRING-DESIGN.md` §8–§11 ·
`docs/INSTALL.md` §3 · `docs/ANDROID-DEVICE-AUDIT-2026-10-09.md` ·
`jarvis-client/app/src/main/AndroidManifest.xml` · `jarvis-client/app/build.gradle.kts` ·
`platform/ApprovalKey.kt` · `ui/approval/BiometricGate.kt` · `audio/Speaker.kt` ·
`platform/PlatformReadiness.kt` · `data/NotificationRedactor.kt` · `net/AlsoOnPhone.kt`
