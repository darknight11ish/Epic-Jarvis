package com.jarvis.client.ui.parts

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The talk button's release decision, off-device.
 *
 * The button's gesture could not be driven in this session (no emulator, no
 * local Gradle), so the decision it makes in its `finally` is held here as
 * data - the four cases the owner's report of 2026-10-13 runs into, pinned so
 * the old "begins then immediately cancels" behaviour cannot come back
 * through a one-line edit.
 *
 * The bug this protects against: the `pointerInput` used to be keyed on
 * `capturing`, so the flag flipping mid-press RESTARTED the gesture, its
 * `finally` saw no release, and the teardown branch called `onCancel()` right
 * after `onBegin()`. KEEP is the release that must now come out of a quick
 * first tap instead of CANCEL - that is the line that changed.
 */
class VoicePressTest {

    @Test
    fun aQuickFirstTapLeavesTheRecordingRunning() {
        // The owner taps once: the clip must outlive the tap (the button's own
        // contract), not be thrown away.
        assertEquals(
            VoicePress.Release.KEEP,
            VoicePress.release(
                wasCapturingAtDown = false,
                cancelled = false,
                released = true,
                durationMs = 120,
            ),
        )
    }

    @Test
    fun theThresholdIsAHold() {
        assertEquals(
            VoicePress.Release.SEND,
            VoicePress.release(
                wasCapturingAtDown = false,
                cancelled = false,
                released = true,
                durationMs = VoicePress.HOLD_THRESHOLD_MS,
            ),
        )
    }

    @Test
    fun holdingTheFirstPressDownSendsOnRelease() {
        assertEquals(
            VoicePress.Release.SEND,
            VoicePress.release(
                wasCapturingAtDown = false,
                cancelled = false,
                released = true,
                durationMs = 900,
            ),
        )
    }

    @Test
    fun theSecondTapWhileCapturingSends() {
        assertEquals(
            VoicePress.Release.SEND,
            VoicePress.release(
                wasCapturingAtDown = true,
                cancelled = false,
                released = true,
                durationMs = 150,
            ),
        )
    }

    @Test
    fun slidingAwayCancelsEvenIfTheFingerLifts() {
        assertEquals(
            VoicePress.Release.CANCEL,
            VoicePress.release(
                wasCapturingAtDown = false,
                cancelled = true,
                released = true,
                durationMs = 900,
            ),
        )
        assertEquals(
            VoicePress.Release.CANCEL,
            VoicePress.release(
                wasCapturingAtDown = true,
                cancelled = true,
                released = true,
                durationMs = 900,
            ),
        )
    }

    @Test
    fun aGestureTornDownWithoutAReleaseCancels() {
        // Composition disposed, parent gone: never send words nobody finished.
        assertEquals(
            VoicePress.Release.CANCEL,
            VoicePress.release(
                wasCapturingAtDown = false,
                cancelled = false,
                released = false,
                durationMs = 50,
            ),
        )
        assertEquals(
            VoicePress.Release.CANCEL,
            VoicePress.release(
                wasCapturingAtDown = true,
                cancelled = false,
                released = false,
                durationMs = 5_000,
            ),
        )
    }

    @Test
    fun theHoldThresholdIsStillFourHundredMilliseconds() {
        // The number the old private constant carried; a change is a change to
        // how the button feels and should be deliberate.
        assertEquals(400L, VoicePress.HOLD_THRESHOLD_MS)
    }

    // ------------------------- the middle of a press (added 2026-11-06) ---
    //
    // The owner's report: "I'm holding down the mic manual button and ... it
    // keeps cutting me off ... even when I'm still speaking". Hold-versus-tap
    // used to be decided only when the finger LIFTED, so nothing told the
    // session a finger was still down and a pause ended the clip. These are
    // the three ways a press must NOT be announced as a hold, and the one way
    // it must - exactly once.

    @Test
    fun aPressThatReachesTheThresholdIsAHold() {
        assertFalse(
            "one millisecond under the threshold is not a hold",
            VoicePress.holdReached(
                durationMs = VoicePress.HOLD_THRESHOLD_MS - 1,
                cancelled = false,
                released = false,
                alreadyFired = false,
            ),
        )
        assertTrue(
            VoicePress.holdReached(
                durationMs = VoicePress.HOLD_THRESHOLD_MS,
                cancelled = false,
                released = false,
                alreadyFired = false,
            ),
        )
        assertTrue(
            "a long-held press must announce once",
            VoicePress.holdReached(
                durationMs = 5_000,
                cancelled = false,
                released = false,
                alreadyFired = false,
            ),
        )
    }

    @Test
    fun aQuickTapIsNeverAnnouncedAsAHold() {
        // The finger is already up: the session gets SEND (or KEEP), not a
        // hold. This is the tap mode the owner asked to keep unchanged.
        assertFalse(
            VoicePress.holdReached(
                durationMs = 120,
                cancelled = false,
                released = true,
                alreadyFired = false,
            ),
        )
        assertFalse(
            VoicePress.holdReached(
                durationMs = 399,
                cancelled = false,
                released = false,
                alreadyFired = false,
            ),
        )
    }

    @Test
    fun slidingAwayBeforeTheThresholdIsNeverAnnouncedAsAHold() {
        // A slide-away cancels; it must not also tell the session the finger
        // is still down (the hold would keep a capture the owner just threw
        // away from being ended by a pause).
        assertFalse(
            VoicePress.holdReached(
                durationMs = 900,
                cancelled = true,
                released = false,
                alreadyFired = false,
            ),
        )
    }

    @Test
    fun aHoldIsAnnouncedExactlyOncePerGesture() {
        // The second and later buffers of the same held press must not call the
        // session again - once per gesture, by construction.
        assertFalse(
            VoicePress.holdReached(
                durationMs = 1_000,
                cancelled = false,
                released = false,
                alreadyFired = true,
            ),
        )
    }
}
