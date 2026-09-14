package com.jarvis.client

import androidx.compose.ui.graphics.Color
import com.jarvis.client.face.Binding
import com.jarvis.client.face.Bindings
import com.jarvis.client.face.Palette
import com.jarvis.client.face.Pattern
import com.jarvis.client.face.Spec
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.float
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Asserts the Kotlin constants still match `jarvis-visual-spec.json`.
 *
 * This is the test that was missing, and its absence was structural rather than
 * an oversight: every other face test compares Kotlin constants to other Kotlin
 * constants, so no amount of them could ever catch a transcription drift. Two
 * had already happened — standby's breathe period and three of the nine chrome
 * colours — and both were invisible to a green suite.
 *
 * The spec is the contract shared with the desktop. A change there should break
 * this build, not quietly re-colour one of the two clients.
 */
class SpecDriftTest {

    private val spec: JsonObject by lazy {
        val text = checkNotNull(javaClass.classLoader?.getResourceAsStream("jarvis-visual-spec.json")) {
            "jarvis-visual-spec.json is missing from test resources"
        }.bufferedReader().readText()
        Json.parseToJsonElement(text).jsonObject
    }

    private fun hex(s: String): Color {
        val v = s.removePrefix("#")
        return Color(0xFF000000.toInt() or v.toInt(16))
    }

    @Test
    fun `the palette carries all fifty colours, matching the spec`() {
        val colors = spec.getValue("palette").jsonObject.getValue("colors").jsonArray
        assertEquals("the spec should carry 50 colours", 50, colors.size)
        assertEquals(50, Palette.byId.size)
        for (entry in colors) {
            val o = entry.jsonObject
            val id = o.getValue("id").jsonPrimitive.content
            val expected = hex(o.getValue("hex").jsonPrimitive.content)
            val actual = Palette.byId[id]
            assertNotNull("Palette is missing $id", actual)
            assertEquals("$id has drifted from the spec", expected, actual)
        }
    }

    @Test
    fun `the renderer background matches`() {
        val bg = spec.getValue("renderer").jsonObject.getValue("background").jsonPrimitive.content
        assertEquals(hex(bg), Spec.BACKGROUND)
    }

    @Test
    fun `every pattern's own params match the spec`() {
        val patterns = spec.getValue("patterns").jsonArray
        assertEquals("the spec should carry 12 patterns", 12, patterns.size)
        assertEquals(12, Pattern.entries.size)

        for (entry in patterns) {
            val o = entry.jsonObject
            val id = o.getValue("id").jsonPrimitive.content
            val ours = Pattern.byId(id)
            assertNotNull("no Pattern for '$id'", ours)
            ours!!
            assertEquals(
                "$id has the wrong kind",
                o.getValue("kind").jsonPrimitive.content,
                ours.kind.name.lowercase(),
            )

            val params = o["params"]?.jsonObject ?: JsonObject(emptyMap())
            val p = ours.params
            for ((key, value) in params) {
                when (key) {
                    "period_s" -> assertEquals("$id period_s", value.jsonPrimitive.float, p.periodS)
                    "depth" -> assertEquals("$id depth", value.jsonPrimitive.float, p.depth)
                    "sharpness" -> assertEquals("$id sharpness", value.jsonPrimitive.float, p.sharpness)
                    "span_deg" -> assertEquals("$id span_deg", value.jsonPrimitive.float, p.spanDeg)
                    "offset_deg" -> assertEquals("$id offset_deg", value.jsonPrimitive.float, p.offsetDeg)
                    "sat" -> assertEquals("$id sat", value.jsonPrimitive.float, p.sat)
                    "light" -> assertEquals("$id light", value.jsonPrimitive.float, p.light)
                    "gain" -> assertEquals("$id gain", value.jsonPrimitive.float, p.gain)
                    "hold_s" -> assertEquals("$id hold_s", value.jsonPrimitive.float, p.holdS)
                    "blend_s" -> assertEquals("$id blend_s", value.jsonPrimitive.float, p.blendS)
                    "rate_hz" -> assertEquals("$id rate_hz", value.jsonPrimitive.float, p.rateHz)
                    "family" -> assertEquals("$id family", value.jsonPrimitive.content, p.family)
                    "color" -> assertEquals("$id color", Palette.byId[value.jsonPrimitive.content], p.color)
                    "from" -> assertEquals("$id from", Palette.byId[value.jsonPrimitive.content], p.from)
                    "to" -> assertEquals("$id to", Palette.byId[value.jsonPrimitive.content], p.to)
                    "tail" -> assertEquals("$id tail", Palette.byId[value.jsonPrimitive.content], p.tail)
                    // strobe calls its pair `a` and `b`.
                    "a" -> assertEquals("$id a", Palette.byId[value.jsonPrimitive.content], p.onColor)
                    "b" -> assertEquals("$id b", Palette.byId[value.jsonPrimitive.content], p.offColor)
                    "quiet" -> assertEquals("$id quiet", Palette.byId[value.jsonPrimitive.content], p.quiet)
                    "loud" -> assertEquals("$id loud", Palette.byId[value.jsonPrimitive.content], p.loud)
                    "cold" -> assertEquals("$id cold", Palette.byId[value.jsonPrimitive.content], p.cold)
                    "warm" -> assertEquals("$id warm", Palette.byId[value.jsonPrimitive.content], p.warm)
                    "hot" -> assertEquals("$id hot", Palette.byId[value.jsonPrimitive.content], p.hot)
                    "colors" -> assertEquals(
                        "$id colors",
                        value.jsonArray.map { Palette.byId.getValue(it.jsonPrimitive.content) },
                        p.colors,
                    )
                    else -> error("$id carries an unmapped param '$key'")
                }
            }
        }
    }

    @Test
    fun `every shipped binding matches the spec's state default`() {
        val states = spec.getValue("states").jsonArray
        assertEquals("the spec should carry 8 states", 8, states.size)

        for (entry in states) {
            val o = entry.jsonObject
            val id = o.getValue("id").jsonPrimitive.content
            val state = FaceState.valueOf(id.uppercase())
            val default = o.getValue("default").jsonObject
            val ours: Binding = Bindings.DEFAULTS.of(state)

            assertEquals(
                "$id binds the wrong pattern",
                default.getValue("pattern").jsonPrimitive.content,
                ours.pattern.id,
            )

            val colour = default["color"]?.jsonPrimitive?.contentOrNullSafe()
            assertEquals("$id binds the wrong colour", colour?.let { Palette.byId[it] }, ours.color)

            // Rule 1: what the spec does not set, the pattern supplies. Reading
            // the MERGED params is the point — a default that repeats a
            // pattern's own value is a value that can drift from it, and
            // standby's breathe period did exactly that.
            val params = default["params"]?.jsonObject ?: JsonObject(emptyMap())
            val merged = ours.merged
            for ((key, value) in params) {
                when (key) {
                    "period_s" -> assertEquals("$id period_s", value.jsonPrimitive.float, merged.periodS)
                    "sharpness" -> assertEquals("$id sharpness", value.jsonPrimitive.float, merged.sharpness)
                    "span_deg" -> assertEquals("$id span_deg", value.jsonPrimitive.float, merged.spanDeg)
                    "offset_deg" -> assertEquals("$id offset_deg", value.jsonPrimitive.float, merged.offsetDeg)
                    "sat" -> assertEquals("$id sat", value.jsonPrimitive.float, merged.sat)
                    "light" -> assertEquals("$id light", value.jsonPrimitive.float, merged.light)
                    "gain" -> assertEquals("$id gain", value.jsonPrimitive.float, merged.gain)
                    "loud" -> assertEquals("$id loud", Palette.byId[value.jsonPrimitive.content], merged.loud)
                    else -> error("$id carries an unmapped param '$key'")
                }
            }

            // And where the spec sets nothing, the pattern's own value must be
            // what comes out.
            if ("period_s" !in params && ours.pattern.params.periodS != null) {
                assertEquals(
                    "$id should inherit ${ours.pattern.id}'s period",
                    ours.pattern.params.periodS,
                    merged.periodS,
                )
            }
        }
    }

    @Test
    fun `the photosensitivity limits match the spec`() {
        val flash = spec.getValue("limits").jsonObject.getValue("flash").jsonObject
        assertEquals(
            flash.getValue("max_transitions_per_s").jsonPrimitive.int,
            Spec.FLASH_MAX_TRANSITIONS_PER_S,
        )
        assertEquals(
            flash.getValue("min_luma_delta").jsonPrimitive.float,
            Spec.FLASH_MIN_LUMA_DELTA,
            1e-6f,
        )
        assertEquals(flash.getValue("strobe_max_s").jsonPrimitive.float, Spec.STROBE_MAX_S, 1e-6f)
        assertEquals(
            flash.getValue("flicker_rate_hz_max").jsonPrimitive.float,
            Spec.FLICKER_RATE_HZ_MAX,
            1e-6f,
        )
        assertEquals(
            flash.getValue("flicker_harmonic").jsonPrimitive.float,
            Spec.FLICKER_HARMONIC,
            1e-6f,
        )
    }

    @Test
    fun `the strobe floor is the spec's, not the prose's`() {
        // The strobe pattern's own `safety` string says "period_s below 0.4
        // would exceed the transition budget". It is wrong by a factor of two
        // — a strobe makes TWO opposing transitions per period — and I shipped
        // 0.4 because I read that sentence instead of doing the arithmetic.
        // limits.flash.enforced_in.resolve names the real floor.
        val flash = spec.getValue("limits").jsonObject.getValue("flash").jsonObject
        val max = flash.getValue("max_transitions_per_s").jsonPrimitive.int
        assertEquals(2f / max, Spec.STROBE_MIN_PERIOD_S, 1e-6f)
    }

    @Test
    fun `the spec names where each flash limit is enforced`() {
        // Added 14 Sep after this client found the third enforcement point was
        // not enforcing. If the block goes away, so has the guarantee.
        val flash = spec.getValue("limits").jsonObject.getValue("flash").jsonObject
        val where = flash.getValue("enforced_in").jsonObject
        for (key in listOf("randomiser", "resolve", "governor", "build_check")) {
            assertTrue("enforced_in is missing '$key'", key in where)
        }
    }

    @Test
    fun `the resting frame rates match the spec`() {
        val fps = spec.getValue("frame_rate").jsonObject.getValue("state_fps").jsonObject
        for ((id, value) in fps) {
            val state = FaceState.valueOf(id.uppercase())
            assertEquals("$id draws at the wrong rate", value.jsonPrimitive.int, Spec.fpsFor(state))
        }
    }

    @Test
    fun `every kind the spec names can be expressed`() {
        // A list of plain strings, not objects.
        val kinds = spec.getValue("pattern_kinds").jsonArray
            .map { it.jsonPrimitive.content }
        for (kind in kinds) {
            assertTrue(
                "no PatternKind for '$kind' — randomise can roll it and nothing would render",
                com.jarvis.client.face.PatternKind.entries.any { it.name.lowercase() == kind },
            )
        }
    }
}

private fun kotlinx.serialization.json.JsonPrimitive.contentOrNullSafe(): String? =
    if (this is kotlinx.serialization.json.JsonNull) null else content
