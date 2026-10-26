package com.jarvis.client.ui.parts

import org.junit.Assert.assertEquals
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
}
