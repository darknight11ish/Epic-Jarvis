# Jarvis Live: feature audit - bugs, both apps, fit (studio, 2026-09-28)

Line numbers from deff2f5a. No rule-breaking problem. Parity clean;
live-cases.json in step; test_live 246, test_voice_strict 265,
test_private_aloud 97, test_reach 133, test_asks_first 174, test_wellbeing
135, test_chat_log 177, test_auto_learn 350; jarvis-live.mjs 24; clippy
clean. (Voice tests need numpy - CI installs it.)

## Bugs a fit pass finds

1. **Side talk shows as raw "[not for me]" in History on both apps.**
   LIVE-DESIGN.md:78-83, :390-393 say "(not for Jarvis)"; the backend
   returns `side_talk` (`jarvis_agent.py:5205`) but nothing reads it; only
   the Live screen/bar converts it (`ChatSession.kt:698`,
   `LiveScreen.kt:199`, `main.js` `liveSideTalk`). Map it in both History
   views, or store "(not for Jarvis)".
2. **A card already waiting is handled differently**: the desktop closes the
   mic for any card open in the bar (`main.js:1445, :4728`); the phone's
   LiveService never passes `cardShown` (`LiveService.kt:175, :315`).
   JARVIS-API §63.4 says close it while a card is on screen. (Same as the
   bug hunt's #3.)
3. **Talk button during Live**: the desktop refuses push-to-talk with
   "automatic listening is already using the microphone" (confusing); the
   phone does not block `VoiceSession.begin()`, and LiveService does not
   step aside for `Phase.CAPTURING` - two recorders possible. Make both the
   same, with Live's own words.

## Both apps

1. No "more time" button on the desktop (phone has "20 more minutes",
   `LiveScreen.kt:169`; `live_act extend` exists in `live.rs`).
2. The "I heard you" sound plays in Live on the phone only
   (`JarvisRuntime.kt:3741`); on the desktop `liveHeard` returns at
   `main.js:3891` before `playHeardSound` (`:3918`) and `liveAsk` (`:4595`)
   never plays it. Call `playHeardSound()` in `liveAsk` (under its switch).
3. The move offer says "your desktop" (`jarvis_live.py:272`) - say "your PC".
4. Not built and not noted: the phone app-icon shortcut
   (LIVE-DESIGN.md:228) and a Live mark on the tray icon (:241).

## Fit

1. "Interrupting Jarvis in Live" is in the wrong place on both apps: the
   desktop's sits inside `voice-body` (`settings.html:557/605`, hidden until
   the PC answers though it is local) above a footer that doesn't apply
   (`:612`); the existing "Interrupting Jarvis" switch (`:649`) is outside
   `voice-body` on purpose. Phone: `VoiceCheckScreen.kt:380` above the same
   footer (`:382`); its barge-in switch is on `ReadinessScreen.kt:671`. Move
   it next to the existing switch. **Owner's call:** keep two near-duplicate
   switches (the old one doesn't apply in Live) or merge them.
2. "What asks first" does not list Live (nor Focus, "Watch with me", the
   talk button). **Owner's call:** a fixed row "Start Jarvis Live - Does it
   without asking".
3. Side-talk turns are kept in chat history - listed as an owner answer in
   LIVE-DESIGN.md:81-83 but it was the builder's choice. **Owner's call.**

## Docs that don't match the code

- LIVE-DESIGN.md:106, :394-395 say no Live turn feeds "suggest the bigger
  model" - ordinary Live turns do count struggles (`jarvis_agent.py:5179`);
  only crisis and side-talk turns are left out. Fix the doc.
- JARVIS-API §16's voice status / enroll contract (~2207, 2285-2298, 2384)
  doesn't list `hands_free_live` (only §63.5 does).
- JARVIS-TODAY.md:144-150 says Live is "being built"; :59 says built.
- LIVE-DESIGN.md:3 still names the `studio-live` branch.
