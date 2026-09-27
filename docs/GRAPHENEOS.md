# Running the phone app on GrapheneOS

The owner is considering moving their Pixel 9 to GrapheneOS at some point.
GrapheneOS is a more locked-down version of Android, built by a different
team than Google's, with extra privacy and security protections switched on
by default. This page is what to check first, written down now (2026-09-27)
so it is not forgotten when the actual switch happens - no code changes,
because none look necessary.

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
