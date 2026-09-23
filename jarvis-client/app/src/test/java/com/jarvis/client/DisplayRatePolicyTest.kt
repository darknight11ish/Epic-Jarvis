package com.jarvis.client

import com.jarvis.client.platform.DisplayRate
import com.jarvis.client.platform.SmoothMotion
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * When the screen is asked for its fastest refresh rate.
 *
 * The rule used to be "whenever the face's state wants every frame", which
 * held a 120 Hz panel at 120 on screens with no face and all the way through
 * ERROR. These pin the narrower rule in [DisplayRate.wantsHigh].
 */
class DisplayRatePolicyTest {

    private val prefs = SmoothMotion.values()

    @Test
    fun neverWithTheFaceOffScreen() {
        for (state in FaceState.values()) {
            for (pref in prefs) {
                assertFalse(
                    "$state / $pref off screen",
                    DisplayRate.wantsHigh(state, faceOnScreen = false, msInState = 0L, constrained = false, pref = pref),
                )
            }
        }
    }

    @Test
    fun neverInBatterySaverOrWhenHot() {
        for (state in FaceState.values()) {
            for (pref in prefs) {
                assertFalse(
                    "$state / $pref constrained",
                    DisplayRate.wantsHigh(state, faceOnScreen = true, msInState = 0L, constrained = true, pref = pref),
                )
            }
        }
    }

    @Test
    fun neverInError_evenWhenAskedForAlways() {
        for (pref in prefs) {
            assertFalse(
                DisplayRate.wantsHigh(FaceState.ERROR, faceOnScreen = true, msInState = 0L, constrained = false, pref = pref),
            )
        }
    }

    @Test
    fun neverInRestingStates() {
        val resting = listOf(FaceState.IDLE, FaceState.APPROVAL, FaceState.STANDBY, FaceState.BANKED)
        for (state in resting) {
            for (pref in prefs) {
                assertFalse(
                    "$state / $pref",
                    DisplayRate.wantsHigh(state, faceOnScreen = true, msInState = 0L, constrained = false, pref = pref),
                )
            }
        }
    }

    @Test
    fun listeningAndSpeakingAskUnderAuto() {
        for (state in listOf(FaceState.LISTENING, FaceState.SPEAKING)) {
            assertTrue(DisplayRate.wantsHigh(state, faceOnScreen = true, msInState = 0L, constrained = false))
            assertTrue(DisplayRate.wantsHigh(state, faceOnScreen = true, msInState = 600_000L, constrained = false))
        }
    }

    @Test
    fun thinkingAsksOnlyForItsFirstSecondsUnderAuto() {
        assertTrue(DisplayRate.wantsHigh(FaceState.THINKING, faceOnScreen = true, msInState = 0L, constrained = false))
        assertFalse(
            DisplayRate.wantsHigh(
                FaceState.THINKING,
                faceOnScreen = true,
                msInState = DisplayRate.THINKING_HIGH_MS,
                constrained = false,
            ),
        )
        assertTrue(
            DisplayRate.wantsHigh(
                FaceState.THINKING,
                faceOnScreen = true,
                msInState = DisplayRate.THINKING_HIGH_MS * 10,
                constrained = false,
                pref = SmoothMotion.ALWAYS,
            ),
        )
    }

    @Test
    fun offNeverAsks() {
        for (state in FaceState.values()) {
            assertFalse(
                DisplayRate.wantsHigh(state, faceOnScreen = true, msInState = 0L, constrained = false, pref = SmoothMotion.OFF),
            )
        }
    }

    /** The caller stops re-checking when couldWantHigh says no, so it must never say no to a yes. */
    @Test
    fun couldWantHighCoversEveryYes() {
        for (state in FaceState.values()) {
            for (onScreen in listOf(true, false)) {
                for (pref in prefs) {
                    if (DisplayRate.wantsHigh(state, onScreen, msInState = 0L, constrained = false, pref = pref)) {
                        assertTrue("$state / $onScreen / $pref", DisplayRate.couldWantHigh(state, onScreen, pref))
                    }
                }
            }
        }
    }
}
