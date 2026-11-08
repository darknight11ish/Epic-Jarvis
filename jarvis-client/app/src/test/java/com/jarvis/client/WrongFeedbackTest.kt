package com.jarvis.client

import com.jarvis.client.net.AnswerMark
import com.jarvis.client.net.FeedbackReason
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.MarkReceipt
import com.jarvis.client.net.WrongFeedback
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The Wrong sheet's pure rules (Wave 10, 2026-11-08).
 *
 * The owner's choice of 2026-11-07 - "Mark + why + save my correction" - is
 * five reason chips, an optional one-line correction and two submit controls
 * on the phone's existing answer menu. The screen cannot be driven from a JVM
 * unit test in this project (no Android build at all in a JVM test; the
 * phone's own jobs are the first compiler), so everything that decides what
 * gets SENT is here, as pure functions, and the sheet calls exactly these.
 *
 * What is proved: the five chips are the owner's own list and the PC's own
 * wire words; the 500-character cap; a chip tapped twice clears; CANCEL sends
 * NOTHING (through the same function every control uses - not because the
 * screen remembered not to); a dead link sends nothing; "Just mark it wrong"
 * sends today's body unchanged; Submit with nothing chosen sends the same old
 * body; Submit with a reason/correction sends the v2 body; and the receipt is
 * the PC's own `said`, with one honest fixed line only when an older PC sends
 * none.
 */
class WrongFeedbackTest {

    private val id32 = "0123456789abcdef0123456789abcdef"

    private fun obj(text: String) = JarvisJson.parseToJsonElement(text) as JsonObject

    private fun field(body: String, name: String): String =
        (obj(body)[name] as JsonPrimitive).content

    // ----------------------------------------------------- the five chips --

    @Test
    fun `the five reasons are the owner's own list, in the PC's wire words`() {
        assertEquals(
            listOf("wrong fact", "outdated", "misunderstood", "too long", "too sensitive"),
            FeedbackReason.values().map { it.label },
        )
        assertEquals(
            listOf("wrong_fact", "outdated", "misunderstood", "too_long", "too_sensitive"),
            FeedbackReason.values().map { it.wire },
        )
    }

    @Test
    fun `one reason at a time, and tapping the chosen one clears it`() {
        assertEquals(FeedbackReason.OUTDATED, WrongFeedback.toggle(null, FeedbackReason.OUTDATED))
        assertEquals(
            FeedbackReason.TOO_LONG,
            WrongFeedback.toggle(FeedbackReason.OUTDATED, FeedbackReason.TOO_LONG),
        )
        assertNull(WrongFeedback.toggle(FeedbackReason.TOO_LONG, FeedbackReason.TOO_LONG))
    }

    // --------------------------------------------- the 500-character cap --

    @Test
    fun `the correction is one line and at most 500 characters`() {
        assertEquals(WrongFeedback.MAX_CORRECTION, 500)
        // 500 is allowed exactly; the 501st character is dropped.
        assertEquals(500, WrongFeedback.cap("x".repeat(500)).length)
        assertEquals(500, WrongFeedback.cap("x".repeat(501)).length)
        assertEquals("x".repeat(500), WrongFeedback.cap("x".repeat(700)))
        // A pasted line break would make it more than one line.
        assertEquals("one two", WrongFeedback.cap("one\ntwo"))
        assertEquals("one two", WrongFeedback.cap("one\r\ntwo"))
        assertEquals("one two", WrongFeedback.cap("one\rtwo"))
        // Ordinary text is left alone.
        assertEquals("it was 2024, not 2023", WrongFeedback.cap("it was 2024, not 2023"))
    }

    @Test
    fun `the counter counts the cap, not the raw paste`() {
        assertEquals(500, WrongFeedback.remaining(""))
        assertEquals(495, WrongFeedback.remaining("hello"))
        assertEquals(0, WrongFeedback.remaining("x".repeat(600)))
        assertEquals("3 characters left", WrongFeedback.remainingLabel("x".repeat(497)))
        assertEquals("500 characters left", WrongFeedback.remainingLabel(""))
    }

    // ------------------------------------------- what a tap sends (and not) --

    @Test
    fun `CANCEL can never send anything`() {
        // The dismiss control goes through the SAME function as every other
        // control, and comes back Nothing by construction. This is the "sends
        // nothing until Submit" rule proved on the function the screen calls.
        for (canSend in listOf(true, false)) {
            assertEquals(
                WrongFeedback.Request.Nothing,
                WrongFeedback.request(
                    WrongFeedback.Tap.CANCEL,
                    id32,
                    WrongFeedback.Draft(FeedbackReason.OUTDATED, "some words"),
                    canSend,
                ),
            )
        }
    }

    @Test
    fun `a dead link or a bad id sends nothing`() {
        for (tap in WrongFeedback.Tap.values()) {
            assertEquals(
                WrongFeedback.Request.Nothing,
                WrongFeedback.request(
                    tap,
                    id32,
                    WrongFeedback.Draft(FeedbackReason.WRONG_FACT, "words"),
                    canSend = false,
                ),
            )
            assertEquals(
                WrongFeedback.Request.Nothing,
                WrongFeedback.request(
                    tap, "not-an-id", WrongFeedback.Draft(), canSend = true,
                ),
            )
        }
    }

    @Test
    fun `Just mark it wrong sends today's body, byte for byte`() {
        val request = WrongFeedback.request(
            WrongFeedback.Tap.JUST_WRONG,
            id32,
            // Even with words on screen: the plain control ignores them, so a
            // tap on it can never carry a correction the owner did not submit.
            WrongFeedback.Draft(FeedbackReason.TOO_SENSITIVE, "typed but not sent"),
            canSend = true,
        )
        assertTrue(request is WrongFeedback.Request.Send)
        assertEquals(
            """{"turn_id":"$id32","mark":"wrong"}""",
            (request as WrongFeedback.Request.Send).body,
        )
    }

    @Test
    fun `Submit with nothing chosen sends the old body too`() {
        val request = WrongFeedback.request(
            WrongFeedback.Tap.SUBMIT,
            id32,
            WrongFeedback.Draft(reason = null, correction = ""),
            canSend = true,
        )
        assertEquals(
            """{"turn_id":"$id32","mark":"wrong"}""",
            (request as WrongFeedback.Request.Send).body,
        )
        // The draft knows it is plain, so the UI can word the receipt as the
        // plain mark's if it ever needs to.
        assertTrue(WrongFeedback.Draft().plain)
        assertTrue(WrongFeedback.Draft(correction = "   ").plain)
    }

    @Test
    fun `Submit sends the reason and the correction as the v2 body`() {
        val request = WrongFeedback.request(
            WrongFeedback.Tap.SUBMIT,
            id32,
            WrongFeedback.Draft(
                reason = FeedbackReason.WRONG_FACT,
                correction = "the meeting is on Tuesday",
            ),
            canSend = true,
        )
        val body = (request as WrongFeedback.Request.Send).body
        assertEquals(id32, field(body, "turn_id"))
        assertEquals("wrong", field(body, "mark"))
        assertEquals("wrong_fact", field(body, "reason"))
        assertEquals("the meeting is on Tuesday", field(body, "correction"))
        // The cap applies to what is SENT, not only to what is drawn.
        val long = WrongFeedback.request(
            WrongFeedback.Tap.SUBMIT,
            id32,
            WrongFeedback.Draft(correction = "y".repeat(600)),
            canSend = true,
        ) as WrongFeedback.Request.Send
        assertEquals(500, field(long.body, "correction").length)
    }

    @Test
    fun `every one of the five reasons reaches the body under its own wire word`() {
        for (reason in FeedbackReason.values()) {
            val request = WrongFeedback.request(
                WrongFeedback.Tap.SUBMIT,
                id32,
                WrongFeedback.Draft(reason = reason),
                canSend = true,
            ) as WrongFeedback.Request.Send
            assertEquals(reason.wire, field(request.body, "reason"))
        }
    }

    // ------------------------------------------------------------ receipts --

    @Test
    fun `the PC's said sentence is the receipt, word for word`() {
        assertEquals(
            "Saved your correction. One card is waiting on your PC.",
            WrongFeedback.receiptWords(
                MarkReceipt(said = "Saved your correction. One card is waiting on your PC."),
            ),
        )
        // Nothing sent yet: no receipt line at all.
        assertNull(WrongFeedback.receiptWords(null))
    }

    @Test
    fun `an older PC with no said gets one honest fixed line, never a claim`() {
        assertEquals(
            WrongFeedback.SAID_FALLBACK,
            WrongFeedback.receiptWords(MarkReceipt(said = "", cardRaised = false)),
        )
        assertEquals(
            WrongFeedback.CARD_FALLBACK,
            WrongFeedback.receiptWords(MarkReceipt(said = "  ", cardRaised = true)),
        )
        // The fallback never says the mark changed memory - it only says what
        // the phone knows: the mark reached the PC (and a card is waiting).
        assertTrue(!WrongFeedback.SAID_FALLBACK.contains("remember", ignoreCase = true))
        assertTrue(!WrongFeedback.CARD_FALLBACK.contains("remember", ignoreCase = true))
        assertTrue(WrongFeedback.CARD_FALLBACK.contains("card", ignoreCase = true))
    }

    @Test
    fun `the sheet's own words are the plain ones the pins expect`() {
        assertEquals("Just mark it wrong", WrongFeedback.JUST_WRONG)
        assertEquals("Send", WrongFeedback.SUBMIT)
        assertEquals("What was wrong?", WrongFeedback.TITLE)
        assertEquals("What should I have said?", WrongFeedback.CORRECTION_LABEL)
        // The plain-language rule: no jargon on the owner's screen.
        for (word in listOf("payload", "JSON", "endpoint", "API")) {
            assertTrue(
                "'$word' is in the sheet's words",
                !WrongFeedback.TITLE.contains(word) &&
                    !WrongFeedback.SUBTITLE.contains(word) &&
                    !WrongFeedback.CORRECTION_LABEL.contains(word),
            )
        }
    }

    @Test
    fun `the mark it asks for is always wrong`() {
        for (tap in WrongFeedback.Tap.values()) {
            val request = WrongFeedback.request(
                tap, id32, WrongFeedback.Draft(), canSend = true,
            )
            if (request is WrongFeedback.Request.Send) {
                assertEquals("wrong", field(request.body, "mark"))
                assertEquals(AnswerMark.WRONG.wire, field(request.body, "mark"))
            }
        }
    }
}
