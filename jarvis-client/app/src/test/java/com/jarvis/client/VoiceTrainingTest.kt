package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.VoiceCalibration
import com.jarvis.client.net.VoiceStatus
import com.jarvis.client.net.VoiceTrainingLast
import com.jarvis.client.net.VoiceTrainingReply
import com.jarvis.client.net.enrollRequestBody
import com.jarvis.client.net.thresholdRequestBody
import com.jarvis.client.voice.VoiceTraining
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Train my voice": the sentences, the words on the screen, and the request.
 *
 * The status payloads below are what `backend/jarvis_speech.py`'s status()
 * builds (its `gate` block), trimmed to the keys these tests read.
 * `backend/test_voice_contract.py` checks the other direction: that the
 * desktop sends every field `VoiceModels.kt` declares.
 */
class VoiceTrainingTest {

    private fun status(json: String) = JarvisJson.decodeFromString(VoiceStatus.serializer(), json)

    private val untrained = status(
        """{"available": true,
            "listening": {"push_to_talk": false,
                          "push_to_talk_why": "Jarvis has not learned your voice yet. Use Train my voice on the Checks screen."},
            "gate": {"mode": "owner", "enabled": true, "enrolled": false, "samples": 0,
                     "threshold": 0.35, "embedder": "spectral-v1", "speaker_model": false,
                     "needs_retraining": false, "note": "",
                     "training": {"available": true, "pending": false,
                                  "limits": {"min_clips": 3, "max_clips": 8}}}}""",
    )

    private val trained = status(
        """{"available": true,
            "gate": {"mode": "owner", "enabled": true, "enrolled": true, "samples": 5,
                     "threshold": 0.31, "embedder": "sherpa-onnx:357a834f702b",
                     "speaker_model": true, "needs_retraining": false,
                     "training": {"available": true, "pending": false,
                                  "last": {"outcome": "enrolled", "at": 1.0, "samples": 5}}}}""",
    )

    // ------------------------------------------------------ the sentences ---

    @Test
    fun `twelve short sentences, all different, each a few seconds long`() {
        val s = VoiceTraining.SENTENCES
        assertEquals(12, s.size)
        assertEquals(12, s.toSet().size)
        for (line in s) {
            // Roughly two to four seconds read aloud: 6 to 11 words.
            val words = line.split(" ").size
            assertTrue("$words words: $line", words in 6..11)
            assertTrue("ends like a sentence: $line", line.last() in ".?!")
        }
    }

    @Test
    fun `four start with hey Jarvis, so the PC can learn how the owner says it`() {
        // jarvis_wakeword.build_verifier needs at least two it can hear.
        assertEquals(4, VoiceTraining.SENTENCES.count { it.startsWith("Hey Jarvis,") })
        assertEquals(3, VoiceTraining.OTHER_SENTENCES.size)
        assertEquals("phone", VoiceTraining.MIC)
    }

    @Test
    fun `the sentences cover different sounds`() {
        val all = VoiceTraining.SENTENCES.joinToString(" ").lowercase()
        // Every letter at least once - the first one is a pangram.
        for (c in 'a'..'z') assertTrue("no '$c'", c in all)
        assertTrue("a question, so the voice rises once", VoiceTraining.SENTENCES.any { it.endsWith("?") })
        assertTrue("the name the owner will say most", VoiceTraining.SENTENCES.any { "Jarvis" in it })
    }

    @Test
    fun `the intro is the plain one`() {
        assertEquals(
            "Jarvis only listens to your voice. Read these 12 short sentences so it learns what " +
                "you sound like, and how you say \"hey Jarvis\". It takes about two minutes.",
            VoiceTraining.INTRO,
        )
        assertEquals("Approve the card on your PC or phone to finish.", VoiceTraining.AFTER_SENDING)
    }

    // --------------------------------------------------------- the clips ----

    @Test
    fun `a clip must be one to ten seconds, the PC's own limits`() {
        assertNotNull(VoiceTraining.clipProblem(0.4f))
        assertNotNull(VoiceTraining.clipProblem(0.99f))
        assertNull(VoiceTraining.clipProblem(1.0f))
        assertNull(VoiceTraining.clipProblem(4.2f))
        assertNull(VoiceTraining.clipProblem(10.0f))
        assertNotNull(VoiceTraining.clipProblem(10.5f))
    }

    @Test
    fun `lengths read the same in every language`() {
        assertEquals("3.4 s", VoiceTraining.lengthLabel(3.43f))
        assertEquals("10.0 s", VoiceTraining.lengthLabel(10f))
    }

    @Test
    fun `nothing is sent while the link is stale, or before all twelve are recorded`() {
        val stale = "Not connected to the desktop, so this cannot be delivered."
        assertEquals(stale, VoiceTraining.sendBlocker(12, 12, stale))
        assertEquals(stale, VoiceTraining.sendBlocker(2, 12, stale))
        assertEquals("Record all 12 sentences first (11 done).", VoiceTraining.sendBlocker(11, 12, null))
        assertNull(VoiceTraining.sendBlocker(12, 12, null, totalSeconds = 45f))
        // Twelve ten-second clips would not fit in one request to the PC.
        val long = VoiceTraining.sendBlocker(12, 12, null, totalSeconds = 95f)
        assertNotNull(long)
        assertTrue(long!!.contains("80"))
    }

    // ------------------------------------------------------ the request -----

    @Test
    fun `the request is clips as base64, in order, and nothing else`() {
        val a = byteArrayOf(82, 73, 70, 70, 0, 1, 2)
        val b = byteArrayOf(-1, 0, 127, -128)
        val body = enrollRequestBody(listOf(a, b))
        val obj = JarvisJson.parseToJsonElement(body) as JsonObject
        assertEquals(setOf("clips"), obj.keys)
        val clips = obj["clips"] as JsonArray
        assertEquals(2, clips.size)
        val dec = java.util.Base64.getDecoder()
        assertArrayEquals(a, dec.decode((clips[0] as JsonPrimitive).content))
        assertArrayEquals(b, dec.decode((clips[1] as JsonPrimitive).content))
    }

    @Test
    fun `an empty list is still valid JSON`() {
        assertEquals("""{"clips":[]}""", enrollRequestBody(emptyList()))
    }

    @Test
    fun `the microphone and the mode go first, as plain words`() {
        val body = enrollRequestBody(listOf(byteArrayOf(1, 2)), mic = "phone", mode = "calibrate")
        val obj = JarvisJson.parseToJsonElement(body) as JsonObject
        assertEquals(setOf("mode", "mic", "clips"), obj.keys)
        assertEquals("calibrate", (obj["mode"] as JsonPrimitive).content)
        assertEquals("phone", (obj["mic"] as JsonPrimitive).content)
        val t = JarvisJson.parseToJsonElement(thresholdRequestBody(0.523, "phone")) as JsonObject
        assertEquals("threshold", (t["mode"] as JsonPrimitive).content)
        assertEquals("0.52", (t["threshold"] as JsonPrimitive).content)
        assertFalse("no clips in a threshold request", "clips" in t.keys)
    }

    // ------------------------------------------------ the state, in words ---

    @Test
    fun `not trained, trained with N samples, and unknown are three different lines`() {
        assertEquals(
            "Not trained yet. Until it is, Jarvis will not act on anyone's voice.",
            VoiceTraining.stateLine(untrained, answered = true),
        )
        assertEquals("Trained, from 5 samples.", VoiceTraining.stateLine(trained, answered = true))
        val perMic = status(
            """{"available": true, "gate": {"enrolled": true, "samples": 12,
                "prints": {"phone": {"trained": true, "samples": 12, "threshold": 0.4},
                           "desktop": {"trained": false}, "general": {"trained": false}}}}""",
        )
        assertEquals("Trained on this phone, from 12 samples.", VoiceTraining.stateLine(perMic, true))
        assertEquals(
            "Your PC's own microphone uses this one until it is trained separately.",
            VoiceTraining.desktopLine(perMic, true),
        )
        assertNull(VoiceTraining.desktopLine(untrained, true))
        // Not answering is not the same as "not trained".
        assertEquals(
            "Your PC has not answered yet, so this is not known.",
            VoiceTraining.stateLine(trained, answered = false),
        )
    }

    @Test
    fun `a waiting card and a changed voice check are said before 'trained'`() {
        val waiting = status(
            """{"gate": {"enrolled": true, "samples": 5,
                         "training": {"available": true, "pending": true, "clips": 5, "expires_in": 170}}}""",
        )
        assertEquals(
            "Waiting for you to approve the card on your PC or phone.",
            VoiceTraining.stateLine(waiting, answered = true),
        )
        val retrain = status("""{"gate": {"enrolled": true, "samples": 5, "needs_retraining": true}}""")
        assertTrue(VoiceTraining.stateLine(retrain, true).contains("Train your voice again"))
    }

    @Test
    fun `broad mode says training is optional`() {
        val broad = status("""{"gate": {"mode": "broad", "enrolled": false}}""")
        assertTrue(VoiceTraining.stateLine(broad, true).contains("optional"))
    }

    @Test
    fun `the basic-check warning shows only for the basic check, and only when known`() {
        val line = VoiceTraining.basicCheckLine(untrained, answered = true)
        assertNotNull(line)
        assertTrue(line!!.startsWith("Using the basic voice check"))
        assertTrue(line.contains("Install the better one on your PC"))
        assertNull(VoiceTraining.basicCheckLine(trained, answered = true))
        assertNull(VoiceTraining.basicCheckLine(untrained, answered = false))
        assertNull(VoiceTraining.basicCheckLine(VoiceStatus(available = false), answered = true))
    }

    @Test
    fun `a status with no gate at all reads as not trained, never as trained`() {
        // An older desktop: no `gate` key. The defaults are the refusing ones.
        val old = status("""{"listening": {"push_to_talk": true}}""")
        assertFalse(old.gate.enrolled)
        assertFalse(old.gate.speakerModel)
        assertFalse(old.gate.training.available)
        assertTrue(VoiceTraining.stateLine(old, true).startsWith("Not trained"))
    }

    @Test
    fun `the last outcome, in words`() {
        assertEquals(
            "Last training was approved: 5 samples saved.",
            VoiceTraining.lastLine(trained.gate.training.last),
        )
        assertEquals(
            "Last training was denied on the card. Nothing changed.",
            VoiceTraining.lastLine(VoiceTrainingLast(outcome = "denied")),
        )
        assertEquals(
            "Nobody answered the last training card in time. Nothing changed.",
            VoiceTraining.lastLine(VoiceTrainingLast(outcome = "timed_out")),
        )
        assertEquals(
            "The last training failed: no usable audio in those clips.",
            VoiceTraining.lastLine(VoiceTrainingLast(outcome = "failed", reason = "no usable audio in those clips")),
        )
        assertNull(VoiceTraining.lastLine(null))
        assertNull(untrained.gate.training.last)
        assertEquals(
            "Last training was approved: 12 samples saved. Its \"hey Jarvis\" check was built too.",
            VoiceTraining.lastLine(
                VoiceTrainingLast(outcome = "enrolled", samples = 12, wakeCheck = "built from 4 \"hey Jarvis\" sentences"),
            ),
        )
        assertEquals(
            "Last training was approved: 12 samples saved. Its \"hey Jarvis\" check was not " +
                "built (\"hey Jarvis\" was heard in 1 of the sentences; it needs at least 2).",
            VoiceTraining.lastLine(
                VoiceTrainingLast(
                    outcome = "enrolled", samples = 12,
                    wakeCheck = "not built: \"hey Jarvis\" was heard in 1 of the sentences; it needs at least 2",
                ),
            ),
        )
        assertEquals(
            "The new setting was approved: voices must now score 0.52 to pass.",
            VoiceTraining.lastLine(VoiceTrainingLast(outcome = "threshold_set", threshold = 0.52)),
        )
    }

    // ------------------------------------------- the "someone else" check ---

    @Test
    fun `the check is offered only by a PC that understands it, with a print to check`() {
        assertFalse("an older PC would read it as a training", VoiceTraining.canCheck(trained, true))
        val ready = status(
            """{"available": true, "gate": {"enrolled": true,
                "prints": {"phone": {"trained": true, "samples": 12}},
                "training": {"available": true, "calibrate": true}}}""",
        )
        assertTrue(VoiceTraining.canCheck(ready, true))
        assertFalse(VoiceTraining.canCheck(ready, false))
    }

    @Test
    fun `the result says what would pass, and proposes only a safe, stricter bar`() {
        fun cal(json: String) = JarvisJson.decodeFromString(VoiceCalibration.serializer(), json)
        val apart = VoiceTraining.checkResult(
            cal("""{"ok": true, "scores": [0.21, 0.4, 0.33], "threshold": 0.35, "owner_low": 0.62,
                    "others_high": 0.4, "separated": true, "suggested": 0.51}"""),
        )
        assertTrue(apart.ok)
        assertEquals(0.51, apart.suggested!!, 1e-9)
        assertTrue(apart.message, apart.message.startsWith("1 of their 3 clips would pass as you now."))
        assertTrue(apart.message, apart.message.contains("0.51 (now 0.35)"))

        val close = VoiceTraining.checkResult(
            cal("""{"ok": true, "scores": [0.7, 0.5], "threshold": 0.35, "separated": false,
                    "message": "Their voice came as close to yours as your own clips did."}"""),
        )
        assertNull(close.suggested)
        assertTrue(close.message, close.message.startsWith("2 of their 2 clips would pass"))

        val fine = VoiceTraining.checkResult(
            cal("""{"ok": true, "scores": [0.1, 0.12], "threshold": 0.5, "separated": true, "suggested": 0.4}"""),
        )
        assertNull("never suggests LOWERING the bar", fine.suggested)
        assertTrue(fine.message.startsWith("Good: none of their 2 clips"))

        val refused = VoiceTraining.checkResult(cal("""{"error": "no voice has been trained yet"}"""))
        assertFalse(refused.ok)
        assertEquals("No voice has been trained yet.", refused.message)
    }

    // ------------------------------------------------------- the answer -----

    @Test
    fun `a 202 says approve the card, a refusal says the PC's own sentence`() {
        val ok = JarvisJson.decodeFromString(
            VoiceTrainingReply.serializer(),
            """{"ok": true, "pending": true, "clips": 5, "seconds": 21.4,
                "message": "Approve the card on your PC or phone to finish. Nothing changes until you do."}""",
        )
        assertTrue(VoiceTraining.accepted(ok))
        assertEquals(VoiceTraining.AFTER_SENDING, VoiceTraining.replyLine(ok))

        val bad = JarvisJson.decodeFromString(
            VoiceTrainingReply.serializer(),
            """{"error": "clip 3 is too short (0.6 s) - read the whole sentence"}""",
        )
        assertFalse(VoiceTraining.accepted(bad))
        assertEquals("Clip 3 is too short (0.6 s) - read the whole sentence.", VoiceTraining.replyLine(bad))

        val busy = JarvisJson.decodeFromString(
            VoiceTrainingReply.serializer(),
            """{"error": "a voice training is already waiting for approval - approve or deny that card first",
                "pending": true, "expires_in": 120}""",
        )
        assertFalse(VoiceTraining.accepted(busy))
        assertEquals(120, busy.expiresIn)
    }
}
