package com.jarvis.client

import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.VoiceStatus
import com.jarvis.client.net.VoiceStrict
import com.jarvis.client.net.VoiceTrainingLast
import com.jarvis.client.net.VoiceTrainingReply
import com.jarvis.client.voice.VoiceTraining
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Clear previous voice training" on the phone (the owner's 2026-10-19
 * decision; docs/JARVIS-API.md section 5): one more mode on the EXISTING
 * `/api/voice/enroll` route, ONE `change_own_config` card on the PC, nothing
 * deleted until it is approved. The phone never decides and never approves.
 *
 * Every real status is `contract/phone-voice-cases.json`, made by
 * `tools/gen_phone_voice_cases.py` from the backend's own `jarvis_speech.status()`
 * and `jarvis_voice_enroll.stage()`. The one made thing is "an older PC": a
 * real status with the new flags taken out, which is what a PC before the
 * clear mode sends.
 *
 * NOT tested here, and never counted as tested: the card round trip itself
 * (a real app + a running backend), and the screen drawing it. The JVM tests
 * hold the words and the state machine; the card is NOT-TESTABLE on a desk.
 */
class VoiceClearTest {

    private val strict: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/phone-voice-cases.json")) {
            "contract/phone-voice-cases.json is missing - run tools/gen_phone_voice_cases.py"
        }.readText()
        (JarvisJson.parseToJsonElement(text) as JsonObject)["strict"]!!.jsonObject
    }

    private fun status(case: String): JsonObject = strict["status"]!!.jsonObject[case]!!.jsonObject

    private fun view(case: String) = VoiceStrict.parse(status(case))

    private fun last(case: String): VoiceTrainingLast? =
        JarvisJson.decodeFromJsonElement(VoiceStatus.serializer(), status(case)).gate.training.last

    // ------------------------------------------------------------ the body --

    @Test
    fun `the clear is one mode on the existing route, with nothing else in the body`() {
        assertEquals("""{"mode":"clear"}""", VoiceTraining.CLEAR_BODY)
    }

    // --------------------------------------------------------- the answers --

    @Test
    fun `a waiting card says nothing is deleted yet, and never claims it cleared`() {
        val reply = VoiceTrainingReply(
            ok = true,
            pending = true,
            files = 7,
            message = "Approve the card on your PC or phone to clear it. Nothing is deleted until you do.",
        )
        val said = VoiceTraining.clearReply(reply)
        assertTrue(said.accepted)
        assertTrue(said.message.contains("Nothing is deleted until you do"))
        assertFalse("a waiting card is not a clear", said.message.contains("cleared", ignoreCase = true))
    }

    @Test
    fun `nothing-to-clear is the PC's own sentence, and it is not a card`() {
        val message = "There is nothing to clear: no saved voice training was found on this PC, " +
            "so no voice files are saved."
        val said = VoiceTraining.clearReply(
            VoiceTrainingReply(ok = true, cleared = false, trained = false, message = message),
        )
        assertFalse(said.accepted)
        assertEquals(message, said.message)
        assertFalse(said.message.contains("card was raised", ignoreCase = true))
    }

    @Test
    fun `another voice card waiting is refused in the PC's words`() {
        val said = VoiceTraining.clearReply(
            VoiceTrainingReply(
                error = "a voice card is already waiting for approval - approve or deny that one first",
                pending = true,
            ),
        )
        assertFalse(said.accepted)
        assertTrue(said.message.contains("already waiting for approval"))
        assertFalse(said.message.contains("cleared", ignoreCase = true))
    }

    @Test
    fun `a tier that cannot end in a person's yes is a refusal, never a card`() {
        val said = VoiceTraining.clearReply(
            VoiceTrainingReply(
                error = "change_own_config is tier 'auto' in jarvis-framework.toml; clearing your " +
                    "voice training needs a person to say yes, so it must be 'ask'",
            ),
        )
        assertFalse(said.accepted)
        assertTrue(said.message.contains("needs a person to say yes"))
        assertTrue(said.message.contains("must be 'ask'"))
    }

    @Test
    fun `an unreadable answer claims nothing`() {
        val said = VoiceTraining.clearReply(VoiceTrainingReply())
        assertFalse(said.accepted)
        assertTrue(said.message.contains("did not say whether it cleared anything"))
    }

    // --------------------------------------------------------- the outcome --

    @Test
    fun `the outcome lines tell the truth, and only for an outcome newer than the ask`() {
        assertEquals(
            VoiceTraining.CLEARED_LINE,
            VoiceTraining.clearOutcomeLine(VoiceTrainingLast(outcome = "cleared", at = 100.0), 10.0),
        )
        val denied = VoiceTraining.clearOutcomeLine(VoiceTrainingLast(outcome = "denied", at = 101.0), 100.0)
        assertTrue(denied!!.contains("You said no"))
        assertTrue(denied.contains("every saved voice file stays"))
        assertTrue(
            VoiceTraining.clearOutcomeLine(VoiceTrainingLast(outcome = "timed_out", at = 101.0), 100.0)!!
                .contains("Nobody answered the clear card"),
        )
        assertTrue(
            VoiceTraining.clearOutcomeLine(
                VoiceTrainingLast(outcome = "failed", reason = "could not delete 1 of 7 saved voice files", at = 101.0),
                100.0,
            )!!.contains("did not finish: could not delete 1 of 7 saved voice files"),
        )
        assertTrue(
            VoiceTraining.clearOutcomeLine(
                VoiceTrainingLast(outcome = "refused", reason = "the approval gate failed (RuntimeError)", at = 101.0),
                100.0,
            )!!.startsWith("Your PC refused the clear"),
        )
        // The same outcome the screen already saw BEFORE the ask is not this
        // clear's: the line needs no clock to agree across two devices.
        assertNull(VoiceTraining.clearOutcomeLine(VoiceTrainingLast(outcome = "denied", at = 100.0), 100.0))
        assertNull(VoiceTraining.clearOutcomeLine(null, 0.0))
        // An outcome that is not a clear is never reworded as one.
        assertNull(VoiceTraining.clearOutcomeLine(VoiceTrainingLast(outcome = "enrolled", at = 101.0), 100.0))
    }

    // -------------------------------------------------------- the waiting --

    @Test
    fun `a waiting voice card names itself and stops a second request`() {
        val pendingClear = VoiceStrict.View(clear = true, pendingKind = "clear")
        assertTrue(VoiceTraining.clearWaitingLine(pendingClear)!!.contains("A clear card is already waiting"))
        assertFalse(VoiceTraining.clearWaitingLine(pendingClear)!!.contains("cleared"))
        val pendingOther = VoiceStrict.View(clear = true, pendingKind = "enroll")
        assertTrue(VoiceTraining.clearWaitingLine(pendingOther)!!.contains("A voice card is already waiting"))
        assertNull(VoiceTraining.clearWaitingLine(VoiceStrict.View(clear = true, pendingKind = "")))
    }

    // ------------------------------------------------------ the capability --

    @Test
    fun `every real status says the PC understands the clear`() {
        for (case in strict["status"]!!.jsonObject.keys) {
            assertTrue(case, view(case).clear)
        }
    }

    @Test
    fun `an older PC - the clear flag taken out of a real status - offers no button`() {
        val real = status("strong_untrained")
        val gate = real["gate"]!!.jsonObject
        val training = JsonObject(gate["training"]!!.jsonObject - setOf("clear"))
        val older = JsonObject(real + ("gate" to JsonObject(gate + ("training" to training))))
        val v = VoiceStrict.parse(older)
        assertFalse(v.clear)
        // ...and the request is still one mode on the route an older PC reads
        // as a bad mode: nothing new to call, so no route-parity change.
        assertEquals("""{"mode":"clear"}""", VoiceTraining.CLEAR_BODY)
    }

    // ------------------------------------------------------- the words ------

    @Test
    fun `the screen's words promise the ONE card and what is not deleted`() {
        assertTrue(VoiceTraining.CLEAR_LABEL.startsWith("Clear previous voice training"))
        assertTrue(VoiceTraining.CLEAR_WHAT_IT_DOES.contains("ONE card approves it"))
        assertTrue(VoiceTraining.CLEAR_WHAT_IT_DOES.contains("nothing is deleted until you say yes"))
        assertTrue(VoiceTraining.CLEAR_WHAT_IT_DOES.contains("does not delete your custom speaking voices"))
        assertTrue(VoiceTraining.CLEARED_LINE.contains("Train your voice again"))
    }

}
