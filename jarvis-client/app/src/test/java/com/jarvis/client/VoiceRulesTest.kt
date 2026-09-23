package com.jarvis.client

import com.jarvis.client.audio.Wav
import com.jarvis.client.net.Heard
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.VoiceStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs

/**
 * The rules of the voice path that are safety rather than behaviour.
 *
 * The shapes below were copied out of `jarvis_speech.py`, not out of the prose.
 */
class VoiceRulesTest {

    /**
     * The nested half of what `backend/jarvis_speech.py`'s status() builds,
     * for a trained owner on a PC with speech-to-text set up. (Before
     * 2026-09-23 this comment said "exactly what status() builds" and it was
     * not: status() sent none of these keys. `backend/test_voice_contract.py`
     * now checks the real output against VoiceModels.kt.)
     */
    private val realStatus = """
        {"available": true,
         "listening": {"push_to_talk": true, "push_to_talk_why": "", "wake_word": false,
                       "wake_word_why": "off unless you turn it on: a phone's microphone goes wherever you do"},
         "stt": {"engine": "sherpa-onnx", "available": true, "status": "ready",
                 "client_fallback_ok": false},
         "tts": {"engine": "sherpa-onnx", "available": false,
                 "status": "no Kokoro model files on disk yet", "client_fallback_ok": true},
         "audio_in": {"format": "WAV, 16-bit mono PCM", "sample_rate": 16000,
                      "max_seconds": 30.0, "client_stt_allowed": false,
                      "why": "the voice check can only check a voice if it is given the voice"},
         "gate": {"mode": "owner", "enabled": true, "enrolled": true, "samples": 5,
                  "threshold": 0.31, "embedder": "spectral-v1", "speaker_model": false,
                  "needs_retraining": false, "note": "",
                  "training": {"available": true, "pending": false}}}
    """.trimIndent()

    private fun status(json: String) = JarvisJson.decodeFromString(VoiceStatus.serializer(), json)

    @Test
    fun `the server forbids client-side speech-to-text and this client reads it`() {
        // The brief asks for this assertion by name. The field exists so the
        // rule is checkable rather than merely written down: a client that
        // transcribed locally would send text, the owner voice-print gate
        // would have nothing left to examine, and "is this the owner?" would
        // quietly become "is this someone holding the owner's phone?".
        assertFalse(status(realStatus).audioIn.clientSttAllowed)
    }

    @Test
    fun `an absent client_stt_allowed is false, not permissive`() {
        // Fail closed. A server too old to carry the field must not be read as
        // permission to transcribe here.
        assertFalse(status("""{"audio_in": {}}""").audioIn.clientSttAllowed)
        assertFalse(status("{}").audioIn.clientSttAllowed)
    }

    @Test
    fun `the wake word is off unless the desktop says otherwise`() {
        assertFalse(status(realStatus).wakeWordOn)
        assertFalse(status("{}").wakeWordOn)
        assertTrue(
            status("""{"listening": {"push_to_talk": true, "wake_word": true}}""").wakeWordOn,
        )
    }

    @Test
    fun `a failed status call hides the microphone rather than offering it`() {
        // §2: a capability reporting false means hide the UI, not show a button
        // that 404s. The refusing default is the whole point.
        assertFalse(VoiceStatus(available = false).canPushToTalk)
        assertFalse(status("""{"available": false, "error": "ImportError"}""").canPushToTalk)
        assertTrue(status(realStatus).canPushToTalk)
    }

    // ------------------------------------------------------- the verdicts ---

    private fun heard(json: String) = JarvisJson.decodeFromString(Heard.serializer(), json)

    @Test
    fun `a verified utterance is the only one that carries words`() {
        val h = heard(
            """{"ok": true, "owner": true, "text": "what is waiting for me",
                "score": 0.81, "threshold": 0.35, "seconds": 1.9, "engine": "faster-whisper"}""",
        )
        assertEquals(Heard.Outcome.TRANSCRIBED, h.outcome)
        assertEquals("what is waiting for me", h.message())
    }

    @Test
    fun `a voice that did not match is refused without a transcript`() {
        val h = heard(
            """{"ok": false, "owner": false, "text": "",
                "score": 0.11, "threshold": 0.35,
                "reason": "did not match your voice (0.11 < 0.35)"}""",
        )
        assertEquals(Heard.Outcome.NOT_THE_OWNER, h.outcome)
        assertEquals("", h.text)
        assertEquals("That didn't sound like you.", h.message())
    }

    @Test
    fun `unusable audio is not reported as a stranger`() {
        // The distinction that matters. `owner:false` covers both "not your
        // voice" and "there was nothing to check" — and hear() refuses the
        // second BEFORE the gate runs, so it comes back with no threshold.
        // Telling someone their own voice was not recognised, when really the
        // microphone caught 90ms of nothing, is both wrong and alarming.
        val short = heard("""{"ok": false, "owner": false, "seconds": 0.09,
                              "reason": "too short to identify a voice (0.09s)"}""")
        assertEquals(Heard.Outcome.REFUSED, short.outcome)
        assertNotEquals("That didn't sound like you.", short.message())
        assertEquals("too short to identify a voice (0.09s)", short.message())

        val silence = heard("""{"ok": false, "owner": false, "reason": "silence"}""")
        assertEquals(Heard.Outcome.REFUSED, silence.outcome)

        val bad = heard("""{"ok": false, "owner": false, "reason": "need 16000Hz, got 44100Hz"}""")
        assertEquals(Heard.Outcome.REFUSED, bad.outcome)
    }

    @Test
    fun `no engine is its own case, never silence`() {
        // An empty transcript would read downstream as silence, and acting on
        // silence is acting on nothing at all.
        val h = heard(
            """{"ok": false, "owner": true, "text": "", "score": 0.79, "threshold": 0.35,
                "engine": "none", "reason": "no speech-to-text engine installed"}""",
        )
        assertEquals(Heard.Outcome.NO_ENGINE, h.outcome)
        assertTrue(h.message().contains("no speech-to-text", ignoreCase = true))
    }

    // ------------------------------------------------------------- audio ----

    @Test
    fun `the wav header says what the server requires`() {
        val wav = Wav.encode(ShortArray(16_000) { (it % 100).toShort() })
        assertEquals("RIFF", String(wav, 0, 4, Charsets.US_ASCII))
        assertEquals("WAVE", String(wav, 8, 4, Charsets.US_ASCII))
        fun le16(o: Int) = (wav[o].toInt() and 0xFF) or ((wav[o + 1].toInt() and 0xFF) shl 8)
        fun le32(o: Int) = le16(o) or (le16(o + 2) shl 16)
        assertEquals("PCM", 1, le16(20))
        assertEquals("mono", 1, le16(22))
        assertEquals("16 kHz", 16_000, le32(24))
        assertEquals("16-bit", 16, le16(34))
        assertEquals("byte rate", 32_000, le32(28))
        assertEquals("block align", 2, le16(32))
        assertEquals("data size", 32_000, le32(40))
        assertEquals(44 + 32_000, wav.size)
    }

    @Test
    fun `resampling lands on exactly the rate the server demands`() {
        // The server refuses anything that is not 16 kHz rather than carrying a
        // resampler in code that runs before the gate, so getting this wrong is
        // a round trip that always fails.
        for (rate in intArrayOf(48_000, 44_100, 32_000, 22_050, 8_000)) {
            val oneSecond = ShortArray(rate) { i ->
                (16_000 * kotlin.math.sin(2.0 * Math.PI * 220.0 * i / rate)).toInt().toShort()
            }
            val out = Wav.resample(oneSecond, rate)
            assertTrue(
                "$rate Hz resampled to ${out.size} samples, wanted ~16000",
                abs(out.size - 16_000) <= 2,
            )
            // And it must still be a signal, not silence — a decimator with a
            // sign or index error produces the right LENGTH of nothing.
            assertTrue("$rate Hz resampled to silence", Wav.rms(out) > 0.05f)
        }
    }

    @Test
    fun `16 kHz input is passed through untouched`() {
        val input = ShortArray(1000) { (it * 7 % 3000).toShort() }
        assertTrue(Wav.resample(input, 16_000) === input)
    }

    @Test
    fun `rms is bounded and silent input reads as silent`() {
        assertEquals(0f, Wav.rms(ShortArray(512)), 1e-6f)
        assertTrue(Wav.rms(ShortArray(512) { Short.MAX_VALUE }) <= 1f)
        assertTrue(Wav.rms(ShortArray(512) { Short.MIN_VALUE }) <= 1f)
        assertEquals(0f, Wav.rms(ShortArray(0)), 0f)
    }
}
