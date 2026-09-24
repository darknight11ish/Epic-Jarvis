package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.CustomVoices
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream

/**
 * Custom voices on the phone, against what the PC REALLY answers:
 * `contract/phone-voice-cases.json` (`voices`), written by
 * tools/gen_phone_voice_cases.py from backend/jarvis_voices.py's own
 * status(), create(), switch(), delete() and set_better().
 */
class CustomVoicesTest {

    private val voices: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/phone-voice-cases.json")) {
            "contract/phone-voice-cases.json is missing - run tools/gen_phone_voice_cases.py"
        }.readText()
        (JarvisJson.parseToJsonElement(text) as JsonObject)["voices"]!!.jsonObject
    }

    private fun raw(case: String) = voices["status"]!!.jsonObject[case]!!.jsonObject

    private fun status(case: String) = requireNotNull(CustomVoices.parse(raw(case))) { "$case did not parse" }

    private fun answer(case: String): CustomVoices.Answer {
        val a = voices["answers"]!!.jsonObject[case]!!.jsonObject
        return CustomVoices.answer(a["status"]!!.jsonPrimitive.int, a["body"]!!.jsonObject)
    }

    private val stale = "Not connected to the desktop, so this cannot be delivered."

    // ------------------------------------------------------------ reading --

    @Test
    fun `every real status reads`() {
        for (case in voices["status"]!!.jsonObject.keys) {
            val s = status(case)
            assertTrue(case, s.voices.first().builtin)
            assertEquals(case, CustomVoices.BUILTIN, s.voices.first().id)
            assertEquals(case, 5, s.sentences.size)
        }
    }

    @Test
    fun `the list, the one in use, the engine and the limits`() {
        val s = status("speaking_custom")
        assertEquals("grandpa", s.active)
        assertEquals("Grandpa", s.activeName)
        assertEquals("zipvoice", s.speakingWith)
        assertEquals(listOf("grandpa"), s.custom.map { it.id })
        assertEquals(5.3, s.custom[0].seconds, 0.0)
        assertEquals("Jarvis speaks in \"Grandpa\", made by ZipVoice, on your PC's processor.", CustomVoices.nowLine(s))
        assertNull(CustomVoices.fallbackLine(s))
        assertEquals(3.0, s.limits.minSeconds, 0.0)
        assertEquals(40, s.limits.maxNameChars)
        assertEquals("Jarvis speaks in its built-in voice.", CustomVoices.nowLine(status("empty")))
    }

    @Test
    fun `when the chosen voice cannot be made, the reason is shown`() {
        val s = status("fallback")
        assertEquals("kokoro", s.speakingWith)
        assertEquals(
            "Using the built-in voice instead, because ZipVoice could not be loaded (RuntimeError).",
            CustomVoices.fallbackLine(s),
        )
        assertEquals(
            listOf("Built-in voice: 28 characters, ready in 0.5 s for 1.0 s of speech - built-in voice " +
                "used because ZipVoice could not be loaded (RuntimeError)."),
            CustomVoices.timingLines(s),
        )
    }

    @Test
    fun `recent timings, newest first, never any text`() {
        val lines = CustomVoices.timingLines(status("speaking_custom"))
        assertEquals(listOf("ZipVoice: 54 characters, ready in 0.5 s for 3.6 s of speech."), lines)
        assertTrue(CustomVoices.timingLines(status("empty")).isEmpty())
    }

    @Test
    fun `a broken folder is listed with its reason`() {
        val broken = status("broken_folder").voices.first { it.id == "broken" }
        assertFalse(broken.ready)
        assertTrue(broken.why, broken.why.contains("its recording or its words are missing"))
    }

    @Test
    fun `a waiting card and the last card's outcome`() {
        assertEquals(
            "Waiting for your approval to add \"Aunt May\". Approve it on your PC or on this phone's Home screen.",
            CustomVoices.pendingLine(status("create_waiting")),
        )
        assertNull(CustomVoices.pendingLine(status("empty")))
        assertEquals("The voice \"Grandpa\" was added. Switch to it to hear it.", CustomVoices.lastLine(status("one_voice")))
    }

    @Test
    fun `an older PC, or none installed, is said plainly`() {
        assertTrue(CustomVoices.read(ApiResult.Failed(ApiError.NotFound)) is CustomVoices.Read.Missing)
        assertTrue(CustomVoices.read(ApiResult.Failed(ApiError.NotAvailable)) is CustomVoices.Read.Missing)
        assertTrue(CustomVoices.read(ApiResult.Ok(raw("empty"))) is CustomVoices.Read.Loaded)
        assertNull(CustomVoices.parse(JsonObject(mapOf("available" to JsonPrimitive(false)))))
    }

    // ------------------------------------------------------------ answers --

    @Test
    fun `adding asks - a 202 and the PC's own words`() {
        val a = answer("create")
        assertEquals(202, a.code)
        assertTrue(a.pending)
        assertTrue(a.accepted)
        assertEquals("Approve the card on your PC or phone to add the voice. Nothing is kept until you do.",
            CustomVoices.answerLine(a))
    }

    @Test
    fun `a 202 is a card up, whatever else the body says`() {
        // The real 202, with its `pending` field taken out: the status code alone says a card is up.
        val a = voices["answers"]!!.jsonObject["create"]!!.jsonObject
        val body = JsonObject(a["body"]!!.jsonObject - "pending")
        assertTrue(CustomVoices.answer(202, body).pending)
        assertFalse(CustomVoices.answer(200, body).pending)
    }

    @Test
    fun `the owner's own voice is refused, with the owner's wording first`() {
        val a = answer("create_owner_voice")
        assertEquals(409, a.code)
        assertEquals("owner_voice", a.refused)
        assertFalse(a.accepted)
        val line = CustomVoices.answerLine(a)
        assertTrue(line, line.startsWith("This sounds like you, so Jarvis won't copy it. This recording sounds too much like YOUR voice"))
    }

    @Test
    fun `refusals are the PC's sentences`() {
        assertEquals("There is already a voice called \"Grandpa\".", CustomVoices.answerLine(answer("create_name_taken")))
        assertTrue(CustomVoices.answerLine(answer("create_words_do_not_fit")).startsWith("The words do not fit the recording"))
        assertTrue(CustomVoices.answerLine(answer("create_too_short")).startsWith("The recording has 1.8 seconds of speech"))
        assertEquals("A voice card is already waiting - approve or deny it first.",
            CustomVoices.answerLine(answer("create_card_waiting")))
        assertEquals("There is no voice with that id.", CustomVoices.answerLine(answer("active_unknown")))
        assertEquals("The built-in voice cannot be deleted.", CustomVoices.answerLine(answer("delete_builtin")))
        assertTrue(CustomVoices.answerLine(answer("better_no_card")).startsWith("The better voice cannot be turned on"))
    }

    @Test
    fun `switching to a custom voice asks, back to built-in is at once`() {
        val custom = answer("active_custom")
        assertEquals(202, custom.code)
        assertTrue(custom.pending)
        val builtin = answer("active_builtin")
        assertEquals(200, builtin.code)
        assertFalse(builtin.pending)
        assertEquals("builtin", builtin.active)
        assertEquals("Jarvis speaks in its built-in voice.", CustomVoices.answerLine(builtin))
        assertFalse(answer("active_already").pending)
    }

    @Test
    fun `deleting is at once and says which voice is in use after`() {
        val d = answer("delete")
        assertEquals(200, d.code)
        assertTrue(d.accepted)
        assertEquals("builtin", d.active)
    }

    @Test
    fun `the better voice - on asks, off is at once`() {
        assertTrue(answer("better_on").pending)
        assertEquals(202, answer("better_on").code)
        assertFalse(answer("better_off").pending)
        assertEquals("The better voice is off.", CustomVoices.answerLine(answer("better_off")))
        assertTrue(CustomVoices.answerLine(answer("better_waiting")).contains("already waiting"))
        val can = status("better_can_turn_on").better
        assertTrue(can.canTurnOn)
        assertFalse(status("empty").better.canTurnOn)
        assertEquals("Waiting for your approval to turn it on. Approve it on your PC or on this phone's Home screen.",
            CustomVoices.betterLine(status("better_waiting")))
        assertTrue(CustomVoices.betterLine(status("empty")).startsWith("Needs a capable second graphics card"))
    }

    // ---------------------------------------------------------------- rules --

    @Test
    fun `only the requests that raise a card are held on a stale link`() {
        val s = status("one_voice")
        assertEquals(stale, CustomVoices.blocker(raisesCard = true, linkBlocker = stale, status = s))
        assertNull(CustomVoices.blocker(raisesCard = false, linkBlocker = stale, status = s))
        assertNull(CustomVoices.blocker(raisesCard = true, linkBlocker = null, status = s))
        assertNotNull(CustomVoices.blocker(raisesCard = true, linkBlocker = null, status = status("create_waiting")))
    }

    @Test
    fun `add is checked on the phone first`() {
        val s = status("one_voice")
        val wav = wav(16_000, 1, 16, 5.0)
        assertEquals(stale, CustomVoices.createBlocker("Aunt May", "Hello", wav, 5.0, s, stale))
        assertEquals("Give the voice a name.", CustomVoices.createBlocker(" ", "Hello", wav, 5.0, s, null))
        assertEquals("There is already a voice called \"grandpa\".",
            CustomVoices.createBlocker("grandpa", "Hello", wav, 5.0, s, null))
        assertEquals("Record the sentence, or pick an audio file.", CustomVoices.createBlocker("Aunt May", "Hello", null, null, s, null))
        assertEquals("Type exactly what is said in the recording.", CustomVoices.createBlocker("Aunt May", "  ", wav, 5.0, s, null))
        assertTrue(CustomVoices.createBlocker("Aunt May", "Hello", wav, 2.0, s, null)!!.contains("at least 3 seconds"))
        assertNull(CustomVoices.createBlocker("Aunt May", "Hello there", wav, 5.0, s, null))
        assertNotNull(CustomVoices.createBlocker("Aunt May", "Hello there", wav, 5.0, status("create_waiting"), null))
    }

    @Test
    fun `the create body carries the shown words exactly, escaped`() {
        val body = CustomVoices.createBody(" Aunt \"May\" ", byteArrayOf(1, 2, 3), "Hello, \"there\".")
        val o = JarvisJson.parseToJsonElement(body).jsonObject
        assertEquals("Aunt \"May\"", o["name"]!!.jsonPrimitive.content)
        assertEquals("Hello, \"there\".", o["transcript"]!!.jsonPrimitive.content)
        assertEquals("AQID", o["clip"]!!.jsonPrimitive.content)
        assertEquals("{\"voice\":\"builtin\"}", CustomVoices.activeBody("builtin"))
        assertEquals("{\"enabled\":false}", CustomVoices.betterBody(false))
    }

    // ------------------------------------------------------------ WAV files --

    @Test
    fun `a picked file is checked the way the PC reads it`() {
        assertEquals(CustomVoices.WavCheck.Ok(5.0), CustomVoices.checkWav(wav(24_000, 1, 16, 5.0)))
        assertEquals(CustomVoices.WavCheck.Ok(4.0), CustomVoices.checkWav(wav(48_000, 2, 24, 4.0)))
        assertTrue(CustomVoices.checkWav(wav(16_000, 1, 8, 2.0)) is CustomVoices.WavCheck.Bad)
        assertTrue(CustomVoices.checkWav(wav(96_000, 1, 16, 1.0)) is CustomVoices.WavCheck.Bad)
        assertTrue(CustomVoices.checkWav(wav(16_000, 1, 16, 1.0, format = 3)) is CustomVoices.WavCheck.Bad)
        assertEquals(
            CustomVoices.WavCheck.Bad("That file is not a WAV recording. Pick a .wav file."),
            CustomVoices.checkWav("ID3 not a wav at all".toByteArray()),
        )
        assertTrue(CustomVoices.checkWav(ByteArray(3_000_000)) is CustomVoices.WavCheck.Bad)
    }

    @Test
    fun `each engine in a line, with the PC's reason when it cannot speak`() {
        assertEquals(
            listOf(
                "Built-in voice (Kokoro): ready.",
                "ZipVoice, on your PC's processor: ZipVoice could not be loaded (RuntimeError).",
                "Better voice (F5-TTS), on the second graphics card: Not running - it starts when " +
                    "Jarvis speaks in a custom voice.",
            ),
            CustomVoices.engineLines(status("fallback")),
        )
    }

    @Test
    fun `a picked file is kept only when it can be used, and a recording must be long enough`() {
        val ok = CustomVoices.picked(wav(24_000, 1, 16, 5.0))
        assertNull(ok.problem)
        assertEquals(5.0, ok.seconds!!, 0.0)
        val bad = CustomVoices.picked("not a wav".toByteArray())
        assertEquals(0, bad.bytes.size)
        assertNotNull(bad.problem)
        assertEquals("That was too short: read the whole sentence, at least 3 seconds.",
            CustomVoices.recordingProblem(2.0f))
        assertNull(CustomVoices.recordingProblem(4.5f))
        assertNotNull(CustomVoices.recordingProblem(12.5f))
    }

    @Test
    fun `engine words`() {
        assertEquals("ZipVoice, on your PC's processor", CustomVoices.engineWords("zipvoice"))
        assertTrue(CustomVoices.engineWords("f5").contains("second graphics card"))
        val s = status("speaking_custom")
        assertTrue(CustomVoices.deleteQuestion(s.custom[0], s).endsWith("Jarvis goes back to its built-in voice."))
    }

    private fun wav(rate: Int, channels: Int, bits: Int, seconds: Double, format: Int = 1): ByteArray {
        val frame = channels * bits / 8
        val data = (rate * seconds).toInt() * frame
        val out = ByteArrayOutputStream()
        fun le(v: Long, n: Int) { for (i in 0 until n) out.write(((v shr (8 * i)) and 0xFF).toInt()) }
        out.write("RIFF".toByteArray()); le(36L + data, 4); out.write("WAVE".toByteArray())
        out.write("fmt ".toByteArray()); le(16, 4); le(format.toLong(), 2); le(channels.toLong(), 2)
        le(rate.toLong(), 4); le((rate * frame).toLong(), 4); le(frame.toLong(), 2); le(bits.toLong(), 2)
        out.write("data".toByteArray()); le(data.toLong(), 4); out.write(ByteArray(data))
        return out.toByteArray()
    }
}
