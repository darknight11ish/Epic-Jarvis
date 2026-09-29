package com.jarvis.client

import com.jarvis.client.audio.LipSync
import com.jarvis.client.face.CritterPose
import com.jarvis.client.audio.Wav
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.double
import kotlinx.serialization.json.float
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.intOrNull
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.security.MessageDigest
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.sin

/**
 * The animals' mouths move the same way on the phone as on the desktop.
 *
 * The two apps cannot share code, so each has its own copy of the lip-sync
 * analysis: `lipsync.js` on the desktop and [LipSync] here.
 * `tools/gen_lipsync.py` runs the JavaScript over the test clips in
 * `src/test/resources/lipsync/` - Jarvis's own Kokoro voice, in its default
 * voice and three animal voices (docs/LIPSYNC.md) - and saves every frame of
 * every mouth track in `lipsync-golden.json`. This checks the Kotlin copy
 * gives the same numbers. If it fails after a change to one copy, make the
 * same change to the other and re-run the generator.
 */
class LipSyncTest {

    private val golden: JsonObject by lazy {
        val text = checkNotNull(javaClass.classLoader?.getResourceAsStream("lipsync-golden.json")) {
            "lipsync-golden.json is missing from test resources - run tools/gen_lipsync.py"
        }.bufferedReader().readText()
        Json.parseToJsonElement(text).jsonObject
    }

    private fun clip(name: String): ByteArray =
        checkNotNull(javaClass.classLoader?.getResourceAsStream("lipsync/$name")) {
            "test clip lipsync/$name is missing"
        }.readBytes()

    private fun resource(path: String): ByteArray =
        checkNotNull(javaClass.classLoader?.getResourceAsStream(path)) {
            "test resource $path is missing - run tools/gen_lipsync.py"
        }.readBytes()

    private val tol = 1e-3f

    @Test
    fun `the constants match the desktop's`() {
        assertEquals(golden["fps"]!!.jsonPrimitive.int, LipSync.FPS)
        assertEquals(golden["lead_s"]!!.jsonPrimitive.double, LipSync.LEAD_S.toDouble(), 1e-6)
    }

    @Test
    fun `every mouth track matches the desktop's`() {
        val clips = golden["clips"]!!.jsonArray
        assertTrue("the fixture should hold the test clips", clips.size >= 5)
        for (c in clips) {
            val o = c.jsonObject
            val name = o["file"]!!.jsonPrimitive.content
            val wav = clip(name)
            val rate = Wav.rateOf(wav)
            assertEquals("$name: sample rate", o["sampleRate"]!!.jsonPrimitive.int, rate)
            val pcm = Wav.decode(wav)
            assertEquals("$name: samples", o["samples"]!!.jsonPrimitive.int, pcm.size)
            val track = LipSync.analyse(pcm, rate)
            assertEquals("$name: frames", o["n"]!!.jsonPrimitive.int, track.n)
            assertEquals(LipSync.FPS, track.fps)
            for ((key, got) in listOf("level" to track.level, "open" to track.open,
                "wide" to track.wide, "round" to track.round)) {
                val want = o[key]!!.jsonArray
                assertEquals("$name: $key length", want.size, got.size)
                for (i in got.indices) {
                    val w = want[i].jsonPrimitive.float
                    assertTrue("$name: $key[$i] is ${got[i]}, the desktop says $w", abs(got[i] - w) <= tol)
                }
            }
            // Where the phrases end, worked out before the clip plays: the desktop's answer.
            val ends = LipSync.phraseEnds(track)
            val wantEnds = o["phrase_ends"]!!.jsonArray.map { it.jsonPrimitive.float }
            assertEquals("$name: phrase ends ${ends.toList()} vs the desktop's $wantEnds", wantEnds.size, ends.size)
            for (i in ends.indices) assertEquals("$name: phrase end $i", wantEnds[i], ends[i], 2e-3f)
            // sample() at the same moments the desktop was asked about.
            val out = FloatArray(4)
            for (r in o["reads"]!!.jsonArray) {
                val ro = r.jsonObject
                val t = ro["t"]!!.jsonPrimitive.float
                val inside = ro["inside"]!!.jsonPrimitive.boolean
                val want = ro["out"]!!.jsonArray.map { it.jsonPrimitive.float }
                assertEquals("$name: sample($t) inside the clip?", inside, LipSync.sample(track, t, out))
                for (k in 0..3) {
                    assertTrue("$name: sample($t)[$k] is ${out[k]}, the desktop says ${want[k]}",
                        abs(out[k] - want[k]) <= tol)
                }
            }
        }
    }

    @Test
    fun `sample outside the clip, or with no track, is all zeros`() {
        val out = floatArrayOf(9f, 9f, 9f, 9f)
        assertFalse(LipSync.sample(null, 0.3f, out))
        assertArrayEquals(FloatArray(4), out, 0f)

        val track = LipSync.Track(LipSync.FPS, FloatArray(10) { 1f }, FloatArray(10) { 1f },
            FloatArray(10) { 0.5f }, FloatArray(10) { 0.25f })
        out.fill(9f)
        assertFalse("before the lead-in", LipSync.sample(track, -LipSync.LEAD_S - 0.01f, out))
        assertArrayEquals(FloatArray(4), out, 0f)
        out.fill(9f)
        assertFalse("after the last frame", LipSync.sample(track, 0.09f - LipSync.LEAD_S + 0.01f, out))
        assertArrayEquals(FloatArray(4), out, 0f)
        assertTrue("inside", LipSync.sample(track, 0.02f, out))
        // 20 ms in: the mouth is 40% faded in (ONSET_S), the level is not faded.
        assertArrayEquals(floatArrayOf(1f, 0.4f, 0.2f, 0.1f), out, 1e-5f)

        val empty = LipSync.Track(LipSync.FPS, FloatArray(0), FloatArray(0), FloatArray(0), FloatArray(0))
        assertFalse(LipSync.sample(empty, 0f, out))
    }

    @Test
    fun `sample reads LEAD_S ahead and interpolates between frames`() {
        val n = 40
        val ramp = FloatArray(n) { it / (n - 1f) }
        val track = LipSync.Track(LipSync.FPS, ramp, ramp, FloatArray(n), FloatArray(n))
        val out = FloatArray(4)
        // At playback time t the mouth shows frame (t + LEAD_S) * FPS.
        assertTrue(LipSync.sample(track, 0.0f, out))
        assertEquals(LipSync.LEAD_S * LipSync.FPS / (n - 1f), out[0], 1e-4f)
        // The mouth starts shut and fades in over ONSET_S; the level does not.
        assertEquals(0.05f, LipSync.ONSET_S, 0f)
        assertEquals(0f, out[1], 0f)
        // Halfway between frames 7 and 8, and half faded in (25 ms).
        assertTrue(LipSync.sample(track, 0.075f - LipSync.LEAD_S, out))
        assertEquals(7.5f / (n - 1f), out[0], 1e-4f)
        assertEquals(0.5f * 7.5f / (n - 1f), out[1], 1e-4f)
        assertTrue(LipSync.sample(track, 0.1f, out))
        assertEquals("fully in from ONSET_S on", out[0], out[1], 1e-6f)
        // ...and faded out over the track's last ONSET_S (the level is not):
        // a clip whose sound runs to its end must not snap shut in one frame.
        val lastT = (n - 1) / 100f - LipSync.LEAD_S
        assertTrue(LipSync.sample(track, lastT - 0.025f, out))
        assertEquals("the level is not faded", (n - 3.5f) / (n - 1f), out[0], 1e-4f)
        assertEquals("half faded out 25 ms before the end", 0.5f * out[0], out[1], 1e-4f)
        assertTrue(LipSync.sample(track, lastT - 0.0001f, out))
        assertTrue("shut at the last frame: ${out[1]}", out[1] < 0.01f)
        assertTrue(LipSync.sample(track, lastT - 0.06f, out))
        assertEquals("not faded before the last ONSET_S", out[0], out[1], 1e-6f)
    }

    @Test
    fun `a sample that is not a number counts as silence, never a NaN mouth`() {
        val rate = 24_000
        val clean = FloatArray(rate) { i -> if (i in 6_000 until 18_000) (0.4 * sin(2 * Math.PI * 200 * i / rate)).toFloat() else 0f }
        val want = LipSync.analyse(clean, rate)
        for (bad in listOf(Float.NaN, Float.POSITIVE_INFINITY, Float.NEGATIVE_INFINITY)) {
            val dirty = clean.copyOf()
            dirty[3_000] = bad
            val got = LipSync.analyse(dirty, rate)
            for ((a, b) in listOf(want.level to got.level, want.open to got.open, want.wide to got.wide, want.round to got.round)) {
                assertArrayEquals("$bad at a silent sample is silence", a, b, 0f)
            }
            dirty[12_000] = bad
            val mid = LipSync.analyse(dirty, rate)
            for (ch in listOf(mid.level, mid.open, mid.wide, mid.round)) for (v in ch) assertTrue("$bad in the sound gave $v", v in 0f..1f)
        }
    }

    @Test
    fun `silence gives a closed mouth, and bad input gives an empty track`() {
        val silent = LipSync.analyse(ShortArray(24_000), 24_000)
        assertEquals(LipSync.FPS, silent.n)
        for (i in 0 until silent.n) {
            assertEquals(0f, silent.level[i], 0f)
            assertEquals(0f, silent.open[i], 0f)
            assertEquals(0f, silent.wide[i], 0f)
            assertEquals(0f, silent.round[i], 0f)
        }
        assertEquals(0, LipSync.analyse(ShortArray(0), 24_000).n)
        assertEquals(0, LipSync.analyse(ShortArray(1000), 0).n)
        // One frame per 10 ms, rounded up, at any rate.
        assertEquals(1, LipSync.analyse(ShortArray(441), 44_100).n)
        assertEquals(2, LipSync.analyse(ShortArray(442), 44_100).n)
        assertEquals(2, LipSync.analyse(ShortArray(320), 16_000).n)
        // A voiced sound at a rate no WAV here has (the voice's pitch is only
        // looked for from 4 kHz up): a track in range, never an exception.
        for (rate in listOf(1, 100, 1000, 3999, 4000, 192_000)) {
            val len = max(rate, 400)
            val buzz = ShortArray(len) { i ->
                val t = i.toDouble() / rate
                (8000 * (sin(2 * Math.PI * 150 * t) + 0.5 * sin(2 * Math.PI * 900 * t))).toInt().toShort()
            }
            val tr = LipSync.analyse(buzz, rate)
            for (ch in listOf(tr.level, tr.open, tr.wide, tr.round)) for (v in ch) assertTrue("$rate Hz gave $v", v in 0f..1f)
        }
    }

    @Test
    fun `a tone that stops leaves the mouth shut in the silence after it`() {
        // 0.6 s of a vowel-like buzz, then 0.6 s of silence.
        val rate = 24_000
        val pcm = ShortArray(rate * 12 / 10) { i ->
            if (i < rate * 6 / 10) {
                val t = i.toDouble() / rate
                (8000 * (sin(2 * Math.PI * 180 * t) + 0.6 * sin(2 * Math.PI * 720 * t) +
                    0.4 * sin(2 * Math.PI * 1260 * t))).toInt().toShort()
            } else 0
        }
        val track = LipSync.analyse(pcm, rate)
        assertTrue("open while it sounds", track.open[30] > 0.3f)
        for (i in 75 until track.n) assertEquals("closed at frame $i", 0f, track.open[i], 0f)
        for (i in track.level.indices) {
            assertTrue(track.level[i] in 0f..1f && track.open[i] in 0f..1f &&
                track.wide[i] in 0f..1f && track.round[i] in 0f..1f)
        }
    }

    // ---- Mouth shapes inside the WAV (the "jmth" chunk) ----------------------

    private val mouth: JsonObject get() = golden["mouth"]!!.jsonObject

    @Test
    fun `a clip carrying the PC's mouth shapes merges them as the desktop does`() {
        val m = mouth
        val wav = resource("lipsync-mouth/${m["file"]!!.jsonPrimitive.content}")
        val src = clip(m["source"]!!.jsonPrimitive.content)
        // The chunk is never sound: the same samples, the same rate, as the clip without it.
        assertArrayEquals("the chunk was read as sound", Wav.decode(src), Wav.decode(wav))
        assertEquals(Wav.rateOf(src), Wav.rateOf(wav))
        val text = Wav.mouthChunk(wav)
        assertNotNull("the fixture should carry a jmth chunk", text)
        assertTrue(text!!.startsWith("v1;"))
        val lips = LipSync.mouthFrom(text)
        assertNotNull("the fixture's chunk should parse", lips)
        assertEquals(m["mouthN"]!!.jsonPrimitive.int, lips!!.n)

        val pcm = Wav.decode(wav)
        val rate = Wav.rateOf(wav)
        val audio = LipSync.analyse(pcm, rate)
        val track = LipSync.forClip(wav, pcm, rate)
        assertEquals(m["n"]!!.jsonPrimitive.int, track.n)
        assertArrayEquals("the level stays the clip's own", audio.level, track.level, 0f)
        for ((key, got) in listOf("level" to track.level, "open" to track.open,
            "wide" to track.wide, "round" to track.round)) {
            val want = m[key]!!.jsonArray
            assertEquals("$key length", want.size, got.size)
            for (i in got.indices) {
                val w = want[i].jsonPrimitive.float
                assertTrue("$key[$i] is ${got[i]}, the desktop says $w", abs(got[i] - w) <= tol)
            }
        }
        // The frames past the end of the (2 frames shorter) mouth are closed.
        for (i in lips.n until track.n) {
            assertEquals(0f, track.open[i], 0f); assertEquals(0f, track.wide[i], 0f); assertEquals(0f, track.round[i], 0f)
        }
        val out = FloatArray(4)
        for (r in m["reads"]!!.jsonArray) {
            val t = r.jsonObject["t"]!!.jsonPrimitive.float
            val want = r.jsonObject["out"]!!.jsonArray.map { it.jsonPrimitive.float }
            LipSync.sample(track, t, out)
            for (k in 0..3) assertTrue("sample($t)[$k] is ${out[k]}, the desktop says ${want[k]}", abs(out[k] - want[k]) <= tol)
        }
    }

    /**
     * The voice-speed check (2026-09-28): the same sentence at the slowest
     * pace the apps offer (0.7225, an animal's Slower times the owner's) and
     * the fastest (1.3225), each carrying the PC's mouth timing. The phone
     * plays exactly what the desktop plays at both, and at both the mouth
     * still shuts between the words and for m / b / p (the desktop's
     * lipsync.mjs checks the same clips in more detail).
     */
    @Test
    fun `at the slowest and the fastest pace the phone's mouth is the desktop's`() {
        val paces = golden["paces"]!!.jsonArray
        assertEquals("the fixture should hold the slowest and the fastest pace", 2, paces.size)
        for (p in paces) {
            val o = p.jsonObject
            val name = o["file"]!!.jsonPrimitive.content
            val wav = clip(name)
            val pcm = Wav.decode(wav)
            val rate = Wav.rateOf(wav)
            val audio = LipSync.analyse(pcm, rate)
            val track = LipSync.forClip(wav, pcm, rate)
            assertTrue("$name: the PC's mouth was not taken", o["merged"]!!.jsonPrimitive.boolean)
            assertFalse("$name: the PC's mouth was not taken", audio.open.contentEquals(track.open))
            assertEquals("$name: frames", o["n"]!!.jsonPrimitive.int, track.n)
            for ((key, got) in listOf("level" to track.level, "open" to track.open,
                "wide" to track.wide, "round" to track.round)) {
                val want = o[key]!!.jsonArray
                assertEquals("$name: $key length", want.size, got.size)
                for (i in got.indices) {
                    val w = want[i].jsonPrimitive.float
                    assertTrue("$name: $key[$i] is ${got[i]}, the desktop says $w", abs(got[i] - w) <= tol)
                }
            }
            val out = FloatArray(4)
            for (r in o["reads"]!!.jsonArray) {
                val t = r.jsonObject["t"]!!.jsonPrimitive.float
                val want = r.jsonObject["out"]!!.jsonArray.map { it.jsonPrimitive.float }
                LipSync.sample(track, t, out)
                for (k in 0..3) assertTrue("$name: sample($t)[$k] is ${out[k]}, the desktop says ${want[k]}", abs(out[k] - want[k]) <= tol)
            }
            // "Okay. Maybe Bob made a map.": the pause and the lips close the
            // mouth between openings - from the sound alone and from the PC's timing.
            assertTrue("$name: ${closures(audio.open)} closures from the sound", closures(audio.open) >= 5)
            assertTrue("$name: ${closures(track.open)} closures from the PC's timing", closures(track.open) >= 4)
        }
    }

    /** Times the mouth drops below 0.12 between two openings above 0.25 (lipsync.mjs `closures`). */
    private fun closures(open: FloatArray): Int {
        var count = 0
        var low = 1f
        var armed = false
        for (o in open) {
            if (o > 0.25f) {
                if (armed && low < 0.12f) count++
                armed = true
                low = 1f
            } else if (armed) low = minOf(low, o)
        }
        return count
    }

    @Test
    fun `every good and broken chunk is read as the desktop reads it, and a broken one changes nothing`() {
        val src = clip(mouth["source"]!!.jsonPrimitive.content)
        val srcPcm = Wav.decode(src)
        val rate = Wav.rateOf(src)
        val plain = LipSync.analyse(srcPcm, rate)
        val cases = mouth["cases"]!!.jsonArray
        assertTrue("the fixture should list the variants", cases.size >= 20)
        for (c in cases) {
            val spec = c.jsonObject
            val name = spec["name"]!!.jsonPrimitive.content
            val wav = variant(src, spec)
            assertEquals("$name: not the bytes tools/gen_lipsync.py built", spec["sha256"]!!.jsonPrimitive.content, sha256(wav))
            val lips = Wav.mouthChunk(wav)?.let { LipSync.mouthFrom(it) }
            assertEquals("$name: a mouth?", spec["mouth"]!!.jsonPrimitive.boolean, lips != null)
            val pcm = Wav.decode(wav)
            assertArrayEquals("$name: the sound changed", srcPcm, pcm)
            assertEquals("$name: the rate changed", rate, Wav.rateOf(wav))
            val audio = LipSync.analyse(pcm, rate)
            val merged = LipSync.merge(audio, lips) !== audio
            assertEquals("$name: merged?", spec["merged"]!!.jsonPrimitive.boolean, merged)
            val track = LipSync.forClip(wav, pcm, rate)
            if (!merged) {
                // Exactly as without the chunk.
                for ((a, b) in listOf(plain.level to track.level, plain.open to track.open,
                    plain.wide to track.wide, plain.round to track.round)) assertArrayEquals(name, a, b, 0f)
            } else {
                assertArrayEquals("$name: level", plain.level, track.level, 0f)
                assertFalse("$name: the shapes were not taken", plain.open.contentEquals(track.open))
            }
        }
    }

    @Test
    fun `unpack refuses anything that is not whole frames at FPS`() {
        // One frame, 4 bytes: level 255, open 0, wide 128, round 1.
        val one = LipSync.unpack("100:/wCAAQ==")
        assertNotNull(one)
        assertEquals(1, one!!.n)
        assertArrayEquals(floatArrayOf(1f, 0f, 128 / 255f, 1 / 255f),
            floatArrayOf(one.level[0], one.open[0], one.wide[0], one.round[0]), 1e-6f)
        for (bad in listOf("", "100:", "50:/wCAAQ==", "100/wCAAQ==", "100:/wCAAQ=", "100:/wCAAQ", "100:/wC*AQ==",
            "100:/w==AQ==", "100:/wCA", "abc:/wCAAQ==", "100:/wCAAQ==\n", " 100:/wCAAQ==", "10000:/wCAAQ==")) {
            assertNull("\"$bad\" should be refused", LipSync.unpack(bad))
        }
        assertNull(LipSync.mouthFrom("v1;src=kokoro"))
        assertNull(LipSync.mouthFrom("v1;src=kokoro;;100:/wCAAQ=="))
        assertNull(LipSync.mouthFrom("V1;100:/wCAAQ=="))
        assertNotNull(LipSync.mouthFrom("v1;src=kokoro;100:/wCAAQ==\u0000"))
        assertNotNull(LipSync.mouthFrom("v1;100:/wCAAQ=="))
    }

    @Test
    fun `merge takes the level from the clip and the shapes from the PC, within 3 frames`() {
        fun t(n: Int, v: Float, fps: Int = LipSync.FPS) =
            LipSync.Track(fps, FloatArray(n) { v }, FloatArray(n) { v }, FloatArray(n) { v }, FloatArray(n) { v })
        val audio = t(10, 0.25f)
        val m = LipSync.merge(audio, t(8, 0.75f))
        assertEquals(10, m.n)
        assertSame(audio.level, m.level)
        assertEquals(0.75f, m.open[7], 0f); assertEquals(0f, m.open[8], 0f); assertEquals(0f, m.round[9], 0f)
        assertEquals(10, LipSync.merge(audio, t(13, 0.75f)).n)
        assertEquals(0.75f, LipSync.merge(audio, t(7, 0.75f)).wide[0], 0f)
        assertSame(audio, LipSync.merge(audio, t(6, 0.75f)))
        assertSame(audio, LipSync.merge(audio, t(14, 0.75f)))
        assertSame(audio, LipSync.merge(audio, null))
        assertSame(audio, LipSync.merge(audio, t(10, 0.75f, fps = 50)))
        assertSame(audio, LipSync.merge(audio, t(0, 0.75f)))
    }

    /** The same bytes as tools/gen_lipsync.py's `variant()`: change both together. */
    private fun variant(src: ByteArray, spec: JsonObject): ByteArray {
        fun le32(v: Int) = byteArrayOf(v.toByte(), (v ushr 8).toByte(), (v ushr 16).toByte(), (v ushr 24).toByte())
        fun ascii(s: String) = s.toByteArray(Charsets.US_ASCII)
        val payload = spec["payload"]!!.jsonPrimitive.content.toByteArray(Charsets.ISO_8859_1)
        val declared = payload.size + (spec["sizeDelta"]?.jsonPrimitive?.intOrNull ?: 0)
        val chunk = ByteArrayOutputStream()
        chunk.write(ascii("jmth")); chunk.write(le32(declared)); chunk.write(payload)
        val pad = spec["pad"]?.jsonPrimitive?.boolean ?: true
        if (pad && declared % 2 == 1) chunk.write(0)
        val list = spec["list"]?.jsonPrimitive?.content
        val extra = if (list == null) ByteArray(0) else
            ascii("LIST") + le32(3) + ascii("abc") + (if (list == "padded") byteArrayOf(0) else ByteArray(0))
        val where = spec["where"]?.jsonPrimitive?.content ?: "after"
        val out = if (where == "after") {
            src + extra + chunk.toByteArray()
        } else {
            var at = 12
            while (!(src[at] == 'd'.code.toByte() && src[at + 1] == 'a'.code.toByte() &&
                    src[at + 2] == 't'.code.toByte() && src[at + 3] == 'a'.code.toByte())) at++
            src.copyOfRange(0, at) + chunk.toByteArray() + src.copyOfRange(at, src.size)
        }
        le32(out.size - 8).copyInto(out, 4)
        val cut = spec["cut"]?.jsonPrimitive?.intOrNull ?: 0
        return out.copyOfRange(0, out.size - cut)
    }

    private fun sha256(b: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(b).joinToString("") { "%02x".format(it) }

    /** The phrase finder's rules, on made-up levels (the desktop's animal-motion.mjs holds the same numbers). */
    @Test
    fun `phrase ends are found before the clip plays, by the live finder's rules`() {
        fun track(n: Int, f: (Int) -> Float) = LipSync.Track(100, FloatArray(n, f), FloatArray(n), FloatArray(n), FloatArray(n))
        fun ends(t: LipSync.Track) = LipSync.phraseEnds(t).map { Math.round(it * 100) / 100f }
        assertEquals(emptyList<Float>(), ends(track(0) { 0f }))
        assertEquals(listOf(4f), ends(track(400) { 0.5f }))
        assertEquals("a pause of 0.1 s at 2.00 s", listOf(2f, 5f), ends(track(500) { if (it in 200 until 210) 0f else 0.5f }))
        assertEquals("0.3 s of sound before a pause is too short", listOf(2f, 5f),
            ends(track(500) { if (it in 200 until 210 || it in 30 until 60) 0f else 0.5f }))
        assertEquals("the clip's own end, under 2 s after a pause, is left out", listOf(2f),
            ends(track(400) { if (it in 200 until 210) 0f else 0.5f }))
        // The next end still to come, from a heard moment (what the face is handed ahead of time).
        val e = floatArrayOf(1.2f, 3.5f)
        assertEquals(1.2f, LipSync.nextEnd(e, 0f), 1e-6f)
        assertEquals(0.7f, LipSync.nextEnd(e, 0.5f), 1e-6f)
        assertEquals(2.3f, LipSync.nextEnd(e, 1.2f), 1e-6f)
        assertEquals(LipSync.NO_PHRASE_END, LipSync.nextEnd(e, 3.5f), 0f)
        assertEquals(LipSync.NO_PHRASE_END, LipSync.nextEnd(FloatArray(0), 0f), 0f)
        // The same numbers as the live finder's (CritterPose.Pause).
        assertEquals(CritterPose.Pause.ON, LipSync.PhraseRule.ON, 0f)
        assertEquals(CritterPose.Pause.OFF, LipSync.PhraseRule.OFF, 0f)
        assertEquals(CritterPose.Pause.TALK_MIN, LipSync.PhraseRule.TALK_MIN, 0f)
        assertEquals(CritterPose.Pause.PHRASE_QUIET, LipSync.PhraseRule.QUIET, 0f)
        assertEquals(CritterPose.Pause.PHRASE_GAP, LipSync.PhraseRule.GAP, 0f)
    }
}
