package com.jarvis.client

import com.jarvis.client.voice.ReadMemoriesCommand
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * "Stop reading remembered answers out loud" / "read everything out loud" / the
 * state question - the owner's decision of 2026-11-07, on a plain JVM.
 *
 * The commands change the PHONE's own remembered-answers switch. The phone
 * answers them itself, from the owner's own typed or spoken sentence, so a
 * model answer can never toggle the switch (nothing an assistant writes goes
 * through this parser), and the words never reach the PC - which has no such
 * switch to change.
 */
class ReadMemoriesCommandTest {

    @Test
    fun `the owner's off sentences turn it off`() {
        for (said in listOf(
            "stop reading remembered answers out loud",
            "stop reading remembered answers aloud",
            "stop reading remembered facts out loud",
            "stop reading everything out loud",
            "stop reading everything aloud",
            "don't read everything out loud",
            "dont read remembered answers out loud",
            "do not read everything out loud",
            "turn off reading remembered answers out loud",
            "turn off reading everything out loud",
            "  Stop  Reading Everything Out Loud?! ",
            "hey jarvis, stop reading remembered answers out loud",
        )) {
            assertEquals(said, ReadMemoriesCommand.Change.OFF, ReadMemoriesCommand.command(said))
        }
    }

    @Test
    fun `the owner's on sentences turn it on`() {
        for (said in listOf(
            "read everything out loud",
            "read everything aloud",
            "read remembered answers out loud",
            "read your replies out loud",
            "read your answers out loud",
            "turn on reading remembered answers out loud",
            "turn on reading everything out loud",
            "jarvis, read everything out loud.",
        )) {
            assertEquals(said, ReadMemoriesCommand.Change.ON, ReadMemoriesCommand.command(said))
        }
    }

    @Test
    fun `the state questions ask, and do not change anything`() {
        for (said in listOf(
            "are you reading everything out loud?",
            "are you reading remembered answers out loud",
            "are you reading your replies out loud?",
            "are remembered answers read out loud?",
            "is reading everything out loud on?",
            "hey jarvis, are you reading everything out loud?",
        )) {
            assertEquals(said, ReadMemoriesCommand.Change.ASK, ReadMemoriesCommand.command(said))
        }
    }

    @Test
    fun `the state answer says which one it is, in plain words`() {
        val on = ReadMemoriesCommand.stateLine(true)
        assertEquals(true, "Yes" in on)
        assertEquals(true, "Jarvis Live" in on)
        assertEquals(true, "sensitive" in on)
        val off = ReadMemoriesCommand.stateLine(false)
        assertEquals(true, "No" in off)
        assertEquals(true, "read everything out loud" in off)
    }

    @Test
    fun `a real question is never hijacked`() {
        for (said in listOf(
            "",
            null,
            "read this link out loud",
            "read my notes aloud",
            "what does memory aloud mean?",
            "stop reading my mind",
            "read everything about my project",
            "are you reading my messages?",
            "was this answer right",
            "hey jarvis",
        )) {
            assertNull(said, ReadMemoriesCommand.command(said))
        }
    }

    @Test
    fun `the spoken line says a change happened and names the sensitive rule`() {
        assertEquals(true, "on now" in ReadMemoriesCommand.SAID_ON)
        assertEquals(true, "sensitive" in ReadMemoriesCommand.SAID_ON)
        assertEquals(true, "off now" in ReadMemoriesCommand.SAID_OFF)
        // OFF is not a dead end: the tap that reads one answer still exists.
        assertEquals(true, "Read aloud" in ReadMemoriesCommand.SAID_OFF)
    }
}
