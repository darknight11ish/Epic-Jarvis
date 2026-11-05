package com.jarvis.client

import com.jarvis.client.voice.MicOwner
import com.jarvis.client.voice.MicOwner.Use
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The hands-free answer window and the talk button share one microphone, and
 * this file proves the ONE ledger (voice/MicOwner.kt) makes them exclude each
 * other in words.
 *
 * The bug this file exists for (privacy audit, 2026-11-05): `MicOwner` named
 * TALK and nothing ever held it, so the answer window could open a second
 * recorder over a sentence in progress and no refusal could fire. The rules are
 * now main's pure state machine - `mayOpen` / `opened` / `closed` on plain data -
 * so every case below runs on the JVM, and the last test pins the two Android
 * call sites no JVM test can drive.
 */
class MicHandsfreeRulesTest {

    private val idle = MicOwner.State()

    @Test
    fun `the answer window is refused while the talk button holds the microphone`() {
        val talking = MicOwner.opened(idle, Use.TALK)
        val decision = MicOwner.mayOpen(talking, Use.HANDSFREE)
        assertFalse("the window opened over a sentence in progress", decision.allowed)
        assertEquals(MicOwner.TALKING, decision.why)
    }

    @Test
    fun `the talk button is refused while the answer window holds it`() {
        val window = MicOwner.opened(idle, Use.HANDSFREE)
        val decision = MicOwner.mayOpen(window, Use.TALK)
        assertFalse("the talk button opened a second recorder", decision.allowed)
        assertEquals(MicOwner.LISTENING, decision.why)
    }

    @Test
    fun `the two always-on listeners pause for either holder`() {
        for (holder in listOf(Use.TALK, Use.HANDSFREE)) {
            val held = MicOwner.opened(idle, holder)
            for (listener in listOf(Use.LIVE, Use.WAKE)) {
                val decision = MicOwner.mayOpen(held, listener)
                assertFalse("$listener must pause while $holder records", decision.allowed)
                assertEquals(MicOwner.LISTENING, decision.why)
            }
        }
    }

    @Test
    fun `a refused open never steals the microphone`() {
        val window = MicOwner.opened(idle, Use.HANDSFREE)
        MicOwner.mayOpen(window, Use.TALK)
        assertEquals("the window still has it", Use.HANDSFREE, window.capturing)
        assertTrue("the holder itself is never refused", MicOwner.mayOpen(window, Use.HANDSFREE).allowed)
    }

    @Test
    fun `closing gives the microphone back, and a stale close frees nothing`() {
        val window = MicOwner.opened(idle, Use.HANDSFREE)
        assertTrue(MicOwner.mayOpen(MicOwner.closed(window, Use.HANDSFREE), Use.TALK).allowed)
        val talking = MicOwner.opened(idle, Use.TALK)
        assertEquals(
            "another path's close must not free the talk button's microphone",
            Use.TALK,
            MicOwner.closed(talking, Use.HANDSFREE).capturing,
        )
    }

    @Test
    fun `call recording still outranks both of them`() {
        val recording = MicOwner.opened(MicOwner.arm(idle), Use.CALL_RECORD)
        for (use in listOf(Use.TALK, Use.HANDSFREE, Use.LIVE, Use.WAKE)) {
            assertFalse("$use must stay closed while a call is recorded", MicOwner.mayOpen(recording, use).allowed)
        }
    }

    @Test
    fun `the two refusals name different things and neither is silent`() {
        assertTrue(MicOwner.TALKING.isNotBlank())
        assertTrue(MicOwner.LISTENING.isNotBlank())
        assertTrue(MicOwner.TALKING != MicOwner.LISTENING)
        assertTrue(MicOwner.TALKING.contains("talking"))
        assertTrue(MicOwner.LISTENING.contains("Try again"))
    }

    @Test
    fun `the answer window and the recorder really ask this ledger`() {
        val service = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/service/HandsfreeService.kt",
        )
        val recorder = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/audio/Recorder.kt",
        )
        assertTrue("the window must ask before opening", service.contains("MicNow.mayOpen(MicOwner.Use.HANDSFREE)"))
        assertTrue("and register itself", service.contains("MicNow.opened(MicOwner.Use.HANDSFREE)"))
        assertTrue("and give the microphone back", service.contains("MicNow.closed(MicOwner.Use.HANDSFREE)"))
        assertTrue("a refusal is shown in words", service.contains("flow.fail(may.why)"))
        assertTrue("the talk button registers too", recorder.contains("MicNow.opened(MicOwner.Use.TALK)"))
        assertTrue("and gives it back in a finally", recorder.contains("MicNow.closed(MicOwner.Use.TALK)"))
        assertFalse("neither side keeps its own ledger any more", service.contains("MicClaim") || recorder.contains("MicClaim"))
    }
}
