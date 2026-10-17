package com.jarvis.client

import com.jarvis.client.voice.LiveRules
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Why this phone's Live stopped, and what it says (the owner's Pixel 9,
 * 2026-10-17). Pure function, so this runs on the JVM: no device, no Android.
 *
 * THE BITE: change `endedWords(FGS_REFUSED)` back to "You ended it." and
 * [an android refusal never says the owner ended it] fails. Change
 * `endedWords(MIC_STOPPED)` to the background sentence and
 * [a microphone taken away is not reported as a background refusal] fails.
 */
class LiveStopReasonTest {

    @Test
    fun `an android refusal never says the owner ended it`() {
        val why = LiveRules.LiveStop.FGS_REFUSED
        assertEquals(LiveRules.ENDED_FGS_REFUSED, LiveRules.endedWords(why))
        assertFalse(LiveRules.endedWords(why).contains("You ended it"))
        assertFalse(LiveRules.endedByOwner(why))
    }

    @Test
    fun `a microphone taken away is not reported as a background refusal`() {
        val why = LiveRules.LiveStop.MIC_STOPPED
        assertEquals(LiveRules.STOP_MIC_STOPPED, LiveRules.endedWords(why))
        assertFalse(LiveRules.endedWords(why).contains("background"))
        assertFalse(LiveRules.endedByOwner(why))
    }

    @Test
    fun `only the owner's own end says you ended it`() {
        val why = LiveRules.LiveStop.OWNER
        assertEquals("You ended it.", LiveRules.endedWords(why))
        assertTrue(LiveRules.endedByOwner(why))
    }

    @Test
    fun `the refusal words name Android and the background, the microphone words do not`() {
        assertTrue(LiveRules.stopWords(LiveRules.LiveStop.FGS_REFUSED).contains("Android"))
        assertTrue(LiveRules.stopWords(LiveRules.LiveStop.FGS_REFUSED).contains("background"))
        assertTrue(LiveRules.stopWords(LiveRules.LiveStop.MIC_STOPPED).contains("microphone"))
        assertFalse(LiveRules.stopWords(LiveRules.LiveStop.MIC_STOPPED).contains("background"))
    }
}
