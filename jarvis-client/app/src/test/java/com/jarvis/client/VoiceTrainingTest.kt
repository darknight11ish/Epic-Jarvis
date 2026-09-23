package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.VoiceStatus
import com.jarvis.client.net.VoiceTrainingLast
import com.jarvis.client.net.VoiceTrainingReply
import com.jarvis.client.net.enrollRequestBody
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
    fun `five sentences, all different, each a few seconds long`() {
        val s = VoiceTraining.SENTENCES
        assertEquals(5, s.size)
        assertEquals(5, s.toSet().size)
        for (line in s) {
            // Roughly three to six seconds read aloud: 8 to 14 words.
            val words = line.split(" ").size
            assertTrue("$words words: $line", words in 8..14)
            assertTrue("ends like a sentence: $line", line.last() in ".?!")
        }
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
            "Jarvis only listens to your voice. Read these 5 sentences so it learns what you " +
                "sound like. It takes about a minute.",
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
    fun `nothing is sent while the link is stale, or before all five are recorded`() {
        val stale = "Not connected to the desktop, so this cannot be delivered."
        assertEquals(stale, VoiceTraining.sendBlocker(5, 5, stale))
        assertEquals(stale, VoiceTraining.sendBlocker(2, 5, stale))
        assertEquals("Record all 5 sentences first (4 done).", VoiceTraining.sendBlocker(4, 5, null))
        assertNull(VoiceTraining.sendBlocker(5, 5, null))
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

    // ------------------------------------------------ the state, in words ---

    @Test
    fun `not trained, trained with N samples, and unknown are three different lines`() {
        assertEquals(
            "Not trained yet. Until it is, Jarvis will not act on anyone's voice.",
            VoiceTraining.stateLine(untrained, answered = true),
        )
        assertEquals("Trained, from 5 samples.", VoiceTraining.stateLine(trained, answered = true))
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
