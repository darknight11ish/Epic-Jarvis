package com.jarvis.client

import com.jarvis.client.handsfree.HandsfreeFlow
import com.jarvis.client.net.Handsfree
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The hands-free sequence: a card, a read-out, a window, an upload, a decision.
 *
 * Everything else in this feature is Android (a speaker, a microphone, a
 * socket) and cannot be held still here; this is the part that says WHAT
 * happens and in what order, so this is the part that is proven. The invariant
 * the owner asked for - "nothing records while no card is waiting" - is
 * `the_microphone_is_open_only_inside_a_handled_card` below.
 *
 * The window is the PC's, not this app's: `handsfree_card`'s `expires_in_sec`
 * is how long a spoken ANSWER is open (docs/JARVIS-API.md section 191.4), so a
 * card that says 60 gets 60 seconds and one that says 30 gets 30 - and a card
 * that says nothing falls back to the read's `window_sec`, then to the
 * contract's minute. The clock is a parameter everywhere, so a minute costs no
 * time at all.
 */
class HandsfreeFlowTest {

    private fun card(id: String = "c1", expires: Int = 60) = Handsfree.Card(
        cardId = id,
        action = "models_switch",
        say = "Jarvis wants to switch the model to llama3.",
        expiresInSec = expires,
    )

    private fun clip(): ByteArray = ByteArray(400) { it.toByte() }

    private fun started(flow: HandsfreeFlow, now: Long = 1_000L): HandsfreeFlow {
        flow.onCard(card(), now)
        return flow
    }

    @Test
    fun `a card is read out first, and nothing is recorded until it has been`() {
        val flow = HandsfreeFlow()
        assertEquals(HandsfreeFlow.State.Idle, flow.state)
        assertFalse("nothing records on an idle flow", flow.listening)

        val moved = flow.onCard(card(), 1_000L)
        assertTrue(moved is HandsfreeFlow.Moved.To)
        assertEquals(HandsfreeFlow.State.Reading(card()), flow.state)
        assertFalse("reading out is not recording", flow.listening)
        assertEquals(Handsfree.READING, flow.line())
    }

    @Test
    fun `the window opens only after the read-out, and is the PC's own answer window`() {
        val flow = started(HandsfreeFlow())
        val moved = flow.onSpoken(2_000L)
        assertTrue(moved is HandsfreeFlow.Moved.To)
        // The card said 60 seconds and arrived at 1_000 ms: the PC stops taking
        // an answer at 61_000 ms, and that is where this phone's window ends.
        assertEquals(
            HandsfreeFlow.State.Listening(card(), until = 61_000L),
            flow.state,
        )
        assertTrue(flow.listening)
        assertEquals(Handsfree.LISTENING, flow.line())
        assertFalse("not yet over", flow.windowOver(60_999L))
        assertTrue("over at the PC's deadline", flow.windowOver(61_000L))
    }

    @Test
    fun `a card's own shorter countdown is the whole window`() {
        val flow = HandsfreeFlow()
        flow.onCard(card(expires = 5), 1_000L)
        flow.onSpoken(2_000L)
        assertEquals(
            HandsfreeFlow.State.Listening(card(expires = 5), until = 6_000L),
            flow.state,
        )
    }

    @Test
    fun `a card with no window of its own takes the PC's read, never this app's old ten seconds`() {
        // The read said 45; the card said nothing.
        val flow = HandsfreeFlow()
        flow.onCard(card(expires = 0), 1_000L, fallbackSec = 45)
        assertEquals(45, flow.windowSec)
        flow.onSpoken(2_000L)
        assertEquals(
            HandsfreeFlow.State.Listening(card(expires = 0), until = 46_000L),
            flow.state,
        )
        // ...and with nothing said anywhere, the contract's minute.
        val bare = HandsfreeFlow()
        bare.onCard(card(expires = 0), 1_000L)
        assertEquals(Handsfree.WINDOW_SEC, bare.windowSec)
        assertEquals(1_000L + HandsfreeFlow.WINDOW_MS, bare.deadline)
    }

    @Test
    fun `a window longer than the contract's minute is clamped to it`() {
        val flow = HandsfreeFlow()
        flow.onCard(card(expires = 3_600), 1_000L)
        assertEquals(60, flow.windowSec)
        assertEquals(61_000L, flow.deadline)
    }

    @Test
    fun `a second card cannot interrupt one being handled, and the same one is not re-read`() {
        val flow = started(HandsfreeFlow())
        assertEquals(
            HandsfreeFlow.Moved.No(HandsfreeFlow.Refusal.ALREADY),
            flow.onCard(card(), 1_100L),
        )
        assertEquals(
            HandsfreeFlow.Moved.No(HandsfreeFlow.Refusal.BUSY),
            flow.onCard(card(id = "c2"), 1_100L),
        )
        assertEquals("still on the first card", HandsfreeFlow.State.Reading(card()), flow.state)
    }

    @Test
    fun `a window that closed with nothing in it fails in words and uploads nothing`() {
        val flow = started(HandsfreeFlow())
        flow.onSpoken(2_000L)
        val moved = flow.onWindowClosed(null, 12_000L)
        assertTrue(moved is HandsfreeFlow.Moved.To)
        assertEquals(
            HandsfreeFlow.State.Failed(card(), Handsfree.NOTHING_HEARD),
            flow.state,
        )
        assertFalse(flow.listening)
        // Nothing was uploaded, so an answer now is impossible as well as wrong.
        assertEquals(
            HandsfreeFlow.Moved.No(HandsfreeFlow.Refusal.NOT_UPLOADING),
            flow.onAnswer(Handsfree.Answer(ok = true, heard = "yes", decision = "approved"), null, 12_100L),
        )
    }

    @Test
    fun `an empty clip is the same nothing`() {
        val flow = started(HandsfreeFlow())
        flow.onSpoken(2_000L)
        flow.onWindowClosed(ByteArray(0), 12_000L)
        assertEquals(HandsfreeFlow.State.Failed(card(), Handsfree.NOTHING_HEARD), flow.state)
    }

    @Test
    fun `a real clip goes to the PC, and its answer is shown in plain words`() {
        val flow = started(HandsfreeFlow())
        flow.onSpoken(2_000L)
        flow.onWindowClosed(clip(), 12_000L)
        assertEquals(HandsfreeFlow.State.Uploading(card()), flow.state)
        assertFalse(flow.listening)
        assertEquals(Handsfree.SENDING, flow.line())

        val moved = flow.onAnswer(
            Handsfree.Answer(ok = true, heard = "yes, do it", decision = "approved", cardState = "approved"),
            null,
            13_000L,
        )
        assertTrue(moved is HandsfreeFlow.Moved.To)
        val settled = flow.state as HandsfreeFlow.State.Settled
        assertEquals("Heard: \"yes, do it\" - approved.", settled.line)
        assertEquals(true, settled.approved)
        assertEquals(settled.line, flow.line())
    }

    @Test
    fun `a deny is a deny, and never words that could be read as a yes`() {
        val flow = started(HandsfreeFlow())
        flow.onSpoken(2_000L)
        flow.onWindowClosed(clip(), 12_000L)
        flow.onAnswer(Handsfree.Answer(ok = true, heard = "no", decision = "denied"), null, 13_000L)
        val settled = flow.state as HandsfreeFlow.State.Settled
        assertEquals(false, settled.approved)
        assertEquals("Heard: \"no\" - denied.", settled.line)
    }

    @Test
    fun `the PC's own sentence is what the owner sees when it sent one`() {
        val flow = started(HandsfreeFlow())
        flow.onSpoken(2_000L)
        flow.onWindowClosed(clip(), 12_000L)
        flow.onAnswer(
            Handsfree.Answer(
                ok = true,
                heard = "yes",
                decision = "approved",
                cardState = "approved",
                say = "Approved. Carrying on.",
            ),
            null,
            13_000L,
        )
        assertEquals("Approved. Carrying on.", flow.line())
        assertEquals(
            true,
            (flow.state as HandsfreeFlow.State.Settled).approved,
        )
    }

    @Test
    fun `an unclear answer asks once more, in a second window inside the same deadline`() {
        val flow = started(HandsfreeFlow())
        flow.onSpoken(2_000L)
        flow.onWindowClosed(clip(), 3_000L)
        // The PC heard something it could not place: `again`, the card is still
        // waiting, and the phone goes back to reading out its question.
        val moved = flow.onAnswer(
            Handsfree.Answer(ok = false, heard = "mmm", decision = "again", cardState = "pending"),
            null,
            3_100L,
        )
        assertTrue(moved is HandsfreeFlow.Moved.To)
        assertEquals(HandsfreeFlow.State.Reading(card()), flow.state)
        assertFalse("the microphone shuts between windows", flow.listening)
        // Back to Reading because the service now speaks the PC's own question
        // ("Sorry - was that yes or no?") before opening the second window.
        assertEquals(Handsfree.READING, flow.line())
        // ...and the second window ends at the SAME PC deadline, not a new one.
        flow.onSpoken(3_200L)
        assertEquals(HandsfreeFlow.State.Listening(card(), until = 61_000L), flow.state)
        // The second answer decides, because the PC treats a second unclear
        // answer as a deny.
        flow.onWindowClosed(clip(), 4_000L)
        flow.onAnswer(
            Handsfree.Answer(ok = true, heard = "no", decision = "denied", say = "OK, I won't do that."),
            null,
            4_100L,
        )
        assertEquals("OK, I won't do that.", flow.line())
        assertFalse(flow.listening)
    }

    @Test
    fun `an unclear answer with no window left is shown, not re-asked`() {
        val flow = HandsfreeFlow()
        flow.onCard(card(expires = 2), 1_000L)
        flow.onSpoken(1_100L)
        flow.onWindowClosed(clip(), 2_900L)
        // The PC's deadline (3_000 ms) has passed: a second window would be one
        // the PC refuses, so its question is shown and the card is left waiting.
        flow.onAnswer(
            Handsfree.Answer(ok = false, decision = "again", cardState = "pending", say = "Sorry - was that yes or no?"),
            null,
            3_100L,
        )
        val settled = flow.state as HandsfreeFlow.State.Settled
        assertEquals("Sorry - was that yes or no?", settled.line)
        assertNull("nothing was decided", settled.approved)
        assertFalse(flow.listening)
    }

    @Test
    fun `a failed upload fails with the reason, and invents no decision`() {
        val flow = started(HandsfreeFlow())
        flow.onSpoken(2_000L)
        flow.onWindowClosed(clip(), 12_000L)
        flow.onAnswer(null, "Your PC isn't answering.", 13_000L)
        val failed = flow.state as HandsfreeFlow.State.Failed
        assertEquals("Your PC isn't answering.", failed.why)
        assertEquals("the card is still named", card(), failed.card)
    }

    @Test
    fun `a card past its answer window never opens a microphone`() {
        val flow = HandsfreeFlow()
        flow.onCard(card(id = "c9", expires = 30), now = 1_000L)
        assertFalse("not yet", flow.expired(30_999L))
        assertTrue("30 seconds later", flow.expired(31_000L))

        val moved = flow.onSpoken(31_000L)
        assertTrue(moved is HandsfreeFlow.Moved.To)
        assertFalse("the window did not open", flow.listening)
        val failed = flow.state as HandsfreeFlow.State.Failed
        assertEquals(Handsfree.WINDOW_OVER, failed.why)
    }

    @Test
    fun `the_microphone_is_open_only_inside_a_handled_card`() {
        val flow = HandsfreeFlow()
        // Idle, and after every kind of finish: nothing records.
        assertFalse(flow.listening)
        assertEquals(HandsfreeFlow.Moved.No(HandsfreeFlow.Refusal.NOT_READING), flow.onSpoken(1L))
        assertFalse(flow.listening)
        assertEquals(
            HandsfreeFlow.Moved.No(HandsfreeFlow.Refusal.NOT_LISTENING),
            flow.onWindowClosed(clip(), 2L),
        )
        assertFalse(flow.listening)

        // The only way in is a card that was read out and had not expired.
        flow.onCard(card(), 1_000L)
        assertFalse(flow.listening)
        flow.onSpoken(2_000L)
        assertTrue(flow.listening)
        flow.onWindowClosed(clip(), 12_000L)
        assertFalse("the window is over once the clip goes", flow.listening)

        // ...and after a reset - the mode switched off mid-card - it is shut.
        flow.reset()
        assertEquals(HandsfreeFlow.State.Idle, flow.state)
        assertFalse(flow.listening)
        assertNull(flow.line())
    }

    @Test
    fun `a finished card makes room for the next one`() {
        val flow = started(HandsfreeFlow())
        flow.onSpoken(2_000L)
        flow.onWindowClosed(null, 12_000L)
        assertTrue(flow.state is HandsfreeFlow.State.Failed)
        val moved = flow.onCard(card(id = "c3"), 20_000L)
        assertTrue("a new card starts", moved is HandsfreeFlow.Moved.To)
        assertEquals(HandsfreeFlow.State.Reading(card(id = "c3")), flow.state)
    }

    @Test
    fun `a card with no id is refused rather than answered into nothing`() {
        val flow = HandsfreeFlow()
        val moved = flow.onCard(Handsfree.Card(cardId = "  "), 1_000L)
        assertEquals(HandsfreeFlow.Moved.No(HandsfreeFlow.Refusal.ALREADY), moved)
        assertEquals(HandsfreeFlow.State.Idle, flow.state)
    }

    @Test
    fun `a card that cannot be read out is freed rather than blocking the next one`() {
        // The audit's bug: a card read out into a call, or with no voice on the
        // PC, left the flow in Reading - and then EVERY later card was refused
        // as BUSY. The mode would have looked like it quietly stopped after one
        // silent card.
        val flow = started(HandsfreeFlow())
        assertEquals(HandsfreeFlow.State.Reading(card()), flow.state)
        flow.fail(Handsfree.NO_VOICE)
        val failed = flow.state as HandsfreeFlow.State.Failed
        assertEquals(Handsfree.NO_VOICE, failed.why)
        assertEquals("the card is still named", card(), failed.card)
        assertFalse(flow.listening)

        val next = flow.onCard(card(id = "c4"), 30_000L)
        assertTrue("a later card starts", next is HandsfreeFlow.Moved.To)
        assertEquals(HandsfreeFlow.State.Reading(card(id = "c4")), flow.state)

        // ...and the same works from a window that was already open.
        flow.onSpoken(31_000L)
        assertTrue(flow.listening)
        flow.fail(Handsfree.IN_CALL)
        assertFalse("the microphone is shut", flow.listening)
        assertEquals(0L, flow.deadline)
        assertEquals(
            HandsfreeFlow.State.Failed(card(id = "c4"), Handsfree.IN_CALL),
            flow.state,
        )
    }

    @Test
    fun `an answer the PC refused keeps the PC's own sentence`() {
        val flow = started(HandsfreeFlow())
        flow.onSpoken(2_000L)
        flow.onWindowClosed(clip(), 12_000L)
        flow.onAnswer(
            Handsfree.Answer(ok = false, say = "That card was already decided."),
            null,
            13_000L,
        )
        val settled = flow.state as HandsfreeFlow.State.Settled
        assertEquals("That card was already decided.", settled.line)
        assertNull("nothing was decided by this answer", settled.approved)
    }
}
