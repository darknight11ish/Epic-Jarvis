package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.VoiceStrict
import com.jarvis.client.voice.VoiceRounds
import com.jarvis.client.voice.VoiceTraining
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Train my voice" in rounds: which rounds, what is sent, and "record them
 * again" - against the PC's real statuses and answers
 * (`contract/phone-voice-cases.json`, tools/gen_phone_voice_cases.py).
 */
class VoiceRoundsTest {

    private val strict: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/phone-voice-cases.json")) {
            "contract/phone-voice-cases.json is missing - run tools/gen_phone_voice_cases.py"
        }.readText()
        (JarvisJson.parseToJsonElement(text) as JsonObject)["strict"]!!.jsonObject
    }

    private fun view(case: String) = VoiceStrict.parse(strict["status"]!!.jsonObject[case]!!.jsonObject)

    private fun answer(case: String): VoiceStrict.Answer {
        val a = strict["answers"]!!.jsonObject[case]!!.jsonObject
        return VoiceStrict.answer(a["status"]!!.jsonPrimitive.int, a["body"]!!.jsonObject)
    }

    private val older = VoiceStrict.View()

    private fun clips(n: Int) = List(n) { byteArrayOf(it.toByte(), 1, 2) }

    // ------------------------------------------------------------ the plan --

    @Test
    fun `very strict gets three rounds of the same twelve sentences`() {
        val p = VoiceRounds.plan(view("strong_untrained"))
        assertEquals(VoiceRounds.Kind.EXTENDED, p.kind)
        assertEquals(listOf(1, 2, 3), p.rounds.map { it.number })
        assertTrue(p.rounds.all { it.sentences == VoiceTraining.SENTENCES.indices.toList() })
        assertEquals(36, p.total)
        assertFalse(p.add)
    }

    @Test
    fun `balanced keeps today's single round`() {
        val p = VoiceRounds.plan(view("balanced"))
        assertEquals(VoiceRounds.Kind.SINGLE, p.kind)
        assertEquals(1, p.rounds.size)
    }

    @Test
    fun `an older PC keeps today's single round, sent the old way`() {
        val p = VoiceRounds.plan(older)
        assertEquals(VoiceRounds.Kind.SINGLE_OLD, p.kind)
        val body = JarvisJson.parseToJsonElement(VoiceRounds.body(p, 0, clips(12), "phone")).jsonObject
        assertEquals(setOf("mic", "clips"), body.keys)
        assertNull(VoiceRounds.more(older, 2))
    }

    // ---------------------------------------------------------- the bodies --

    @Test
    fun `rounds are held until the last, which finishes - one card`() {
        val p = VoiceRounds.plan(view("strong_untrained"))
        for (i in 0..2) {
            val b = JarvisJson.parseToJsonElement(VoiceRounds.body(p, i, clips(12), "phone")).jsonObject
            assertEquals("train", b["mode"]!!.jsonPrimitive.content)
            assertEquals(i + 1, b["round"]!!.jsonPrimitive.int)
            assertEquals("phone", b["mic"]!!.jsonPrimitive.content)
            assertEquals(false, b["add"]!!.jsonPrimitive.boolean)
            assertEquals(i == 2, b["finish"]!!.jsonPrimitive.boolean)
            assertEquals(12, b["clips"]!!.jsonArray.size)
        }
        assertEquals("Send round 1 to your PC", VoiceRounds.sendLabel(p, 0))
        assertEquals("Send the last round and finish", VoiceRounds.sendLabel(p, 2))
    }

    @Test
    fun `train more adds, in the condition chosen`() {
        val p = VoiceRounds.more(view("trained_three_rounds"), 2)!!
        assertEquals(VoiceRounds.Kind.MORE, p.kind)
        assertTrue(p.add)
        val b = JarvisJson.parseToJsonElement(VoiceRounds.body(p, 0, clips(12), "phone")).jsonObject
        assertEquals(2, b["round"]!!.jsonPrimitive.int)
        assertEquals(true, b["add"]!!.jsonPrimitive.boolean)
        assertEquals(true, b["finish"]!!.jsonPrimitive.boolean)
        assertEquals("More recordings: further away from the microphone, or quieter",
            VoiceRounds.roundTitle(p, 0, view("trained_three_rounds")))
    }

    @Test
    fun `cancel is the PC's own body`() {
        val b = JarvisJson.parseToJsonElement(VoiceStrict.CANCEL_BODY).jsonObject
        assertEquals(JsonPrimitive("train"), b["mode"])
        assertEquals(JsonPrimitive(true), b["cancel"])
    }

    // --------------------------------------------------------- the answers --

    @Test
    fun `a held round is not a card - the PC's own words say what is next`() {
        val a = answer("train_round_held")
        assertEquals(200, a.code)
        assertTrue(a.accepted)
        assertFalse(a.pending)
        assertEquals(2, a.nextRound)
        assertEquals(12, a.held!!.clips)
        val p = VoiceRounds.plan(view("strong_untrained"))
        assertEquals(
            "Round 1 is kept on your PC, in memory only. Next: round 2, further away from the " +
                "microphone, or quieter. Nothing changes until you finish and approve the card.",
            VoiceRounds.heldLine(a, p, 0),
        )
    }

    @Test
    fun `the last round raises the card, and is said so`() {
        val a = answer("train_finish_waiting")
        assertEquals(202, a.code)
        assertTrue(a.accepted)
        assertTrue(a.pending)
        assertEquals("Approve the card on your PC or phone to finish. Nothing changes until you do.",
            VoiceRounds.finishedLine(a))
        assertEquals("kind enroll, waiting", "kind ${view("training_card_waiting").pendingKind}, waiting")
    }

    @Test
    fun `a 202 is a card, even when the PC's body says it was already answered`() {
        // Real answer: the card was raised and answered at once (pending false in the body).
        val a = answer("train_finish")
        assertEquals(202, a.code)
        assertTrue(a.pending)
        assertTrue(a.accepted)
    }

    @Test
    fun `refusals are the PC's sentences, and a held training elsewhere can be cancelled`() {
        val other = answer("train_other_session")
        assertFalse(other.accepted)
        assertEquals(
            "Another training is being recorded (for your phone's microphone) - finish it or " +
                "cancel it first. Tap Cancel to delete what your PC is holding and start again.",
            VoiceRounds.otherSessionLine(other),
        )
        assertNull(VoiceRounds.otherSessionLine(answer("train_card_waiting")))
        val bad = answer("train_bad_clip")
        assertEquals(400, bad.code)
        assertFalse(bad.accepted)
        val needs = answer("train_needs_model")
        assertTrue(needs.needsModel)
        assertFalse(needs.accepted)
        assertEquals("Cancelled. The recordings were deleted.", VoiceRounds.cancelledLine(answer("train_cancel")))
        assertEquals("Cancelled. There was nothing held to delete.",
            VoiceRounds.cancelledLine(answer("train_cancel_nothing")))
    }

    // ------------------------------------------------------ record again --

    @Test
    fun `the left-out clip is named as the sentence it was`() {
        val v = view("trained_three_rounds")
        val sent = VoiceRounds.plan(view("strong_untrained"))
        assertEquals(
            "Your PC left out 1 recording because it did not sound like the rest: round 2, " +
                "\"${VoiceTraining.SENTENCES[4]}\".",
            VoiceRounds.outliersLine(v.last, sent),
        )
        // Not knowing what was sent: only how many.
        assertEquals("Your PC left out 1 recording because it did not sound like the rest.",
            VoiceRounds.outliersLine(v.last, null))
    }

    @Test
    fun `record them again - exactly those, topped up to the PC's minimum, added`() {
        val v = view("trained_three_rounds")
        val sent = VoiceRounds.plan(view("strong_untrained"))
        val redo = VoiceRounds.redo(v, v.last, sent)!!
        assertEquals(VoiceRounds.Kind.REDO, redo.kind)
        assertTrue(redo.add)
        assertEquals(1, redo.rounds.size)
        assertEquals(2, redo.rounds[0].number)
        // Clip 5 is sentence index 4; then the next two, so the PC's 3-clip minimum is met.
        assertEquals(listOf(4, 5, 6), redo.rounds[0].sentences)
        val b = JarvisJson.parseToJsonElement(VoiceRounds.body(redo, 0, clips(3), "phone")).jsonObject
        assertEquals(true, b["add"]!!.jsonPrimitive.boolean)
        assertEquals(2, b["round"]!!.jsonPrimitive.int)
        assertEquals(true, b["finish"]!!.jsonPrimitive.boolean)
        // A redo of a redo maps clip numbers through the redo's own sentences.
        val again = VoiceRounds.redo(v, VoiceStrict.Last("enrolled", outliers = listOf(VoiceStrict.Outlier(2, 2))), redo)!!
        assertEquals(5, again.rounds[0].sentences.first())
    }

    @Test
    fun `nothing to redo after a failed training, without knowing what was sent, or on an older PC`() {
        val failed = view("failed_outliers")
        assertEquals("failed", failed.last!!.outcome)
        assertEquals(6, failed.last.outliers.size)
        val sent = VoiceRounds.plan(view("strong_untrained"))
        assertNull(VoiceRounds.redo(failed, failed.last, sent))
        assertNull(VoiceRounds.outliersLine(failed.last, sent))
        val v = view("trained_three_rounds")
        assertNull(VoiceRounds.redo(v, v.last, null))
        assertNull(VoiceRounds.redo(older, v.last, sent))
        // A clip number the phone never sent: no guessing.
        assertNull(VoiceRounds.redo(v, VoiceStrict.Last("enrolled", outliers = listOf(VoiceStrict.Outlier(2, 40))), sent))
    }

    @Test
    fun `send is blocked until every sentence is recorded, and on a stale link`() {
        val p = VoiceRounds.plan(view("strong_untrained"))
        assertEquals("Record all 12 sentences first (5 done).", VoiceRounds.sendBlocker(p, 0, 5, 20f, null))
        val stale = "Not connected to the desktop, so this cannot be delivered."
        assertEquals(stale, VoiceRounds.sendBlocker(p, 0, 12, 30f, stale))
        assertNotNull(VoiceRounds.sendBlocker(p, 0, 12, 81f, null))
        assertNull(VoiceRounds.sendBlocker(p, 0, 12, 30f, null))
    }

    @Test
    fun `a later round is not sent when the PC no longer holds the earlier ones`() {
        val p = VoiceRounds.plan(view("strong_untrained"))
        val held = view("round_held").session
        // Round 2 after round 1 is held: fine.
        assertNull(VoiceRounds.lostRounds(p, 1, held))
        // Round 3 when only round 1 is held (round 2 was lost): refused.
        assertNotNull(VoiceRounds.lostRounds(p, 2, held))
        // Nothing held any more (15 minutes passed): refused, in words.
        val gone = VoiceRounds.lostRounds(p, 1, view("cancelled").session)!!
        assertTrue(gone, gone.contains("15 minutes"))
        // The first round never needs anything held.
        assertNull(VoiceRounds.lostRounds(p, 0, null))
        // A held training of the other kind (adding) is not this one's rounds.
        assertNotNull(VoiceRounds.lostRounds(p, 1, held!!.copy(add = true)))
    }

    @Test
    fun `an unfinished training on the PC can be picked up at the next round`() {
        val v = view("round_held")
        val (plan, next) = VoiceRounds.resume(v, "phone")!!
        assertEquals(VoiceRounds.Kind.EXTENDED, plan.kind)
        assertEquals(1, next)
        assertEquals(
            "Your PC is holding an unfinished training (round 1, 12 recordings) in its memory. " +
                "It deletes them by itself 15 minutes after the last round arrived.",
            VoiceRounds.unfinishedLine(v),
        )
        // Not a training this phone can continue: another microphone, or one that adds.
        assertNull(VoiceRounds.resume(v, "desktop"))
        assertNull(VoiceRounds.resume(v.copy(session = v.session!!.copy(add = true)), "phone"))
        assertNull(VoiceRounds.resume(view("strong_untrained"), "phone"))
        assertNull(VoiceRounds.unfinishedLine(view("strong_untrained")))
    }

    @Test
    fun `the words for very strict's first training say three rounds and one card`() {
        val p = VoiceRounds.plan(view("strong_untrained"))
        assertTrue(VoiceRounds.intro(p).contains("three times"))
        assertTrue(VoiceRounds.introDetail(p).contains("ONE approval card"))
        assertEquals("Round 2 of 3: further away from the microphone, or quieter",
            VoiceRounds.roundTitle(p, 1, view("strong_untrained")))
    }
}
