# Design: true barge-in with echo cancellation (Voice Slice F, phase 1)

**Status: DESIGN PLUS AN OFF-BY-DEFAULT PROTOTYPE. Nothing here runs on the
owner's PC, and the live voice path is unchanged.** The owner approved the whole
Live & Voice program on 2026-10-21; this document is the first (design) phase of
its largest and riskiest slice. It answers the audit's V5 finding ("true
barge-in on open speakers needs echo cancellation") with a measured plan, a
no-new-dependency prototype, and an explicit list of what is still unknown.

| item | state |
|---|---|
| The prototype | `backend/jarvis_barge_in.py` - reference-subtraction (NLMS) canceller + a 350 ms speech decision. **Not imported by any live module, not wired, no route.** |
| The switch | `[voice] aec_barge_in = false` (new, off). Nothing reads it in the live path yet; the prototype's constructor reads it and does nothing when off. |
| New dependencies | **None.** Standard library plus numpy, already required by the voice modules. A dependency (speexdsp / WebRTC AEC) is only justified if this prototype fails the plan in §7 - that would be a separate decision, with a `requirements.lock` change and evidence. |
| Real open-speaker barge-in | **NOT-MEASURED.** It needs the owner's microphone and speakers. Everything below is SYNTHETIC. |
| The tests | `backend/test_barge_in.py`, deterministic synthetic signals (52 checks before the switch-isolation additions; counted in the suite's own `N passed` line). |

Why phase 1 looks like this: the audit is right that the current design has a
hole on open speakers - but the project's own rule is that a feature that
touches the live microphone path is off until *that feature* is measured on the
owner's hardware, and the echo path is exactly the thing that cannot be
modelled from a repository. So the first deliverable is the design, a
prototype that can be measured deterministically, and a switch that stays off.

---

## 1. The premise: what the gate already does, quoted

This is not a greenfield hole. Three shipped mechanisms decide today whether a
sound over Jarvis's own voice can interrupt it.

### 1a. The self-echo block (`#660 F3`, landed 2026-10-20)

`backend/jarvis_speech.py:1991-2030` (comments trimmed):

```python
#: F3 (the 2026-10-18 frontiers audit; landed 2026-10-20). Jarvis's own
#: spoken answer can reach the microphone through open speakers, and CAM++ can
#: verify a cloned voice as the owner. So say() records when its sound should
#: have finished - the WAV's own length - plus this acoustic tail, and hear()
#: refuses the AUTOMATIC "the owner said something" path while that window is
#: open. The explicit barge-in answers are decided before the gate: barge_in()
#: (source=barge_in) and the "stop" word check below still work during
#: playback; only turning Jarvis's own words into a command is blocked.
ECHO_TAIL_SECONDS = 0.25
_SPEAKING_UNTIL: dict = {}       # mic ("" = every app) -> monotonic end
```

`is_speaking()` (`:2020-2030`) answers "is Jarvis's own sound, or its 250 ms
tail, possibly reaching this microphone", and `hear()` refuses the automatic
path while it is true (`backend/jarvis_speech.py:2695-2704`):

```python
    # F3: an automatic clip heard while Jarvis's own sound (or its tail) can
    # still reach the microphone is not checked, not transcribed and not
    # acted on. The stop checks above are before this line ON PURPOSE: a
    # spoken "stop" (or the 2 s barge-in detector's source=barge_in answer)
    # still stops Jarvis during playback.
    if is_speaking(mic):
        ...
        return Heard(False, source=source, seconds=seconds, reason=ECHO_REFUSAL)
```

So: a normal "the owner said something" clip is **never** turned into a command
while the reply is still sounding. The two paths that may answer during
playback are the stop-word check above that line and the explicit
`source=barge_in` answer.

### 1b. What the desktop sends during playback (`voice.rs` + `voice_flow.rs`)

`jarvis-desktop/src-tauri/src/voice.rs:82-103` (comments trimmed):

```rust
//! INTERRUPTING JARVIS: "STOP", AND WINDOWS' ECHO CANCELLING
//! While Jarvis speaks, this listener keeps listening. Saying "hey Jarvis"
//! already cut a reply off; saying "stop" now does too, and does nothing
//! else. The server spots it (`jarvis_wakeword.spot_stop`: a small
//! stop-word model on the same sound fingerprint as the wake word) in a
//! SHORT clip and answers `stop: true` before any voice check - stopping
//! speech is harmless, so it may act first ...
//! Since 2026-09-25 talking over a reply works too (voice_flow.rs): half a
//! second of speech tells the Jarvis bar, which pauses the reply and asks
//! for the first two seconds to be checked by the PC as "stop or not"
//! (`source=barge_in`, never transcribed); the utterance still goes as
//! `source=wake_word` when it ends.
```

`jarvis-desktop/src-tauri/src/voice_flow.rs:46-54` gives the numbers:

```rust
pub(crate) const BARGE_ONSET: Duration = Duration::from_millis(500);
pub(crate) const BARGE_CLIP: Duration = Duration::from_millis(2000);
```

and `voice_flow.rs:4-26` describes the shape: the bar pauses first, the PC
decides second, and the PC's answer only says "stop for good, or carry on".

### 1c. The PC's decision on that clip (`jarvis_voice_flow.barge_in`)

`backend/jarvis_voice_flow.py:422-465` answers ONE question - "should Jarvis
stop talking?" - and nothing else. Its gates, in order: the
`[voice] barge_in_enabled` switch (default **true**), the WAV, Silero VAD,
the stop word said by anyone, at least `MIN_SECONDS = 1.0` of speech, the
owner's voice print at the balanced bar, and finally a comparison against
Jarvis's own voices (the active custom voice, the cached "One moment." clip,
and a sentence of the built-in voice) - a clip at least as close to one of
those as to the owner's print is not the owner. The clip is **never
transcribed** and nothing is stored.

### 1d. Echo cancelling today, and what it is worth

* **Phone:** while Jarvis speaks, the reply plays as a voice call and the
  microphone is the voice-call one with `AcousticEchoCanceler` on
  (`backend/README.md:6016`).
* **Desktop:** the listener opens Windows' "communications" capture category
  and uses it ONLY when Windows reports acoustic echo cancellation active on
  the stream (`jarvis-desktop/src-tauri/src/aec.rs`). That module's own header
  says it has **never run on Windows** (`aec.rs:53-55`: "NOT VERIFIED ON
  WINDOWS. It compiles against the Windows target ... it has not been run on a
  Windows machine"); how much of Jarvis's voice it removes, and how well, is
  unknown (`backend/README.md:6059-6069`).
* **No reference we generate is used anywhere.** The desktop relies on the
  driver's echo canceller, not on the TTS PCM the PC already has in hand.

## 2. What the 2 s detector already catches, and what "natural interruption" does today

| sound while Jarvis speaks | today |
|---|---|
| "hey Jarvis" | Caught by the wake-word spotter; interrupts the reply. |
| "stop" (anyone) | Caught by the small stop-word model (`jarvis_wakeword.spot_stop`, `jarvis_wakeword.py:83-90`); stops speech before any voice check, because stopping speech is harmless. |
| The owner just talking over the reply | A **two-step** path: 500 ms of speech tells the bar to pause, the listener sends the first 2 s, the PC runs the owner print over a clip that still contains Jarvis's own voice, and answers stop-or-not. If Windows' echo cancelling is not active on the machine, the clip is the raw open-speaker mix, and the "Jarvis's own voices" comparison is what keeps it from accepting the assistant itself. A wrong answer either keeps talking over the owner (false negative) or cuts a reply (false positive). |
| The TV, music, another person | Should not stop it: the owner print refuses a stranger, and the Jarvis-voice comparison refuses the assistant. A false cut only shortens a reply. |
| An ordinary clip while Jarvis speaks | Refused by `is_speaking()` (§1a) - it is not even owner-checked. |

So the gap the audit names is real but narrow: **there is no reference-based
echo cancellation, so the owner's own words are judged through Jarvis's voice
on open speakers, and a plain interruption costs two round trips (2 s of
audio plus the check) instead of a cut decided on the PC itself.** Improving
that does not need a new wake phrase, a new route, or a new permission model;
it needs a cleaner residual and a shorter judgement.

## 3. The reference, decided: Jarvis's own outbound TTS PCM (system loopback ruled out)

**The ruling (2026-10-21, the owner-approved Live & Voice program and Gemini's
combined review): the reference signal is the TTS PCM Jarvis itself generated.
A system capture (WASAPI loopback, "Stereo Mix") is explicitly NOT the
reference.** An earlier draft of this document presented the two as candidates;
the ruling settles it, and the prototype follows the ruling.

Why the generated PCM is the right reference:

* **It is exact.** `jarvis_speech.say()` returns the 16-bit PCM before it is
  played, so the reference is the assistant's own sound - not a second capture
  of it, with a second device's buffering and clock.
* **It needs no alignment between two capture streams.** The only unknown is
  the playback+device delay, which the adaptive filter learns as part of the
  echo path (the prototype's 16 ms filter window covers a small delay and the
  first reflections).
* **It is the smaller privacy surface.** A loopback capture records everything
  the PC plays - the TV, music, a call - and any residual buffer made from it
  would carry those too. The generated reference carries only Jarvis's own
  voice, which the PC made anyway.
* **It is enough for the question being asked.** What has to be cancelled to
  hear the owner over Jarvis is Jarvis's own reply. Other sound is not echo;
  it is a false-positive risk on the owner check, and CAM++ - the verify-first
  gate this project already uses for the shipped barge-in clip - is the
  backstop for that, not an echo canceller.

Why system loopback is rejected (said here so it is not re-proposed quietly in
a later slice):

* it needs extra Windows capture code in the desktop shell (a new device class
  and its own unsafe surface) and a second timing domain, for a reference the
  product question does not need;
* it captures every sound the PC makes, which widens the residual buffer's
  privacy story for no gain here;
* the ruling above names it out. If the generated reference ever fails the
  measurement in §7, the answer is a measured decision - a playback timestamp
  from the shell, a longer filter, or a dependency such as speexdsp/WebRTC -
  **not** the system loopback.

## 4. The prototype in `backend/jarvis_barge_in.py`

```python
BargeInDetector(verifier=..., enabled=None)   # enabled=None reads the switch
    .feed(mic_frame, ref_frame) -> dict | None
    .reset() / .close()                       # per utterance / done
    .buffered_samples / .metrics()            # numbers only
```

The filter is a normalized least-mean-squares (NLMS) adaptive filter over the
known reference: it learns the echo path (device delay, attenuation, a little
room tail) and subtracts it from each 20 ms microphone frame. Two details
matter and are in the code with comments:

* the update is divided by `max(reference power, POWER_FLOOR)`, because a
  quiet moment in a TTS sentence otherwise makes the normalized step enormous
  (the synthetic harness measured the prediction reaching 3x the echo it was
  modelling before this floor existed);
* the filter adapts only on frames that look like echo ("double talk" freezes
  it), so the owner's voice is not learned as if it were part of the echo path.

What is left is the residual. The detector judges it in this order:

1. **warm-up** - the first 600 ms only learn the room and build the echo-only
   residual floor; no decision can be made in it;
2. **above the echo floor** - the residual must be at least 3x the median
   echo-only residual (the subtraction error), and above an absolute gate;
3. **speech-shaped** - a voiced zero-crossing rate, a harmonic (not flat)
   spectrum, and a syllable envelope (the frame RMS moves at 2-8 Hz). This is
   what a steady tone or white noise fails;
4. **at least 350 ms** of such frames, with a 200 ms quiet hangover;
5. **the owner check** - a supplied `verifier(residual_audio, sample_rate) ->
   bool` (CAM++ in the real design). No verifier means no stop (fail closed);
   a raising verifier means no stop.

The CAM++ gate is preserved, and it is verify-FIRST: `should_stop` is true
only after the verifier returns true, a missing verifier and a raising verifier
both fail closed, and the prototype has no action to take before that answer
exists. The future wiring keeps that order: verify, then (only on true) cut.

The decision dict carries numbers only - `should_stop`, `reason`, `speech_ms`,
`residual_rms`, `echo_rms`, an ERLE proxy, when it happened, and the sample
count - and **nothing acts on it**. The future wiring would read
`should_stop` and, on true, stop the reply and treat the interruption as the
next turn; that wiring is deliberately not in this phase.

## 5. Privacy of the residual buffer

The residual is microphone audio, so it gets the project's usual treatment:

* **memory only** - the module has no file, network or logging call at all,
  and the tests prove it prints and logs nothing and that importing it starts
  no live voice module;
* **per utterance, bounded** - at most `MAX_RUN_S = 3 s` is ever held, handed
  once to the owner check, and discarded in the same call; `reset()` and
  `close()` leave zero samples and the tests assert it; no residual buffer
  outlives the decision it existed for;
* **never transcribed**, no words stored - the owner check is a speaker
  embedding comparison, exactly as `jarvis_voice_flow.barge_in()` does today;
* the **reference** is Jarvis's own voice, not the owner's;
* the filter keeps a **fixed-size** reference history (16 ms) that is
  overwritten in place - not a recording.

If the product ever logs a decision, the rule must be: numbers only, never
audio, never words (`jarvis_voice_flow`'s timing rows are the precedent).

## 6. What the phase-1 suite proves (SYNTHETIC everywhere)

`backend/test_barge_in.py` builds a synthetic TTS reference (harmonic tone with
a 3.7 Hz syllable envelope), a synthetic room (a delayed and attenuated echo:
two early reflections and a tail), synthetic voices, white noise, a steady
music-like chord and amplitude-modulated noise. It measures, on this machine,
with numpy only:

* the purely echo case is cancelled: **ERLE about 50 dB** on the synthetic
  echo (the design's pass bar is >= 30 dB on this harness; the real bar on the
  owner's PC is in §7);
* a synthetic owner over the echo is detected in **0.36 s** from speech onset
  in **3/3** voice variants - one decision, `should_stop: true`, 360 ms of
  speech (the design's floor is 350 ms);
* a **wrong-speaker** residual (verifier spy returns false) is rejected
  (`should_stop: false`, `not_owner`);
* **no verifier** and a **raising verifier** both fail closed;
* **zero false cuts** across the synthetic pure-echo, white-noise,
  music-chord and amplitude-modulated-noise cases (the suite prints the
  count);
* a decision retains **zero** residual samples; a second identical run makes
  an identical decision (deterministic); the same input makes the same event
  twice.

These are numbers about synthetic signals, not about the owner's room. They are
the prototype's acceptance bar, not a claim of real barge-in.

## 7. The measurement plan on the owner's hardware (NOT DONE YET)

Run this only after the owner chooses to try it, with the switch still off by
default until the numbers are in. Measure, with Jarvis's real reply through the
real speakers and the real microphone, at the owner's usual volume:

| number | what it means | suggested pass bar (to confirm with the owner) |
|---|---|---|
| **AEC residual echo level** | how much of Jarvis's own voice is left at the microphone after cancellation, measured on a sentence with no one else talking (ERLE dB, and the residual's RMS vs the reply's RMS) | at least 20 dB better than no cancellation on the same clip; the design expects 30-40 dB from the synthetic evidence, but the real number decides |
| **False-cut rate with Jarvis speaking** | over N replies with no interruption (the owner moving papers, the TV on, music), how many cut by mistake | 0 in the first N; any cut is a finding, because a cut throws away a reply |
| **Detection rate and latency** | over M deliberate interruptions at natural speed: detected / missed, and time from the first speech sample to the decision | detected >= M-1; latency <= 350 ms + one frame if the owner's own check is the only cost (the synthetic prototype measures 360 ms) |
| **Owner-voice verification on the residual** | CAM++'s score distribution for the owner's residual vs a stranger's vs Jarvis's own residual (the last one must be judged not-owner) | the owner's residual clears the existing balanced bar with margin; the assistant's own residual does not |
| **Alignment** | the playback+device delay the filter learns at the start of a reply (the peak tap position), and how stable it is between replies | stable enough to keep one filter per reply; if it drifts inside one sentence, a measured decision is needed (a playback timestamp from the shell, a longer filter, or a dependency), never the system loopback |

Scenarios to cover: open speakers at the owner's usual volume; headphones
(nothing to cancel - the detector must not cut); the TV on; music; a second
person talking. Until this table is filled with real numbers, phase 1 is not a
product and the switch stays off.

## 8. The switch, the approval rule, and rollback

* Key: `[voice] aec_barge_in`, default **false** (both copies of the shipped
  `jarvis-framework.toml` carry the commented default). It is read fresh every
  time a detector is built, so turning it off applies to the next utterance -
  no restart.
* Turning it **on** is one `change_own_config` approval card, the same tier as
  every other change to Jarvis's own behaviour; turning it **off** is
  immediate and needs no card (it only takes something away, the same rule as
  the existing `[voice]` switches).
* With the switch off, the prototype processes nothing at all (not one frame;
  the suite proves it), and it is not imported by any live module, so the old
  behaviour is the only behaviour. Phase 1 has no live-path change at all;
  enabling a wiring is a *later* phase whose diff is reviewed on its own.
* The existing `[voice] barge_in_enabled` switch is a different thing and is
  untouched: it says whether the PC answers the current 2-second barge-in
  clips at all (default true). `barge_in` is the new, off, reference-based
  prototype; the names are deliberately close because they are the same
  product question at two levels, and both are documented in the config.

## 9. Both apps, and one-sidedness

Phase 1 is **desktop-only on purpose, and nothing is wired even there yet.**
The phone cannot run this prototype: the echo canceller runs on the PC beside
the TTS PCM and the CAM++ model, and the phone already has its own
`AcousticEchoCanceler` in voice-call mode (`backend/README.md:6016`). A phone
half of this feature would be "keep using the platform's canceller" plus the
existing barge-in path - no new code in this slice. The one-sided-on-purpose
row is in `docs/ARCHITECTURE.md` §8.

## 10. What is honestly still open

* **No real measurement.** Every number in §6 is synthetic; open-speaker
  barge-in on the owner's hardware is NOT-MEASURED and must not be claimed.
* **The webview's playback timing.** The reference is exact, but the moment
  it reaches the speaker is not something the Python side observes. The
  filter can learn a stable delay, but if the delay changes inside a sentence
  (the desktop queues speech pieces, `jarvis_speech.say()` -> main.js), the
  generated reference may be too weak. The measured answer would then be a
  playback timestamp from the shell, a longer filter, or a dependency - **not**
  the system loopback, which the ruling in §3 rules out. The measurement plan
  looks at this first.
* **Non-linear echo and device processing.** Speakers distort, Windows applies
  its own enhancements, and the "communications" stream may already cancel
  some of the echo before the microphone stream reaches us. An NLMS filter is
  linear; the real residual may not be as clean as the synthetic one.
* **Music/TV with speech-like modulation.** The synthetic guard rejects the
  cases above, but a real TV voice is speech-shaped and can pass the residual
  checks; the CAM++ owner check is the backstop, and the false-cut measurement
  is where that risk is counted.
* **The owner check on a residual** is untested: CAM++ has been run on whole
  clips, never on 350 ms of echo-cancelled residual. The measurement plan
  makes it a first-class number.
* **A dependency decision remains open, not taken.** If the numbers in §7
  are poor, speexdsp or the WebRTC canceller become candidates; that is a
  separate decision with a `requirements.lock` change and the project's
  THIRD-PARTY-NOTICES process. The first attempt is deliberately dependency-
  free so the evidence for that decision can be gathered cheaply.
* **The live voice path was not touched.** No `jarvis_speech.py`,
  `jarvis_voice_flow.py`, `voice.rs` or `voice_flow.rs` change is in this
  phase; the prototype and its switch are additions a reviewer can read in
  one sitting.
