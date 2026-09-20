# Epic-Jarvis

Epic Javis based on openjarvis and greatly enhanced.

A local-first personal assistant. A Python backend on a Windows 11 desktop, a
Tauri 2 shell around it, an 8B model in Ollama on the same machine, and an
Android companion reachable over Tailscale. Nothing private leaves the
machine, there is no public tunnel, there are no API keys in the app, and
there is no approve-all control anywhere. Non-commercial.

## Where to start

| document | what it is |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | **The source of truth.** How the pieces fit, the invariants, and the one permission model everything must use. Read this before adding anything; where another document disagrees, this one wins. |
| [`docs/INSTALL.md`](docs/INSTALL.md) | Getting it running, including the parts that are rough. |
| [`docs/PEERS.md`](docs/PEERS.md) | What twenty comparable projects did about memory, approval gates, voice and packaging — read from their source. What to copy, what to refuse, where Jarvis is behind. |
| [`docs/COMPARISON.md`](docs/COMPARISON.md) | Their files beside ours, both quoted. Where Jarvis is ahead, where it is behind, and the two recommendations that did not survive the comparison. |
| [`docs/ASK-GEMINI.md`](docs/ASK-GEMINI.md) | Copy-paste prompts for a model with a working browser. GitHub's API is blocked from the dev container, so these are the lookups that cannot be done here. |
| [`docs/MODEL-TOPOLOGY.md`](docs/MODEL-TOPOLOGY.md) | Which model, at what context length, and why — including what does not fit. |
| [`backend/README.md`](backend/README.md) | The thirteen backend patches, what each fixes, and how to apply them. |
| [`docs/AUDIT.md`](docs/AUDIT.md) | Findings from the audits, and which are fixed. |

## Building the Android APK

APKs are built in CI, since the Android SDK is not vendored in this repo.

Two apps live here, and each has its own workflow and its own Gradle root:

| App | Workflow | Artifact |
| --- | --- | --- |
| `jarvis-android/` — the full companion (approvals, duplex audio, widgets, assistant role) | **Build Android APK** | `jarvis-android-debug-apk` |
| `jarvis-client/` — the rewrite against `ANDROID-BUILD.md`, currently step 0 | **Jarvis client** | `jarvis-client-debug-apk` |

### Getting the APK onto a phone

**Easiest — the Releases page.** Every `jarvis-android` build publishes to a
rolling prerelease tagged `android-latest`:

> https://github.com/darknight11ish/Epic-Jarvis/releases/tag/android-latest

That is a plain `.apk` at a stable URL. Open it on the phone, tap the file, and
allow your browser to install unknown apps — or download it on a computer and
`adb install -r jarvis-android-<sha>.apk`.

**The other way — run artifacts.** Actions → the workflow → a run → the
**Artifacts** box at the bottom. This gives a `.zip` that has to be unpacked
first, and note that **the GitHub mobile app cannot download run artifacts at
all** — that path needs a browser.

Builds are signed with a debug key restored in CI from the `DEBUG_KEYSTORE_B64`
repository secret (see `keystore/README.md`), so a new build installs over an
old one in place and the pairing secret survives.

Unit tests gate both builds, and the workflows assert that the test task
actually matched sources: Gradle reports `NO-SOURCE` and exits 0 for a module
with no tests, so a green check is otherwise compatible with nothing having run.

**Debug builds only, and deliberately.** The app is sideloaded over adb and is
never listed on Play, so there is no channel a release build would serve.

## Layout

- `backend/` — patches against the OpenJarvis backend, one executable test
  each, plus `jarvis_research.py`. The backend itself lives outside this repo;
  `docs/ARCHITECTURE.md` §9 says where.
- `jarvis-desktop/` — the Tauri 2 shell: Rust commands in `src-tauri/`, the
  windows in `src/`.
- `jarvis-android/` — the full Android companion app.
- `jarvis-client/` — the Android client rewrite that is meant to replace it.
- `server/` — the desktop-side WebSocket endpoint the Android apps talk to.
- `keystore/` — how the shared debug signing key is restored in CI; the key
  itself is never committed.
- `tools/` — build-time and verification scripts for the Android apps.
- `docs/` — everything above, plus the Android-side audits and protocol notes.
- `scripts/` — build-time generators for the desktop app.

Licence: see [`LICENSE`](LICENSE) and
[`THIRD-PARTY-NOTICES.txt`](THIRD-PARTY-NOTICES.txt).
