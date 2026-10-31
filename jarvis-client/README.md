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
over Tailscale or NordVPN Meshnet - never the home network (Android refuses
this app plain http:// to it) and never a public
tunnel (`docs/ARCHITECTURE.md`, rule 2). Chat, voice ("Hey Jarvis" and
push-to-talk), approvals, the Brain (memory, history, settings), the
floating avatar (Bubble/Overlay mode), notifications, and a home-screen
widget. What each screen must and must not do is written down in
`docs/ARCHITECTURE.md` and `CLAUDE.md` - in particular: no model catalogue,
no editable memory graph (the Galaxy is a read-only picture, 2026-10-26), no
deep config editing, and no speech-to-text of its own on this app (the
desktop does that, and hands the words back).

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

The owner's Windows PC, where these sessions run, has the Android SDK and a JDK
installed, so **the unit tests build and run locally** - see the root
`CLAUDE.md`, "How the Android apps get built". CI is still where the APK that is
published and installed is built, signed and smoke-tested. On a machine with
the Android SDK installed:

```bash
./gradlew assembleDebug     # app/build/outputs/apk/debug/app-debug.apk
./gradlew testDebugUnitTest # the unit and contract tests
```

CI (`.github/workflows/jarvis-client.yml`) builds, unit-tests, signs, and
runs an emulator smoke test on every push; a build is published to
`client-latest` only once that smoke test has actually installed and
started that exact file, and only from `main`.

The release APK is also checked for the classes **R8 is asked for by name** -
WorkManager's InputMerger and Worker, Room's generated database - because R8
cannot see a class that is created by reflection and will strip its constructor
without failing the build. That is the 2026-10-27 widget failure: every
home-screen widget update died with "Could not create Input Merger" while the
unit tests and the debug build were green. From the repository root:

```bash
python3 tools/check_apk_reflective_keeps.py   # add -v, or --list, or --self-test
```

It reads `classes*.dex` inside the release APK, needs no device, and exits 1
naming the class. Its docstring says why it deliberately does not check the
debug APK, and how to add a reflective entry point when a new one appears.

## Connecting to a backend

The app pairs with one Jarvis backend at a time (QR code, with a short
typed code as a backup), confirmed by an approval card on the PC first.
The address it's given must be on the owner's own networks - this PC,
Tailscale, or NordVPN Meshnet. A home-network address is on them, but Android
refuses this app plain http:// to it, so the phone asks for the Tailscale or
NordVPN name instead (`data/PhoneAddress.kt`); anything on the open internet,
a public tunnel included, is refused with a plain message rather than
silently falling back to a different address. `docs/INSTALL.md` part 3 has
the exact steps.

## Reading further

- `docs/JARVIS-API.md` - every address this app calls and what each
  answers.
- `docs/ARCHITECTURE.md` - the rules every feature follows, and the one
  approval model.
- `CLAUDE.md` - the project's day-to-day decisions, most recent last.
