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
 * The clock is a parameter everywhere, so ten seconds and an expiry cost no
 * time at all.
 */
class HandsfreeFlowTest {

    private fun card(id: String = "c1", expires: Int = 0) = Handsfree.Card(
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
    fun `the window opens only after the read-out, and for exactly the ten seconds`() {
        val flow = started(HandsfreeFlow())
        val moved = flow.onSpoken(2_000L)
        assertTrue(moved is HandsfreeFlow.Moved.To)
        assertEquals(
            HandsfreeFlow.State.Listening(card(), until = 2_000L + HandsfreeFlow.LISTEN_MS),
            flow.state,
        )
        assertTrue(flow.listening)
        assertEquals(Handsfree.LISTENING, flow.line())
        // Ten seconds: the owner's own number.
        assertEquals(10_000L, HandsfreeFlow.LISTEN_MS)

        assertFalse("not yet over", flow.windowOver(11_999L))
        assertTrue("over at the boundary", flow.windowOver(12_000L))
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
    fun `a failed upload fails with the reason, and invents no decision`() {
        val flow = started(HandsfreeFlow())
        flow.onSpoken(2_000L)
        flow.onWindowClosed(clip(), 12_000L)
        flow.onAnswer(null, "Your PC isn't answering.", 13_000L)
        val failed = flow.state as HandsfreeFlow.State.Failed
        assertEquals("Your PC isn't answering.", failed.why)
        assertNull("no decision is claimed", (failed as? HandsfreeFlow.State.Settled)?.approved)
    }

    @Test
    fun `a card past its own time never opens a microphone`() {
        val flow = HandsfreeFlow()
        flow.onCard(card(id = "c9", expires = 30), now = 1_000L)
        assertFalse("not yet", flow.expired(30_999L))
        assertTrue("30 seconds later", flow.expired(31_000L))

        val moved = flow.onSpoken(31_000L)
        assertTrue(moved is HandsfreeFlow.Moved.To)
        assertFalse("the window did not open", flow.listening)
        val failed = flow.state as HandsfreeFlow.State.Failed
        assertTrue(failed.why.contains("expired"))
    }

    @Test
    fun `a card the PC gave no time for never expires on the phone`() {
        val flow = HandsfreeFlow()
        flow.onCard(card(expires = 0), 1_000L)
        assertFalse("no deadline, no expiry", flow.expired(Long.MAX_VALUE / 2))
        flow.onSpoken(2_000L)
        assertTrue(flow.listening)
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
            Handsfree.Answer(ok = false, why = "That card was already decided."),
            null,
            13_000L,
        )
        val settled = flow.state as HandsfreeFlow.State.Settled
        assertEquals("That card was already decided.", settled.line)
        assertNull("nothing was decided by this answer", settled.approved)
    }
}
