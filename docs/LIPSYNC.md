# Lip-sync: how the mouths follow Jarvis's voice

The owner's request, 2026-09-28: "Make sure the mouths do a great job of
matching Jarvis's voice."

## In plain words

When Jarvis speaks, the whole sound clip for that sentence reaches the app
**before** it starts playing. So the app listens to the clip once, up front,
and writes down what a mouth would be doing at every hundredth of a second:

| Number (0 to 1) | What it means | Sounds that push it up |
|---|---|---|
| **level** | how loud Jarvis is right now | everything; this is what the twenty non-animal faces react to |
| **open** | how far the mouth is open. 0 = shut | open vowels ("ah") most; it drops to 0 in pauses and for **m, b, p** |
| **wide** | lips spread, teeth showing | "ee", "i", and hissing sounds like "s" |
| **round** | lips pushed into a circle | "oo", "o", "w" |

That list of numbers is the **mouth track**. While the clip plays, each
face reads the track at the exact point of the sound you are hearing, so the
mouth cannot drift out of step, even if the computer or phone is busy.

- It works for Jarvis's normal voice, the three animal voices (pitched up
  by default, and whatever voice, pitch - deeper or higher - and pace the
  owner picks for each animal since 2026-09-28), and recorded custom
  voices, because it only looks at the sound itself. The Kokoro timing
  below follows the chosen voice, pitch and pace too: see "Each animal's
  own voice" at the end.
- **Nothing leaves your device** (rule 1). The track is made from sound
  that is already on your PC or phone, and it stays there.
- **No sound, no mouth movement.** A typed answer, Quiet mode, or an answer
  kept on screen rather than read aloud has no clip, so there is no track,
  and the animals keep their mouths shut. (docs/CRITTERS.md, "How the
  mouths talk".)
- It is cheap: 10 seconds of speech is analysed in about 10-20 ms on the
  development machine (the budget was 50 ms), once per sentence. It has not
  been timed on a real phone yet.

There is nothing to switch on and no setting. If a mouth ever looks early or
late on your PC or phone, say so - the timing numbers are below, and the
fix is one number.

**Since 2026-09-28 the PC can do better for its own voice.** When Jarvis
speaks in its built-in voice (Kokoro), the PC works out the exact moment of
every speech sound from Kokoro itself and sends the mouth shapes inside the
same sound file; both apps use them instead of guessing the shape from the
sound (they still take the loudness from the sound). It needs a one-time
step on the PC; until then, and whenever anything is in doubt, everything
works exactly as described here. See "Mouths from Kokoro's own timing" at
the end.

**Honest limits** (details under "Known limits"): the owl's rounded "oo"
shapes are weaker than the other animals', because its voice is breathy; an
"r" in the owl's voice can close the mouth as if it were an "m"; the mouth
also closes for t, d and n, not only m, b, p (that looks natural, but it is
not strictly lip-reading-correct); and Bluetooth headphones delay the sound
by more than the apps can see, so the mouth will look early with them.

## Where it lives

| | Desktop | Phone |
|---|---|---|
| The analysis | `jarvis-desktop/src/lipsync.js` (`JarvisLipSync`) | `jarvis-client/.../audio/LipSync.kt` (`LipSync`) |
| Who calls it | `main.js` analyses each clip it plays and sends the track to every face window (`face-voice.js`) | `Speaker.play` analyses each clip before writing it to the `AudioTrack` |
| Who reads it | `faces.html`, every frame, at the audio's clock | `Speaker.mouthNow` → `FaceView` / the animals |

The two copies are written line for line and must give the same numbers
(checked, see "Tests").

API (both apps; the contract every caller relies on):

```
JS      JarvisLipSync.FPS                  100
        JarvisLipSync.LEAD_S               0.05
        JarvisLipSync.analyse(samples: Float32Array (-1..1, mono), sampleRate)
            -> { fps, n, level, open, wide, round }   (Float32Array(n) each)
        JarvisLipSync.ONSET_S              0.05
        JarvisLipSync.sample(track, tSeconds, out?) -> { level, open, wide, round }
            reads the track at tSeconds + LEAD_S, linear between frames;
            open, wide and round fade in over the first ONSET_S of playback
            (level does not); all 0 before the start / after the end;
            null track -> null
        JarvisLipSync.fromWav(ArrayBuffer | Uint8Array) -> { samples, sampleRate, mouth? }
            16-bit PCM, mono or stereo (averaged); anything else -> no samples.
            `mouth`: the track in the clip's "jmth" chunk, only when there is a
            valid one (see "Mouths from Kokoro's own timing")
        JarvisLipSync.mouthFrom(payload: string) -> track | null   (strict)
        JarvisLipSync.merge(audioTrack, mouthTrack) -> track
            level from the audio track; open, wide, round from the mouth track
            (a shorter one padded shut) - only when both are 100 fps and their
            lengths differ by at most MERGE_SLACK (3) frames; otherwise the
            audio track unchanged
        JarvisLipSync.pack(track) -> "100:<base64>"   (4 bytes a frame)
        JarvisLipSync.unpack(string) -> track
Kotlin  LipSync.FPS, LipSync.LEAD_S, LipSync.ONSET_S, LipSync.MERGE_SLACK,
        LipSync.Track(fps, level, open, wide, round) { n }
        LipSync.analyse(pcm: ShortArray, sampleRate) / analyse(samples: FloatArray, sampleRate)
        LipSync.forClip(wav: ByteArray, pcm: ShortArray, sampleRate): Track
            analyse(), merged with the clip's "jmth" mouth when it has a valid
            one (Speaker.play uses this)
        LipSync.mouthFrom(payload), LipSync.unpack(packed) (strict: null for
            anything malformed), LipSync.merge(audio, mouth?)
        LipSync.sample(track?, tSeconds, out: FloatArray): Boolean
            out[0..3] = level, open, wide, round; false (and zeros) outside the clip
        Wav.mouthChunk(wav: ByteArray): String?, Wav.MOUTH_CHUNK = "jmth"
Python  backend/jarvis_mouth.py (the PC): pack() byte for byte the same as
        lipsync.js pack(); add_chunk(wav, payload), read_chunk(wav)
```

Frame `i` describes the moment `i / 100` seconds into the clip (its
analysis window is centred there), and `n = ceil(samples * 100 / rate)`.

## How it works (for anyone changing it)

Speech-driven animation usually either (a) recognises phonemes and maps them
to mouth shapes, or (b) reads cheap acoustic cues straight into a few mouth
controls. (a) needs a speech recogniser and a language model, is slow, and
fails on made-up voices; the whole-clip-in-advance design here makes (b)
both cheap and exact in time. This is (b), with care taken over the three
things that make it look right: **silence and closures** (the mouth must
shut when the sound says it is shut), **no lag** (smoothing that looks
both ways), and **anticipation** (lips move before the sound).

### 1. Frames and features (per 10 ms)

- A window of about 25 ms (the power of two nearest 25 ms: 512 samples at
  16, 22.05 or 24 kHz; 1024 at 44.1 or 48 kHz), Hann-weighted, centred on
  the frame's time.
- **Loudness** of the raw window (dB).
- The **spectrum** (one real FFT per frame; frames that are digital silence
  skip it) of the pre-emphasised window, summed into quarter-octave bands
  from 75 Hz. Every cue below is a band total or a ratio of two, in dB:
  - `dO`, 300-4000 Hz: **oral** energy - what comes out of an open mouth.
    A hummed "m" or the voice-bar of a "b" has little of it.
  - `dH`, 4-10 kHz: **hiss** (s, sh, f, th).
  - `dL`, 80-1000 Hz: **voicing**, which carries on through an "m".
  - `lm` = 300-700 Hz vs 800-1400 Hz: high for close vowels (ee, oo), low
    for open ones (ah) - a stand-in for the first formant, i.e. the jaw.
  - `fb` = 2100-3300 Hz vs 1400-2100 Hz: high for front vowels (ee: second
    and third formants up high), low for back and rounded ones - a
    stand-in for the second formant.
  - `sh` = 2.5-5 kHz vs 300-1500 Hz (since 2026-09-28): "sh", "ch" and a
    breath put their hiss at 2.5-5 kHz, inside the oral band, so `dH` alone
    missed them (the owl's "Shall" opened to 0.87 on the "sh"); a vowel,
    even "ee", is 20 dB or more the other way. 15-25 dB of it counts as
    hiss, like `dH`.

  Band ratios were chosen over formant tracking on purpose: a peak-picking
  F2 estimate was tried and was wrong most of the time on this voice (it
  locked onto the edges); the ratios were chosen by searching band edges for
  the best separation of "oo" words from "ee" words across all four voices.

### 2. Per-clip normalisation

- `ref` = the 95th-percentile loudness of the clip; the **silence gate** is
  30-50 dB below it, set from the clip's own quiet frames (so a noisy
  custom voice still has a gate above its hiss).
- The oral reference `refO` = the 95th percentile of `dO` over speech.
- **The voice's colour.** Voices differ: the owl's breathy voice (Kokoro
  speaker 2) reads about 5 dB "brighter" on `fb` and 6 dB lower on `lm`
  than the default; the panda's (speaker 1) is darker. Both lip cues are
  therefore centred on the clip's own median vowel - but only in proportion
  to how many vowels the clip has (`m / (m + 80)` frames) and not all the way
  (0.8 and 0.9), so a short "Done." keeps a typical voice's centre and a
  sentence full of "ee"s still reads as spread. The animal voices' pitch
  shift (+1 to +3 semitones, formants 6-19 % higher) is a smaller effect
  than the difference between speakers, and this handles both.

### 3. The four channels

- **level**: loudness mapped from the gate (0) to `ref` (1), then an
  envelope with a fast attack (20 ms) and slower release (75 ms) - the
  classic speech-meter look, for the non-animal faces.
- **open**:
  1. target = `(oral loudness)^1.4` x (0.55 + 0.45 x jaw openness from
     `lm`) x less for nasals (`dL - dO` high) x less for hiss (teeth nearly
     together for s, f);
  2. smoothed **forward and backward** (25 ms each way), so it neither lags
     nor jitters;
  3. **closures**: a dip in `dO` of 7.5-12 dB or more, 140 ms or shorter,
     between two louder stretches, shuts the mouth for the dip - m, b, p
     (and t, d, n). At the edge of a pause (a dip with only one side, e.g.
     the "M" of "Maybe"), a quieter, nasal-sounding start or end is shut too;
  4. **pauses**: 80 ms or more below the gate shuts the mouth completely,
     40 ms into the silence, and it starts opening 30 ms before speech
     resumes;
  5. a soft ceiling, so loud peaks do not all slam to exactly 1.
- **wide / round**: read only from clear vowel frames (not hiss, not
  nasal): wide rises with `fb`; round needs a low `fb` **and** a close jaw
  (`lm` high), so "ah" (low `fb` but open) is not round. Consonants between
  vowels borrow their neighbours' lip shape (a weighted smoothing), which is
  what real lips do (coarticulation): the rounding of "oo" in "soon" is
  already there during the "s". The backward smoothing is slower (60 ms)
  than the forward (40 ms), so the lips shape up slightly **before** the
  vowel - anticipation. Hiss adds a little "wide" (teeth). Finally
  `wide x (1 - round)` and `round x (1 - wide)`: the two are never both high
  (measured: never both above 0.25 at once on any test clip, tuning or
  held out).

All the tuned numbers are in one table (`K` in lipsync.js, `object K` in
LipSync.kt). They were tuned by a search over the measurements below, then
checked on sentences that were not used for tuning.

### Why 50 ms (LEAD_S)

`sample(track, t)` reads the track at `t + 0.05 s`: the mouth is shown 50 ms
ahead of the sound being heard.

- **People notice a late mouth much sooner than an early one.** The
  broadcast standard for sound and picture (ITU-R BT.1359) finds that viewers
  detect sound arriving *before* the picture at about 45 ms, but sound
  arriving *after* the picture only at about 125 ms. So errors should fall
  on the "mouth early" side.
- **Real mouths move first.** In natural speech the lips and jaw start
  moving before the sound they make (for a "b", the lips shut before the
  silence is heard; a mouth opens before the vowel's sound peaks).
  Studies of talking faces report this lead as anything from a few tens of
  milliseconds to 100-300 ms at the start of a phrase (Chandrasekaran et
  al., 2009, found the long end; Schwartz and Savariaux, 2014, showed it is
  often much shorter in running speech). Animators lead by a frame or two
  for the same reason.
- **The screen is late.** A frame computed now is on the glass one to two
  refreshes later (16-33 ms at 60 Hz), which eats part of the lead.
- **Measured here:** without the lead, the track's first opening
  (`open >= 0.1`) comes a median **19 ms after** the first audible sound of
  a phrase (10th-90th percentile -8 to +81 ms; 134 phrase starts over all
  16 test sentences): the first sound is often a consonant, where the mouth
  is still nearly shut. With the 50 ms lead, the mouth starts to open about
  30 ms before the sound, minus the screen's delay: early by roughly 0-30 ms
  - inside the region nobody notices, and never late.

**The first 50 ms of a clip (ONSET_S).** Because of the lead, t = 0
already reads 50 ms into the track, and Kokoro often starts sounding 10-50
ms into a clip: the mouth used to jump from shut to a quarter open (the
owl's "Shall": lips spread 0.9) in one frame at the start of a sentence.
Since 2026-09-28 `sample()` fades open, wide and round in over the first
ONSET_S (50 ms) of playback; `level` is not faded.

The two apps also take the audio output's own delay off the playback clock
before calling `sample()` (desktop: when the clip plays through the app's
Web Audio graph, `main.js` subtracts the `baseLatency + outputLatency` it
reports; phone: `Speaker` uses the
AudioTrack's timestamp of the frame that actually left the phone), so
LEAD_S does not have to cover that. **Bluetooth** adds 150-250 ms that
neither app can see: with Bluetooth headphones the mouth will look early.
A larger LEAD_S would make that worse, which is one more reason to keep it
small.

## What was measured

### The test speech

Jarvis's real voice: Kokoro-82M v0.19 (the sherpa-onnx `kokoro-en-v0_19`
release, Apache-2.0 - the model the owner's PC uses), built exactly as
`backend/jarvis_speech.py` builds it (`OfflineTtsKokoroModelConfig`, `lang
en-us`), each clip made through `jarvis_speech.kokoro_speak` so the animal
pitch rise is the real one:

| Voice | Kokoro speaker | Speed | Pitch |
|---|---|---|---|
| default | 0 | 1.0 | - |
| red panda | 1 | 1.0 | +2 semitones |
| pygmy owl | 2 | 0.85 | +1 |
| sea otter | 4 | 1.15 | +3 |
| monkey (added 2026-09-28; not in these clips - `backend/test_mouth.py`'s real-model run covers it) | 6 | 1.0 | +1 |

(`backend/jarvis_voices.py` `FACE_VOICES`.) 24 kHz, 16-bit mono.

- **Sentences** (each voice): rounded vowels "Who knew the moon would glow so
  blue?", spread vowels "Please see these three sheep.", lips "Maybe Bob
  made a map.", pauses "Okay. Let me check. Done."
- **Labelled words** (each voice): 28 words synthesised one at a time and
  joined with 250 ms of silence, so every word's time is known exactly
  without anyone listening: rounded (who, moon, blue, food, you, boot),
  spread (see, sheep, three, tea, keep, fee), open (father, hot, car, top),
  a lip closure in the middle (happy, rubber, summer, hamper, lumber, super)
  and none (hello, Hawaii, carry, lower, mirror, arrow).
- **Held out** (not used for tuning): "Two blue shoes? Soon, too.", "We need
  three cheese pizzas, please.", "My mom picked up a bamboo map."

Seven of the sentence clips (about 12 s, 580 KB) are committed as test
clips: `jarvis-client/app/src/test/resources/lipsync/kokoro-*.wav` (the
default voice's four, the panda's and the owl's "lips", the otter's
"wide"). THIRD-PARTY-NOTICES.txt records them. The rest stayed in the
scratch folder they were made in.

### Results

Silence (frames whose own audio peaks under -50 dBFS, in runs of 120 ms or
more, 40 ms trimmed at each end): **mean open 0.0000** in every clip of every
voice, and in the 250 ms gaps between the 28 labelled words (27 gaps per
voice); the largest mean, in one panda sentence, was 0.0001.

Lip closures inside a word (lowest open inside the word / the smaller of
the peaks either side; under 0.25 counts as closed):

| | happy | rubber | summer | hamper | lumber | super |
|---|---|---|---|---|---|---|
| default | 0.00 | 0.05 | 0.02 | 0.00 | 0.07 | 0.00 |
| panda | 0.01 | 0.03 | **0.88** | 0.01 | 0.18 | 0.01 |
| owl | 0.00 | 0.02 | 0.00 | 0.00 | 0.00 | 0.00 |
| otter | 0.01 | 0.03 | 0.10 | 0.00 | 0.05 | 0.00 |

23 of 24. The panda's "summer" misses: its "mm" drops the oral band only
~10 dB against a weak following "er". Of the words with no lip closure,
"carry", "mirror" and "arrow" stayed open (0.55-1.00) in the default and
panda voices; the otter's "arrow" (0.21) and the owl's "lower", "mirror"
and "arrow" close on the "r" or "w" (see limits). "hello" and "Hawaii"
close on the "l" and the "w" in every voice - the tongue for "l" and the
rounded lips for "w" really do nearly close the mouth.

Lip shape per word (mean over the word's vowel frames; round words should
be round, spread words wide):

| | round on oo-words (who moon blue food you boot) | wide on ee-words (see sheep three tea keep fee) |
|---|---|---|
| default | 0.65 0.49 0.61 0.75 0.38 0.65 (mean 0.59; wide 0.06) | 0.83 0.87 0.46 0.84 0.74 0.74 (mean 0.75; round 0.03) |
| panda | 0.66 0.56 0.54 0.69 0.45 0.80 (0.62; wide 0.07) | 0.95 0.87 0.56 0.94 0.91 0.87 (0.85; round 0.01) |
| owl | 0.38 0.20 0.34 0.33 0.22 0.32 (0.30; wide 0.09) | 0.79 0.68 0.60 0.78 0.48 0.58 (0.65; round 0.04) |
| otter | 0.65 0.06 0.49 0.56 0.31 0.68 (0.46; wide 0.08) | 0.98 0.61 0.60 0.98 0.35 0.89 (0.73; round 0.03) |

Every "ee" word is wider than it is round, in every voice (24/24). Every
"oo" word is rounder than it is wide except the owl's "you" (it starts with
the "ee"-like "y") and the otter's "moon" (0.06 round vs 0.15 wide). Open
vowels (father, hot, car, top) open to 0.51-0.77 in every voice.

Whole sentences (mean over vowel frames), tuning set / held out:

| voice | "moon...blue" round vs wide | "see...sheep" wide vs round | "Maybe Bob made a map" closures | held-out "Two blue shoes" round vs wide | held-out "three cheese pizzas" wide vs round | held-out "My mom... map" closures |
|---|---|---|---|---|---|---|
| default | 0.36 vs 0.09 | 0.37 vs 0.14 | 4 | 0.37 vs 0.16 | 0.36 vs 0.18 | 7 |
| panda | 0.33 vs 0.13 | 0.36 vs 0.09 | 5 | 0.32 vs 0.29 | 0.29 vs 0.12 | 5 |
| owl | 0.16 vs 0.13 | 0.46 vs 0.09 | 4 | **0.12 vs 0.31** | 0.42 vs 0.05 | 7 |
| otter | 0.22 vs 0.12 | 0.44 vs 0.10 | 5 | 0.23 vs 0.24 (a tie) | 0.39 vs 0.12 | 5 |

("Closures" = times the mouth drops below 0.12 between two openings above
0.25.) On the held-out sentences: silence shut in all 12, closures in all 4
voices, "ee" sentences right in all 4, the "oo" sentence right in 2, tied in
1 (otter) and wrong for the owl.

Speed: a 10 s clip at 24 kHz, node on the dev container: 10-20 ms warm,
about 30 ms the very first time (the JavaScript engine is still compiling).
The Kotlin copy on a desktop JVM: the same 10 s in about 30 ms the first
time and 7-12 ms after. **Not measured on a phone** (there is no Android
device here); a phone is several times slower than this machine, but
Jarvis speaks sentence by sentence (usually 2-6 s each), the analysis runs
once per sentence, before it plays, and not on the drawing thread.

## Known limits

- **The owl's rounding is weak.** Its voice (Kokoro speaker 2) is breathy:
  noise fills the upper bands on every vowel and makes "oo" look brighter.
  Its "oo" words still read rounder than wide, but at about half the other
  voices' strength, and a sentence full of "s" and "sh" around its "oo"s
  (the held-out "Two blue shoes? Soon, too.") came out wider than round.
- **"r" can close the mouth**, mostly the owl's (mirror, arrow, lower;
  once for the otter): the "r" dips the oral band like an "m" does in that
  voice. An English "r" is made with rounded,
  nearly closed lips, so this looks less wrong than it sounds.
- **The mouth closes for t, d, n (and k, g)** as well as for m, b, p. The
  sound alone cannot cheaply tell a closure at the lips from one made with
  the tongue. Almost every lip-sync system does the same; it reads as normal
  talking.
- **"sh" is not rounded.** English "sh" is said with pushed-out lips; the
  hiss band that could tell "sh" from "s" did not separate them reliably in
  Kokoro's voice, so both get the small "teeth" spread. (With the PC's Kokoro timing,
  "sh" is rounded - see the last section.)
- **American "oo" is fronted** ("knew", "you"): its second formant sits
  between "ee" and "oh". Those vowels come out less round, which is roughly
  what the lips do too.
- **Custom voices are now measured** (2026-09-28): Piper (amy, lessac and
  the male alan), ZipVoice (the backend's own cloning engine, from a clean
  and from a noisy reference) and Pocket TTS - see "Deep and noisy voices"
  below.
- **A voice pitched 3 semitones down is only partly corrected** (the band
  move is capped at 3/8 of an octave), and am_adam at -3 reads "oo" a
  little less round than before (0.71 -> 0.59 of words rounder than
  wide).
- **Bluetooth delay** (see "Why 50 ms").
- The phone's own fallback voice (Android's text-to-speech, used when the
  PC's voice is not available) never gives the app the whole clip, so it
  cannot use this analysis; `SpeechClock.kt` estimates the opening from
  loudness only.

## Deep and noisy voices (2026-09-28)

Two steps were added to the analysis after the corpus tests. Both are in
`lipsync.js` and `LipSync.kt` (byte-identical output on 3,541 clips).

- **The lip bands follow the voice's pitch.** A deep voice's formants sit
  lower, so "ee" was read as round. `pitchOf()` estimates the median pitch
  of the vowel frames (normalised autocorrelation on the clip averaged down
  to ~6 kHz, every third vowel frame, with an octave guard), and both lip
  band sets move down by `0.6 x 4 log2(F0 / 210)` quarter-octaves, only
  down and at most 3/8 of an octave (`K.pitchRef 210, pitchAlpha 0.6,
  pitchLo -1.5, pitchHi 0`). Below a 4 kHz sample rate it does nothing.
  Moving the bands UP for high voices was tried and rejected (it broke
  the default voice's high-pitched "oo").
- **An adaptive noise floor.** The silence gate is raised to 7 dB above
  the clip's quietest 2% of frames, never more than 18 dB under its
  loudest (`gate = min(ref - 18, max(gate, p2 + 7))`). Clean clips' floor
  sits 38-60 dB down, so no clean voice changed; on a noisy clip the gate
  lands just above the noise.

| voice | before | after |
|---|---|---|
| am_adam (deep), "ee" sentences read wide | 0 / 8 | **8 / 8** |
| four voices at -3 semitones, "ee" wider than round | 0.28 | **0.72** |
| am_michael, bm_george, bm_lewis, "ee" sentences | 0.38 | **1.00** |
| Kokoro with noise 20 dB under it: mouth open in pauses | 0.16 | **0.01** |
| ZipVoice cloned from a noisy recording: level in pauses | 0.24 | **0.14** |

What it cost (kept because each is within a sentence or so of noise, and
every margin stays the right way round): the default voice and the otter
each read one of eight "oo" sentences less round (still rounder than
wide); Piper alan the same; the owl pitched +4 "oo rounder" 0.68 -> 0.61
(about 1.3 standard errors); breathy owl vowels under 20 dB of noise open
past 0.2 a little less often (0.96 -> 0.89). About +0.5 ms per second of
audio in node. Two new test clips: `kokoro-default-wide-deep.wav` (a
"sheep" sentence at -3 semitones) and `kokoro-default-pauses-noisy.wav`.

## Tests

- `tools/gen_lipsync.py` runs `lipsync.js` under node over the committed
  clips and writes `jarvis-client/app/src/test/resources/lipsync-golden.json`
  (every frame of every track, plus `sample()` reads).
  `python3 tools/gen_lipsync.py --check` fails if the fixture is stale; CI's
  backend job runs it.
- `jarvis-client/.../LipSyncTest.kt`: the Kotlin copy against the fixture
  (within 1e-3; the JVM run in the dev container matched to 5e-7, i.e. the
  fixture's rounding), `sample()` at and around the edges, silence, bad
  input, frame counts. Android CI compiles and runs it; it was also compiled
  and passed (6 tests) with plain `kotlinc` + JUnit in the dev container.
- `jarvis-desktop/tests/lipsync.mjs` (node, no browser): the quality numbers
  above on the committed clips (silence shut, m/b/p closures in every voice,
  oo rounder / ee wider), wide and round never both high, `sample()`'s lead
  and edges, pack/unpack, `fromWav` on mono, stereo and odd chunks, the speed
  of a 10 s clip, and that the fixture is fresh.
- **The PC's mouth shapes in the WAV** (2026-09-28): `tools/gen_lipsync.py`
  also builds `lipsync-mouth/kokoro-panda-lips-jmth.wav` (a committed clip
  with a `jmth` chunk, payload `v1;src=fixture;...`) and puts its merged
  track, its reads and a table of broken chunks (another version, a field
  that is not key=value, bad base64, not whole frames, another frame rate,
  the chunk before `data`, cut short, lengths more than 3 frames apart) in
  the golden file. `lipsync.mjs` and `voice-mouth.mjs` (desktop) and
  `LipSyncTest.kt` (phone) check both apps against it: a good chunk is
  merged (level from the sound), every broken one is ignored and the clip
  plays exactly as without it, and a WAV with no chunk behaves as before.
- `backend/test_mouth.py` (the PC half): sherpa-onnx's pause shortening
  copied exactly (against a line-for-line copy of the C++ loop), how a
  clause ended, Kokoro's token pieces, the mouth on two committed real
  Kokoro sentences (`backend/fixtures/mouth/`: m/b/p shut for their whole
  sound, f/v a lip-bite, "oo"/"w" rounded and rounding 80 ms early, "ee"
  spread, ah > eh > ee, pauses shut, no jumps), the chunk and every backend
  reader of the WAV, lipsync.js reading the Python-made chunk (with node),
  say() adding the chunk only when the timing is exact and speaking exactly
  as before otherwise, status() wording, and the one-time step on a toy
  model (with onnx). With `JARVIS_KOKORO_DIR` set to a kokoro-en-v0_19
  folder it also runs the real model; `--make-fixtures` rebuilds the
  fixtures from it.

To change the analysis: change `lipsync.js` and `LipSync.kt` the same way,
run `python3 tools/gen_lipsync.py`, then `node jarvis-desktop/tests/lipsync.mjs`.
If a quality check fails, the change made the mouths worse on Jarvis's real
voice - that is the point of those checks.

## Mouths from Kokoro's own timing (the PC, 2026-09-28)

The owner's choice, 2026-09-28: "Build it" - take the timing of each speech
sound from Jarvis's voice engine instead of guessing it from the sound.

### In plain words

Before Kokoro makes any sound, it decides how long each speech sound will
last (an "m", an "oo", the pause after a comma). sherpa-onnx, the
program that runs Kokoro on the PC, never hands those numbers out. So the
PC keeps a small copy of just the part of Kokoro that decides the lengths
(`model.durations.onnx`, made once by a one-line step,
backend/README.md "Mouths that match the words"), asks it the same question
sherpa-onnx asks, and turns the answer into mouth shapes. They travel in
the WAV `/api/voice/say` already returns, as one extra block after the
sound (a RIFF chunk called `jmth`, docs/JARVIS-API.md section 5). Nothing
leaves the PC; the voice model itself is never changed.

It can only ever add: no one-time step yet, a custom (recorded) voice, the
"One moment." clip, or any doubt about a sentence - and that WAV simply has
no block, and the apps do exactly what the sections above describe.

### How it works

`backend/jarvis_mouth.py`, called from `jarvis_speech.kokoro_speak` for
`say()` only:

1. **Words to speech sounds**, exactly as sherpa-onnx makes them for
   Kokoro v0.19 (Kokoro v1.0 reads the text slightly differently first -
   see "Kokoro v1.0: the same exact timing" below): espeak-ng (the espeak-ng library the `espeakng-loader`
   package ships - it has Windows builds; piper-phonemize, which sherpa-onnx
   uses inside, has none), reading the Kokoro download's own
   `espeak-ng-data` folder, clause by clause, the way piper-phonemize
   calls it. One call piper-phonemize relies on (how a clause ended: ".",
   "?", ",", a paragraph...) exists only in its own espeak-ng build, so the
   ending is read from the text espeak-ng consumed (`_clause_end`).
   **Measured:** equal to piper-phonemize on 48,416 of 48,424 lines (every
   line of this repository's docs, plus the 36 test sentences below - all
   36 equal), with piper-phonemize not loaded; the 8 that differ are code
   fragments (`".."`, a full-width `？`, a colon after a closing quote).
   Any difference changes a sentence's length, which step 4 catches.
2. **Sounds to Kokoro's token numbers** (`tokens.txt`), split and padded as
   sherpa-onnx does (a 0 at each end, a space after every ".", at most 510
   a piece).
3. **The durations model** (onnxruntime, one thread; for v1.0 cut from its
   own second output instead, below) with the same voice
   style row and speed: frames per sound, 1 frame = 600 samples = 25 ms.
   `model.durations.onnx` is Kokoro's graph walked backwards from node
   `/Cast_output_0` (Round -> Clip -> Cast, checked by the one-time step),
   56 MB from the 346 MB fp32 `model.onnx` the owner has; it has none of
   Kokoro's random-noise nodes, so its answer is always the same.
4. **The sound, and the proof.** sherpa-onnx is asked for the sound with
   its pause-shortening off (`GenerationConfig.silence_scale = 1`), one
   piece per sentence (its callback), while steps 1-3 run on a thread of
   their own. Each piece must be exactly as long as step 3 says, to the
   sample - otherwise no block. Then the pauses are shortened by
   `scale_silence`, a line-for-line copy of sherpa-onnx's own
   `GeneratedAudio::ScaleSilence` (a stretch of 0.2 s or more within
   +-0.01 keeps its first 20 %, float32 arithmetic as in C++), which also
   says where every sample went. The animal's pitch
   (`jarvis_speech.pitch_up`) then divides every time by f = 2^(semitones/12)
   - above 1 for a higher voice (shorter), below 1 for a deeper one
   (longer; since 2026-09-28 the owner may pick -3 to +4 per animal).
5. **Sounds to mouth shapes** (`build_track`, 100 frames a second, the same
   n as the apps' own analysis): each sound pulls the mouth towards its
   shape with a weight that fades before and after it (Cohen and Massaro's
   "dominance" model of coarticulation), so shapes blend instead of
   jumping. Shapes by sound (the groups adapted from HeadTTS's
   misakiToOculusViseme, MIT; the numbers are Jarvis's own, all in one
   table `K` / `_V` / `_CLASS`):
   - **m, b, p shut for their whole sound** (open forced to 0; closing over
     50 ms before, opening over 50 ms after; a sound given no time still
     shuts for 30 ms);
   - **f, v: a lip-bite** - open at most 0.1 for their sound, lips spread;
   - **"oo", "oh", "w", "sh", American "r": rounded**, starting early
     (reach 75 ms before; measured below: already 0.42-0.52 round 80 ms
     before an "oo" or "w");
   - **"ee", "i", "y", "s": spread**; open by vowel: "ah" 0.95, "eh" 0.62,
     "ee" 0.22 (times 0.82 unstressed, 0.92 secondary stress);
   - t, d, n, l, k, g: jaw a little closed, lips borrowed from neighbours;
     h and the glottal stop take their neighbours' shape;
   - pauses and punctuation: shut.
   Then `open` is scaled by the clip's own loudness per frame (the quietest
   speech opens half as far as the shape says, the loudest all the way -
   so stressed syllables open more), silence in the clip (80 ms or more
   below the gate, as above) shuts the mouth, and everything is smoothed
   lightly (12 ms each way). `level` is the same loudness channel as
   lipsync.js's (the apps take their own anyway).
6. **The block**: `v1;src=kokoro;` + `pack()` (byte for byte lipsync.js's -
   checked by running lipsync.js on the Python output), after `data`,
   padded to even length, RIFF size fixed. Every backend reader was checked
   (Python `wave`, `_read_wav`, `jarvis_voice_flow._wav_samples`).

### What was measured (dev container, 2026-09-28)

The 36 test sentences (numbers, times, "a.m.", "Dr.", "U.S.", "#58213",
"$12.99", "£10", an em dash, ellipses, questions, exclamations, quotes,
brackets, three-sentence answers, one-word answers, "Beyoncé and Björk")
in all four voices (default; red panda speaker 1, +2 semitones; pygmy owl
speaker 2, speed 0.85, +1; sea otter speaker 4, speed 1.15, +3): 144
sentences.

- **Exactness: 144 / 144.** Every sentence piece sherpa-onnx spoke was
  exactly the length the timing predicted (error 0 samples in every piece;
  nothing fell back). The sound was **byte-for-byte the same** as
  sherpa-onnx's own pause-shortened sound in 144/144 - measured with a test
  copy of Kokoro whose two random-noise nodes were given fixed seeds,
  because Kokoro's graph adds random noise (RandomNormalLike,
  RandomUniformLike), so two runs of the real model differ by a few samples
  in where each pause is cut, even in sherpa-onnx alone.
- **Time added:** the timing (steps 1-3) took a median 104 ms (p90 168,
  worst 217 ms) per sentence on one thread, against a median 1.98 s to
  make the sound (sherpa-onnx, two threads) - it runs alongside, and never
  once was it still running when the sound was ready. After the sound:
  median 9.5 ms (p90 21, worst 37 ms) for the pause-shortening, the pitch
  rise, the shapes and the WAV, for clips of 3.2 s median (10.9 s
  longest). On the owner's PC both sides scale with the processor, so the
  timing stays hidden behind the sound; loading the durations model
  (about 0.4 s here) happens once, in the background, when the voice
  loads. The one-time step took 1.8 s here.
- **Against the analysis from the sound** (the sections above), over the
  same 144 sentences - "closed" is the lowest opening in the sound under
  0.1:

| | default | panda | owl | otter |
|---|---|---|---|---|
| m, b, p shut (sound analysis / Kokoro timing) | 39/100 / **100/100** | 37/100 / **100/100** | 49/100 / **100/100** | 38/99 / **99/99** |
| t, d, n, k between vowels shut the lips (should not) | 114/189 / 18/189 | 118/224 / 17/224 | 122/214 / 34/214 | 132/216 / 22/216 |
| "r" shuts the lips (should not) | 19/36 / 5/36 | 16/41 / 7/41 | 11/30 / 6/30 | 24/48 / 8/48 |
| f, v highest opening | 0.40 / **0.10** | 0.37 / **0.10** | 0.43 / **0.10** | 0.38 / **0.10** |
| "oo", "oh", "w" mean round | 0.29 / **0.67** | 0.34 / **0.66** | 0.21 / **0.66** | 0.26 / **0.67** |
| round 80 ms before "oo"/"w" | 0.19 / 0.44 | 0.29 / 0.44 | 0.15 / 0.52 | 0.21 / 0.42 |
| "sh", "zh" mean round | 0.25 / 0.43 | 0.25 / 0.43 | 0.13 / 0.44 | 0.20 / 0.41 |
| "ee", "ih" mean wide (round) | 0.28 (0.13) / **0.54 (0.03)** | 0.33 (0.12) / 0.53 (0.03) | 0.34 (0.07) / 0.52 (0.02) | 0.34 (0.09) / 0.52 (0.03) |
| highest opening: ah / eh / ee | 0.70 0.53 0.25 / 0.68 0.47 0.24 | 0.66 0.50 0.25 / 0.69 0.46 0.23 | 0.73 0.58 0.31 / 0.72 0.47 0.22 | 0.77 0.62 0.27 / 0.68 0.45 0.23 |
| mouth open in pauses | 0.02 / 0.00 | 0.02 / 0.00 | **0.20** / 0.00 | 0.01 / 0.00 |
| biggest step in 10 ms | 0.42 / 0.27 | 0.44 / 0.27 | 0.48 / 0.27 | 0.46 / 0.27 |

  Where they differ most (the largest single-frame differences): the
  sound analysis reading **no rounding on "oo"** ("moons", "pool", "noon",
  "you", "do" - American "oo" sounds half-way to "ee", its known limit)
  where the timing knows it is /u/ and rounds (0.96); **open mouths on
  "b" and "m"** ("backup", "because", "model": 0.93 open where the lips
  are shut); **spread lips on "n" and "zh"** (0.99, hiss and nasal
  murmur read as "ee"); and rounding carried across "n", "t", "d" next to
  an "oo" (real coarticulation: the lips stay rounded through "moons").
  The openness of vowels agrees (ah > eh > ee in both). Of the 117 t, d,
  n, k and "r" the timing still shuts, 81 are where the sound itself is
  below the silence gate at that moment (the hold of a "t" or "k" is
  silent), 27 are next to an m, b or p (whose closing starts 50 ms early)
  and 9 are other quiet "l", "n" and "r" sounds.

### Correction: Kokoro's sound comes about 50 ms before its own plan

Found by the corpus tests later the same day (2026-09-28), and fixed.
Kokoro's durations say when each sound is PLANNED; the sound itself comes
about 50-60 ms earlier. Measured on raw Kokoro audio (no pause shortening,
no pitch change): hiss 60 ms early at speed 1.0 and 0.8 alike - a fixed
two Kokoro frames, not a share of each sound - and m/b/p energy troughs
42-49 ms early over 1,130 clips. So the timed mouth was showing about
10 ms LATE instead of the intended ~50 ms early.

- **The fix:** `jarvis_mouth.SOUND_LEAD` (2 frames, 50 ms) moves every
  sound earlier in `finish()`. Piece edges and the sample-exact length
  check are unchanged. After it, on the same clips: hiss -20 ms, speech
  onset -10 ms, loudness-vs-mouth cross-correlation +5 to +10 ms,
  troughs -5 ms (default voice). The owl's troughs are still about
  -45 ms, so its lead may be a little larger; one value is used for all
  voices rather than fitting a small sample.
- **The table above is biased by this.** It scored the sound analysis at
  the plan's moments, 50 ms after the sounds really happen. Scored where
  the sounds actually are (the sound-analysis tester, 738 Kokoro clips),
  the sound analysis does much better than the table says - m, b, p shut
  509/548 (default), 68/90 (panda), 526/546 (owl), 75/101 (otter) against
  the timing's 441/548, 74/90, 430/546, 85/101 at the time (before the
  fix); and the owl's "0.20 open in pauses" is really 0.02. The timing is
  still clearly better at "oo" rounding (about 0.6 against 0.18-0.37),
  and at not shutting on t, d, n, k and "r".
- **The corpus test** (`backend/test_mouth_corpus.py`, 25 checks, no model
  needed; 28 with `JARVIS_KOKORO_DIR`): 3,286 lines built to break things
  - every verb form, the 720 Harvard sentences, minimal pairs, every sound
  at the start, middle and end of a word, numbers, dates, money, names,
  emoji, web addresses, control characters, a 20,000-character word -
  timed in all four voices (13,144 tracks: no errors, m/b/p shut and f/v
  bitten 100%), and 2,631 clips spoken by the real model: a mouth made for
  99.24% (the rest fall back safely to no mouth, sound unchanged), the
  sound byte-identical with and without the mouth in 504/504, the mouth
  open in 0 of 13,224 silent frames. Six text-reading bugs it found are
  fixed (punctuation with no letter, NUL, U+FFFD, which characters count
  as digits, other English accents' vowels, and memory on a 10-minute
  answer: ~1 GB down to 256 MB).
- **Left as they are** (each would change `test_mouth.py`'s committed
  tracks): "w" before "ee" rounds weakly (median 0.36); no early rounding
  straight after a pause (the silence gate); the biggest one-frame step is
  0.326 at an f/v release, just over the 0.3 the tests allow elsewhere.

### Kokoro v1.0: the same exact timing (2026-09-29)

The owner's decision, 2026-09-29, when asked about the gap the v1.0 upgrade
left ("the mouths use the analysed-from-sound fallback"): **"Build exact
timing."** Built the same day. This is what was found and what was built.

**In plain words.** The new voice pack (Kokoro v1.0) also works out how long
each speech sound lasts before it speaks - and, unlike the old pack, its
model file already carries those numbers as a second answer next to the
sound. So the one-time step (`py -3 .\jarvis_mouth.py --prepare`, the same
one line as before) cuts out just that part into a small file
(`model.durations.onnx`, 56 MB, beside `model.onnx`) exactly as it did for
the old pack, and the animals' mouths follow Kokoro's own timing again.
The voice pack itself is only read. With no such file, or a file that does
not belong to the pack that is installed, nothing changes: the apps work the
mouth out from the sound, as before.

**What the v1.0 model has (read off the real file, 2026-09-29, the pinned
`kokoro-multi-lang-v1_0` download, `model.onnx` 325,560,556 bytes):**

- Two declared outputs: `audio` (float) and a second one, int64, called
  `onnx::Shape_3411` - an auto-made name, so it is never looked for by name.
  It is `Squeeze( Cast_int64( Clip( Round( ReduceSum( Sigmoid( duration_proj )) / speed ))))`
  - the same Round -> Clip -> Cast chain the old pack's `/Cast_output_0`
  had, one Squeeze later. Inputs are the same three: `tokens`, `style`,
  `speed`. The old pack's name `/Cast_output_0` also exists in v1.0 but is
  something else (a Cast of a ReduceMax), which is why the old one-time step
  refused v1.0: it followed the name into the wrong chain.
- **It is the lengths, measured:** for "Hello, my name is Jarvis." the
  output sums to 94 frames = 94 x 600 = 56,400 samples, and sherpa-onnx's
  sound for that sentence is 56,400 samples. The slice (2,026 nodes, 45
  weights, no noise nodes) gave exactly the model's own second output in
  every test input, and takes 30-80 ms a sentence on one thread.
- **What differs is the reading of the words**, not the timing: sherpa-onnx
  reads v1.0 text with its own front end (`KokoroMultiLangLexicon`, read in
  sherpa-onnx v1.13.8's source), which - with a `lang` and no lexicon, as
  Jarvis runs it - (1) changes every ":" to ",", every wide Chinese mark to
  its plain twin and every run of white space to one space (so a blank line
  no longer ends a sentence), (2) sends the whole text to espeak-ng as
  before, but (3) **joins a short sentence (10 sounds or fewer) onto the
  one before it** when the two stay under 50 tokens (or the short one is
  under 3 sounds), and (4) reads Chinese from the pack's own lexicon.
  `jarvis_mouth.multilang_pieces()` copies (1)-(3); a text with Chinese gets
  no mouth block (the length check would refuse it anyway). British voices
  are read with `en-gb-x-rp` (`jarvis_kokoro.accent_lang`) - handed both to
  the timing and to sherpa-onnx as the per-call language, as `_kokoro_generate`
  does.
- **The pin.** The one-time step makes a v1.0 copy only from the one file
  `jarvis_kokoro.V1_MODEL` names (size and SHA-256, read off the pinned
  download), and the copy records that fingerprint; `_Model` refuses a copy
  that does not carry it, and `ready()` reports "made from a different voice
  model" in plain words (an old copy left beside a new pack, or the other way
  round, is never paired). It also runs the copy against the full model on
  three inputs and keeps it only if the answers are equal.
- **The sound's lead.** Kokoro's sound comes ahead of its plan (above,
  `SOUND_LEAD`, 50 ms). Re-measured for v1.0 with the same method on both
  packs - slide the planned "s / sh / f / th / z / zh" stretches against the
  4-10 kHz energy of the raw sound and take the best-matching shift, per
  sentence: **v0.19 -70 ms, v1.0 -70 ms** (median over 102 sentence pieces
  each, three voices each; quarter to three-quarter range -89 to -65 and
  -80 to -60). The same, so the same 50 ms is used for both.

**Checked with the real v1.0 model** (dev container, sherpa-onnx 1.13.8, the
pinned pack, 2026-09-29):

- **532 of 532** English sentences got their mouth - every piece sherpa-onnx
  spoke was exactly as long as the timing said, to the sample: 268 texts
  (all 239 lines of the corpus fixture `backend/fixtures/mouth_corpus`, its
  12 awkward "speak" texts and 17 more: "Ok", "?", ".", "One: two: three.",
  runs of spaces, a blank line, a colon, ellipses, "10:30 a.m.", ten short
  sentences in a row), each in an American voice (`af_heart`) and a British
  one (`bm_george`, `en-gb-x-rp`). The 4 that got no mouth are the two texts
  with Chinese characters, in both accents, by design.
- Also exact, in `test_mouth.py` with `JARVIS_KOKORO_V1_DIR` (70 of 70): 5
  voices x 14 texts - a deeper and a higher animal pitch, a fast and a slow
  pace, two British voices; four of the texts are bare punctuation (".",
  "(", "?!", "..."), which sherpa-onnx speaks on its own. Also exact, run by
  hand: a 764-character sentence with no full stop (split at
  510), a 3,149-character answer of 40 sentences, 150 short sentences in a
  row, and a one-character sentence after a very long one.
- **The old pack is unchanged:** the same code run on the real v0.19 pack
  gave a `model.durations.onnx` **byte-identical** to the one the old code
  made, the same timing for 36 sentence/voice pairs, and a mouth for all 36.
- **Time:** the one-time step took 9.5 s here (it reads the 326 MB model,
  fingerprints it and checks the copy against it). Timing a sentence is
  30-80 ms on one thread against about 1.4 s for the sound.

**Not checked, said plainly:** nothing was run on Windows or the owner's PC
(see "Limits"); nobody has looked at a v1.0 animal talking - only the
numbers above; on Windows sherpa-onnx's front end converts text to wide
characters, and whether an emoji or other rare character is handled the
same there was not seen - any difference is caught by the same length check
and gives that sentence no mouth, never a wrong one.

### Limits, said plainly

- **Not run on Windows or on the owner's PC.** The Windows espeakng-loader
  wheel was downloaded and checked: its `espeak-ng.dll` exports the three
  calls used and needs the Microsoft C++ runtime (`MSVCP140.dll`), which
  onnxruntime brings into the process first. If it cannot load, status
  says so and nothing else changes.
- **Kokoro v0.19 and v1.0** (v1.0 since 2026-09-29, above): each needs its
  own one-time step (`--prepare`) after the pack is installed - the copy
  made for one pack is refused beside the other (`ready()` says so). Until
  then, and for any sentence in doubt, the mouth is analysed from the sound.
  A pack other than these two (a v1.1, say) is refused by the step.
- **Only the built-in Kokoro voice** (the model sherpa-onnx speaks here).
  Custom voices and the "One moment." clip keep the sound
  analysis (the "One moment." clip is made by jarvis_voice_flow.py, which
  was not changed).
- **The timing is Kokoro's plan, not a measurement of the lips.** The
  shapes per sound are a model (tuned by eye and the numbers above), not
  motion capture.
- The apps show the mouth 50 ms early (LEAD_S) on top of the timing's own
  anticipation, as for the sound analysis.

### Tests

`backend/test_mouth.py` (see "Tests" above); with `JARVIS_KOKORO_DIR` it
also runs the real model in all four voices, and with
`JARVIS_KOKORO_V1_DIR` (an unpacked `kokoro-multi-lang-v1_0` folder) the same
on v1.0 - plus, with no model at all, the v1.0 front end's pieces, the pin,
and the one-time step on a toy model shaped like v1.0's graph (a decoy
`/Cast_output_0` and the lengths as a declared second output).
`backend/test_kokoro.py` checks `kokoro_speak` asks for the mouth on either
pack. The scratch scripts that made
the numbers above (the 144-sentence exactness run with the seeded copy, the
comparison, the 48,424-line espeak check, and for v1.0 the 536-run stress
test and the lead measurement) were run in the dev container and
are not committed.

## Each animal's own voice (2026-09-28)

The owner can now pick, for each animal, any of the eleven built-in voices,
a pitch from 3 steps deeper to 4 steps higher (half steps) and a pace
(`JARVIS-API.md` section 15). Nothing about the mouths had to be added for
it: the timing already follows whatever voice number and speed Kokoro is
asked for, and every time is divided by the pitch factor f =
2^(semitones/12). What changed is that f may now be **below 1** (a deeper
voice is played slower, so it is longer): `jarvis_speech.pitch_up` and
`jarvis_mouth.speak` both take a negative number, and Kokoro is asked for
speed / f - faster - so the pace still comes out as chosen.

**Checked with the real Kokoro model** (dev container, one fixed
three-piece answer, each combination spoken end to end through
`jarvis_speech.say()`): 11 combinations - three per animal, every pace,
pitches -3, -2, -1.5, -1, -0.5, 0, +2.5 and +4, voices 0, 3, 5, 6, 7, 8,
9 and 10, and the owner's own speed at Faster and Slower on top. In
**11/11** the `jmth` block was made, every piece sherpa-onnx spoke was
exactly as long as the timing said (0 samples out), the timing's end and
the final sound's end agreed within **0.94 samples** at worst, and the
track had exactly one frame per 10 ms of the final sound. With the test
copy of Kokoro whose random-noise nodes are seeded (see above), the sound
with the mouth was **the same sound, sample for sample, as the sound
without it** in 10 of the 11. The eleventh (voice 7, pitch 0, Faster)
differed in that long run, but run again on its own - twice, and beside
voice 0 and a +0.5 pitch - it was identical every time (0 samples
different). Pitch 0 is the one case this change does not touch (no pitch
factor at all), so the likeliest cause is the two seeded copies falling out
of step in the long run, not the new code; it is written down rather than
explained away. With the timing made impossible (a missing
durations model) the answer was still spoken, with no block - the
audio-only fallback is unchanged. `test_mouth.py` now also checks
`finish()` at +4, -1.5 and -3, and its real-model run (with
`JARVIS_KOKORO_DIR`) includes the deepest voice at a quick pace.

