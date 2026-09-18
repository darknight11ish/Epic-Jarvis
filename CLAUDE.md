# Working with the owner of this repo

## Explain things simply

The owner is a **beginner developer**. Write for someone who is smart and is
learning, not for someone who already knows the jargon.

- Say what a thing *is* before using its name. "R8 (the tool that shrinks the
  app)" beats "R8" on first mention.
- Prefer short sentences and plain words. "The app was slow because it was
  built in debug mode" beats "the debuggable variant disables ART AOT
  compilation".
- When something technical is unavoidable, explain it in one line and move on.
- **Say what to actually do**, concretely: which button, which file, which
  command, in order. Do not leave the next step implied.
- Do not assume knowledge of Gradle, Android build variants, CI, git internals,
  or Kotlin idioms.
- Lead with the answer. Put the reasoning after it, for anyone who wants it.

This is about clarity, not simplification of substance. Do not hide problems,
soften bad news, or skip caveats - explain them in plain words instead. If
something is broken or uncertain, say so directly.

## What this project is

Two clients for a local-first personal assistant whose Python backend runs on
the owner's desktop.

- `jarvis-client/` - the Android app (Jetpack Compose). Branch:
  `claude/android-apk-build-q435fi`.
- `jarvis-desktop/` - the Tauri desktop app, worked on in a separate session.
  Branch: `claude/jarvis-desktop-tauri-vey6bc`.
- `jarvis-android/` - an older Android attempt, kept for reference only.

## The five rules that are not negotiable

1. Anything touching email, files, credentials or stored memory stays on the
   local model. The app sends none of it anywhere.
2. The app never opens a public tunnel. No ngrok, no Cloudflare Tunnel, no
   Tailscale Funnel, no "share my Jarvis".
3. API keys are allowed in the app - the owner reversed the old blanket ban
   on 2026-09-17, to unblock things like a GitHub API integration. Any key
   still gets the same care the pairing token already gets: never logged,
   sent only to the one service it authenticates against, and kept out of
   anything the app writes to disk in plain text.
4. The app never auto-approves anything, and blocks acting when the event
   stream is stale.
5. Non-commercial build. Sideloaded via adb, never listed on Play.

Also standing: do not build the model catalogue, the memory graph, or deep
config editing on the phone. A client must not do speech-to-text. Never build a
control that clears a rush latch or approves in bulk. Send
`X-Jarvis-Client: hud` on every request. Never log the token.

Amended by the owner on 2026-09-18: **switching the local model from the
phone is allowed** - between models the desktop already has, via
`/api/models/switch`, which raises an approval card like any other change.
The catalogue is still off the phone: no browsing, no downloading, no
`/api/models/install`.

## Tell the owner when something is wrong

Standing instruction from them: "Tell me plainly when something in the brief is
wrong, out of date, or won't work on the platform - I'd much rather hear that
than have you route around it quietly."

## How this code gets built

There is no local build. `dl.google.com` is blocked by the network policy, so
the Android Gradle plugin cannot resolve and **GitHub Actions is the only
compiler available**. Expect a CI round trip (~15 min) to find out whether
anything compiles. Check work carefully before pushing.

The APK is published to the rolling `client-latest` release, but only when the
emulator smoke job passes.
