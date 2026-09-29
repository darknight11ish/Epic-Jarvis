# Animal voice casting, condensed (nothing listened to)
Mascot branch head 96707dc: no owl/otter code pushed; CRITTERS.md says "(not started)".
All Kokoro kokoro-en-v0_19 (11 voices, Apache weights; trained on permissive + synthetic audio from closed models per model card). Pitch via slow-then-resample (no dep), keep 0.94-1.08x. Pace multiplies owner's speed setting.
Red panda: Bella (1), pitch 1.04, pace 0.97; listening soft rising two-note chirp; thinking "mm" in Bella.
Pygmy owl: Emma (7, British), pitch 1.06, pace 1.05, longer pause after 1st sentence; listening soft "toot", thinking two toots.
Sea otter: Michael (6), pitch 0.97, pace 0.94; listening tiny squeak; thinking two pebble taps.
Classic faces: owner's voice unchanged, no sounds.
Habits = pace/pitch/pauses only, no catchphrases. Off on approval cards, errors, crisis, Plain manner. No sound for approval or asleep. Sounds procedurally generated (licence-free); reuse "I heard you" (listening, off by default) and "One moment" (thinking) switches.
Caveat: phone fallback Speaker.speakOnDevice uses Android TTS - check vs "phone never makes speech on its own" (CLAUDE.md says client must not do STT; TTS fallback not ruled - verify).
Mouth: amplitude only (critter-pose.js P.mouth = clamp(amp*1.35,0,1); amp smoothed 40ms rise/120ms fall, floor 0.18). DESKTOP NOT IN SYNC: main.js playClip->attachSpeechSource measures real voice but level never reaches faces.html (setSpeechLevel no caller; jarvis-hud-face message carries state+appearance only) -> fake 4.2 syll/s rhythm. Fix = ui-audit-2026-09-26/alive.md item 1 (post level ~30 Hz). Phone: real level from Speaker.kt:276 but measured at hand-off not playback -> mouth early (unmeasured); fix by play position.
Face->voice: recommend "offer once" per face ("The panda has its own voice. Use it?" Use it / Keep my voice); never auto.
For mascot session: keep amp as single mouth input for all animals; add optional "wide vs round" second mouth number (defaults to amp) in both pose files + golden; per-animal rise/fall; voice hint (speaker, pitch, pace) on each animal in jarvis-visual-spec.json; never play sounds from face code; reword CRITTERS.md "mouth opens and closes with Jarvis's voice" (not true on desktop yet).
Listen line (untested): posts /api/voice/voices/speaker then /api/voice/say for voices 1,4,6,7,9 -> Desktop WAVs, resets to 0.
