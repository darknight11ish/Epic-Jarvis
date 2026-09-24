# The wake word — what it needs before it can be built

## Status, 2026-09-23: built

Everything below this section is the design record from before it was
built, kept because its reasoning still holds. What was decided and built:

- **The spotter: openWakeWord's `hey_jarvis` model**, the "intended path" of
  §1 - the three files §1 asked for are now in
  `jarvis-client/app/src/main/assets/wakeword/` (with their CC BY-NC-SA
  licence beside them) and downloaded onto the PC by the owner. They were
  fetched from the project's GitHub release, which the proxy allows; the 404s
  in §1 were raw-file paths. Run through ONNX Runtime: on the phone
  `com.microsoft.onnxruntime:onnxruntime-android` 1.22.0 from Maven Central
  (pinned - 1.30.0 adds a telemetry uploader), on the PC the `onnxruntime`
  pip package. The phone's Kotlin (`voice/WakeSpotter.kt`) and the PC's
  Python (`backend/jarvis_wakeword.py`) implement the same streaming steps
  and were checked to score within 0.0005 of each other.
- **Porcupine: not chosen.** The owner's API-key change made it allowable,
  but `jarvis-framework.toml` records that its free tier ended in June 2026
  and that it checks its key online - a licence call from the phone on a
  timer, and an account the wake word would depend on - while openWakeWord
  needs neither and has a model for this exact phrase.
- **Where detection runs.** On the phone, on the phone (§1's requirement):
  nothing is sent until the phrase is heard. On the desktop, the Jarvis
  server on the same PC runs it: the desktop app cuts the room's sound into
  sentences and sends each over loopback only (it refuses a non-loopback
  server address), and the server drops any without the phrase before the
  owner check or speech-to-text. *Since then (2026-09-24):* that address is
  checked again right before every clip is sent and every Smart Turn check
  (`wake_audio_refusal` in `voice.rs`), not only when listening starts, and
  changing the server address in Settings stops listening, with a line
  saying so. Turn it on again to listen with the new address. Either way the PC checks the phrase again,
  then the voice, then transcribes - and the transcript must start with
  "hey Jarvis", which stops "...the computer was called Jarvis".
- **§2's service**: `service/WakeWordService.kt`, its own foreground service
  of type `microphone` (the link keeps `specialUse`), with a notification and
  a Stop action, never started at boot, `START_NOT_STICKY`.
- **§4's order**, all five: the separate service (1); a 2-second ring buffer
  so the clip holds the phrase (2); the spotter behind an interface
  (`WakeModels`), a model that fails to load being a named failure (3); the
  toggle, gated on the desktop's switch and saying the microphone indicator
  stays on (4); and `WakeListenTest`'s "a wake-word capture is never made or
  sent while the desktop says the wake word is off" (5).
- **§3's "approval means approved"** is now true in the module too: ON raises
  one card (`change_own_config`), OFF is immediate.

The owner's steps, and what was and was not measured, are in
`backend/README.md`, "Voice that works".

---

Step 3 of the current build order. It is **not** blocked on the API: the
transport exists and push-to-talk already uses it. It is blocked on two things
that are decisions rather than work, and one platform requirement the brief
does not mention.

---

## 1. It needs a keyword-spotter model, and I cannot fetch one here

Push-to-talk needs no model — the phone records and the desktop decides. A wake
word must decide *on the device*, continuously, that a phrase was spoken, and
that means a small neural model in the APK.

Three options. Android's own recogniser is out for a reason that is a rule
rather than taste; Porcupine was too, until the API-key rule changed:

| | Cost | Verdict |
|---|---|---|
| **Porcupine** (Picovoice) | Best accuracy, smallest model — and it requires an **AccessKey at runtime**. | **Reopened — your decision.** It was refused under the old rule 3, "No API keys in the app". You lifted that on 2026-09-17, so the AccessKey is no longer disqualifying: it would be stored like the pairing token (encrypted, never logged, sent only to Picovoice). What is still true: the key ties the wake word to a Picovoice account, and its licence terms for personal use should be read before choosing it. Not yet checked here: whether and how often the key is validated over the network. |
| **openWakeWord** (TFLite or ONNX) | Three model files — a mel-spectrogram front end, an embedding model, and one per wake phrase. A few MB total. Models are **CC BY-NC-SA**. | **The intended path.** Rule 5 already says "One dependency chain (the wake-word models) is CC BY-NC-SA. It stays non-commercial until that changes" — so the brief was written with this, or something like it, in mind. |
| **Android `SpeechRecognizer` in continuous mode** | No model to ship. | **Refused.** That is on-device speech-to-text, which §4.1 forbids, and it is a network service unless on-device recognition happens to be installed — so it would move the privacy boundary without anyone being told. |

**What I could not do from this build environment:** download the openWakeWord
models. Maven Central is reachable (a library dependency would resolve in CI),
`raw.githubusercontent.com` is reachable for text, but the model paths I tried
returned 404 and HuggingFace is blocked outright. The GitHub API is scoped to
this repository, so I cannot enumerate the upstream tree to find the current
paths.

**What that leaves you:** drop three files into
`jarvis-client/app/src/main/assets/wakeword/` and the rest is wiring I can do.
Whatever ships alongside them needs its licence and attribution recorded in the
repo, because CC BY-NC-SA requires both.

I have deliberately **not** built a wake-word toggle that does nothing. A
switch whose only possible outcome is silence is the "button that 404s" §2
exists to forbid, and it would be worse here than elsewhere: a control labelled
"listen for 'hey jarvis'" that quietly never listens is a promise about a
microphone.

---

## 2. It needs a foreground service type the app does not currently hold

This is the part the brief does not mention, and it matters more than the model.

Since Android 11, an app cannot read the microphone from the background at all
unless it is running a foreground service **whose declared type includes
`microphone`**, and on Android 14+ that also requires holding
`FOREGROUND_SERVICE_MICROPHONE`. The app today declares `specialUse` only —
chosen deliberately, because `dataSync`'s six-hour daily cap would kill the
event stream on a timer.

So the wake word needs either a second service or `specialUse|microphone` on
the existing one. Both are fine technically. What follows from it is not a
technical detail:

**While that service runs, Android shows the microphone indicator
continuously.** The green dot, in the status bar, for as long as the wake word
is armed. That is the correct behaviour and it should not be worked around —
but it does mean "the wake word is on" becomes a visible, permanent property of
the phone rather than a setting buried in a screen. Worth knowing before you
decide, and worth saying in the UI that turns it on.

It also means the wake word is not, on Android, merely "a trigger in your code"
as the same-transport argument suggests. The transport is identical and that
argument holds for the posting half. The *listening* half is a different
capability with its own permission, its own service type, its own battery
profile and its own permanent indicator.

---

## 3. What is already done for it

- `POST /api/voice/utterance?source=wake_word` — `JarvisApi.utterance()` takes
  the source; `JarvisApi.SOURCE_WAKE_WORD` is the constant.
- `POST /api/voice/wake` — `JarvisApi.setWakeWord(enabled)`. Note the server
  gates it as a config change and **approval means approved, not already
  live**; the value lands in the TOML, so a success is not a state change and
  the UI must re-read `/api/voice/status` rather than assume.
- `VoiceStatus.wakeWordOn`, defaulting to **false**, with `VoiceRulesTest`
  asserting that an absent field is also false.
- `VoiceSession.begin(source)` already takes the source, so the wake word is a
  second caller rather than a second path — which is the part of the
  same-transport argument that does hold.
- The server refuses a wake-word capture while the wake word is off, and says
  which. That refusal is already handled as a plain `REFUSED` with the server's
  own words.

## 4. The order I would build it in, once the models exist

1. Split the always-listening capture into its own foreground service with the
   `microphone` type, so the event stream's `specialUse` service is not
   entangled with it and can still be stopped independently.
2. A ring buffer of the last ~1.5 s, so the utterance posted to the server
   **includes the wake phrase and the words before the spotter fired**. A
   spotter takes a few hundred milliseconds to decide; capture that starts at
   the decision has already lost the start of the sentence.
3. The spotter behind an interface with a null implementation, so the absence
   of a model is a named state ("no wake-word model is bundled") rather than a
   silent failure.
4. The toggle, gated on **both** `listening.wake_word` from the server and the
   presence of a model, saying plainly that turning it on makes the microphone
   indicator permanent.
5. A test that a wake-word capture is never posted while
   `VoiceStatus.wakeWordOn` is false — the client half of the server's refusal,
   so it never relies on being told no.
