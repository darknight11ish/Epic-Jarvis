# Epic-Jarvis

A personal assistant that runs on your own Windows PC, with an Android app to
reach it from your phone. Built on OpenJarvis and heavily extended.
Non-commercial, for one owner.

## How it fits together

- **Backend.** A Python server on the PC. It does the work, and uses a local
  model through Ollama on the PC's own graphics card.
- **Desktop app** (`jarvis-desktop/`). A Windows 11 app built with Tauri. It
  has a quick-ask bar (`Alt+Space`), a full HUD window, a desktop widget, and a
  tray menu.
- **Phone app** (`jarvis-client/`). An Android app that connects to the PC over
  your private network, either Tailscale or NordVPN Meshnet.

## What it can do

- **Chat** with the local model. Answers stream in as they are written.
  Cloud models are optional, and never see anything private.
- **Ask before acting.** Anything risky waits for your decision, and you can
  approve or deny it on the PC or the phone. Nothing is ever auto-approved, and
  there is no "approve all".
- **Remember things.** Jarvis saves facts about you from your own words -
  never from emails, web pages or files. Every saved fact is listed in both
  apps with a Forget button. Health, money, passwords and other people's
  private details wait for your yes. Old facts are retired rather than
  deleted, so Jarvis knows both what is true now and what was true before.
- **Stay quiet.** Jarvis may speak up on its own only a few times a day.
  Anything else waits in a daily digest.
- **Show what it is doing.** An animated reactor face shows its state:
  listening, thinking, speaking, or waiting on you. There are 20 face designs,
  and the faces and colours match on the PC and the phone.
- **Take voice**, by push-to-talk on the phone. It checks it is your voice
  before anything is transcribed.
- **Look how you like.** You choose the theme, the face, the colours and the
  layout. Appearance settings on the phone never change the desktop's
  configuration.

## Ground rules

1. Email, files, credentials and memory stay on the local model.
2. No public tunnel. It is reachable only over your private network, and needs
   a pairing token.
3. API keys are allowed. They are never logged, and each one is sent only to
   the service it belongs to.
4. Nothing is auto-approved, and acting is blocked while the connection to the
   PC is stale.
5. The phone app is installed by hand (sideloaded), never through the Play
   Store.

## Getting started

- **Set it up:** [`docs/INSTALL.md`](docs/INSTALL.md).
- **Install the phone app:** download the APK from the
  [`client-latest` release](https://github.com/darknight11ish/Epic-Jarvis/releases/tag/client-latest).
  Open it on the phone to install it, or run `adb install -r <file>.apk` from a
  PC. Each new build installs over the last one - except once: builds from
  before 19 Sep 2026 were signed with a different key, and the phone refuses
  to update those in place. [`keystore/README.md`](keystore/README.md) says
  what to do (uninstall once, install, pair again).
- **The backend** lives on the PC, outside this repo. [`backend/`](backend/)
  holds the patches applied to it, with a test for each one, and the modules
  it needs. One script puts all of it in place:
  `scripts/apply-patches.ps1` - [`docs/INSTALL.md`](docs/INSTALL.md) has the
  exact command.

There is one phone app to install: `jarvis-client`, from the release above.
`jarvis-android/` is an older app kept only as source to borrow from. It
speaks a protocol the backend never implemented, so it cannot talk to Jarvis
at all, and it no longer publishes a release: two similarly named downloads
where one silently cannot work is a trap, and installing the wrong one reads
as "my phone is broken" rather than "wrong app". CI still builds it, as a run
artifact, so it does not rot.

## Documents

| document | what it covers |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | **Read first.** How the pieces fit, the rules, and the one permission model. |
| [`docs/INSTALL.md`](docs/INSTALL.md) | Getting it running. |
| [`docs/JARVIS-API.md`](docs/JARVIS-API.md) | The API the apps talk to. |
| [`docs/MODEL-TOPOLOGY.md`](docs/MODEL-TOPOLOGY.md) | Which model runs on the graphics card, and why. |
| [`backend/README.md`](backend/README.md) | The backend patches: what each one fixes. |
| [`docs/UI-AUDIT-2026-09-23.md`](docs/UI-AUDIT-2026-09-23.md) | The latest review of the phone app's design. |

## Building

The phone app is built by GitHub Actions. There is no Android build tooling in
this repo. A build is published only after an emulator has installed and
started it. Any branch that changes the phone app publishes to the same
`client-latest` release, so its notes start with the branch and commit the
APK was built from - check them before installing.

The desktop app builds on Windows with `npm install` and `npm run tauri build`
in `jarvis-desktop/`. See its [README](jarvis-desktop/README.md) for details.

## Layout

| folder | what is in it |
|---|---|
| `jarvis-desktop/` | The desktop app. Rust is in `src-tauri/`, the windows are in `src/`. |
| `jarvis-client/` | The Android app. |
| `backend/` | Patches for the backend, and their tests. |
| `docs/` | Design, install, API and audit documents. |
| `scripts/`, `tools/` | Build and patch scripts. |
| `keystore/` | How the app's signing key is restored in CI from a secret. The key itself is never committed. |
| `jarvis-android/` | The older phone app, kept as source only (see above). |

Licence: [`LICENSE`](LICENSE) and [`THIRD-PARTY-NOTICES.txt`](THIRD-PARTY-NOTICES.txt).
