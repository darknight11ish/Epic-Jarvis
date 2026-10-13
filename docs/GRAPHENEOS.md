# Running the phone app on GrapheneOS

The owner is moving their Pixel 9 to GrapheneOS. GrapheneOS is a more
locked-down version of Android, built by a different team than Google's, with
extra privacy and security protections switched on by default. This page is
what to check first, written down on 2026-09-27 so it was not forgotten when
the switch happened.

> **The full evaluation has now been done** (2026-10-12), against the app as it
> stands today and against GrapheneOS's current Android 17 release for the
> Pixel 9. **The answer is yes: the app works on a GrapheneOS Pixel 9 and needs
> no code change to do so** — it uses no Google services at all, on purpose.
>
> That evaluation is
> [`GRAPHENEOS-PIXEL9-EVAL-2026-10-12.md`](GRAPHENEOS-PIXEL9-EVAL-2026-10-12.md).
> Read it for the evidence; read this page for the two things that matter most:
>
> - the **hard prerequisite** below, which must be met before anyone raises
>   `targetSdk` to 37 (the app is safe at 36 today);
> - the **three accepted differences**, below that, so none of them is
>   diagnosed as a bug on the first run.
>
> The original five first-run checks further down are still correct; they are
> just not the whole list any more.

## HARD PREREQUISITE for any targetSdk 37 bump

**Do not raise `jarvis-client`'s `targetSdk` above 36 until the
`ACCESS_LOCAL_NETWORK` flow below exists and has been tested on a real
GrapheneOS phone.** This is the one item in this whole page that can break the
app silently, and it is written here as a standing rule rather than as advice,
because the failure it causes looks like something else entirely.

**What changed in Android.** From Android 17, "local network protections" are
mandatory for apps that target API 37 or higher: local-network access is
blocked by default. Jarvis talks to the PC over Tailscale or NordVPN Meshnet,
and Android's definition of a local network **includes the CGNAT range
`100.64.0.0/10`** — which is exactly what those two mesh networks use.

**Where the app stands today.** `targetSdk = 36` (checked in
`jarvis-client/app/build.gradle.kts`), and enforcement is keyed to `targetSdk
37+`. **So the app is safe today and nothing needs doing now.** This section
exists so that the day someone bumps that number, they already know.

**What the failure would look like** (and why it must not be allowed to
happen): a fixed `targetSdk 37` build would install, start and pair normally,
and then **never reach the PC** — reporting *"Your PC isn't answering"*
forever, with nothing anywhere mentioning a permission. There is no
workaround: the app-compat override cannot be disabled for a non-debuggable
app on a user build. A real report of exactly this is Kodi on GrapheneOS with
Android 17.

**What the fix is, when it is built** (five changes, no design work — full
detail in §6 of
[`GRAPHENEOS-PIXEL9-EVAL-2026-10-12.md`](GRAPHENEOS-PIXEL9-EVAL-2026-10-12.md)):

1. Declare `<uses-permission android:name="android.permission.ACCESS_LOCAL_NETWORK" />`
   in `jarvis-client/app/src/main/AndroidManifest.xml`.
2. Request it at runtime from the **pairing screen** — when the owner types a
   desktop address — not at app start, so the prompt has context.
3. On denial, show the existing plain-language message plus a **Try again**,
   rather than letting it become a silent timeout.
4. Add a row to `PlatformReadiness.kt` beside "Desktop address", so the Checks
   screen explains it the way it explains cleartext.
5. Test both mesh paths (Tailscale and Meshnet) on the real GrapheneOS phone
   with `targetSdk 37`, before that bump ships.

**A genuine ambiguity, to be settled by that test rather than assumed:**
Android's guidance also says a local network "excludes cellular and **VPN**
connections", and this app's traffic to the PC goes out over the VPN interface.
If the rule follows the interface, Jarvis is exempt even at 37; if it follows
the address range, it is not. Both statements are in the official material, so
step 5 is what decides it.

## Three things that work differently on GrapheneOS, accepted

None of these is a defect in the app, and none needs a code change. They are
written down so they are not diagnosed as bugs later — each one already has a
plain-language message or a safe fallback built in.

| What | What happens | Why it is accepted |
|---|---|---|
| **No text-to-speech engine.** GrapheneOS ships without one. | If the PC has no voice pack, the phone cannot speak the reply. It says so: *"No offline voice on this phone, so it was not spoken aloud. The reply is on screen."* | The app deliberately refuses network voices (rule 1), so silence plus the reply on screen is the **correct** outcome, not a fault. The normal voice is the PC's own and is unaffected. **Do not change the voice behaviour to make it speak here.** |
| **No calendar app.** GrapheneOS bundles none. | The reminder half of "Also on my phone" has nothing to hand an event to. The app says so: *"This phone has no calendar app that takes events from other apps."* The alarm half still works. | A missing feature, correctly reported. Install a calendar app if the reminder half is wanted — noting that a third-party one may sync to a cloud account, which is the owner's own choice. |
| **No face unlock.** | Risky approvals rest on the fingerprint or the PIN instead. | **Harmless.** The app already asks for `BIOMETRIC_STRONG or DEVICE_CREDENTIAL` and explicitly refuses weak biometrics, so GrapheneOS removes an option the app never wanted. |

## The short answer

**No separate build is needed.** `jarvis-client` should install and run on
GrapheneOS the same way it does on a normal Pixel, using the same `adb
install` steps already in `docs/INSTALL.md`.

## Why this is likely fine, checked against the real code (2026-09-27)

The two things that usually break an app on GrapheneOS are needing **Google
Play Services** (a set of Google-only background services GrapheneOS does
not include by default) and needing **Firebase push notifications** (Google's
service for sending an app a message while it is closed). Checked both:

- `jarvis-client/app/build.gradle.kts` has no Firebase or Google Play
  Services dependency of any kind - confirmed by reading the whole
  dependency list, not by assuming.
- Approval cards and other live events reach the phone through the app's
  **own** always-on background service (`EventService.kt`), not through
  Google's push service. This was already true before GrapheneOS came up -
  rule 1 in `CLAUDE.md` (nothing private goes through an outside company's
  servers) ruled out Google's push service from the start.
- The app is already installed by `adb`, never through the Play Store (rule
  5) - the exact same way apps get installed on GrapheneOS.
- Every permission it asks for (microphone, notifications, "draw over other
  apps" for the new floating avatar, its own background service) is a
  standard Android permission GrapheneOS supports. GrapheneOS shows a couple
  of its own extra toggles for some of these (for example, a per-app network
  on/off switch) - they just need to be left on, the same one-time thing as
  granting the permission itself.

## The one real uncertainty

The "Hey Jarvis" listener runs a small AI model right on the phone using
Microsoft's ONNX Runtime, which is a native-code library (not plain Kotlin).
GrapheneOS's extra memory-safety hardening has, in rare cases, caused
problems for native libraries in other apps. Nothing in how this app uses
ONNX Runtime looks fragile - but this can only really be proven by running it
on an actual GrapheneOS phone, which nothing in this project's build setup
can do.

## Android developer verification (2027)

From 2027 Google will make phones with its certification (most phones sold
with Google Play) ask for a one-time "advanced" flow with a 24-hour wait
before installing an app from an unverified developer **by tapping the
file**. Installing with `adb` from the PC stays allowed. That comes from a
search summary of Google's announcement, not from a phone.

GrapheneOS is not a Google-certified system, so it is **likely** unaffected -
this is an inference, not checked on a GrapheneOS phone. `adb install`, which
step 1 below already uses, is the way that stays allowed either way.
`docs/INSTALL.md` §3.3 has the same note for other phones.

## What to check, the first time it runs on GrapheneOS

In order, right after installing:

1. **Install it exactly like `docs/INSTALL.md` already says** (`adb install`
   the APK from the latest `client-latest` release). No different steps for
   GrapheneOS.
2. **Say "Hey Jarvis" a few times** with the app in the background. This is
   the one part with a real, if small, chance of trouble (see above). If it
   crashes or the wake-word stops responding, that is the specific thing to
   report back.
3. **Turn on the floating avatar** (Settings -> This app -> Floating Jarvis)
   and try both Bubble and Overlay. GrapheneOS will show its own permission
   screen for "draw over other apps" - allow it, the same as on stock
   Android.
4. **Check a notification arrives** for an ordinary approval card, and that
   tapping it opens the app.
5. **Leave the app in the background for a while**, then send a chat message
   from it. This is what actually exercises the always-on `EventService.kt`
   background connection - if GrapheneOS's battery/background rules are
   stricter in a way that matters, this is where it would show up.

If all five hold up, the app is working the same as on stock Android and
nothing further needs to change. If something breaks, note exactly which
step and what happened - that is what would decide whether anything here
needs a real fix, and where.
