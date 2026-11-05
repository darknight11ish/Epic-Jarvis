package com.jarvis.client

import com.jarvis.client.voice.MicOwner
import com.jarvis.client.voice.MicOwner.Use
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * ONE microphone, four paths, one arbitration point (voice/MicOwner.kt).
 *
 * Until 2026-11-04 nothing decided who owned the microphone: Live, the wake
 * word and the talk button each opened it when they liked and the "may I
 * listen" checks were written per service. Adding call recording without this
 * would have been a fifth opinion - and the one path whose whole reason is a
 * moment that does not come back.
 */
class MicOwnerTest {

    private val fresh = MicOwner.State()

    // ------------------------------------------------------ the pecking order ---

    @Test
    fun `with nothing going on every path may open the microphone`() {
        for (use in Use.values()) {
            assertTrue("$use should be allowed when the phone is idle", MicOwner.mayOpen(fresh, use).allowed)
        }
    }

    @Test
    fun `arming call recording closes the other three`() {
        val armed = MicOwner.arm(fresh)
        assertTrue(armed.armed)
        assertEquals(Use.CALL_RECORD, armed.heldBy)
        for (use in listOf(Use.LIVE, Use.WAKE, Use.TALK)) {
            val decision = MicOwner.mayOpen(armed, use)
            assertFalse("$use must not open the microphone while a call is waited for", decision.allowed)
            assertEquals(MicOwner.ARMED_REFUSAL, decision.why)
        }
    }

    @Test
    fun `call recording itself is always allowed`() {
        assertTrue(MicOwner.mayOpen(MicOwner.arm(fresh), Use.CALL_RECORD).allowed)
        val liveTalking = MicOwner.opened(fresh, Use.LIVE)
        val decision = MicOwner.mayOpen(liveTalking, Use.CALL_RECORD)
        assertTrue("call recording preempts", decision.allowed)
        assertTrue("and the other path is told to close", decision.close)
    }

    @Test
    fun `while a call is being recorded the other paths say why`() {
        val recording = MicOwner.opened(MicOwner.arm(fresh), Use.CALL_RECORD)
        for (use in listOf(Use.LIVE, Use.WAKE, Use.TALK)) {
            val decision = MicOwner.mayOpen(recording, use)
            assertFalse(decision.allowed)
            assertEquals(MicOwner.RECORDING_REFUSAL, decision.why)
        }
    }

    @Test
    fun `disarming gives the microphone back at once`() {
        val recording = MicOwner.opened(MicOwner.arm(fresh), Use.CALL_RECORD)
        val after = MicOwner.disarm(recording)
        assertEquals(MicOwner.State(), after)
        assertTrue(MicOwner.mayOpen(after, Use.LIVE).allowed)
        assertTrue(MicOwner.mayOpen(after, Use.WAKE).allowed)
        assertTrue(MicOwner.mayOpen(after, Use.TALK).allowed)
        assertFalse(MicOwner.callRecordingHolds(after))
    }

    // --------------------------------------------------------------- states ---

    @Test
    fun `an opened path is the one that holds it, and only it can close it`() {
        val live = MicOwner.opened(fresh, Use.LIVE)
        assertEquals(Use.LIVE, live.capturing)
        // The wake word closing does not clear Live's claim.
        assertEquals(Use.LIVE, MicOwner.closed(live, Use.WAKE).capturing)
        assertNull(MicOwner.closed(live, Use.LIVE).capturing)
    }

    @Test
    fun `two ordinary paths do not fight each other`() {
        // Live and the wake word have their own existing rules for when they
        // run; the arbitration only exists for the call recorder, and it must
        // not invent a new restriction between them.
        val live = MicOwner.opened(fresh, Use.LIVE)
        assertTrue(MicOwner.mayOpen(live, Use.WAKE).allowed)
    }

    @Test
    fun `callRecordingHolds is true for armed, for recording, and false after`() {
        assertFalse(MicOwner.callRecordingHolds(fresh))
        assertTrue(MicOwner.callRecordingHolds(MicOwner.arm(fresh)))
        assertTrue(MicOwner.callRecordingHolds(MicOwner.opened(MicOwner.arm(fresh), Use.CALL_RECORD)))
        // A stale heldBy with nothing armed is still call recording's.
        assertTrue(MicOwner.callRecordingHolds(MicOwner.State(heldBy = Use.CALL_RECORD)))
        // And a path that merely holds the microphone is not call recording.
        assertFalse(MicOwner.callRecordingHolds(MicOwner.opened(fresh, Use.WAKE)))
    }

    @Test
    fun `opening as call recording replaces whoever had it`() {
        val wake = MicOwner.opened(fresh, Use.WAKE)
        val recording = MicOwner.opened(MicOwner.arm(wake), Use.CALL_RECORD)
        assertEquals(Use.CALL_RECORD, recording.capturing)
        assertEquals(Use.CALL_RECORD, recording.heldBy)
    }

    @Test
    fun `a refusal always carries a sentence to show`() {
        val armed = MicOwner.arm(fresh)
        assertTrue(MicOwner.mayOpen(armed, Use.LIVE).why.isNotBlank())
        val recording = MicOwner.opened(armed, Use.CALL_RECORD)
        assertTrue(MicOwner.mayOpen(recording, Use.TALK).why.isNotBlank())
        // An allowed one carries none, so a screen never shows a stray line.
        assertEquals("", MicOwner.mayOpen(fresh, Use.LIVE).why)
    }
}
