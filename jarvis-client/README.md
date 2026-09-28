# Jarvis Client

The Android companion app for Jarvis. **This is the app to install** - the
one published to the [`client-latest`
release](https://github.com/darknight11ish/Epic-Jarvis/releases/tag/client-latest).
`jarvis-android`, elsewhere in this repository, is an older app kept only for
reference: it speaks a connection method the backend never had, so it cannot
talk to Jarvis at all (see that folder's own README).

Kotlin, Jetpack Compose, Material 3. `compileSdk` 36, `targetSdk` 36,
`minSdk` 33 (Android 13 and newer).

## What it does

Talks to the real backend over the real API (`docs/JARVIS-API.md`), reached
over Tailscale, NordVPN Meshnet, or the home network - never a public
tunnel (`docs/ARCHITECTURE.md`, rule 2). Chat, voice ("Hey Jarvis" and
push-to-talk), approvals, the Brain (memory, history, settings), the
floating avatar (Bubble/Overlay mode), notifications, and a home-screen
widget. What each screen must and must not do is written down in
`docs/ARCHITECTURE.md` and `CLAUDE.md` - in particular: no model catalogue,
no memory graph, no deep config editing, and no speech-to-text of its own
on this app (the desktop does that, and hands the words back).

## Layout

```text
jarvis-client/
└── app/src/main/java/com/jarvis/client/
    ├── MainActivity.kt     # entry point
    ├── JarvisApp.kt        # application class, startup wiring
    ├── JarvisRuntime.kt    # the one place screens read/change state
    ├── net/                # the API client, contracts shared with the backend
    ├── data/               # settings, stores, local state
    ├── ui/                 # Compose screens
    ├── voice/               # wake word, push-to-talk, playback
    ├── audio/               # recording
    ├── face/                # the animated face, shared look with the desktop
    ├── service/             # foreground services (wake word, notifications, the floating avatar)
    ├── widget/               # the home-screen and Bubble widgets (Glance)
    ├── assistant/            # Android's own Assistant-app hooks
    └── platform/             # thin wrappers over Android APIs
```

Tests live beside the code they check, under `app/src/test/`
(`app/src/test/java/com/jarvis/client/`) - most of them **contract tests**:
they hold a fixed list or a piece of wording to a JSON fixture that a
`tools/gen_*_cases.py` script generates from the real backend source, so
the phone and the backend can never quietly disagree (`OpenChatPhraseContractTest.kt`
and `tools/gen_open_chat_cases.py` are one example).

## Building

There is no Android SDK in the container most Claude sessions on this
project run in, so **GitHub Actions is the only compiler** - see the root
`CLAUDE.md`, "How the Android apps get built". On a real machine with the
Android SDK installed:

```bash
./gradlew assembleDebug     # app/build/outputs/apk/debug/app-debug.apk
./gradlew testDebugUnitTest # the unit and contract tests
```

CI (`.github/workflows/jarvis-client.yml`) builds, unit-tests, signs, and
runs an emulator smoke test on every push; a build is published to
`client-latest` only once that smoke test has actually installed and
started that exact file, and only from `main` or the owner's working
branch.

## Connecting to a backend

The app pairs with one Jarvis backend at a time (QR code, with a short
typed code as a backup), confirmed by an approval card on the PC first.
The address it's given must be on the owner's own networks - this PC, the
home network, Tailscale, or NordVPN Meshnet; anything on the open internet,
a public tunnel included, is refused with a plain message rather than
silently falling back to a different address. `docs/INSTALL.md` part 3 has
the exact steps.

## Reading further

- `docs/JARVIS-API.md` - every address this app calls and what each
  answers.
- `docs/ARCHITECTURE.md` - the rules every feature follows, and the one
  approval model.
- `CLAUDE.md` - the project's day-to-day decisions, most recent last.
