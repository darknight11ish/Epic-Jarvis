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

- It works for Jarvis's normal voice, the three animal voices (which are
  pitched up), and recorded custom voices, because it only looks at the
  sound itself.
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
        JarvisLipSync.sample(track, tSeconds, out?) -> { level, open, wide, round }
            reads the track at tSeconds + LEAD_S, linear between frames;
            all 0 before the start / after the end; null track -> null
        JarvisLipSync.fromWav(ArrayBuffer | Uint8Array) -> { samples, sampleRate }
            16-bit PCM, mono or stereo (averaged); anything else -> no samples
        JarvisLipSync.pack(track) -> "100:<base64>"   (4 bytes a frame)
        JarvisLipSync.unpack(string) -> track
Kotlin  LipSync.FPS, LipSync.LEAD_S, LipSync.Track(fps, level, open, wide, round) { n }
        LipSync.analyse(pcm: ShortArray, sampleRate) / analyse(samples: FloatArray, sampleRate)
        LipSync.sample(track?, tSeconds, out: FloatArray): Boolean
            out[0..3] = level, open, wide, round; false (and zeros) outside the clip
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
  Kokoro's voice, so both get the small "teeth" spread.
- **American "oo" is fronted** ("knew", "you"): its second formant sits
  between "ee" and "oh". Those vowels come out less round, which is roughly
  what the lips do too.
- **Custom (recorded) voices were not measured** - only Kokoro. The
  per-clip normalisation should carry over; it is untested.
- **Bluetooth delay** (see "Why 50 ms").
- The phone's own fallback voice (Android's text-to-speech, used when the
  PC's voice is not available) never gives the app the whole clip, so it
  cannot use this analysis; `SpeechClock.kt` estimates the opening from
  loudness only.

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

To change the analysis: change `lipsync.js` and `LipSync.kt` the same way,
run `python3 tools/gen_lipsync.py`, then `node jarvis-desktop/tests/lipsync.mjs`.
If a quality check fails, the change made the mouths worse on Jarvis's real
voice - that is the point of those checks.
