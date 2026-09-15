package com.jarvis.client

import com.jarvis.client.face.Binding
import com.jarvis.client.face.Palette
import com.jarvis.client.face.Pattern
import com.jarvis.client.face.resolveRaw
import androidx.compose.ui.graphics.Color
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.float
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * The Kotlin half of the shared `resolve()` fixture.
 *
 * The spec calls `resolve(binding, t, amp, seed) -> {a, b}` the contract and
 * everything else data — and it exists three times: `faces.html` in JS,
 * `spec.rs` for the desktop tray, and `Resolve.kt` here. Three ports of one
 * function, agreeing by discipline. This turns that agreement into a test.
 *
 * The fixture is generated from the JS implementation, which the other two are
 * ports of, by `scripts/build-resolve-vectors.mjs` on the desktop branch. Times
 * land on and off each cyclic pattern's period boundary, so a port that is off
 * by a half-phase fails here rather than passing at t=0, where most of them
 * agree by accident.
 *
 * Run against `resolveRaw`, not `resolve`: the governor and the strobe budget
 * are per-surface safety machinery layered on top, and the contract is the
 * colour the pattern asks for.
 */
class ResolveVectorsTest {

    private val fixture: JsonObject =
        Json.parseToJsonElement(
            requireNotNull(javaClass.classLoader?.getResourceAsStream("resolve-vectors.json"))
                .bufferedReader().readText(),
        ).jsonObject

    @Test
    fun `every exact vector reproduces the reference implementation`() {
        var checked = 0
        val wrong = mutableListOf<String>()

        for (v in fixture["vectors"]!!.jsonArray.map { it.jsonObject }) {
            if (!v["exact"]!!.jsonPrimitive.boolean) continue
            val bind = bindingOf(v) ?: continue
            checked += 1

            val got = resolveRaw(
                bind,
                t = v["t"]!!.jsonPrimitive.float,
                amp = v["amp"]!!.jsonPrimitive.float,
                seed = v["seed"]!!.jsonPrimitive.int,
            )
            val want = v["expect"]!!.jsonObject
            val wantA = css(want["a"]!!.jsonPrimitive.content)
            val wantB = css(want["b"]!!.jsonPrimitive.content)
            if (rgb8(got.a) != wantA || rgb8(got.b) != wantB) {
                wrong += "${v["kind"]!!.jsonPrimitive.content} t=${v["t"]!!.jsonPrimitive.content}: " +
                    "a ${rgb8(got.a)} want $wantA, b ${rgb8(got.b)} want $wantB"
            }
        }

        assertTrue("no exact vectors ran - the fixture did not load", checked > 50)
        assertEquals(
            "this port disagrees with the reference implementation on ${wrong.size} of " +
                "$checked vectors:\n" + wrong.take(12).joinToString("\n"),
            emptyList<String>(),
            wrong,
        )
    }

    /**
     * The flicker vectors, which must NOT be compared for equality.
     *
     * `hash01()` takes the fractional part of a sin, which is not bit-portable
     * across V8, libm and Rust's std. Flicker uses that hash to pick an INDEX
     * into a family ramp, so the output is discontinuous: one ulp either
     * changes the colour outright or not at all, and "close" is not a relation
     * between two entries in a ramp. A tolerance here would be meaningless
     * rather than lenient.
     *
     * What is portable, and is the actual contract, is the structure: both
     * colours come from the family ramp, and `b` sits two steps below `a`,
     * floored at the start.
     */
    @Test
    fun `flicker lands on the family ramp with b two steps below a`() {
        var checked = 0
        for (v in fixture["vectors"]!!.jsonArray.map { it.jsonObject }) {
            if (v["exact"]!!.jsonPrimitive.boolean) continue
            val holds = v["holds"]?.jsonObject ?: continue
            val bind = bindingOf(v) ?: continue
            checked += 1

            val ramp = holds["ramp"]!!.jsonArray.map { css(it.jsonPrimitive.content) }
            val got = resolveRaw(
                bind,
                t = v["t"]!!.jsonPrimitive.float,
                amp = v["amp"]!!.jsonPrimitive.float,
                seed = v["seed"]!!.jsonPrimitive.int,
            )
            val ia = ramp.indexOf(rgb8(got.a))
            val ib = ramp.indexOf(rgb8(got.b))
            val family = holds["family"]!!.jsonPrimitive.content

            assertTrue(
                "flicker produced ${rgb8(got.a)}, which is not an entry in the $family ramp $ramp",
                ia >= 0,
            )
            assertTrue(
                "flicker's second colour ${rgb8(got.b)} is not an entry in the $family ramp $ramp",
                ib >= 0,
            )
            assertEquals(
                "b should be two ramp steps below a, floored at the start",
                max(0, ia - 2),
                ib,
            )
        }
        assertTrue("no flicker vectors ran - the fixture did not load", checked > 0)
    }

    // ------------------------------------------------------------------ --

    /**
     * Null for a vector this port cannot construct a binding for.
     *
     * Only `__unknown_id__` hits that, and the fixture's own note says it is
     * not discriminating on this spec anyway: `patterns[0]` is solid/ice-4,
     * ice-4 is #6fe3ff, and that is also the reference's own fallback colour,
     * so an implementation that wrongly returns the hardcoded default passes
     * regardless. Skipped rather than asserted, so it cannot read as coverage.
     */
    private fun bindingOf(v: JsonObject): Binding? {
        val b = v["bind"]!!.jsonObject
        val pattern = Pattern.byId(b["pattern"]!!.jsonPrimitive.content) ?: return null
        // A palette id OR a literal hex. `Palette.byId["#ff0000"]` is null, so
        // reading only the palette silently DROPPED the override and resolved
        // with the pattern's own colour - which is what all eight of run 62's
        // disagreements were. The fixture says so in its own note on those
        // vectors: "a literal hex passes through hexOf unchanged".
        //
        // The arithmetic settles it: twelve vectors carry a hex override, four
        // of them use patterns that ignore a bound colour (rainbow, sweep,
        // cycle, temperature), and twelve minus four is eight. The port was
        // never wrong; it was never handed the colour.
        val colour = b["color"]?.jsonPrimitive?.content?.let { id ->
            Palette.byId[id] ?: if (id.startsWith("#")) {
                val (r, g, bl) = css(id)
                Color(red = r / 255f, green = g / 255f, blue = bl / 255f)
            } else {
                error("vector names a colour '$id' that is neither a palette id nor a hex literal")
            }
        }
        return Binding(pattern = pattern, color = colour)
    }

    /** `#rrggbb` or `rgb(r,g,b)`, the two shapes the JS reference emits. */
    private fun css(s: String): Triple<Int, Int, Int> = when {
        s.startsWith("#") -> Triple(
            s.substring(1, 3).toInt(16),
            s.substring(3, 5).toInt(16),
            s.substring(5, 7).toInt(16),
        )
        s.startsWith("rgb(") -> s.removePrefix("rgb(").removeSuffix(")")
            .split(",").map { it.trim().toInt() }
            .let { Triple(it[0], it[1], it[2]) }
        else -> error("unrecognised colour literal '$s' in the fixture")
    }

    private fun rgb8(c: Color): Triple<Int, Int, Int> = Triple(
        (c.red * 255f).roundToInt(),
        (c.green * 255f).roundToInt(),
        (c.blue * 255f).roundToInt(),
    )
}
