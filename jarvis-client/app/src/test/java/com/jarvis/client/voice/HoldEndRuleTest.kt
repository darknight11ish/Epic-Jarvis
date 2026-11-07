package com.jarvis.client.voice

import com.jarvis.client.voice.HoldEndRule.Move
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The held-talk-button end rule, off-device.
 *
 * The owner reported on 2026-11-06: "I'm holding down the mic manual button and
 * for whatever reason it keeps cutting me off and acting like I took my finger
 * off of the mic button even when I'm still speaking sometimes." The pause that
 * ends a tap (`TurnEnd.Step.END`) was also ending a hold, because nothing told
 * the capture loop that a finger was still down. These are the five cases that
 * fix turns on, and the tap cases are here to prove tap-to-talk did not change.
 *
 * The gesture that reports the hold is Compose-only (`ui/parts/VoiceButton.kt`)
 * and there is no device in this session; what is pinned here is the decision
 * it feeds, which is the whole of the change. The press predicate itself
 * ([com.jarvis.client.ui.parts.VoicePress.holdReached]) is pinned by
 * [com.jarvis.client.ui.parts.VoicePressTest].
 */
class HoldEndRuleTest {

    @Test
    fun aHeldButtonIsNotEndedByAPause() {
        // (a) The owner is still holding: a mid-sentence pause is thinking, not
        // finishing. This is the line that fixes the 2026-11-06 report.
        assertEquals(
            Move.CONTINUE,
            HoldEndRule.move(
                holdStarted = true,
                releaseRequested = false,
                step = TurnEnd.Step.END,
            ),
        )
        // The same END arrives again on the next buffer: still not a reason to
        // stop, and no second thought is needed.
        assertEquals(
            Move.CONTINUE,
            HoldEndRule.move(
                holdStarted = true,
                releaseRequested = false,
                step = TurnEnd.Step.END,
            ),
        )
    }

    @Test
    fun aHeldButtonDoesNotAskTheModel() {
        // (b) ASK exists only to end the clip on a pause; while held there is no
        // pause ending to ask about, so the model must not be spent on it.
        assertEquals(
            Move.CONTINUE,
            HoldEndRule.move(
                holdStarted = true,
                releaseRequested = false,
                step = TurnEnd.Step.ASK,
            ),
        )
    }

    @Test
    fun lettingGoAlwaysStops() {
        // (c) A release (or a slide-away) ends the capture exactly as before,
        // whatever the pause logic was in the middle of saying.
        for (step in TurnEnd.Step.values()) {
            assertEquals(
                "release must stop on $step",
                Move.STOP,
                HoldEndRule.move(holdStarted = true, releaseRequested = true, step = step),
            )
        }
        // Even while listening, the release ends it - the recorder's own
        // stopWhen does the same thing on a real capture.
        assertEquals(
            Move.STOP,
            HoldEndRule.move(
                holdStarted = true,
                releaseRequested = true,
                step = TurnEnd.Step.LISTEN,
            ),
        )
    }

    @Test
    fun tapToTalkStillEndsOnThePause() {
        // (d) A tap never sets holdStarted, so the Smart Turn pause still sends
        // it: behaviour the owner asked to keep, unchanged.
        assertEquals(
            Move.STOP,
            HoldEndRule.move(
                holdStarted = false,
                releaseRequested = false,
                step = TurnEnd.Step.END,
            ),
        )
    }

    @Test
    fun tapToTalkStillAsksTheModel() {
        // (e) The unchanged tap path: the pause asks Smart Turn, and its answer
        // ends the clip.
        assertEquals(
            Move.ASK,
            HoldEndRule.move(
                holdStarted = false,
                releaseRequested = false,
                step = TurnEnd.Step.ASK,
            ),
        )
    }

    @Test
    fun listeningKeepsRecording() {
        // Neither path is told to stop by a quiet buffer that is not yet a pause.
        for (holdStarted in listOf(false, true)) {
            assertEquals(
                Move.CONTINUE,
                HoldEndRule.move(
                    holdStarted = holdStarted,
                    releaseRequested = false,
                    step = TurnEnd.Step.LISTEN,
                ),
            )
        }
    }
}
