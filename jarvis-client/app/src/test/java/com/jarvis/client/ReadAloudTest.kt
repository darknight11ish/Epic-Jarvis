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
        phoneMemoryAloud: Boolean = false,
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
        phoneMemoryAloud = phoneMemoryAloud,
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

    @Test
    fun `a withheld read shows the one sentence, and only for the privacy reasons`() {
        // The owner's 2026-10-27 ruling: when a read is withheld, SHOW the one
        // fixed sentence - no dead control, nothing else. Locked/offline are not
        // what that sentence says, so they draw nothing (their own screens carry
        // their own truth).
        assertEquals(ReadAloud.ON_SCREEN, facts(privateGate = true).withheld)
        // A memory-only block says what happened (2026-11-05's sentence), not
        // the bare line - and names the switch while it is off.
        assertTrue(
            facts(injectedFacts = 1).withheld.orEmpty().startsWith(ReadAloud.MEMORY_ON_SCREEN),
        )
        assertEquals(ReadAloud.ON_SCREEN, facts(injectedSensitive = 1).withheld)
        assertEquals(ReadAloud.ON_SCREEN, facts(toolRan = true).withheld)
        assertEquals(ReadAloud.ON_SCREEN, facts(screenRead = true).withheld)
        assertEquals(ReadAloud.ON_SCREEN, facts(toolsKnown = false).withheld)
        assertEquals(ReadAloud.ON_SCREEN, facts(hasRoute = false).withheld)
        assertNull("a readable answer must not show a refusal", facts().withheld)
        assertNull("a locked phone is not the privacy sentence", facts(locked = true).withheld)
        assertNull("a stale link is not the privacy sentence", facts(stale = true).withheld)
    }

    // ------------- the owner's own okay (his decision of 2026-11-06) --------

    @Test
    fun `the phone's memory switch lets a typed answer with remembered facts be read`() {
        // His 2026-11-05 setting used to cover only the talk button; his
        // 2026-11-06 decision extends the same switch to "Read aloud" on this
        // phone, under the same rule: the memory rule must be the ONLY blocker.
        val memory = facts(injectedFacts = 3)
        assertFalse("switch off: remembered facts stay on screen", memory.mayRead)
        assertEquals(ReadAloud.Why.MEMORY, memory.why)
        assertTrue(
            "switch on, memory-only: it may be read",
            memory.copy(phoneMemoryAloud = true).mayRead,
        )
        // ...and it is never readable on the switch alone if anything else is
        // private. Each of these is one other blocker, not an opinion.
        for (other in listOf(
            "a sensitive fact" to memory.copy(injectedSensitive = 1, phoneMemoryAloud = true),
            "a screen read" to memory.copy(screenRead = true, phoneMemoryAloud = true),
            "a private gate" to memory.copy(privateGate = true, phoneMemoryAloud = true),
            "a private tool" to memory.copy(toolRan = true, phoneMemoryAloud = true),
            "an unknown tool stream" to memory.copy(toolsKnown = false, phoneMemoryAloud = true),
            "a stale link" to memory.copy(stale = true, phoneMemoryAloud = true),
            "a locked phone" to memory.copy(locked = true, phoneMemoryAloud = true),
            "no route" to memory.copy(hasRoute = false, phoneMemoryAloud = true),
        )) {
            assertFalse(other.first, other.second.mayRead)
        }
        // A plain answer is unaffected either way.
        assertTrue(facts(phoneMemoryAloud = true).mayRead)
    }

    @Test
    fun `the one-off action is only for a memory-only or screen-only refusal, unlocked`() {
        val memory = facts(injectedFacts = 2)
        val screen = facts(screenRead = true)
        assertTrue("remembered non-sensitive facts: the one-off is offered", memory.oneOffAt(unlockedNow = true))
        assertTrue("a screen read: the one-off is offered", screen.oneOffAt(unlockedNow = true))
        // Never while the phone is locked at the tap.
        assertFalse(memory.oneOffAt(unlockedNow = false))
        assertFalse(screen.oneOffAt(unlockedNow = false))
        // Two blockers is one too many: the one-off would read past the second.
        assertFalse(facts(injectedFacts = 2, screenRead = true).oneOffAt(unlockedNow = true))
        assertFalse(facts(injectedFacts = 2, toolRan = true).oneOffAt(unlockedNow = true))
        assertFalse(facts(screenRead = true, privateGate = true).oneOffAt(unlockedNow = true))
        // A sensitive fact, a private tool, an unknown stream, a stale link and
        // a locked phone are hard refusals.
        for (other in listOf(
            facts(injectedFacts = 2, injectedSensitive = 1),
            facts(injectedFacts = 2, toolRan = true),
            facts(injectedFacts = 2, toolsKnown = false),
            facts(injectedFacts = 2, stale = true),
            facts(injectedFacts = 2, locked = true),
            facts(privateGate = true),
            facts(hasRoute = false),
        )) {
            assertFalse(other.why.name, other.oneOffAt(unlockedNow = true))
        }
        // A readable answer has no refusal strip, so nothing to override.
        assertFalse(facts().oneOffAt(unlockedNow = true))
        assertNull(ReadAloud.Offer("an answer", facts()).oneOffLabel(unlockedNow = true))
        assertEquals(ReadAloud.ANYWAY, ReadAloud.Offer("an answer", memory).oneOffLabel(unlockedNow = true))
        assertNull(ReadAloud.Offer("an answer", memory).oneOffLabel(unlockedNow = false))
    }

    @Test
    fun `the memory refusal says what happened and names the switch, every other keeps one line`() {
        // The owner's report of 2026-11-06: a typed memory answer used to draw
        // the bare "It's on your screen." - no reason, no switch.
        val memoryLine = facts(injectedFacts = 2).withheld.orEmpty()
        assertTrue(memoryLine, memoryLine.startsWith(ReadAloud.MEMORY_ON_SCREEN))
        assertTrue("the switch that fixes it is named", "Read them out" in memoryLine)
        // Switch on: the answer is readable, so there is no refusal line at all.
        assertNull(facts(injectedFacts = 2, phoneMemoryAloud = true).withheld)
        // Every other privacy refusal keeps the one fixed sentence and never
        // names a switch.
        for (other in listOf(
            facts(privateGate = true),
            facts(toolRan = true),
            facts(screenRead = true),
            facts(injectedSensitive = 1, injectedFacts = 2),
            facts(hasRoute = false),
        )) {
            assertEquals(other.why.name, ReadAloud.ON_SCREEN, other.withheld)
        }
        // Locked and stale draw nothing (their own screens say their truth).
        assertNull(facts(locked = true).withheld)
        assertNull(facts(stale = true).withheld)
    }

    @Test
    fun `the blockers are the whole ladder, in the voice path's order`() {
        // The order is not decoration: `why` and `withheld` report the first
        // one, so a sensitive fact must outrank a screen read and the memory
        // rule, and a lock and a stale link outrank both.
        assertEquals(emptyList<ReadAloud.Why>(), facts().blockers)
        assertEquals(
            listOf(
                ReadAloud.Why.SENSITIVE,
                ReadAloud.Why.SCREEN,
                ReadAloud.Why.PRIVATE_GATE,
                ReadAloud.Why.MEMORY,
                ReadAloud.Why.TOOL,
                ReadAloud.Why.TOOLS_UNKNOWN,
            ),
            facts(
                injectedFacts = 3,
                injectedSensitive = 1,
                screenRead = true,
                privateGate = true,
                toolRan = true,
                toolsKnown = false,
            ).blockers,
        )
        assertEquals(
            listOf(ReadAloud.Why.LOCKED, ReadAloud.Why.OFFLINE, ReadAloud.Why.NO_ROUTE),
            facts(hasRoute = false, stale = true, locked = true).blockers,
        )
    }

    @Test
    fun `the words of the 2026-11-06 doors are plain and quote nothing`() {
        assertEquals(
            "That answer used things I remember, so it's on your screen.",
            ReadAloud.MEMORY_ON_SCREEN,
        )
        assertEquals("Read it aloud anyway", ReadAloud.ANYWAY)
        assertEquals(
            "To hear these every time, turn on \"Read them out\" in Voice settings.",
            ReadAloud.MEMORY_SWITCH_HINT,
        )
        for (word in listOf("injected", "route", "gate", "memory_aloud", "JSON")) {
            assertFalse(word, word.lowercase() in ReadAloud.MEMORY_SWITCH_HINT.lowercase())
        }
        // The action's words say what the tap does and nothing about the answer.
        assertFalse(ReadAloud.ANYWAY.contains("\n"))
        assertTrue("the action is a tap, not a setting", "aloud" in ReadAloud.ANYWAY.lowercase())
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
