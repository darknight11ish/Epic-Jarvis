# Phone and desktop: what the relationship should be — 14 September 2026

Four reviewers, working independently against `jarvis-client` on
`claude/android-apk-build-q435fi` and the desktop on
`origin/claude/jarvis-desktop-tauri-vey6bc`, each briefed to argue a position
rather than to survey:

| Reviewer | Brief |
|---|---|
| Thin client | The phone is too big. Prove it and say what to delete. |
| Capable peer | The phone is too helpless offline. Say what rule 4 actually forbids. |
| Android platform | What is the phone fighting, and which OS surfaces is it wasting? |
| Protocol skeptic | Attack the two-client framing itself. |

**Every claim below was re-checked against the source before it was written
down.** Three did not survive, and they are recorded here as prominently as the
ones that did — two of them were produced by defects in this repository's own
documentation and tooling, which is the finding that generalises.

---

## 1. Claims that did not survive checking

### 1.1 "`/api/appearance` already exists and the desktop calls it"

It does not. `jarvis-desktop/src-tauri/src/appearance.rs` declares
`const ROUTE: &str = "/api/appearance"` under a heading that reads, verbatim,
**"The route does not exist yet"**, and the module falls back to a local store
on every read.

The reviewer did not invent this. It read it from `tools/check_parity.py`, whose
table asserted "The route already exists". That tool extracts routes with a
regex over Rust source and cannot distinguish a live request from a string
constant — so a name that exists only as an aspiration was promoted to a fact,
and a reviewer reasoned from it. Corrected in the tool, along with a note saying
what a `todo` entry does and does not prove.

### 1.2 "The photosensitivity limits have forked between the two spec copies"

The two copies of `jarvis-visual-spec.json` do differ, and both still say
`"version": 1`, which is a real problem. But every **number** in the `limits`
block is identical: `flicker_harmonic 2.3`, `flicker_rate_hz_max 1.3`,
`max_transitions_per_s 3`, `min_luma_delta 0.10`. What the phone's copy carries
that the desktop's does not is an `enforced_in` block and a `found_14_sep` note
— documentation of the audit, not a change to the safety envelope.

The divergence is real and worth closing. It is not a safety divergence, and
saying so would have been alarming and wrong.

### 1.3 "The manifest has exactly one intent-filter"

It has three: `MAIN`/`LAUNCHER`, `QS_TILE`, and
`BOOT_COMPLETED`/`MY_PACKAGE_REPLACED`. The substantive point underneath it
stands and is worth acting on — there is no `ACTION_SEND` filter, so no app on
the phone can hand anything to Jarvis — but the count was wrong.

---

## 2. Confirmed, and fixed in this pass

### 2.1 A half-open socket condemned the link permanently

Traced end to end and reproduced by reading:

1. `JarvisApi.client` sets `readTimeout(0)`. Correct for a stream held open for
   an hour, and it means OkHttp can never surface a peer that stopped answering.
2. The watchdog in `JarvisRuntime.startStream` detects the silence at 70s and
   sets `_stale = true`. It does **not** cancel the stream job.
3. `decisionBlocker` refuses every approval while `_stale` is true.
4. The only line that clears staleness needs a frame — which cannot arrive on a
   socket nothing is going to close.

So: lose the radio mid-stream, and every approval is refused with "Not connected
to the desktop" until the app is reopened, on a connection the phone believes is
healthy.

The cancellation plumbing built to prevent exactly this did not work either.
`awaitClose { live?.close() }` sits **after** the reconnect loop, and that loop
only ends when `isActive` is read at the top — which cannot happen until the
blocking read returns on its own. The close meant to unblock the read was
reachable only after the read had already unblocked, and by then the `finally`
had nulled the handle.

Fixed with a 90s read timeout on a client used only for `/api/events` (four
missed keepalives at the server's ~20s cadence), plus a child coroutine that is
parked on nothing and can therefore do the close that makes the read throw.

### 2.2 A body carrying only `history` was read as the pending queue

`PendingItem` needs only an id, so a list of already-decided requests decodes
cleanly and nothing downstream can tell. The owner would be shown items settled
days ago as if they were waiting.

### 2.3 The quick-settings tile refused to be tapped in the state that mattered

`Tile.STATE_UNAVAILABLE` when the link is down — and SystemUI does not dispatch
`onClick` to an unavailable tile, so the branch in `onClick` that starts
`EventService` and opens the app was unreachable.

### 2.4 Two documents asserted things the code contradicts

The face picker rendered "Six of the desktop's twenty" while `Faces.all` holds
eight; it counts the list now. And `docs/APPEARANCE-SYNC-PROPOSAL.md` proposed
keying per-client face lists on `X-Jarvis-Client` — but **both clients send the
literal string `hud`**, the phone deliberately, because the server's origin
check runs before its token check and a native client has no `Origin`. The
header is load-bearing for CSRF and carries no identity. The proposal now says
so and names the two ways out.

---

## 3. Confirmed, and not fixed here — these are design decisions

### 3.1 A sleeping desktop is rendered as an alarm

`JarvisRuntime.resolveFace` returns `FaceState.ERROR` whenever the link has been
down longer than `RECONNECT_GRACE_MS` (12s), before it considers anything else.
The spec binds `error` to a rose pulse the code itself calls "deliberately
alarming".

`STANDBY` and `BANKED` — the two calm "not available" faces — are reachable only
from `_power` and `_attention`, both of which require a live connection. So a
desktop that sleeps at 23:00 puts a red alarm on the phone from 23:00:12 until
morning, every night, and there is no state in the shared spec meaning *the
other end is asleep*.

Three of the four reviewers reached this independently from different briefs.

### 3.2 Rule 4 is enforced in one of eight write paths

`decisionBlocker` is consulted by `decide()` and by `MainActivity` for display.
`revert`, `cancelJob`, `cancelHold`, `markDigestSeen`, `setMuted` and
`setWakeWord` have no staleness gate. `revert` is the one state-changing call
the API doc calls "the one state-changing thing a phone may drive", and
`InboxScreen` takes neither `link` nor `stale` as a parameter and renders no
notice surface — so tapping Revert offline fails silently.

Closing this **tightens** rule 4 rather than loosening it.

### 3.3 The app ships debuggable, and `versionCode` is 1

`adb shell run-as` is a shell in the app's data directory on any non-rooted
device, and hardware Keystore binding prevents *extraction*, not *use* by
anything running as the app. `TokenStore` states that the pairing token is the
only thing protecting the backend and then does sixty lines of careful work that
one build-type flag undoes. The `debug` signing config already points at the
committed keystore, so shipping the release variant costs nothing in
sideloading: the certificate is unchanged and `adb install -r` still works.

`versionCode = 1` means a crash report cannot say which build produced it, on an
app distributed as a single rolling tag with no Play Console behind it.

### 3.4 `cancelHold` is unreachable

`JarvisRuntime.cancelHold(handle)` has no caller, because no route serves a hold
handle. The code says so in its own doc comment, which is the honest way to
carry it, and it is noted here only so the next reader does not rediscover it.

---

## 4. The answer to the question

**The phone is not a peer and should not become one. It is also not "the
desktop, smaller". It is the only client that is where the owner is, and that
is the whole of its job description.**

Three of the four reviewers converged on this from different directions, and the
two that started furthest apart — delete a third of the app, versus let it stand
on its own offline — both ended up conceding the same boundary: **display is not
acting.** Rule 4 forbids deciding against a queue you cannot confirm is live. It
does not forbid showing what you last knew, labelled and with the buttons off,
and the app already has that pattern built correctly in `BrainScreen`'s
`Freshness` row and uses it on one screen out of five.

What follows from that:

- **The phone's monopoly is the microphone, the notification, and the
  decision-taken-away-from-the-desk.** Those are the things that cannot happen
  anywhere else. Everything else it renders is a convenience, and convenience
  screens should not grow.
- **Duplicated rendering is fine. Duplicated judgement is not.** Compose, a
  webview and a Rust tray icon genuinely cannot share drawing code, and
  `SHARED-LOOK.md` is right that what they share is data. But the swipe-
  eligibility rule, the risk sentence, and the staleness gate are *judgements*,
  and each is implemented independently in each client. They agree today by
  discipline, not by structure.
- **The backend should own what both clients are currently guessing at**: the
  visual spec served rather than vendored four times, appearance with a real
  revision, and risk prose — for which the precedent already exists, since
  `raised.text` arrives with its ordinal pre-built.
- **The identity problem blocks more than it looks.** Until the server can tell
  the two clients apart, every conversation about giving the travelling device a
  narrower credential is blocked on an origin check that forces them to be
  identical.

The one position I would not adopt is the 36% deletion. Its own author named the
reason: the seven extra faces are ~480 lines of pure draw code with no I/O, no
state and no failure modes, while the genuinely hard code — the frame loop, the
crossfade, the governor — survives deleting all of them. That cut removes the
lines with the best bug-per-line record in the project and keeps the worst. Its
*underlying* observation is worth keeping, though: it is the **choosability** of
the face, not the faces, that pulled in the randomiser, the twelve patterns, the
24-field params merge and the strobe budget that the photosensitivity governor
then had to be written to police.
