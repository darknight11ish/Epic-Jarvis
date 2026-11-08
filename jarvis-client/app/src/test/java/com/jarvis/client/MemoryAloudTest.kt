package com.jarvis.client

import com.jarvis.client.voice.MemoryAloud
import com.jarvis.client.voice.PrivateAloud
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The words of the phone's remembered-answers setting - "Read out answers that
 * use what Jarvis remembers" - held on the JVM, because the thing that went
 * wrong on 2026-11-05 was a sentence as much as a rule: his phone said "It's on
 * your screen." about an answer he expected to hear, and nothing said why.
 *
 * REWRITTEN for the owner's decision of 2026-11-07: "i wanted to read
 * everything out loud if i ask it to by Default or unless I can change it
 * through chat turn that off. unless it's extremely sensitive information it's
 * okay." So:
 *  1. it is ON by default, and the row says so;
 *  2. it covers EVERY voice answer on this phone - the mic, "hey Jarvis" and
 *     Jarvis Live;
 *  3. a TYPED answer is silent unless he taps Read aloud;
 *  4. an extremely sensitive saved fact and a private tool still stay on
 *     screen, always;
 *  5. it says whose setting it is - this phone's - and that the chat can change
 *     it.
 */
class MemoryAloudTest {

    @Test
    fun `the setting is on by default, and the row says so`() {
        assertTrue(PrivateAloud.MEMORY_ALOUD_DEFAULT)
        val on = MemoryAloud.describe(on = true)
        assertTrue(on, on.startsWith("On by default"))
        // The half of the 2026-09-24 rule that never moves.
        assertTrue(on, "sensitive" in on)
        assertTrue(on, "private tool" in on)
        assertTrue(on, "screen" in on)
    }

    @Test
    fun `on says it covers the mic, hey Jarvis and Jarvis Live`() {
        val on = MemoryAloud.describe(on = true)
        assertTrue(on, "\"hey Jarvis\"" in on)
        assertTrue(on, "Jarvis Live" in on)
        assertTrue(on, "mic" in on.lowercase() || "microphone" in on.lowercase())
    }

    @Test
    fun `a typed answer is silent unless asked for`() {
        val on = MemoryAloud.describe(on = true)
        assertTrue(on, "typed" in on.lowercase())
        assertTrue(on, "Read aloud" in on)
        // It is not read "by default": the tap is what reads it.
        assertTrue(on, "only when you tap" in on.lowercase())
    }

    @Test
    fun `off says what happens and how to turn it back on`() {
        val off = MemoryAloud.describe(on = false)
        assertTrue(off, off.startsWith("Off"))
        assertTrue(off, "stays on your screen" in off)
        // An off switch he can fix names the way back, in words he can say.
        assertTrue(off, "read everything out loud" in off)
    }

    @Test
    fun `it says whose setting it is, and that the chat can change it`() {
        assertTrue(MemoryAloud.NOTE, "this phone" in MemoryAloud.NOTE.lowercase())
        assertTrue(MemoryAloud.NOTE, "PC" in MemoryAloud.NOTE)
        assertTrue(MemoryAloud.NOTE, "stop reading remembered answers out loud" in MemoryAloud.NOTE)
        assertTrue(MemoryAloud.NOTE, "read everything out loud" in MemoryAloud.NOTE)
        assertTrue(MemoryAloud.NAME.isNotBlank())
        // A name the owner can find, not a setting key.
        assertTrue(MemoryAloud.NAME.lowercase(), "remember" in MemoryAloud.NAME.lowercase())
        assertTrue(MemoryAloud.NAME.lowercase(), "aloud" !in MemoryAloud.NAME.lowercase())
    }

    @Test
    fun `the two buttons say what pressing them does`() {
        assertEquals("Read them out", MemoryAloud.TURN_ON)
        assertEquals("Keep them on my screen", MemoryAloud.TURN_OFF)
        assertTrue(MemoryAloud.TURN_ON != MemoryAloud.TURN_OFF)
    }

    @Test
    fun `the memory sentence is plain words and the memory rule is the only one with it`() {
        assertEquals(
            "That answer used things I remember, so it's on your screen.",
            PrivateAloud.MEMORY_ON_SCREEN,
        )
        // No jargon in the sentence the owner hears.
        for (word in listOf("injected", "route", "gate", "memory_aloud", "JSON")) {
            assertFalse(word, word.lowercase() in PrivateAloud.MEMORY_ON_SCREEN.lowercase())
        }
    }
}
