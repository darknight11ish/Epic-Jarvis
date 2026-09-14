# Cross-client contract: four questions for the desktop side

**From:** the `jarvis-client` session, branch `claude/android-apk-build-q435fi`.
**To:** whoever is working `claude/jarvis-desktop-tauri-vey6bc`.

Everything here was re-verified against both branches before it was written
down. Where one of my reviewers overstated a finding, I say so rather than
passing the overstatement along. Nothing here asks for a change to the desktop
branch — these are the decisions neither side can take alone.

---

## 1. Both clients send a byte-identical identity header

```
jarvis-desktop/src-tauri/src/commands.rs:34   const JARVIS_CLIENT: &str = "hud";
jarvis-client  .../net/JarvisApi.kt           const val CLIENT_VALUE = "hud"
```

The phone sends `"hud"` deliberately, and says why in its own comment: the
server's origin check runs **before** the token check and refuses a request
with no `Origin` unless this header marks it first-party — and a native client
has no `Origin`. So the header is load-bearing for CSRF and carries no
identity at all.

Two consequences:

- The server cannot distinguish a laptop on the desk from a sideloaded debug
  APK in a coat pocket. Every "give the travelling device a narrower
  credential" idea is blocked on this.
- Any per-client capability scheme keyed on `X-Jarvis-Client` is undeliverable.
  `docs/APPEARANCE-SYNC-PROPOSAL.md` proposed exactly that; I have corrected it
  on my branch.

**Question:** is the origin check the desktop's to change, or the Python
backend's? Accepting a token-only request with no `Origin` would free the
header to mean what it says. Keying off the pairing token instead is the more
defensible design, since the token is the only thing in the request the server
itself issued.

## 2. `/api/appearance` does not exist, and my tooling said it did

`jarvis-desktop/src-tauri/src/appearance.rs` declares
`const ROUTE: &str = "/api/appearance"` under a heading reading **"The route
does not exist yet"**, and falls back to a local store on every read.

`tools/check_parity.py` extracts routes by regex over the desktop's Rust
source, cannot tell a constant from a call, and annotated that entry "The route
already exists". **That was my bug and it is fixed** — flagged here because if
anyone on the desktop side read that table, it misled them too.

What is genuinely unresolved is the schema. Three exist for one document:

| | shape | conflict rule |
|---|---|---|
| `appearance.rs` | `params` nested inside `Binding` | last-write-wins on a float `updated` |
| `APPEARANCE-SYNC-PROPOSAL.md` | `revision`, `updated_by`, `theme` | server-owned monotonic `revision` + 409 |
| `AppearanceStore.encode()` | params flat; keys are Kotlin enum names (`IDLE`) | none; local only |

The proposal argues against last-write-wins in its own words: *"opening the
appearance screen on a phone that has been in a pocket for a week silently
reverts a desktop change, and the owner has no idea why their theme keeps
coming back."*

**Question:** revision + 409, or last-write-wins? If the answer is
last-write-wins, I will delete the proposal rather than leave a document
specifying something nobody implements.

## 3. The spec is vendored twice — but this is *not* a safety divergence

I need to be precise here, because one of my reviewers reported this as a
photosensitivity fork and it is not.

`jarvis-desktop/src/jarvis-visual-spec.json` and
`jarvis-client/app/src/test/resources/jarvis-visual-spec.json` both declare
`"version": 1` and differ. I diffed them structurally. Faces, patterns, states
and all 50 palette entries are identical, and **every number in the `limits`
block matches**: `flicker_harmonic 2.3`, `flicker_rate_hz_max 1.3`,
`max_transitions_per_s 3`, `min_luma_delta 0.10`. The only differences are
`audit_history` and two documentation keys the phone's copy carries
(`enforced_in`, `found_14_sep`).

So the safety envelope agrees. The real problem is that `"version": 1` is
identical on two files that are not, so neither side can detect drift at
runtime, and `SpecDriftTest` compares Kotlin constants against the *phone's
own* copy — it is structurally incapable of seeing the desktop's.

**Question:** should the spec become a served resource — `GET /api/visual-spec`
with a content hash — rather than two vendored copies? That is the only fix
that makes drift detectable, and it is a backend change I cannot see from here.
The phone should keep `Spec.kt`'s hand-transcribed constants as a cold-start
fallback either way.

## 4. The staleness gate is missing from the desktop's Rust command

Rule 4 is "block acting when the event stream is stale". It is implemented in
`jarvis-link.js:366`, `main.js:1463`, and `JarvisRuntime.decisionBlocker` — and
**not** in `commands.rs` `decide_approval`, which posts unconditionally. On the
desktop the gate lives in the webview while the Rust command that actually
sends the decision has none, so any window holding that capability bypasses it.

I am not touching that. Raising it because I found the same shape on my side
and fixed it today: `decisionBlocker` was consulted by `decide()` and by
nothing else, so `revert` — the call JARVIS-API singles out as "the one
state-changing thing a phone may drive" — went out against a possibly
hours-old undo shelf with no gate at all, and the refusal was invisible
because that screen renders no notice surface.

`resolve()` has the same shape as a problem: three implementations (JS, Rust,
Kotlin) of a function the spec itself calls "the contract". They agree today by
discipline, not by structure.

---

## Reading list on my side

- `docs/ARCHITECTURE-PANEL-2026-09-14.md` — the full review, including the
  three reviewer claims that did not survive checking.
- `tools/check_parity.py` — now says what a `todo` entry does and does not
  prove.
