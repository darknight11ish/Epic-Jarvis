package com.jarvis.client

import androidx.compose.ui.graphics.Color
import com.jarvis.client.face.Binding
import com.jarvis.client.face.Palette
import com.jarvis.client.face.Params
import com.jarvis.client.face.Pattern
import com.jarvis.client.face.resolveRaw
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.float
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Replays 640 samples generated from the OTHER client's pattern engine.
 *
 * This is the test the parity review asked for, and its value is entirely in
 * where the expected values came from: `tools/gen_golden.py` is a faithful port
 * of `shell.html`'s `_resolveRaw`, so these numbers were produced by the
 * desktop's algorithm rather than by mine. Every face test before this one
 * compared Kotlin constants to other Kotlin constants, which is exactly why
 * two transcription drifts survived a green suite for a week.
 *
 * It found two more on its first run: `flicker` was implemented as a pair of
 * sine oscillators lifting one colour, where the reference walks the family's
 * palette ramp by a hash — 117/255 out on the hot channel — and `temperature`
 * darkened its structural colour by 0.55 against the reference's 0.50.
 *
 * If this fails, the Kotlin is wrong until proven otherwise. Regenerating the
 * golden file to make it pass turns it back into the thing it replaced.
 */
class PatternGoldenTest {

    private val golden by lazy {
        val text = checkNotNull(javaClass.classLoader?.getResourceAsStream("pattern-golden.json")) {
            "pattern-golden.json is missing from test resources"
        }.bufferedReader().readText()
        Json.parseToJsonElement(text).jsonObject.getValue("cases").jsonArray
    }

    private fun hex(c: Color): String = String.format(
        "#%02x%02x%02x",
        (c.red * 255f).toInt().coerceIn(0, 255),
        (c.green * 255f).toInt().coerceIn(0, 255),
        (c.blue * 255f).toInt().coerceIn(0, 255),
    )

    /** Rounding at the last bit differs between a Float lerp and a Double one. */
    private fun close(a: String, b: String): Boolean {
        if (a == b) return true
        fun ch(s: String, i: Int) = s.substring(1 + i * 2, 3 + i * 2).toInt(16)
        return (0..2).all { kotlin.math.abs(ch(a, it) - ch(b, it)) <= 1 }
    }

    @Test
    fun `every pattern matches the reference implementation`() {
        assertTrue("the golden set is empty", golden.size > 500)
        var checked = 0
        val failures = mutableListOf<String>()

        for (element in golden) {
            val c = element.jsonObject
            val patternId = c.getValue("pattern").jsonPrimitive.content
            val pattern = checkNotNull(Pattern.byId(patternId)) { "no Pattern for '$patternId'" }

            val colour = c["color"]?.jsonPrimitive?.contentOrNull()?.let { Palette.byId[it] }
            val params = c["params"]?.jsonObject?.let { p ->
                Params(
                    periodS = p["period_s"]?.jsonPrimitive?.float,
                    sharpness = p["sharpness"]?.jsonPrimitive?.float,
                    spanDeg = p["span_deg"]?.jsonPrimitive?.float,
                    offsetDeg = p["offset_deg"]?.jsonPrimitive?.float,
                    sat = p["sat"]?.jsonPrimitive?.float,
                    light = p["light"]?.jsonPrimitive?.float,
                    gain = p["gain"]?.jsonPrimitive?.float,
                    loud = p["loud"]?.jsonPrimitive?.content?.let { Palette.byId[it] },
                )
            } ?: Params()

            val out = resolveRaw(
                Binding(pattern, colour, params),
                c.getValue("t").jsonPrimitive.float,
                c.getValue("amp").jsonPrimitive.float,
                c.getValue("seed").jsonPrimitive.int,
            )

            val wantA = c.getValue("a").jsonPrimitive.content
            val wantB = c.getValue("b").jsonPrimitive.content
            val label = c["state"]?.jsonPrimitive?.content?.let { "$it/$patternId" } ?: patternId
            if (!close(hex(out.a), wantA)) {
                failures += "$label t=${c.getValue("t").jsonPrimitive.content} a: got ${hex(out.a)} want $wantA"
            }
            if (!close(hex(out.b), wantB)) {
                failures += "$label t=${c.getValue("t").jsonPrimitive.content} b: got ${hex(out.b)} want $wantB"
            }
            checked++
        }

        assertEquals(golden.size, checked)
        assertTrue(
            "${failures.size} of ${golden.size * 2} colours differ from the reference:\n" +
                failures.take(12).joinToString("\n"),
            failures.isEmpty(),
        )
    }
}

private fun kotlinx.serialization.json.JsonPrimitive.contentOrNull(): String? =
    if (this is kotlinx.serialization.json.JsonNull) null else content
