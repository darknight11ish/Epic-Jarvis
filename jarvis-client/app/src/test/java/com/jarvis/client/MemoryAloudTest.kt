package com.jarvis.client

import com.jarvis.client.voice.MemoryAloud
import com.jarvis.client.voice.PrivateAloud
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The words of the owner's setting of 2026-11-05 - "Read out answers that use
 * what Jarvis remembers" - held on the JVM, because the thing that went wrong
 * on 2026-11-05 was a sentence as much as a rule: his phone said "It's on your
 * screen." about an answer he expected to hear, and nothing said why.
 *
 * Three promises are checked here, in the app's plain words:
 *  1. it is OFF by default, and the row says so;
 *  2. it covers the mic on THIS phone while it is unlocked, and never claims
 *     "hey Jarvis" or Jarvis Live;
 *  3. it says whose setting it is - this phone's; the PC keeps its own rule.
 */
class MemoryAloudTest {

    @Test
    fun `the setting is off by default, and the row says so`() {
        assertFalse(PrivateAloud.MEMORY_ALOUD_DEFAULT)
        val off = MemoryAloud.describe(on = false)
        assertTrue(off, off.startsWith("Off by default"))
        assertTrue(off, "screen" in off)
        // Off is not silence about what ON would do.
        assertTrue(off, "unlocked" in off)
    }

    @Test
    fun `on says what it covers and what still stays on screen`() {
        val on = MemoryAloud.describe(on = true)
        assertTrue(on, on.startsWith("On"))
        assertTrue(on, "unlocked" in on)
        // The half of the 2026-09-24 rule that never moves.
        assertTrue(on, "sensitive" in on)
        assertTrue(on, "private tool" in on)
        assertTrue(on, "screen" in on)
    }

    @Test
    fun `it never claims hey Jarvis or Jarvis Live`() {
        val off = MemoryAloud.describe(on = false)
        assertTrue(off, "\"hey Jarvis\"" in off)
        assertTrue(off, "Jarvis Live" in off)
    }

    @Test
    fun `it says whose setting it is`() {
        assertTrue(MemoryAloud.NOTE, "this phone" in MemoryAloud.NOTE.lowercase())
        assertTrue(MemoryAloud.NOTE, "PC" in MemoryAloud.NOTE)
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
