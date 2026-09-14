# Epic-Jarvis
Epic Javis based on openjarvis  and greatly enhanced . 

## The two Android apps

| | `jarvis-client/` | `jarvis-android/` |
| --- | --- | --- |
| Speaks | **The real API** — SSE on `/api/events` plus REST, `X-Jarvis-Token` | A WebSocket protocol invented before `JARVIS-API.md` existed |
| Talks to Jarvis | **Yes** | No — none of its endpoints exist on the backend |
| Has | Pairing, event stream, chat, approvals with `risk`/`raised`, the reactor face | Duplex audio, lock-screen approvals, Glance widgets, quick capture |
| Release | `client-latest` | `android-latest` |

**Install `jarvis-client`.** `jarvis-android` is architecturally sound and
thoroughly tested, and it is pointed at a server that is not there. Its audio
pipeline, notification path and widgets are worth porting across once the
transport underneath them is right; its protocol is not.

## Getting the APK onto a phone

**Easiest — the Releases page.** Every build publishes to a rolling prerelease:

> **Client (the one that works):** https://github.com/darknight111/Epic-Jarvis/releases/tag/client-latest
>
> Older app: https://github.com/darknight111/Epic-Jarvis/releases/tag/android-latest

That is a plain `.apk` at a stable URL. Open it on the phone, tap the file, and
allow your browser to install unknown apps — or download it on a computer and
`adb install -r <file>.apk`.

**The other way — run artifacts.** Actions → the workflow → a run → the
**Artifacts** box at the bottom. This gives a `.zip` that has to be unpacked
first, and note that **the GitHub mobile app cannot download run artifacts at
all** — that path needs a browser.

Builds are signed with the committed debug key (`keystore/`), so a new build
installs over an old one in place and the pairing token survives.

## Building

APKs are built in CI, since the Android SDK is not vendored here. Unit tests
gate both builds, and the workflows assert that the test task actually matched
sources: Gradle reports `NO-SOURCE` and exits 0 for a module with no tests, so a
green check is otherwise compatible with nothing having run. On a compile
failure the workflow reprints the Kotlin diagnostics at the end of the log.

**Debug builds only, and deliberately.** The app is sideloaded over adb and is
never listed on Play, so there is no channel a release build would serve.

## Documents

- `docs/AUDIT-2026-09-14.md` — the five-reviewer audit of both apps, and what
  was done about each finding.
- `docs/GEMINI-AUDIT-PROMPT.md` and `docs/SOURCE-BUNDLE.md` — for handing the
  tree to an outside reviewer.
