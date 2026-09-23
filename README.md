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

## The Android app

**There is one app to install, and it is `jarvis-client`.** It talks to the
backend over the real API (`JARVIS-API.md`): the event stream on
`/api/events`, plus REST, with `X-Jarvis-Token`. It has pairing, chat,
approvals, the reactor face and push-to-talk.

## Getting the APK onto a phone

**Easiest — the Releases page.** Every `jarvis-client` build publishes to a
rolling prerelease:

> https://github.com/darknight11ish/Epic-Jarvis/releases/tag/client-latest
>
> That is the only release. There is deliberately no second one to pick wrong.

That is a plain `.apk` at a stable URL. Open it on the phone, tap the file, and
allow your browser to install unknown apps — or download it on a computer and
`adb install -r <file>.apk`.

**The other way — run artifacts.** Actions → the workflow → a run → the
**Artifacts** box at the bottom. This gives a `.zip` that has to be unpacked
first, and note that **the GitHub mobile app cannot download run artifacts at
all** — that path needs a browser.

Builds are signed with a debug key restored in CI from the `DEBUG_KEYSTORE_B64`
repository secret (see `keystore/README.md`), so a new build installs over an
old one in place and the pairing secret survives.

**Debug builds only, and deliberately.** The app is sideloaded over adb and is
never listed on Play, so there is no channel a release build would serve.

## Design

`jarvis-client` reads the shared visual spec, which lives here as
`jarvis-client/app/src/test/resources/jarvis-visual-spec.json` so that
`SpecDriftTest` can assert against it — palette, pattern params, state
defaults, flash limits and frame rates. A spec change is a build failure
rather than a quiet re-colour on one client. `face/Palette.kt` is generated
from it by `tools/gen_palette.py`; do not edit it by hand.

- [`docs/UI-AUDIT-2026-09-14.md`](docs/UI-AUDIT-2026-09-14.md) — what six
  reviewers found, what was fixed, what was priced and refused, the six
  backend gaps, and the six places the spec disagrees with itself.
- [`docs/UI-AUDIT-2026-09-18.md`](docs/UI-AUDIT-2026-09-18.md) — the follow-up
  interface audit: where the chrome has not caught up with the face, ranked
  by what it costs the user, with the design decisions left to the owner.
- [`docs/SHARED-LOOK.md`](docs/SHARED-LOOK.md) — what the phone and the desktop
  must agree on, written as a contract. For the desktop thread.

Three themes ship — Reactor, Daylight and High Contrast — switchable in
**Appearance**. Themes own the chrome and never a
state colour; the accent is derived from the idle binding rather than chosen,
so re-rolling the face's colours moves the whole interface with it.

## Building the Android APK

APKs are built in CI, since the Android SDK is not vendored in this repo. Unit
tests gate the build, and the workflow asserts that the test task actually
matched sources: Gradle reports `NO-SOURCE` and exits 0 for a module with no
tests, so a green check is otherwise compatible with nothing having run. On a
compile failure the workflow reprints the Kotlin diagnostics at the end of the
log.

**Sideloaded over adb, never listed on Play.** The published APK is the shrunk
release build, signed with the debug key restored from the `DEBUG_KEYSTORE_B64`
secret so it installs over any earlier build in place. It is published only
after an emulator has installed and started that exact build, so a shrinker
fault cannot ship green.

## Documents

- `docs/AUDIT-2026-09-14.md` — the five-reviewer Android audit, and what was
  done about each finding.
- `docs/GEMINI-AUDIT-PROMPT.md` and `docs/SOURCE-BUNDLE.md` — for handing the
  tree to an outside reviewer.

## Layout

- `backend/` — patches against the OpenJarvis backend, one executable test
  each, plus `jarvis_research.py`. The backend itself lives outside this repo;
  `docs/ARCHITECTURE.md` §9 says where.
- `jarvis-desktop/` — the Tauri 2 shell: Rust commands in `src-tauri/`, the
  windows in `src/`.
- `jarvis-client/` — the Android app that actually talks to the backend.
- `server/` — a desktop-side WebSocket endpoint. `jarvis-client` does not use it.
- `keystore/` — how the shared debug signing key is restored in CI; the key
  itself is never committed.
- `tools/` — build-time and verification scripts for the Android app.
- `docs/` — everything above, plus the Android-side audits and protocol notes.
- `scripts/` — build-time generators for the desktop app.

Licence: see [`LICENSE`](LICENSE) and
[`THIRD-PARTY-NOTICES.txt`](THIRD-PARTY-NOTICES.txt).
