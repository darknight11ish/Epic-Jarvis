package com.jarvis.client

import com.jarvis.client.net.VoiceListening
import com.jarvis.client.net.VoiceStatus
import com.jarvis.client.net.WakeWord
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The wake word's three states, and the one that matters.
 *
 * `VoiceStatus` defaults every field to the refusing value, which is right
 * everywhere else in the app — a status call that fails should leave the
 * microphone button hidden rather than offered. It is wrong here, and
 * dangerously so: it makes "the desktop says the wake word is off" and "I never
 * reached the desktop" produce an identical object.
 *
 * Shown as "Off — nothing is listening", the second one is a promise about a
 * microphone that nothing has checked. These tests exist to keep the two apart.
 */
class WakeWordTest {

    private fun status(on: Boolean, available: Boolean = true) = VoiceStatus(
        available = available,
        listening = VoiceListening(pushToTalk = true, wakeWord = on),
    )

    @Test
    fun `an unanswered desktop is unknown, never off`() {
        // The exact object a failed refresh leaves behind.
        val afterFailure = VoiceStatus(available = false)
        assertEquals(WakeWord.UNKNOWN, WakeWord.of(answered = false, status = afterFailure))

        // And it stays unknown even if the last good answer said off, because
        // what is on the desktop now is not what it said before it went away.
        assertEquals(WakeWord.UNKNOWN, WakeWord.of(answered = false, status = status(on = false)))
    }

    @Test
    fun `an answered desktop reports what it actually said`() {
        assertEquals(WakeWord.ON, WakeWord.of(answered = true, status = status(on = true)))
        assertEquals(WakeWord.OFF, WakeWord.of(answered = true, status = status(on = false)))
    }

    /**
     * `available:false` means the voice module did not load at all, so there is
     * nothing on that side that could be listening. That is a real off — but
     * only when the desktop is the one who said it.
     */
    @Test
    fun `a voice module that did not load is off, not unknown`() {
        val noModule = VoiceStatus(available = false, error = "module failed to load")
        assertEquals(WakeWord.OFF, WakeWord.of(answered = true, status = noModule))
    }

    /**
     * The trap in `VoiceStatus.wakeWordOn`: it ANDs with `available`, so a
     * desktop that reports the wake word listening while the module is down
     * still reads as off. That is the safe direction, and it is worth pinning
     * so nobody "fixes" the AND away later.
     */
    @Test
    fun `wake word on is never reported while the module is unavailable`() {
        val contradictory = VoiceStatus(
            available = false,
            listening = VoiceListening(wakeWord = true),
        )
        assertEquals(WakeWord.OFF, WakeWord.of(answered = true, status = contradictory))
    }

    /** Absent fields in the real payload must decode to off, not to on. */
    @Test
    fun `an empty status decodes to off rather than on`() {
        assertEquals(WakeWord.OFF, WakeWord.of(answered = true, status = VoiceStatus()))
    }
}
