# Epic-Jarvis
Epic Javis based on openjarvis  and greatly enhanced . 

## The two Android apps

| | `jarvis-client/` | `jarvis-android/` |
| --- | --- | --- |
| Speaks | **The real API** — SSE on `/api/events` plus REST, `X-Jarvis-Token` | A WebSocket protocol invented before `JARVIS-API.md` existed |
| Talks to Jarvis | **Yes** | No — none of its endpoints exist on the backend |
| Has | Pairing, event stream, chat, approvals with `risk`/`raised`, the reactor face, push-to-talk | Duplex audio, lock-screen approvals, Glance widgets, quick capture |
| Release | `client-latest` | **none — deliberately** |

**There is one app to install, and it is `jarvis-client`.**

`jarvis-android` no longer publishes a release. That is not tidiness: it used to
sit on the releases page beside `client-latest` under a nearly identical name,
and only one of the two can reach the backend. Two similar links where one
silently cannot work is a trap, and installing the wrong one reads as "my phone
is broken" rather than "wrong app".

The module itself stays, and CI still builds it. It is architecturally sound and
thoroughly tested, and pointed at a server that is not there — its duplex audio,
lock-screen approvals and widgets are worth porting across once the transport
underneath them is right. A module that still compiles is far easier to port
from than one that rotted quietly. Its APK is still produced as a run artifact
for anyone who actually wants it.

## Getting the APK onto a phone

**Easiest — the Releases page.** Every build publishes to a rolling prerelease:

> https://github.com/darknight111/Epic-Jarvis/releases/tag/client-latest
>
> That is the only release. There is deliberately no second one to pick wrong.

That is a plain `.apk` at a stable URL. Open it on the phone, tap the file, and
allow your browser to install unknown apps — or download it on a computer and
`adb install -r <file>.apk`.

**The other way — run artifacts.** Actions → the workflow → a run → the
**Artifacts** box at the bottom. This gives a `.zip` that has to be unpacked
first, and note that **the GitHub mobile app cannot download run artifacts at
all** — that path needs a browser.

Builds are signed with the committed debug key (`keystore/`), so a new build
installs over an old one in place and the pairing token survives.

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

Six themes ship, switchable in **Look**. Themes own the chrome and never a
state colour; the accent is derived from the idle binding rather than chosen,
so re-rolling the face's colours moves the whole interface with it.

## Building

APKs are built in CI, since the Android SDK is not vendored here. Unit tests
gate both builds, and the workflows assert that the test task actually matched
sources: Gradle reports `NO-SOURCE` and exits 0 for a module with no tests, so a
green check is otherwise compatible with nothing having run. On a compile
failure the workflow reprints the Kotlin diagnostics at the end of the log.

**Sideloaded over adb, never listed on Play.** The published APK is the shrunk
release build, signed with the committed debug key so it installs over any
earlier build in place. It is published only after an emulator has installed
and started that exact build, so a shrinker fault cannot ship green.

## Documents

- `docs/AUDIT-2026-09-14.md` — the five-reviewer audit of both apps, and what
  was done about each finding.
- `docs/GEMINI-AUDIT-PROMPT.md` and `docs/SOURCE-BUNDLE.md` — for handing the
  tree to an outside reviewer.
