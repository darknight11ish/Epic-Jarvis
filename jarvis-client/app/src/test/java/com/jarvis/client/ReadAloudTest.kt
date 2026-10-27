package com.jarvis.client

import com.jarvis.client.voice.ReadAloud
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The pure half of "Read aloud" for a typed answer (the owner's ask,
 * 2026-10-27): the fail-closed decision and the sentence splitter. No Android
 * and no network, so every branch runs here; the Compose wiring and the real
 * `/api/voice/say` round trip are held by [ReadAloudWiringTest] and CI.
 */
class ReadAloudTest {

    private fun facts(
        hasRoute: Boolean = true,
        privateGate: Boolean = false,
        injectedFacts: Int = 0,
        injectedSensitive: Int = 0,
        toolRan: Boolean = false,
        toolsKnown: Boolean = true,
        screenRead: Boolean = false,
        stale: Boolean = false,
        locked: Boolean = false,
    ) = ReadAloud.Facts(
        hasRoute = hasRoute,
        privateGate = privateGate,
        injectedFacts = injectedFacts,
        injectedSensitive = injectedSensitive,
        toolRan = toolRan,
        toolsKnown = toolsKnown,
        screenRead = screenRead,
        stale = stale,
        locked = locked,
    )

    @Test
    fun `an ordinary answer with a known route may be read`() {
        val f = facts()
        assertTrue(f.mayRead)
        assertNull(f.refusal)
    }

    @Test
    fun `every unknown or private fact fails closed`() {
        val blocked = listOf(
            "no route" to facts(hasRoute = false),
            "private gate" to facts(privateGate = true),
            "saved facts" to facts(injectedFacts = 1),
            "sensitive facts" to facts(injectedFacts = 2, injectedSensitive = 1),
            "a tool ran" to facts(toolRan = true),
            "the stream could not say" to facts(toolsKnown = false),
            "the screen was read" to facts(screenRead = true),
            "stale link" to facts(stale = true),
            "locked phone" to facts(locked = true),
        )
        for ((why, f) in blocked) {
            assertFalse(why, f.mayRead)
        }
    }

    @Test
    fun `the refusal words never name the answer or a fact`() {
        val texts = listOf(
            facts(hasRoute = false),
            facts(privateGate = true),
            facts(injectedSensitive = 1),
            facts(screenRead = true),
            facts(toolRan = true),
            facts(toolsKnown = false),
            facts(stale = true),
            facts(locked = true),
        ).mapNotNull { it.refusal }
        assertTrue(texts.isNotEmpty())
        for (words in texts) {
            assertTrue("a refusal must say something", words.isNotBlank())
            assertFalse("a refusal must not say the old blank placeholder", words.contains("TODO"))
            assertFalse("a refusal must never quote the answer", words.contains("\n"))
        }
    }

    @Test
    fun `a locked phone says it is locked and a stale link says it is not connected`() {
        assertEquals(ReadAloud.LOCKED, facts(locked = true).refusal)
        assertEquals(ReadAloud.OFFLINE, facts(stale = true).refusal)
        // Everything else that fails for privacy says only "on your screen".
        assertEquals(ReadAloud.ON_SCREEN, facts(privateGate = true).refusal)
        assertEquals(ReadAloud.ON_SCREEN, facts(hasRoute = false).refusal)
    }

    @Test
    fun `the on-screen sentence is the one the voice path already says`() {
        // The literal above is deliberate: this object stays compilable alone.
        // The real `voice.PrivateAloud.ON_SCREEN` is pinned to the same words by
        // ReadAloudWiringTest against the source.
        assertEquals("It's on your screen.", ReadAloud.ON_SCREEN)
    }

    // --- the sentences ------------------------------------------------------

    @Test
    fun `sentences end at stop punctuation and at line breaks`() {
        val got = ReadAloud.sentences("One. Two! Three? Four")
        assertEquals(listOf("One.", "Two!", "Three?", "Four"), got)
    }

    @Test
    fun `a paragraph with no stop punctuation stays one sentence`() {
        assertEquals(listOf("just some words"), ReadAloud.sentences("  just some words \n"))
    }

    @Test
    fun `blank answers have nothing to say`() {
        assertTrue(ReadAloud.sentences("").isEmpty())
        assertTrue(ReadAloud.sentences("   \n\n  ").isEmpty())
    }

    @Test
    fun `a long answer is capped, and a silly cap still speaks one sentence`() {
        val long = (1..40).joinToString(" ") { "Sentence number $it." }
        assertEquals(ReadAloud.READ_ALOUD_SENTENCE_CAP, ReadAloud.sentences(long).size)
        assertEquals(1, ReadAloud.sentences(long, max = 0).size)
        assertEquals(3, ReadAloud.sentences(long, max = 3).size)
    }

    @Test
    fun `the cap keeps the first sentences, in order`() {
        val got = ReadAloud.sentences("First. Second. Third.", max = 2)
        assertEquals(listOf("First.", "Second."), got)
    }
}
