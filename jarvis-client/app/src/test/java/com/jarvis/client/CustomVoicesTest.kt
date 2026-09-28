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
            "Jarvis is using its built-in voice instead, because ZipVoice could not be loaded (RuntimeError).",
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
    fun `when the PC could not check whose voice it is, it says so first`() {
        // Hand-built: the fixture has no such case. The shape is
        // backend/jarvis_voices.py's own refusal ("refused" plus the PC's
        // sentence), carried in `error` like the owner_voice one above.
        for (why in listOf("owner_check_failed", "no_voice_check")) {
            val a = CustomVoices.Answer(
                code = 409, ok = false, pending = false,
                error = "the recording could not be compared with your voice print (too quiet or too short), so it was refused",
                message = "", refused = why, active = "",
            )
            assertEquals(
                why,
                "Jarvis could not make sure this is not your own voice, so it won't copy it. " +
                    "The recording could not be compared with your voice print (too quiet or too short), so it was refused.",
                CustomVoices.answerLine(a),
            )
            assertEquals(
                why,
                CustomVoices.OWNER_CHECK_FAILED,
                CustomVoices.answerLine(a.copy(error = "")),
            )
        }
    }

    @Test
    fun `the add form and the timings use the desktop's words`() {
        assertEquals(
            "Only add the voice of someone who has agreed to it. A recording that sounds like you is refused. " +
                "The recording stays on your PC; nothing is sent anywhere else.",
            CustomVoices.CONSENT,
        )
        assertEquals("How long speaking took", CustomVoices.TIMINGS_TITLE)
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
    fun `how fast Jarvis speaks - the PC's choices and words, no card`() {
        val sp = requireNotNull(status("empty").speed) { "no speed block" }
        assertEquals(listOf("slower", "normal", "faster"), sp.choices.map { it.id })
        assertEquals(listOf("Slower", "Normal", "Faster"), sp.choices.map { it.label })
        assertEquals("normal", sp.choice)
        assertEquals(CustomVoices.SPEED_TITLE, sp.title)
        assertTrue(sp.detail, sp.detail.contains("never asks first"))
        assertEquals("", sp.note)
        assertEquals("faster", status("speed_faster").speed?.choice)
        assertEquals("{\"speed\":\"faster\"}", CustomVoices.speedBody("faster"))
        val a = answer("speed_faster")
        assertTrue(a.accepted)
        assertFalse("no card for the speed", a.pending)
        assertEquals("Jarvis now speaks faster.", CustomVoices.answerLine(a))
        assertEquals("The speed must be slower, normal or faster.", CustomVoices.answerLine(answer("speed_bad")))
        // A PC too old to have it sends no `speed`: nothing is shown.
        assertNull(CustomVoices.parse(JsonObject(raw("empty") - "speed"))?.speed)
    }

    @Test
    fun `Jarvis's built-in voice - the PC's choices and words, no card`() {
        val sk = requireNotNull(status("empty").speaker) { "no speaker block" }
        assertEquals((0..10).map { it.toString() }, sk.choices.map { it.id })
        assertEquals("American (female)", sk.choices[0].label)
        assertEquals("British (male) - George", sk.choices[9].label)
        assertEquals("0", sk.choice)
        assertEquals(CustomVoices.SPEAKER_TITLE, sk.title)
        assertEquals("", sk.note)
        assertEquals("9", status("speaker_9").speaker?.choice)
        assertEquals("{\"speaker\":\"9\"}", CustomVoices.speakerBody("9"))
        val a = answer("speaker_9")
        assertTrue(a.accepted)
        assertFalse("no card for the built-in voice choice", a.pending)
        assertEquals("Jarvis's built-in voice is now British (male) - George.", CustomVoices.answerLine(a))
        assertEquals("Choose one of the listed voices.", CustomVoices.answerLine(answer("speaker_bad")))
        // A PC too old to have it sends no `speaker`: nothing is shown.
        assertNull(CustomVoices.parse(JsonObject(raw("empty") - "speaker"))?.speaker)
    }

    @Test
    fun `Voice follows the face - an on-off switch, the PC's words and line, no card`() {
        // No face saved yet: on by default, and it says there is nothing to follow.
        val none = requireNotNull(status("empty").faceVoice) { "no face_voice block" }
        assertTrue("on by default", none.enabled)
        assertFalse(none.speaking)
        assertEquals(CustomVoices.FACE_TITLE, none.title)
        assertEquals("No face is saved on this PC yet, so there is no animal voice to use.", none.line)
        // The red panda showing: its own voice speaks, and the built-in
        // voice choice says so.
        val panda = requireNotNull(status("face_showing").faceVoice)
        assertTrue(panda.speaking)
        assertEquals("Speaking as the Red Panda: Bella, a little higher.", panda.line)
        assertTrue(status("face_showing").speaker!!.note.contains("Red Panda face is showing"))
        val off = requireNotNull(status("face_off").faceVoice)
        assertFalse(off.enabled)
        assertEquals("Off: the built-in voice stays the same whatever the face.", off.line)
        assertEquals("{\"enabled\":true}", CustomVoices.faceBody(true))
        assertEquals("{\"enabled\":false}", CustomVoices.faceBody(false))
        val a = answer("face_off")
        assertTrue(a.accepted)
        assertFalse("no card for the face's voice", a.pending)
        assertEquals("Jarvis's voice now stays the same whatever the face.", CustomVoices.answerLine(a))
        val b = answer("face_on")
        assertTrue(b.accepted)
        assertFalse("no card for the face's voice", b.pending)
        assertEquals("Jarvis's voice now follows the face.", CustomVoices.answerLine(b))
        assertEquals("Choose on or off.", CustomVoices.answerLine(answer("face_bad")))
        // A PC too old to have it sends no `face_voice`: nothing is shown.
        assertNull(CustomVoices.parse(JsonObject(raw("empty") - "face_voice"))?.faceVoice)
    }

    @Test
    fun `each animal's voice - the PC's rows, choices and words, no card`() {
        for (case in voices["status"]!!.jsonObject.keys) {
            val fv = requireNotNull(status(case).faceVoice) { "$case: no face_voice" }
            assertEquals(case, listOf("redpanda", "pygmyowl", "seaotter"), fv.animals.map { it.face })
            assertEquals(case, 11, fv.choices.voices.size)
            assertEquals(case, listOf("slower", "normal", "faster"), fv.choices.paces.map { it.id })
            assertEquals(case, -3.0, fv.choices.pitchMin, 0.0)
            assertEquals(case, 4.0, fv.choices.pitchMax, 0.0)
            assertEquals(case, 0.5, fv.choices.pitchStep, 0.0)
            assertEquals(case, CustomVoices.ANIMALS_TITLE, fv.animalsTitle)
        }
        val own = requireNotNull(status("face_showing").faceVoice).animals
        assertEquals(
            listOf(Triple("1", 2.0, "normal"), Triple("2", 1.0, "slower"), Triple("4", 3.0, "faster")),
            own.map { Triple(it.speaker, it.semitones, it.pace) },
        )
        assertFalse(own.any { it.changed })
        assertEquals("Bella, 2 steps higher, at normal pace.", own[0].line)
        val panda = requireNotNull(status("animal_changed").faceVoice).animals[0]
        assertEquals("3", panda.speaker)
        assertEquals(-1.5, panda.semitones, 0.0)
        assertEquals("faster", panda.pace)
        assertTrue(panda.changed)
        assertEquals("Sarah, 1.5 steps deeper, a little faster.", panda.line)
        assertEquals(
            "Speaking as the Red Panda: Sarah, a little deeper.",
            requireNotNull(status("animal_changed").faceVoice).line,
        )
        val set = answer("animal_set")
        assertTrue(set.accepted)
        assertFalse("no card for an animal's voice", set.pending)
        assertEquals(
            "The Red Panda's voice is now Sarah, 1.5 steps deeper, a little faster.",
            CustomVoices.answerLine(set),
        )
        assertEquals("The Red Panda speaks in its own voice again.", CustomVoices.answerLine(answer("animal_reset")))
        assertEquals(
            "The pitch must be from 3 steps deeper to 4 steps higher, in half steps.",
            CustomVoices.answerLine(answer("animal_bad")),
        )
        assertEquals(
            "Choose the Red Panda, the Pygmy Owl or the Sea Otter.",
            CustomVoices.answerLine(answer("animal_try_bad")),
        )
        // A PC too old to have the rows: the switch alone, no rows.
        val old = JsonObject(raw("empty") + ("face_voice" to JsonObject(mapOf("enabled" to JsonPrimitive(true)))))
        assertTrue(requireNotNull(CustomVoices.parse(old)?.faceVoice).animals.isEmpty())
    }

    @Test
    fun `each animal's voice - what is sent, and the pitch in words`() {
        assertEquals(
            "{\"face\":\"redpanda\",\"speaker\":\"3\",\"semitones\":-1.5,\"pace\":\"faster\"}",
            CustomVoices.animalBody("redpanda", "3", -1.5, "faster"),
        )
        assertEquals("2.0", CustomVoices.halfSteps(2.0))
        assertEquals("0.5", CustomVoices.halfSteps(0.4999))
        assertEquals("0.0", CustomVoices.halfSteps(Double.NaN))
        assertEquals("{\"face\":\"seaotter\",\"reset\":true}", CustomVoices.animalResetBody("seaotter"))
        assertEquals("{\"face\":\"pygmyowl\"}", CustomVoices.animalTryBody("pygmyowl"))
        val c = CustomVoices.AnimalChoices()
        assertEquals(2.5, CustomVoices.nextPitch(2.0, up = true, c)!!, 0.0)
        assertEquals(-3.0, CustomVoices.nextPitch(-2.5, up = false, c)!!, 0.0)
        assertNull("no deeper than 3 steps", CustomVoices.nextPitch(-3.0, up = false, c))
        assertNull("no higher than 4 steps", CustomVoices.nextPitch(4.0, up = true, c))
        assertEquals(
            listOf("2 steps higher", "1.5 steps deeper", "Normal pitch", "1 step higher", "0.5 steps higher"),
            listOf(2.0, -1.5, 0.0, 1.0, 0.5).map { CustomVoices.pitchWords(it) },
        )
        assertEquals(listOf("+2", "-1.5", "0"), listOf(2.0, -1.5, -0.0).map { CustomVoices.pitchShort(it) })
    }

    @Test
    fun `Pocket TTS, if it ever replaces ZipVoice, is named in ZipVoice's place`() {
        assertEquals("Pocket TTS, on your PC's processor", CustomVoices.engineWords("pocket"))
        val s = status("fallback")
        val swapped = s.copy(engines = s.engines - "zipvoice" + ("pocket" to CustomVoices.Engine(true, "")))
        val lines = CustomVoices.engineLines(swapped)
        assertEquals("Pocket TTS, on your PC's processor: ready.", lines[1])
        assertFalse(lines.any { it.contains("ZipVoice") })
        assertEquals(3, lines.size)
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
