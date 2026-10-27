# Jarvis Live over one persistent stream: design (Slice G)

**Status: DESIGN ONLY. Nothing in this document is built, and no audio path
changes.** The one thing that ships with it is a frozen, switched-off stub:
`GET/POST /api/live/stream` answers `501` with a plain reason, and the
`[live] stream` switch is `false` unless someone flips it (see §8 - the owner's
decision of 2026-10-21 makes that possible from either app, each with its own
card). The existing discrete-clip Live path is untouched.

**The owner answered the five design questions on 2026-10-21.** §11 records the
answers; this text has been updated to them and no longer asks. Two answers were
then refined by Gemini's rulings and folded in: **PCM-only for v1** (Q2, no Opus
dependency) and **drop the unfinished sentence cleanly on a link drop** (Q4, no
one-reconnect stitching); **Q3's either-app decision stands over Gemini's
PC-only recommendation** (advisory only, owner re-confirmed). The stub is
repo-only: the running backend on the owner's PC is not rebuilt with it in the
current deploy, so the switch is off there and the transport does not exist
anywhere yet; the desktop and phone rebuilds come later.

This is Slice G of the owner-approved Live & Voice program (work order
`.dsh-scratch/FOR-GEMINI-OVERNIGHT-WAVE-2026-10-21.md` §10.4 item 5 and §10.6;
audit row **V8**: "real gap: `LiveService.kt` is discrete HTTP clips"). It is
written for the owner first and for the implementer second: plain words first,
then the exact contracts.

---

## 1. Why change anything

Today's phone Live is a loop of **one-shot clips**:

1. the phone records; Smart Turn decides the sentence is finished;
2. the phone sends that whole sentence as one **WAV POST** to
   `/api/voice/utterance?source=live&mic=phone&waited_ms=…`
   (`JarvisApi.kt` `utterance()`; `docs/JARVIS-API.md` §17);
3. the PC checks the clip (session on, speech, voice print, then speech-to-text)
   through `jarvis_speech.hear()` and answers with one `Heard` verdict;
4. the answer is spoken back **while the next clip is being recorded.**

That works, and it keeps the most important promise: **nothing is transcribed
until the PC has verified the speaker.** Its costs are structural, not
accidental:

- the answer cannot start until the **whole** clip has been uploaded and the
  end-of-turn is decided;
- a turn costs one full connection setup (the phone uses a small HTTP pool, so
  this is milliseconds warm - but on a cold or flaky link it is seconds);
- barge-in and "Jarvis heard itself" are managed by the phone cutting audio,
  not by the PC hearing frames as they arrive;
- every stage is a separate request: clip in, words out, speech out. There is
  no one thing that knows "this is the current turn".

A persistent stream makes the phone a **microphone and a speaker attached to
one PC-side session**, like a headset cable. That is the whole idea; everything
below is the safety and honesty around it.

### What is measured, and what is not

Measured on the owner's PC (2026-10-18, warm, real stages -
`docs/LIVE-DESIGN.md` §4.1): VAD **31 ms**, owner check **~140 ms**, STT
(sherpa/Parakeet) **219 ms**, chat first token **125 ms**, Kokoro TTS first
audio **1.36 s**. Those are **stage** numbers, not one Live turn; the combined
number was never measured.

**Nothing in this design has been measured.** No stream exists, so
time-to-first-audio, end-of-speech to first byte, and battery/data figures
below are estimates to be replaced by the measurement plan in §9. Where a
number is an estimate it says so.

---

## 2. The current flow, exactly (what must not break)

These are the parts the stream must reuse, not replace:

| piece | today | file |
|---|---|---|
| Live session (one device, start/stop/extend/pause, status words) | PC owns it; one device at a time | `backend/jarvis_live.py` (`ROUTE = "/api/voice/live"`, `ENGINE`) |
| Phone recording | 16 kHz mono, `AudioRecord`, 300 ms pre-roll ring, Smart Turn end-of-turn (`TURN_MAX_PAUSE_MS = 1500`) | `LiveService.kt`, `SmartTurn.kt`, `LiveRules.kt` |
| Turn send | one WAV POST, `source=live&mic=phone&waited_ms=` | `JarvisApi.kt` `utterance()` |
| PC turn | session check → speech (Silero) → length → **voice print** → STT | `jarvis_speech.hear()` (`:2590`), `Heard` (`:2089`) |
| Playback | phone plays returned speech in chunks; interruption rules | `VoiceSession.kt`, `JarvisApi.say()` / speech chunks |
| Pauses and cards | PC says why; phone renders `LiveRules` words, never approves | `LiveRules.kt` (`CARD_PAUSES`, `VOICE_PAUSES`, `LINK_WORDS`) |

The stream must also keep the two rules that make Live safe today:

- **the segment is checked before its words are used** (`hear()`: "Never USES a
  transcript before the speaker is checked"); and
- **a Live clip is refused, not transcribed, when that device has no session**
  (`jarvis_live.py` module docstring; `_live_refusal` in `jarvis_speech.py`).

---

## 3. Proposed transport

### 3.1 One route, one socket

```
GET /api/live/stream            (WebSocket upgrade, binary frames)
```

- **WebSocket**, because it is bidirectional, ordered, has ping/pong, and both
  the phone's OkHttp and Python's small HTTP server can speak it. No WebRTC:
  no third-party signalling, no ICE/STUN/TURN, no public path.
- **Tailnet only.** The HUD already listens on loopback plus the PC's Tailscale
  or NordVPN Meshnet address; this route is bound by that same listener, and it
  refuses any request whose peer is not a private-network address **and** whose
  `X-Jarvis-Token` does not match. There is **no public listener, no relay, no
  tunnel** - rule 2 holds: the only network is the encrypted device-to-device
  mesh (WireGuard between the owner's own devices), never the internet.
- **One stream per device.** A second handshake for the same device replaces
  the first only by the owner starting Live again; two phones are two device
  names, and the PC allows one Live session at a time (`jarvis_live` already
  enforces it). A stream that does not name a device with an ON session is
  refused with `401`/`409` before any frame is read.
- **Auth at the handshake** - the same `X-Jarvis-Token` as every other request,
  sent as a header on the upgrade request (never in the URL, never logged), plus
  `X-Jarvis-Client: hud`. Token failure closes with `401`; the token is never
  echoed, logged or written.
- **Transport security (the owner's choice, 2026-10-21):** **tailnet encryption
  only.** WireGuard already encrypts the tailnet hop, and the app token at the
  handshake proves the caller; this version adds **no `wss://` certificate
  layer**. It does keep an explicit bind check (refuse non-mesh peers) and the
  token gate. If the measurement slice (§9) ever shows a need for the extra
  layer, it is a later, separately-switched change.

### 3.2 Frames

The phone sends **binary audio frames**, PC → phone sends **binary speech
frames plus small JSON control messages**, all on the one socket:

| direction | message | shape |
|---|---|---|
| phone → PC | audio | binary: one **64 ms** frame at 16 kHz mono (1,024 samples; 2,048 bytes as int16 little-endian), length-prefixed by a varint byte count |
| phone → PC | control | JSON text: `{"t":"hello","device":"phone","live_id":"…"}`, `{"t":"end_turn"}`, `{"t":"cancel"}`, `{"t":"mute"}` |
| PC → phone | speech | binary: int16 PCM at 16 kHz, length-prefixed the same way, one frame per TTS chunk (no codec, no transcode) |
| PC → phone | control | JSON text: `{"t":"ready"}`, `{"t":"turn_started"}`, `{"t":"speech_start","seq":n}`, `{"t":"speech_end","seq":n}`, `{"t":"not_owner"}`, `{"t":"refused","why":"…"}`, `{"t":"dropped"}`, `{"t":"pause","paused":"card"}`, `{"t":"bye","why":"…"}` |

- **64 ms frames** are the unit: small enough that the PC can run VAD and end
  of turn without waiting, big enough that the phone is not waking the radio
  every 20 ms. (The phone's existing recorder already reads small chunks; this
  is a reslicing, not a new recorder.)
- **Codec (Gemini ruling Q2, 2026-10-21): PCM-only for v1.** 16 kHz mono int16
  at about **32 KB/s**, length-prefixed frames, no Opus dependency and **no
  transcode step**: the same samples flow straight into Silero VAD, Smart Turn,
  CAM++ and Parakeet, so there is no encode/decode loss and nothing extra to
  install. The transport is measured with this shape (§9); a codec change is a
  later, separately-measured and owner-switched slice, not part of G.
- **No video, no camera frames** on this socket. Camera stays exactly as it is
  (a still picture per answer, separately gated by its own two-card rule).

### 3.3 The stub in this PR

Before any of the above exists, the URL and the switch are frozen:

```
GET  /api/live/stream   -> 501 {"ok": false, "available": false,
                                "enabled": <switch>, "stream": "off"|"not_built",
                                "error": "<plain sentence>"}
POST /api/live/stream   -> the same, before the body is read
```

The switch is `[live] stream = false` in `jarvis-framework.toml`. Off by
default; a missing table or key is also OFF (never read as permission). When
the switch is on, the stub still answers `501` ("not built") - the transport
arrives in a later slice. Existing `/api/voice/live` and
`/api/voice/utterance` are not touched by the stub.

---

## 4. The PC-side pipeline (what the frame handler will do)

The stream handler is a **thin adapter** over the code that already exists; it
must not become a second speech pipeline.

1. **Session gate.** First JSON `hello` must name a device whose Live session
   is on and not paused for "card" (cards still pause Live) or "other voices".
   Otherwise `bye` with the same words `jarvis_live` already uses. No audio is
   read before this.
2. **Ring + VAD.** Frames go into a short in-memory ring (last ~2 s, for the
   pre-roll). **Silero VAD runs active** (not per-WAV): when speech starts, the
   ring's pre-roll is prepended, so the first syllable is never lost.
3. **Early speaker check (Slice B).** On the first ~1.2 s of speech, CAM++
   compares the early window with the device's voice print while the owner is
   still talking. The gate is unchanged: **a rejected segment is discarded
   without transcription**; an unverified segment is never turned into words.
   If the check needs the full clip for confidence, the handler waits for
   `end_turn` and runs the same `jarvis_speech.hear()` path (compatibility
   fallback) - the stream does not weaken the check.
4. **Rolling STT pre-encode.** While the owner talks, the accepted audio is
   pre-encoded for Parakeet in chunks (same model/engine, no new dependency) so
   the post-end-of-turn cost is the tail chunk, not the whole sentence.
5. **End of turn.** The phone's Smart Turn (`TURN_MAX_PAUSE_MS = 1500`) or its
   explicit `end_turn` ends the segment; the PC finishes STT, composes the
   answer through the **same chat path** (`provenance: "voice"`, the Live model
   and `[live] context_tokens`/`tool_limit`), and streams speech back as
   first-fragment chunks (Kokoro's first clause, then full sentences - the
   Slice C behaviour when it lands).
6. **Pauses and cards.** The PC pushes `pause`/`resume` control messages using
   the existing `paused` vocabulary (`card`, `other_voices`, `voice_trouble`);
   the phone renders `LiveRules` words. A card on screen still pauses Live, and
   no audio is transcribed while it does.
7. **Barge-in** is deliberately **not** designed here; Slice F owns echo
   cancellation. Until then the phone's existing rule applies: pressing Stop
   talking stops playback; the PC never treats stream audio as barge-in.

---

## 5. The phone side

- **Recording** stays `AudioRecord` at 16 kHz mono with the existing device
  choice (voice-communication source while Jarvis speaks, voice-recognition
  otherwise), 64 ms frames pushed to the socket; no file is ever written.
- **Playback queue:** binary PCM16 speech chunks are appended to an `AudioTrack`
  queue (16 kHz mono, no decode step). The phone starts playing on the first
  chunk (`speech_start`) and stops at `speech_end`; the queue is flushed on
  `cancel`, on the mic starting, and on Live ending.
- **Interruption:** pressing Stop talking sends `cancel`, flushes the queue,
  and tells the PC to stop that reply; a card pause shows the existing card
  words and stops sending audio. No approval is ever reachable from audio,
  buttons or the stream (rule 4).
- **Reconnect:** automatic, exponential backoff 0.5 s → 8 s, at most five
  attempts, then the existing `LINK_WORDS` ("Paused: link lost - Live carries
  on when the link is back") and the listener falls back to one-shot clips (the
  current path) until the socket is back. A reconnect gets a new stream epoch;
  audio from the old epoch is never replayed. **On a link drop mid-sentence
  (Gemini ruling Q4, 2026-10-21): the unfinished sentence is dropped cleanly -
  no one-reconnect stitching.** Both ends zero the RAM ring, the PC pushes
  `{"t":"dropped"}`, and the phone shows the plain line **"Connection dropped
  - say that again"**. Stitching a half-sentence back together would corrupt
  CAM++/STT and could execute a half-spoken command, so it is not offered.
- **Battery/data budget:** the phone's screen is usually off during Live, so the
  foreground service and wake lock already exist; the stream adds one socket and
  one Android-side `AudioTrack`, with no codec work. Estimate to be measured in
  §9 (**NOT-MEASURED**): PCM16/16 kHz + 64 ms frames ≈ **1.92 MB/min**, so
  10 minutes of talking is roughly **19 MB**. No audio is stored on either side.

---

## 6. Privacy (rule 1, written into the wire contract)

- **Nothing leaves the owner's devices.** The socket only exists on the
  tailnet; no public listener, no relay, no cloud STT/TTS.
- **The phone streams RAM only.** No clip file, no cache, no transcript on the
  phone; closing the socket discards the buffer.
- **The PC verifies before it transcribes**, exactly as today: session, VAD,
  voice print, then STT. A segment that fails the voice print is discarded
  without text, without a log line carrying audio, and without reaching the
  model.
- **No audio is retained** after the turn on either side; the PC's speech
  modules already promise this for clips and the stream handler reuses those
  buffers.
- **No logs of audio, words by default**, no tokens in URLs; the stream's only
  audit line is a count (`live.stream_opened` with device, seconds, frames) if
  the implementation slice adds one - never content.
- **The camera is still not on** during Live until its own second card passes;
  the stream does not change that.

---

## 7. Failure modes, and what the owner sees

| failure | what happens | what the owner sees |
|---|---|---|
| link drops mid-turn | socket closes; **the unfinished sentence is DROPPED cleanly** - both ends zero the RAM ring, no stitching, new epoch on reconnect (Gemini ruling Q4) | `LINK_WORDS` while reconnecting, then **"Connection dropped - say that again"** |
| PC busy / model loading | handshake accepted, `hello` answered `busy`; keepalive only, no audio accepted | "Jarvis is busy - Live will start when it is free" (existing busy wording), retry on the same socket |
| stale connection (phone slept, socket dead) | heartbeat every 5 s; no pong in 15 s → reconnect; new epoch | nothing at first; then the link words if reconnection fails |
| replay of old audio / old epoch | frames carry the stream epoch in their first byte; the PC accepts only the current epoch and a monotonic sequence, and a closed stream's epoch is dead forever | "Live moved" / "link lost" wording, never a silent second answer |
| token expires or is revoked | handshake or next frame `401`, socket closed; app re-pairs | "I've lost the link to your PC." (existing) |
| phone call / audio focus change | existing `LiveRules.onCall` pause; socket sends `pause`, drains | existing "paused - on a call" words |
| owner closes Live | phone sends `bye`, server ends session; both sides drop audio | "You ended it." |
| two devices try the same session | second handshake refused (`409`, "Live is on your other device") | existing `elsewhere` wording |

**Replay and stale-socket protection** are part of the contract, not an
afterthought: the handshake returns one `stream_epoch` (random, per PC process),
every audio frame starts with the epoch byte and a 32-bit sequence number, and
the PC refuses a frame from any epoch but the current one or with a sequence it
has already seen. A closed stream's epoch is retired and never accepted again.
The token remains the proof of "this phone is the owner's".

---

## 8. The switch: off by default, on with one card from either app

- `[live] stream = false` is the shipped state. Missing key/table = OFF.
- **The owner's decision (2026-10-21): either app may turn it ON, each with its
  own approval card.** The PC path is the existing `change_own_config` card,
  decided by the PC's Windows-Hello-class check; the phone path raises its own
  card and is decided on the phone with the phone's own lock. So the phone
  gains a way to widen its own capability here - deliberately, and bounded:
  exactly ONE card on the side that asks, no card ever approves itself, and
  the PC still enforces every Live rule afterwards (session, voice print,
  cards, pauses). The switch cannot be turned on silently or in bulk. (Gemini's
  Q3 recommendation was "PC-only ON"; the owner considered the clarification
  and kept either-app, so that is the decision recorded here - Gemini's note is
  advisory only.)
- Turning it **off** takes effect immediately from either side and closes any
  open stream (the off direction is never held on a card - it only removes a
  capability).
- The switch also gates the future transport (an open request when off is
  refused with the stub's 501), so an older phone can never accidentally start
  streaming to a PC whose owner has not opted in.
- This slice builds only the OFF state and the 501 stub; the two cards and the
  transport are later slices (§10).

---

## 9. Measurement plan (NOT-MEASURED until run on the owner's phone)

Numbers below are **the plan**, not results. Every row must be measured on the
owner's PC + phone, on the tailnet, with a warm model, before any latency claim
is made. **No audio recording leaves the devices; each timing is a timestamp,
and the PC's log line carries counts only.**

| what | how it is measured | target (owner sets after the baseline) |
|---|---|---|
| time-to-first-audio (press Live → phone plays first speech sample) | phone monotonic marks: `live_start`, `first_speech_chunk_played` | TBD; the current one-shot path is the baseline |
| end-of-speech → first byte back | PC marks VAD stop, `end_turn`, first STT token, first TTS chunk; phone reports socket receive time | TBD |
| partial vs final transcript agreement | PC compares its streaming hypothesis with the final transcript per turn (counts only, never text), 50 turns | TBD; a disagreement rate the owner accepts |
| packet loss behaviour | tailnet path with 1 % / 5 % synthetic loss; count dropped frames recovered by retransmit (WebSocket is TCP: loss becomes latency, not holes - measure the latency) | TBD |
| battery | Android `BatteryManager` deltas over 10 minutes of live conversation | TBD |
| data | phone socket counters, PC socket counters | TBD; PCM16/16 kHz estimate ≈ **1.92 MB/min** (NOT-MEASURED) |
| reconnect / drop | force the link down mid-sentence: time to `LINK_WORDS`, the "Connection dropped - say that again" line, and the clean new epoch (no stitching) | TBD |

The owner must set the pass line ("acceptable") **after** seeing the baseline;
this design does not invent one.

---

## 10. Build plan (each its own PR, seven required checks, no live writes)

1. **G1 (this PR)** - this design + the `[live] stream = false` switch + the
   frozen 501 stub route + tests. No audio path.
2. **G2** - PC stream handler: handshake/auth, hello/session gate, epoch +
   sequence, VAD ring, and the compatibility fallback to `hear()`; tested with
   synthetic frames, no phone.
3. **G3** - phone sender + playback queue behind the switch, `source=live`
   still accepted as a fallback; tested on the emulator and by unit tests.
4. **G4** - measurement slice: run §9, write the numbers in
   `docs/MEASURED-<date>-LIVE-STREAM.md`, set the owner's accepted line; the
   switch stays off until the owner turns it on.
5. **G5+** - wss only if the measurement proves it needed, barge-in with Slice F
   (AEC), and any partial-transcript preview; each with its own tests and
   switch. **No Opus in v1** (Q2): a codec change would be its own later,
   measured, owner-switched slice.

---

## 11. The owner's answers (decided 2026-10-21)

All five questions are **answered**; this design is the accepted direction.
Nothing below is a request any more.

1. **Transport security: tailnet encryption only.** The private Tailscale /
   NordVPN Meshnet hop plus the app token at the handshake. No `wss://`
   certificate layer in v1; it can be a later, separately-switched change only
   if the measurement slice shows a need.
2. **Codec: PCM-only for v1 (Gemini ruling Q2).** 16 kHz mono int16,
   length-prefixed frames at about 32 KB/s, no Opus dependency and no transcode
   step - the samples go straight into Silero VAD / Smart Turn / CAM++ /
   Parakeet. The current WAV path keeps working unchanged. No codec work is
   part of G; a later change would be measured and owner-switched.
3. **Turning the stream ON: either app may do it, each with its own approval
   card.** This is the owner's explicit choice, and the design says plainly what
   it means: the phone gains a way to widen its own capability, bounded by
   exactly one card on the side that asks - the PC path decided by the PC's
   Windows-Hello-class check, the phone path decided on the phone with its own
   lock. No card approves itself, nothing turns on silently or in bulk, and the
   PC still enforces every Live rule (session, voice print, pauses, cards). OFF
   is immediate from either side and closes any open stream. (Gemini's Q3
   "PC-only ON" recommendation is recorded as advisory only: the owner
   considered the clarification and kept either-app.)
4. **A link drop mid-sentence: drop the unfinished sentence cleanly (Gemini
   ruling Q4).** Both ends zero the RAM ring, the PC sends `{"t":"dropped"}`,
   and the phone shows "Connection dropped - say that again". No one-reconnect
   stitching: it would corrupt CAM++/STT and could execute a half-spoken
   command.
5. **Scope: design first (this PR), then the PC handler (G2) as its own slice.**
   The phone changes (G3) come after G2; the switch stays off and the stub
   answers 501 until G2/G3 land and the owner turns it on.

---

## 12. What this document does not claim

- It does not claim the transport is built, fast, or measured.
- It does not claim a WebSocket beats HTTP for throughput; the gain is
  latency/round-trips and one session, and that is a hypothesis until §9 runs.
- It does not change any existing Live behaviour: the one-shot path stays the
  only path until a later slice turns the stream on.
- It does not move any audio off the owner's devices, and it adds no public
  traffic surface.
