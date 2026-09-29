# Jarvis Live: bug hunt (studio, 2026-09-28)

Line numbers are from merge deff2f5a. `test_live.py` 246/246; Windows-target
clippy clean; phone code read (nothing found that should fail to compile).
No finding breaks one of the five rules; no path turns a clip into words
before the owner check; no card pause fails open.

1. **Phone: interrupting Jarvis by voice throws away what the owner said**
   (medium-high). `LiveService.kt:271` checks `stillOpen(overReply)` every
   ~0.4 s; `:311-314` returns false once `speaking != overReply`;
   `VoiceSession.kt:384-397` `stopSpeaking()`; `:1006` phase -> OFF once
   speech drains. So `window()` returns null and `:306` (meant to send it)
   is never reached; `close()` clears the ring (`:165`); the next clip
   starts ~3 s in with no pre-roll. Fix: in `stillOpen`, don't end an
   over-reply window once `voice.replyStopped()`; don't clear the ring when
   only the audio source changes.
2. **Phone: one failed transcription stops the mic while Live still shows
   on** (high). `LiveRules.kt:244` `h.live == "off" || !h.available -> END`;
   `JarvisRuntime.kt:3770-3776`; `jarvis_speech.py:2052-2065` returns
   `available=False` for "no STT model" / "transcription failed" while the
   session stays on; the watcher (`JarvisRuntime.kt:3849-3862`) never
   restarts it. Fix: `available=false` with `live` empty or "on" = keep
   listening (show the reason); END only on `live == "off"`/`"ended"`.
3. **Phone: a card already on screen does not close the mic** (high).
   `LiveService.kt:175-180, 315-320` never pass `cardShown`/`appLocked` to
   `LiveRules.listen`; the tests check an argument the service never
   supplies. Fix: pass `cardShown = JarvisRuntime.pending.value.isNotEmpty()`.
4. **Phone: Unmute during a detected call is undone at once** (high).
   `LiveRules.kt:374-382`; `JarvisRuntime.kt:3724-3735` (`:3727` resets
   `liveCallAsked`). A stuck IN_COMMUNICATION mode means never unmuted. The
   desktop fixed this in 774ba516 (`MIC_OVERRIDDEN`). Fix: the same
   override - no re-mute for "call" until the mode has been seen out of
   call once.
5. **Backend: everyday confirmations end Live** (high, ran it).
   `jarvis_live.py:365-374` END_PHRASES has "that's it", "i'm done", "all
   done"; `:383-384` `_LEAD` strips "right", "perfect", "great", "so",
   "well", "okay". "Right, that's it.", "Okay, I'm done." -> end. Fix: drop
   bare "that's it" / "i'm done" / "all done", or require a Live word
   ("that's it for now", "I'm done with Live").
6. **Desktop: "Hey Jarvis" listening left dead, or switched on unasked,
   around a Live start** (high on code). `voice.rs:1203-1215`
   `open_for_live` closes the wake listener and sets `WAKE_WAS_ON` before
   the Live mic opens: (a) a failed `open_live_listener` never reopens it;
   (b) a double click (`toggleLive`, `main.js:4503`, no busy guard; tray
   too) calls it twice, the second records the Live listener as a wake one,
   and `close_for_live` (`voice.rs:1251`) turns wake listening on though
   the owner had it off. Fix: set `WAKE_WAS_ON` only if `!LIVE_MODE`;
   restore on the error path; a busy flag on `toggleLive` and the tray.
7. **Phone: "Hey Jarvis" silently ignored while Live is on the PC** (high).
   `JarvisRuntime.kt:3777` sets `_liveMove`, read only by
   `LiveScreen.kt:77/176-183`; `jarvis_speech.py:1747-1751` promises never
   silently dropped. Fix: a Home notice or local-only notification.
8. **Backend: the PC-slept check can be defeated by a status read** (high,
   low impact). `jarvis_live.py:770` checks the gap only on the loop's tick;
   `:781` updates `last_tick` on any tick (`handle_get` `:1144-1146`,
   `accepts()` `:851`). Muted: still on after sleep; unmuted: ends `quiet`
   and resumable instead of `slept`. Fix: a separate `last_loop_tick`, or
   check the gap on every tick.
9. **Desktop: the shared "listen" rule is tested but not what runs** (low).
   `live-rules.js:131` `liveListen` only used by the test; the app uses
   Rust `mic_held` (`live.rs:147-155`) / `live_held` (`voice.rs:1130`),
   neither has `answering -> listen:false` for "Interrupt by voice"; a short
   "mm-hm" over an answer makes `sayAside("Say a bit more...")` play on top
   (`main.js:4648-4652`). Fix: in voice.rs drop a cut Live clip while an
   answer plays unless barge-in said it was the owner (as the phone does,
   `LiveService.kt:306`).

Possible, not proven: notification End's `liveStop` in the service scope
cancelled by `onDestroy` (`LiveService.kt:106-110, :135`) - launch on the
runtime's scope; the talk button and phone Live both recording at once.
