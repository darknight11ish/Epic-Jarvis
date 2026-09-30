# Report 09 (audit), agent ac8bc0ba, 2026-09-29T09:55Z

> **What it was asked** (first 600 characters of the task): Repo /home/user/Epic-Jarvis, branch ccr-a9b557ac-cpnbwx (= origin/main 1748ac33 plus small fixes). Do NOT edit files. PR #30 just landed two features on BOTH apps. Bug-hunt the client code: (1) INBOX TIDY: the desktop's Undo strip in the Jarvis bar (jarvis-desktop/src: grep -ril 'inbox' src src-tauri/src), and the phone's Undo strip on Home (jarvis-client: grep -ril 'inbox\|tidy'); the card must be decided by TAP only (never voice), risky approval (Windows Hello on PC / screen lock or fingerprint on phone), Undo one tap for 10 minutes, held on a stale event stream (rule 4) except Undo; App loc

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Bug hunt on the client side of PR #30, inbox tidy and Kokoro "Hear it" plus voice names. I found one real but low-harm bug, plus two small inconsistencies. Nothing serious. Nothing Android compiles here, so every Kotlin claim is read, not run. I did not edit files.

## Proven bugs

### 1. LOW (phone): "Hear it" and an animal's "Try it" can play at the same time, and the microphone-guard flag is then wrong
- **Where:**
  - `jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/VoicesScreen.kt`, `SpeakerPlate` (~line 575) keeps its own `hearing` state.
  - The animal rows keep a separate `trying` state (~line 799, buttons enabled at ~883).
  - `voice/VoiceSession.kt:809-817` (`soundFromPc`) only refuses via `voiceBusy()`, which is `_phase != OFF || job running || liveOn()`. It does not check `tryPlaying`.
- **Trigger:**
  1. Tap "Hear it" on a voice. While it plays (a few seconds), tap "Try it" on an animal row. Its button is enabled because `trying == null`.
  2. `voiceBusy()` is false, so the second clip is fetched and `playTry` runs.
  3. `playTry` sets `tryCut=false`, calls `speaker.arm()` and then `speaker.play(wav)`. That opens a second `AudioTrack` on top of the first.
  4. `Speaker.track` is a single field. It is overwritten, so a later `stop()` only pauses the newest track.
  5. When the first clip ends, its `finally` sets `tryPlaying=false` while the second is still sounding. A "Hey Jarvis" or a talk-button press during that second clip no longer cuts it (`turnStarting`, VoiceSession.kt:884-889). The microphone can hear the sample.
- **What the owner sees:** two voices talking over each other, and the sample not stopping when they start a question.
- **Server side:** the PC's `_TRY_LOCK` (`jarvis_voices.py:620`) only blocks overlapping requests while it is synthesising. It does not cover overlapping playback.
- **Desktop:** it has no such overlap. `playFromPc` calls `stopTry()` first (`voice-panel.js:1414`), and the PC refuses simultaneous requests with 429, so I retracted an earlier suspicion there.
- **Fix:** in `soundFromPc` refuse with the busy words when `tryPlaying` is already true. Or have `playTry` call `speaker.stop()` first and make `tryPlaying` a counter.

### 2. LOW (phone): a "Hear it" sample keeps playing after the owner leaves the Voices screen
- **Where:** `VoicesScreen.kt:127-133`. The `DisposableEffect` only stops recording (`stopFlag`), clears the clip and calls `onClearPicked`. Nothing stops playback.
- **Why the coroutine cancel does not help:** `Speaker.play` (`audio/Speaker.kt:364`) runs the `out.write` loop inside `withContext(IO)` with no `ensureActive()`. That loop only checks the `cancelled` flag, and nothing sets it. Cancelling the plate's scope therefore does not interrupt the write loop. It only takes effect at `drain`'s `delay`.
- **What the owner sees:** the sample runs to its end (a few seconds) after they have navigated away. The `AudioTrack` is released correctly in `finally`, so there is no leak.
- **Fix:** call `JarvisRuntime`/`voice.speaker.stop()` (or `turnStarting`-style cut) from that `onDispose`.

### 3. LOW (phone): an inbox-status 503 wipes an open Undo strip
- **Where:** `net/InboxTidy.kt` `missing(reply)` returns true for 404, 501 and 503. `JarvisRuntime.refreshInboxTidy` (~6309-6320) then sets `_inboxTidy = null`.
- **Trigger:** the backend's GET handler (`jarvis_inbox_tidy.py`, the `except Exception` in the `install()` `do_GET`) answers 503 `{"available": false, ...}` on an internal error. A single transient failure removes the strip while up to 10 minutes of Undo remain, until the next successful 20-second poll.
- **Desktop:** it does not do this. `brain/inbox_tidy.rs::read_answer` treats only 404-without-`ok` and 501 as missing, and keeps the held status on other errors.
- **Fix:** in the status read, treat only 404 and 501 as missing (keep 503 for the undo-reply path, where `ok:false` is checked first anyway).

## Checked, nothing found

### Inbox tidy
- **Desktop tests:** `tests/hud.mjs` passed ("all passed"), so the bar loads cleanly. `tests/inbox-tidy.mjs` passed all checks.
- **Declaration order:** `let inboxTidyView` is at `main.js:699`, before its first uses (708-716, 783, 2532). No start-up bug.
- **Decided by tap only:**
  - `email-sending.js` `isEmailCard` includes `tidy_inbox`, so the widget's one-line Approve is not offered for it.
  - `email_sending.rs` has the same rule.
  - The backend gate risk entry is "yes"/"outbound", so the phone item is not swipeable (`swipeOk` comes from the server).
- **Stale event stream (rule 4):**
  - Desktop: `inbox_tidy_undo` refuses when the link is stale or the words are hidden (`inbox_tidy.rs`), and the button is disabled by `stripFor`.
  - Phone: `inboxTidyUndo` checks `actionBlocker()` and `privateListsHidden`.
  - Status reads are never held, which is correct.
- **App lock:** Rust `redact()` strips the count, action and words when locked or private-hidden. The phone builds the strip with `locked = privateHidden`. Both apps show only the "hidden" line.
- **Wording and contract:** the seconds-left ageing and ceil-minute logic in `inbox-tidy.js` and `InboxTidy.kt` match. The two fixture copies are byte-identical, and `gen_inbox_tidy_cases.py --check` says they match the producer.
- **Markup and CSS:** text is set via `textContent`. The `[hidden]` CSS is overridden correctly (`style.css:2536, 2552`).
- **Header:** the desktop Rust uses `jarvis_headers`, and the phone's `inboxTidyCall` uses `authed()`. No token logging seen.
- **Parity:** `tools/check_parity.py` reports no undecided drift.

### Kokoro voices by name
- **Saved choice is a name:**
  - Neither client stores a voice number. Both show whatever `choice` and `choices` (ids as strings) the PC sends.
  - The stale-number migration (`LEGACY_NAME`) lives in the backend `jarvis_kokoro.py`, not in the clients.
  - The Rust `speaker_name` only accepts `^[a-z][a-z][a-z0-9_]{0,30}$`.
- **Sky and Adam never offered:** the client lists show only what the backend `offered()` returns. `af_sky` and `am_adam` are excluded from the picks. They appear only as "(your current choice)" for an owner who already chose one, and `NEVER_FOR_ANIMALS` blocks them for animals. That is backend design, and neither client hard-codes them.
- **Animal voices:** the sea otter is `af_sarah` and the robot is `bf_emma` (`jarvis_voices.py:753-758`). The one-time animal-voice question comes from the PC's `face_voice.offer` and is shown with `textContent`.
- **"Hear it" behaviour:**
  - Desktop: a button on every voice, beside the radio rather than inside it, so it changes nothing. It sends `hear_voice_sample` with the voice name only. Rust refuses when App lock is on, capture is busy, or Live is on. There is no card and no stale hold, which is correct because it changes nothing.
  - Phone: `SpeakerPlate` has a "Hear it" button per row, sends `sampleBody(voice)` with no words, and is not stale-held.
- **Playback lifecycle:** the phone `Speaker.play` releases the track, abandons focus and clears the level in `finally`. The desktop stops the sample on `face-voice`, capture events, "stop-everything" and link-activity changes. `stopTry` pauses the `Audio`.
- **Headers:** the phone `voiceSound` uses `authed()`, and the desktop `sound_from_pc` uses `jarvis_headers`.
- **Tests:** `tests/custom-voices.mjs` passed. I did not run the phone's Kotlin tests or `gen_phone_voice_cases.py --check` (its Python crashes on a broken `cryptography` install in this container).

## Housekeeping
Running `tests/hud.mjs` rewrote tracked screenshot PNGs under `jarvis-desktop/tests/shots/`. I restored them with `git checkout -- jarvis-desktop/tests/shots`, so the working tree is clean.

## Files
- `/home/user/Epic-Jarvis/jarvis-client/app/src/main/java/com/jarvis/client/voice/VoiceSession.kt`
- `/home/user/Epic-Jarvis/jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/VoicesScreen.kt`
- `/home/user/Epic-Jarvis/jarvis-client/app/src/main/java/com/jarvis/client/audio/Speaker.kt`
- `/home/user/Epic-Jarvis/jarvis-client/app/src/main/java/com/jarvis/client/net/InboxTidy.kt`
- `/home/user/Epic-Jarvis/jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt`
