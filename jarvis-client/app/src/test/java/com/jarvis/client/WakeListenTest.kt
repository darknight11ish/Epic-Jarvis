package com.jarvis.client

import com.jarvis.client.net.Heard
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.VoiceStatus
import com.jarvis.client.voice.WakeClip
import com.jarvis.client.voice.WakeModels
import com.jarvis.client.voice.WakeRules
import com.jarvis.client.voice.WakeSpotter
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.exp
import kotlin.random.Random

/**
 * "Hey Jarvis" on the phone: the spotter's buffering, the clip around a
 * detection, and the rules for when this phone may listen and send.
 *
 * The real models are not needed here (a stand-in with the same shapes is
 * used). They were checked separately: the same WakeSpotter and
 * OrtWakeModels, run on a desktop JVM with the plain onnxruntime jar over 110
 * synthesised clips, scored within 0.0005 of the PC's Python on every clip -
 * see backend/README.md, "the wake word".
 */
class WakeListenTest {

    /** Deterministic stand-in for the three ONNX files, shape-correct. */
    private class FakeModels : WakeModels {
        override fun melspec(samples: FloatArray): Array<FloatArray> {
            val n = (samples.size - 512) / 160 + 1
            return Array(n) { i ->
                var sum = 0f
                for (k in i * 160 until i * 160 + 512) sum += samples[k]
                FloatArray(WakeSpotter.MEL_BINS) { sum / 512f / 1000f }
            }
        }

        override fun embed(frames: Array<FloatArray>): FloatArray {
            var sum = 0f
            for (f in frames) sum += f[0]
            return FloatArray(WakeSpotter.EMB_SIZE) { sum / frames.size }
        }

        override fun score(feats: Array<FloatArray>): Float = (1 / (1 + exp(-feats.last()[0].toDouble()))).toFloat()

        override fun close() = Unit
    }

    private fun noise(n: Int, seed: Int = 3): ShortArray {
        val r = Random(seed)
        return ShortArray(n) { (r.nextInt(-6000, 6000)).toShort() }
    }

    @Test
    fun `one score per 80 ms, however the audio arrives`() {
        val x = noise(16_000 * 3)
        val whole = WakeSpotter(FakeModels()).feed(x)
        assertEquals(x.size / WakeSpotter.CHUNK, whole.size)

        val spotter = WakeSpotter(FakeModels())
        val pieces = ArrayList<Float>()
        val r = Random(9)
        var i = 0
        while (i < x.size) {
            val n = minOf(r.nextInt(1, 3000), x.size - i)
            pieces += spotter.feed(x.copyOfRange(i, i + n)).toList()
            i += n
        }
        assertArrayEquals(whole, pieces.toFloatArray(), 1e-6f)
    }

    @Test
    fun `the first five scores are ignored, as openWakeWord does`() {
        val scores = WakeSpotter(FakeModels()).feed(noise(16_000))
        for (k in 0 until WakeSpotter.WARMUP_SCORES) assertEquals(0f, scores[k], 0f)
        assertTrue(scores.drop(WakeSpotter.WARMUP_SCORES).any { it > 0f })
    }

    @Test
    fun `reset starts over, warm-up and all`() {
        val spotter = WakeSpotter(FakeModels())
        val first = spotter.feed(noise(16_000))
        spotter.reset()
        assertArrayEquals(first, spotter.feed(noise(16_000)), 1e-6f)
    }

    @Test
    fun `1760 samples make exactly the 8 mel frames one step needs`() {
        assertEquals(8, (WakeSpotter.MEL_INPUT - 512) / 160 + 1)
        assertEquals(WakeSpotter.CHUNK + 480, WakeSpotter.MEL_INPUT)
    }

    @Test
    fun `the ring keeps the last two seconds, oldest first`() {
        val ring = WakeClip.Ring(5)
        ring.push(shortArrayOf(1, 2, 3))
        assertArrayEquals(shortArrayOf(1, 2, 3), ring.snapshot())
        ring.push(shortArrayOf(4, 5, 6, 7))
        assertArrayEquals(shortArrayOf(3, 4, 5, 6, 7), ring.snapshot())
        ring.clear()
        assertEquals(0, ring.snapshot().size)
        assertEquals(32_000, (WakeClip.PREROLL_SECONDS * 16_000).toInt())
    }

    @Test
    fun `a clip ends after a pause that follows speech`() {
        val end = WakeClip.EndOfSpeech(graceSeconds = 3f, silenceSeconds = 1f)
        val step = 0.08f
        repeat(10) { assertFalse(end.push(0.001f, step)) } // quiet, still in the grace
        repeat(10) { assertFalse(end.push(0.2f, step)) } // talking
        assertTrue(end.heardSpeech)
        var steps = 0
        while (!end.push(0.001f, step)) steps++
        assertTrue("ended after ${steps + 1} quiet steps", (steps + 1) * step in 0.95f..1.1f)
    }

    @Test
    fun `nothing said after the phrase, it gives up after the grace`() {
        val end = WakeClip.EndOfSpeech(graceSeconds = 2f)
        var t = 0f
        while (!end.push(0.001f, 0.08f)) t += 0.08f
        assertFalse(end.heardSpeech)
        assertTrue(t in 1.8f..2.1f)
    }

    @Test
    fun `a clip that never pauses is cut at the cap`() {
        val end = WakeClip.EndOfSpeech(maxSeconds = 4f)
        var t = 0f
        while (!end.push(0.3f, 0.08f)) t += 0.08f
        assertTrue(t in 3.8f..4.1f)
    }

    @Test
    fun `the loudness bar follows the room, within the desktop's bounds`() {
        assertEquals(0.006f, WakeClip.EndOfSpeech.threshold(0f), 0f)
        assertEquals(0.05f, WakeClip.EndOfSpeech.threshold(1f), 0f)
        var floor = 0.005f
        repeat(200) { floor = WakeClip.EndOfSpeech.updateFloor(floor, 0.001f) }
        assertTrue(WakeClip.EndOfSpeech.threshold(floor) <= 0.007f)
        assertTrue(WakeClip.EndOfSpeech.threshold(WakeClip.EndOfSpeech.updateFloor(floor, 0.3f)) < 0.02f)
    }

    // ------------------------------------------------------------ the rules

    private fun status(json: String) = JarvisJson.decodeFromString(VoiceStatus.serializer(), json)

    private val on = status(
        """{"available": true, "listening": {"push_to_talk": true, "wake_word": true},
            "wake": {"enabled": true, "pending": false, "phrase": "hey_jarvis",
                     "threshold": 0.6, "awake_seconds": 8.0,
                     "spotter": {"available": true, "engine": "openWakeWord", "why": ""}}}""",
    )
    private val off = status("""{"available": true, "listening": {"wake_word": false}}""")

    /** docs/WAKE-WORD.md §4 step 5, by name. */
    @Test
    fun `a wake-word capture is never made or sent while the desktop says the wake word is off`() {
        assertNotNull(WakeRules.mayListen(answered = true, status = off))
        assertNotNull(WakeRules.mayPost(answered = true, status = off, stale = false))
        // An unanswered desktop is not "on", whatever the last answer was.
        assertNotNull(WakeRules.mayListen(answered = false, status = on))
        assertNull(WakeRules.mayListen(answered = true, status = on))
    }

    @Test
    fun `nothing is sent over a stale link`() {
        assertNull(WakeRules.mayPost(answered = true, status = on, stale = false))
        val why = WakeRules.mayPost(answered = true, status = on, stale = true)
        assertNotNull(why)
        assertTrue(why!!.contains("nothing was sent"))
    }

    /** AP-7: what makes the runtime re-read the voice status after an approval event. */
    @Test
    fun `a waiting wake-word or training card is seen, and no card is not`() {
        assertTrue(status("""{"listening": {"wake_word": false, "wake_word_pending": true}}""").cardWaiting)
        assertTrue(status("""{"wake": {"enabled": false, "pending": true}}""").cardWaiting)
        assertTrue(status("""{"gate": {"training": {"available": true, "pending": true, "clips": 5}}}""").cardWaiting)
        assertFalse(on.cardWaiting)
        assertFalse(off.cardWaiting)
        assertFalse("an older desktop that says nothing", status("""{"available": true}""").cardWaiting)
    }

    /** Rule 4: turning it ON raises a card, so it waits for a live link. OFF never waits. */
    @Test
    fun `asking for the wake word ON is held on a stale link, and OFF never is`() {
        val down = "Not connected to the desktop, so this cannot be delivered."
        assertEquals(down, WakeRules.requestBlocker(enabled = true, linkBlocker = down))
        assertNull(WakeRules.requestBlocker(enabled = true, linkBlocker = null))
        assertNull("off only closes things", WakeRules.requestBlocker(enabled = false, linkBlocker = down))
    }

    @Test
    fun `the phone uses the desktop's threshold, held in range`() {
        assertEquals(0.6f, WakeRules.threshold(on), 1e-6f)
        assertEquals(0.5f, WakeRules.threshold(off), 1e-6f) // absent: the default
        val silly = status("""{"wake": {"threshold": 0.0}}""")
        assertEquals(0.1f, WakeRules.threshold(silly), 1e-6f)
    }

    private fun heard(json: String) = JarvisJson.decodeFromString(Heard.serializer(), json)

    @Test
    fun `the desktop's answers, as the listener reads them`() {
        // The shapes jarvis_speech.hear() sends (backend/test_voice_contract.py
        // checks the same four against this reading).
        assertEquals(
            WakeRules.Verdict.ANSWER,
            WakeRules.verdict(heard("""{"ok": true, "owner": true, "text": "what time is it?", "wake_heard": true}""")),
        )
        assertEquals(
            WakeRules.Verdict.AWAKE,
            WakeRules.verdict(heard("""{"ok": true, "owner": true, "text": "", "wake_heard": true, "awake": true, "awake_seconds": 8.0}""")),
        )
        assertEquals(
            WakeRules.Verdict.IGNORE,
            WakeRules.verdict(heard("""{"ok": false, "owner": false, "reason": "no \"hey Jarvis\" in that recording"}""")),
        )
        // Someone else saying it: dropped, never announced as "not you".
        assertEquals(
            WakeRules.Verdict.IGNORE,
            WakeRules.verdict(heard("""{"ok": false, "owner": false, "threshold": 0.35, "score": 0.1}""")),
        )
        // The owner, but the sentence did not start with the phrase.
        assertEquals(
            WakeRules.Verdict.IGNORE,
            WakeRules.verdict(heard("""{"ok": true, "owner": true, "text": "", "wake_heard": false}""")),
        )
        assertEquals(
            WakeRules.Verdict.STOP,
            WakeRules.verdict(heard("""{"ok": false, "owner": false, "available": false, "reason": "the wake word is switched off on the PC"}""")),
        )
        // An older desktop that sends no `available` is not read as broken.
        assertTrue(heard("""{"ok": true, "owner": true, "text": "hi"}""").available)
    }

    @Test
    fun `asking to turn it on is never reported as it being on`() {
        assertEquals(null, WakeRules.afterRequest(enabled = true, nowOn = true, pending = false))
        val waiting = WakeRules.afterRequest(enabled = true, nowOn = false, pending = true)
        assertTrue(waiting!!.contains("Approve the card"))
        assertNotNull(WakeRules.afterRequest(enabled = true, nowOn = false, pending = false))
        assertNull(WakeRules.afterRequest(enabled = false, nowOn = false, pending = false))
        assertTrue(WakeRules.afterRequest(enabled = false, nowOn = true, pending = false)!!.contains("still reports"))
    }

    @Test
    fun `a status that says nothing about the wake word reads as off with no card`() {
        val old = status("""{"available": true}""")
        assertFalse(old.wakeWordOn)
        assertFalse(old.listening.wakeWordPending)
        assertFalse(old.wake.enabled)
        assertFalse(old.wake.spotter.available)
    }
}
