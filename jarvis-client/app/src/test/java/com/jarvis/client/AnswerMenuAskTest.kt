package com.jarvis.client

import com.jarvis.client.net.AnswerMenuAsk
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The owner's field test of 2026-11-01: they typed "was this answer right?"
 * into the phone's chat and it went to the PC as a question - Jarvis answered
 * it, and the answer's own menu stayed shut. These are the sentences that must
 * open that menu on the phone instead, and the near misses that must NOT (a
 * real question is never swallowed by a menu).
 *
 * Pure JVM: [AnswerMenuAsk] holds no Android types.
 */
class AnswerMenuAskTest {

    @Test
    fun `the owner's own sentence opens the menu`() {
        // The exact words from the field test, with the question mark.
        assertTrue(AnswerMenuAsk.matches("was this answer right?"))
    }

    @Test
    fun `every allowed sentence opens the menu`() {
        for (phrase in AnswerMenuAsk.PHRASES) {
            assertTrue("'$phrase' no longer opens the menu", AnswerMenuAsk.matches(phrase))
            assertTrue("'$phrase' with a ? no longer opens the menu", AnswerMenuAsk.matches("$phrase?"))
        }
        // The list itself, so an addition or a removal is a visible change.
        assertEquals(
            listOf(
                "was this answer right",
                "was that answer right",
                "was the last answer right",
                "was the previous answer right",
                "was this right",
                "was that right",
            ),
            AnswerMenuAsk.PHRASES.toList(),
        )
    }

    @Test
    fun `case, spacing and the last punctuation do not matter`() {
        assertTrue(AnswerMenuAsk.matches("  Was  this ANSWER right?! "))
        assertTrue(AnswerMenuAsk.matches("WAS THIS RIGHT."))
        assertTrue(AnswerMenuAsk.matches("was\tthis\nanswer   right"))
    }

    @Test
    fun `a leading hey jarvis or jarvis is allowed`() {
        assertTrue(AnswerMenuAsk.matches("hey jarvis, was this answer right?"))
        assertTrue(AnswerMenuAsk.matches("Hey Jarvis was that right"))
        assertTrue(AnswerMenuAsk.matches("jarvis, was the last answer right?"))
        assertTrue(AnswerMenuAsk.matches("JARVIS was this right"))
        // The greeting alone asks for nothing.
        assertFalse(AnswerMenuAsk.matches("hey jarvis"))
        assertFalse(AnswerMenuAsk.matches("jarvis"))
        // ...and one greeting only.
        assertFalse(AnswerMenuAsk.matches("jarvis jarvis was this right"))
    }

    @Test
    fun `a real question is never taken for the menu`() {
        // Asked ABOUT the answer or about something else, not for the menu.
        for (question in listOf(
            "was this right for you",
            "was that right about the weather",
            "is this answer right",
            "was my answer right",
            "was the answer correct",
            "was this answer right for the money",
            "why was this answer right",
            "was that right, or was the other one",
            "was this answers right",
        )) {
            assertFalse("'$question' was taken for a menu request", AnswerMenuAsk.matches(question))
        }
    }

    @Test
    fun `nothing typed, and words that are not the list, ask for no menu`() {
        assertFalse(AnswerMenuAsk.matches(null))
        assertFalse(AnswerMenuAsk.matches(""))
        assertFalse(AnswerMenuAsk.matches("   "))
        assertFalse(AnswerMenuAsk.matches("hello"))
        assertFalse(AnswerMenuAsk.matches("what time is it"))
        assertFalse(AnswerMenuAsk.matches("?"))
    }

    @Test
    fun `the line said when there is no finished answer is one short sentence`() {
        assertTrue(AnswerMenuAsk.NO_ANSWER.endsWith("."))
        assertFalse("the line is more than one sentence", AnswerMenuAsk.NO_ANSWER.dropLast(1).contains("."))
        assertTrue("the line does not say nothing was sent", AnswerMenuAsk.NO_ANSWER.contains("no finished answer"))
    }
}
