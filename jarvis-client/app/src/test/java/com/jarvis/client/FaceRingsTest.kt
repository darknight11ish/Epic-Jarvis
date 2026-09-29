package com.jarvis.client

import com.jarvis.client.face.FaceRings
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import kotlin.math.max

/**
 * The two still rings round a face (face/FaceRings.kt): "not connected" (a
 * complete circle, heavy) and "error" (a thin arc with a gap at the bottom).
 * Owner, 2026-09-29. The desktop draws the same rings (faces.html
 * drawOfflineRing / drawErrorRing); the colours are held to one golden file,
 * jarvis-desktop/tests/fixtures/ring-cases.json, which tests/face-watchdog.mjs
 * checks the desktop against.
 */
class FaceRingsTest {

    private fun ints(e: kotlinx.serialization.json.JsonElement): IntArray =
        e.jsonArray.map { it.jsonPrimitive.int }.toIntArray()

    private val fixture: JsonObject by lazy {
        Json.parseToJsonElement(repoFile("jarvis-desktop/tests/fixtures/ring-cases.json").readText()).jsonObject
    }

    @Test
    fun `the ring colours are the golden ones the desktop is held to`() {
        val cases: JsonArray = fixture["cases"]!!.jsonArray
        assertTrue("the fixture is big enough to mean something", cases.size >= 50)
        for (c in cases) {
            val o = c.jsonObject
            val name = "${o["colour"]!!.jsonPrimitive.content} on ${o["ground"]!!.jsonPrimitive.content}"
            val got = FaceRings.tone(ints(o["c"]!!), ints(o["bg"]!!))
            assertArrayEquals(name, ints(o["tone"]!!), got)
        }
    }

    @Test
    fun `a ring is always readable against its ground, on dark and light`() {
        // The not-connected ring measured 1.65:1 (dimmed by standby's 0.6); "cannot hear
        // me" and "asleep" looked alike from across a room. Now 3.2:1 at the least.
        val grounds = listOf(
            intArrayOf(4, 7, 12), intArrayOf(0, 0, 0), intArrayOf(16, 20, 24),
            intArrayOf(232, 236, 240), intArrayOf(255, 255, 255), intArrayOf(122, 132, 148),
        )
        val tints = listOf(
            intArrayOf(0x46, 0x56, 0x6A),   // NEUTRAL_3, standby
            intArrayOf(0xFF, 0x7B, 0x86),   // ROSE_4, error
            intArrayOf(0x8F, 0xA3, 0xB8), intArrayOf(0xFF, 0xC0, 0x40),
            intArrayOf(255, 255, 255), intArrayOf(0, 0, 0),
        )
        for (bg in grounds) for (t in tints) {
            val k = FaceRings.contrast(FaceRings.tone(t, bg), bg)
            assertTrue("${t.toList()} on ${bg.toList()} measures $k", k >= 3.2 && k <= 5.6)
        }
        // The old ring, for the record: standby's colour dimmed to 0.6 on the desktop ground.
        val old = IntArray(3) { Math.round(intArrayOf(4, 7, 12)[it] + (intArrayOf(0x46, 0x56, 0x6A)[it] - intArrayOf(4, 7, 12)[it]) * 0.6).toInt() }
        assertTrue(FaceRings.contrast(old, intArrayOf(4, 7, 12)) < 1.7)
    }

    @Test
    fun `the error ring has a gap of seventy degrees centred at the bottom`() {
        // Compose's angles: 0 is three o'clock, clockwise, so 90 is six o'clock.
        assertEquals(90f, FaceRings.SIX_OCLOCK_DEG, 0f)
        val start = FaceRings.errorArcStart()
        val end = start + FaceRings.errorArcSweep()
        assertEquals(360f - FaceRings.ERROR_GAP_DEG, FaceRings.errorArcSweep(), 0f)
        // The arc starts 35 degrees after six o'clock and stops 35 degrees before it (a lap on).
        assertEquals(125f, start, 1e-4f)
        assertEquals(360f + 55f, end, 1e-4f)
        assertEquals("centred on six o'clock", 90f, ((start + end - 360f) / 2f), 1e-4f)
    }

    @Test
    fun `the not-connected ring is the heavy one and the error ring the thin one, at every size`() {
        for (side in listOf(40f, 120f, 300f, 1000f)) {
            val offline = max(FaceRings.OFFLINE_MIN_PX, side * FaceRings.OFFLINE_W)
            val error = max(FaceRings.ERROR_MIN_PX, side * FaceRings.ERROR_W)
            assertTrue("at $side: not connected $offline, error $error", offline >= error * 1.5f)
        }
        // Both sit outside the waiting clock (0.95) and the notch ring (0.93) of the overlay radius.
        assertTrue(FaceRings.RING_R > 0.95f)
    }

    @Test
    fun `the phone draws the error ring only on a character face, only for an error, never while not connected`() {
        val view = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/face/FaceView.kt").readText()
        assertTrue(view.contains("if (!offline && state == FaceState.ERROR && shown is CritterFace)"))
        assertTrue(view.contains("if (errorRing != null) drawErrorRing(size.minDimension, errorRing)"))
        // The colours go through the one rule, not a local dim.
        assertTrue(view.contains("FaceRings.tone("))
        assertTrue("the old dimmed ring is gone", !view.contains("dimmed(bindings.of(state).tint ?: Palette.NEUTRAL_3"))
        // Flat ends, so the gap is exactly the gap; drawn with the shared numbers.
        assertTrue(view.contains("cap = StrokeCap.Butt"))
        assertTrue(view.contains("startAngle = FaceRings.errorArcStart()"))
    }

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }
}
