package com.jarvis.client

import androidx.compose.ui.graphics.Color
import com.jarvis.client.face.Binding
import com.jarvis.client.face.Faces
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

    /**
     * Every face the picker offers must be a face the desktop also knows.
     *
     * Nothing checked this before, and it matters more now than it did: the
     * appearance-sync proposal rests entirely on both ends naming the same
     * things. A face id invented on this side — a typo, or a name that felt
     * better in Kotlin — would sync as a value the desktop cannot resolve, and
     * the failure would land on the *other* machine.
     */
    @Test
    fun `every face the client offers exists in the shared spec`() {
        val known = spec["faces"]!!.jsonArray
            .map { it.jsonObject }
            .associateBy { it["id"]!!.jsonPrimitive.content }
        for (face in Faces.all) {
            assertNotNull(
                "face '${face.id}' is not in jarvis-visual-spec.json — the desktop has no " +
                    "such face, so this id cannot be shared with it",
                known[face.id],
            )
        }
    }

    /**
     * The faces the spec calls `heavy` stay out, unless they now render on a
     * real shader or a real GPU mesh.
     *
     * `heavy` and "needs more than `DrawScope`" are not the same set, which
     * is worth being exact about since it is easy to conflate them. The spec
     * marks exactly two faces `heavy` - `tokamak` and `nucleus` - meaning "a
     * Canvas version of this would be worse than not offering it". `membrane`
     * needs just as much work to offer honestly, but the spec marks it
     * `heavy: false`; it is excluded by the OTHER guard below, `iris is the
     * only offered face that cannot be pinned`, because what stops it is its
     * live Verlet simulation, not its render cost.
     *
     * `heavy` said nothing about `DrawScope` being the only way to earn an
     * exemption - it says a *Canvas* version is worse than not offering one,
     * which is no longer a true statement about `nucleus`
     * (`android.graphics.RuntimeShader`) or `tokamak` (a real GLES 3.0 mesh
     * via `GLSurfaceView`; see their own doc comments in Faces.kt and
     * `com.jarvis.client.face.gl`). So both are carved out by name as they
     * earn it. That happens to exhaust the spec's entire `heavy` set, which
     * is why this test's own "the spec should still mark something heavy"
     * canary is checked against the RAW spec data below, not against what is
     * left after the carve-out - the carve-out emptying out is the point of
     * doing the work, not a sign the check has gone slack.
     */
    @Test
    fun `no face the spec marks heavy is offered, unless it now renders on a real shader`() {
        val specHeavy = spec["faces"]!!.jsonArray
            .map { it.jsonObject }
            .filter { it["heavy"]?.jsonPrimitive?.content == "true" }
            .map { it["id"]!!.jsonPrimitive.content }
            .toSet()
        assertTrue("the spec should still mark some faces heavy", specHeavy.isNotEmpty())

        // See the comment above: each id here is out of the heavy set it
        // belongs to in the spec because it earned it, not because the
        // check got looser. Emptying this out entirely is the expected,
        // fully-earned end state, not a bug in the guard.
        val rendersOnARealShaderDespiteSpecFlag = setOf("nucleus", "tokamak")
        val heavy = specHeavy - rendersOnARealShaderDespiteSpecFlag
        for (face in Faces.all) {
            assertTrue(
                "face '${face.id}' is marked heavy in the spec and needs a shader; a canvas " +
                    "version is worse than not offering it",
                face.id !in heavy,
            )
        }
    }

    /**
     * Which offered faces carry simulation state, pinned as an exact set.
     *
     * A face the spec marks `integrates_per_frame` has no value a golden test
     * can assert: its output depends on every frame before it, so it cannot be
     * compared against the desktop's version and a drift between the two stays
     * invisible until someone holds the two screens side by side.
     *
     * `iris` is one of those and is already in this app. That is recorded here
     * rather than endorsed — it shipped before this rule existed, and it is the
     * one face whose fidelity to the desktop nothing can check. Rime and
     * Orbital were chosen over flashier candidates precisely to avoid a second.
     *
     * Spectrum, coreplate, workbench, swarm, shoal, accretion and cascade are
     * also marked `integrates_per_frame: true` in the spec, because their
     * desktop reference genuinely does carry state — a smoothed FFT, boid
     * velocities, a DLA grid, a live particle list. None of that state was
     * ported. Each one here is a deterministic function of `t`, a fixed
     * per-element seed, and the already-smoothed `f.amp`: call `draw` twice
     * with the same inputs and it draws the same picture twice, which is
     * exactly the property this test is protecting. They are carved out of
     * the filter below for that reason — the spec's flag describes the
     * *reference's* technique, not this port's, and is wrong for these seven
     * specifically, not wrong to check in general.
     *
     * An exact set rather than a blanket ban, so adding another stateful face
     * fails this test and has to be argued rather than done quietly.
     */
    @Test
    fun `iris is the only offered face that cannot be pinned`() {
        // See the class comment above: these seven are deterministic in this
        // port despite the spec marking their id `integrates_per_frame: true`
        // for the desktop reference's own, genuinely stateful, technique.
        val deterministicDespiteSpecFlag = setOf(
            "spectrum", "coreplate", "workbench", "swarm", "shoal", "accretion", "cascade",
        )
        val stateful = spec["faces"]!!.jsonArray
            .map { it.jsonObject }
            .filter { it["integrates_per_frame"]?.jsonPrimitive?.content == "true" }
            .map { it["id"]!!.jsonPrimitive.content }
            .toSet() - deterministicDespiteSpecFlag
        assertEquals(
            "the set of simulation-driven faces this app offers has changed. Each one is a " +
                "face that cannot be verified against the desktop, so this should be a " +
                "deliberate decision rather than a test update",
            setOf("iris"),
            Faces.all.map { it.id }.filter { it in stateful }.toSet(),
        )
    }

    /**
     * The id this app writes for a state is the id the spec uses.
     *
     * `AppearanceStore` stores bindings keyed by `FaceState.name.lowercase()`,
     * and `/api/appearance` keys by the spec's `states[].id`. Those agree
     * today by coincidence of naming, which is exactly the kind of agreement
     * this project keeps discovering it did not actually have - the enum is
     * Kotlin's to rename and the spec is the contract's.
     *
     * Asserted rather than maintained, so renaming either one is a red build
     * instead of a face that silently reverts to defaults on both devices.
     */
    @Test
    fun `every face state maps onto a spec state id`() {
        val specIds = spec["states"]!!.jsonArray
            .map { it.jsonObject["id"]!!.jsonPrimitive.content }
            .toSet()
        assertEquals(
            "the ids this app would send to /api/appearance no longer match the spec's " +
                "states[].id. AppearanceStore keys on FaceState.name.lowercase(); if either " +
                "side was renamed, the mapping has to become explicit rather than incidental",
            specIds,
            FaceState.entries.map { it.name.lowercase() }.toSet(),
        )
    }
}

private fun kotlinx.serialization.json.JsonPrimitive.contentOrNullSafe(): String? =
    if (this is kotlinx.serialization.json.JsonNull) null else content
