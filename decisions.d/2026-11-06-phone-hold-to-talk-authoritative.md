- **2026-11-06 — Holding the talk button is authoritative: the pause-based end is suspended while the finger is down:**
  The owner reported on 2026-11-06 that holding the mic button "keeps cutting
  me off and acting like I took my finger off of the mic button even when I'm
  still speaking sometimes". The talk button is tap-to-talk OR hold-to-talk,
  and its end was decided in two places that never spoke: `ui/parts/VoicePress.kt`
  decided hold-versus-tap only when the finger lifted, and `voice/VoiceSession.kt`
  ended the clip the moment the pause rule fired - the on-phone Smart Turn model
  answering "finished", or `TurnEnd.MAX_PAUSE` (two seconds) of quiet. That is
  exactly what a tap needs, because nothing else would end it, and exactly wrong
  for a hold, where a mid-sentence pause is the owner thinking, not finishing.
  The rule now: **a held talk button is authoritative.** The button reports the
  hold about 400 ms into the press and before the finger lifts
  (`VoiceButton`'s `onHoldStarted`, through `HomeActions` to
  `VoiceSession.holdStarted()`), and while that flag is set and the finger has
  not been released, neither a pause nor the Smart Turn ask may end the capture;
  only the release sends. The decision is one pure, JVM-tested function
  (`voice/HoldEndRule.kt`) so the five cases - held/pause, held/ask, released,
  tap/pause, tap/ask - are proved off-device. Tap-to-talk keeps its pause
  auto-send unchanged: a tap never sets the flag. The physical safety cap is
  unchanged and deliberate: `Recorder.record` still stops a held capture at the
  server's `maxSeconds` (30 s by default), so a finger left on the button cannot
  hold the microphone open for ever. Deliberately NOT touched: the Live,
  handsfree and wake-word paths also build a `TurnEnd`, but they have no held
  button, so their pause-based end is unchanged - the rule lives only in the
  talk-button capture loop. What this cannot prove here is the gesture itself,
  which needs a real phone; the field test is in the pull request.
