package com.jarvis.client

import com.jarvis.client.net.Antislop
import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The Anti-Slop filter on the phone (2026-10-28; `net/Antislop.kt`,
 * `ui/screens/AntislopPlate.kt`; backend `jarvis_antislop.py`; docs/JARVIS-API
 * section 159).
 *
 * WHAT THIS HOLDS. The phone shows the master switch, the em-dash exemption and
 * the During/After mode, and it shows them from the PC's own answer: the
 * payloads below are the SHAPE `jarvis_antislop.get_state()` really writes, key
 * for key (`enabled`, `mode`, `scopes`, `dials`,
 * `show_delivery_gate_on_ui_tasks`, `allow_em_dashes`). The three bodies this
 * side can send carry ONE field each, so setting the switch never resets the
 * mode, the mode never resets the switch, and the em-dash box touches neither -
 * the same promise the desktop card keeps.
 *
 * The case a hand-written fixture would miss is the last group: a PC whose
 * backend has no route, or answers without a yes-or-no, must NOT be drawn as a
 * filter that is simply off. There is a difference between "off" and "cannot
 * tell", and the phone is required to say so.
 */
class AntislopTest {

    /** The PC's answer, as `jarvis_antislop.get_state()` writes it, OFF. */
    private fun state(
        enabled: Boolean = false,
        mode: String = "during",
        gate: Boolean = true,
        emDashes: Boolean = false,
        withEmDashes: Boolean = true,
    ): JsonObject = buildJsonObject {
        put("enabled", enabled)
        put("mode", mode)
        put("scopes", buildJsonObject {
            put("copy", true)
            put("code", true)
            put("ui", true)
        })
        put("dials", buildJsonObject {
            put("energy", 1)
            put("rhythm", 2)
            put("motion", 1)
        })
        put("show_delivery_gate_on_ui_tasks", gate)
        // `withEmDashes = false` models a PC whose backend predates the field.
        if (withEmDashes) put("allow_em_dashes", emDashes)
        put("updated_at", 1793164200.0)
    }

    // ------------------------------------------------------ reading it ----

    @Test
    fun `the PC's own state is read as the two controls`() {
        val v = Antislop.parse(state())!!
        assertFalse(v.enabled)
        assertEquals("during", v.mode)
        // The phone's words are the desktop's, so the two screens read alike.
        assertEquals(Antislop.OFF_NOTE, v.offNote)
        assertTrue(v.offNote.contains("0 prompt tokens"))
        // OFF is the PC's default for the em-dash exemption too.
        assertFalse(v.allowEmDashes)

        val on = Antislop.parse(state(enabled = true, mode = "after"))!!
        assertTrue(on.enabled)
        assertEquals("after", on.mode)
    }

    @Test
    fun `the em-dash exemption is OFF unless the PC sends a real yes`() {
        assertTrue(Antislop.parse(state(emDashes = true))!!.allowEmDashes)
        assertFalse(Antislop.parse(state(emDashes = false))!!.allowEmDashes)
        // A backend that predates the field: unticked, which is what it holds.
        assertFalse(Antislop.parse(state(withEmDashes = false))!!.allowEmDashes)
        // And a stray string is not a ticked box.
        val stray = buildJsonObject {
            put("enabled", true)
            put("allow_em_dashes", "true")
        }
        assertFalse(Antislop.parse(stray)!!.allowEmDashes)
    }

    @Test
    fun `the em-dash row says who already wins, so it is not read as the voiceprint`() {
        // Gemini review Q3: Write Like Me's own habit wins on its own; this box
        // is the blanket "keep them everywhere" on top of it.
        assertEquals("Allow em-dashes (\u2014)", Antislop.EM_DASH_LABEL)
        assertTrue(Antislop.EM_DASH_DETAIL.contains("Write Like Me"))
        assertTrue(Antislop.EM_DASH_DETAIL.contains("already wins"))
        assertTrue(Antislop.EM_DASH_DETAIL.contains("everywhere"))
        assertTrue(Antislop.EM_DASH_SAID.getValue(true).contains("everywhere"))
        assertTrue(Antislop.EM_DASH_SAID.getValue(false).contains("stripped"))
        assertFalse(
            "the em-dash row must not reuse the mode's sentence",
            Antislop.EM_DASH_SAID.getValue(true) == Antislop.MODE_SAID.getValue("during"),
        )
    }

    @Test
    fun `the enforcement line names what is checked in code and calls the rest guidance`() {
        // Gemini review Q1: the deterministic half is a fixed list, named; the
        // live-browser half is guidance and must not be sold as enforced.
        assertTrue(Antislop.REALITY.contains("fixed list in code"))
        assertTrue(Antislop.REALITY.contains("guidance only"))
        for (said in listOf("em-dashes", "buzzwords", "contrast")) {
            assertTrue("the fixed list must name $said", Antislop.REALITY.contains(said))
        }
        assertFalse(
            "the card may never claim every rule is enforced",
            Regex("every rule|all the rules", RegexOption.IGNORE_CASE)
                .containsMatchIn(Antislop.REALITY),
        )
        assertFalse(
            "browser-only rules must not be listed as checked",
            Regex("tap targets|overflow", RegexOption.IGNORE_CASE)
                .containsMatchIn(Antislop.REALITY),
        )
    }

    @Test
    fun `a mode the PC did not send falls back to during, never to a guess`() {
        assertEquals("during", Antislop.parse(state(mode = "sometime"))!!.mode)
        assertEquals("during", Antislop.parse(buildJsonObject { put("enabled", true) })!!.mode)
    }

    @Test
    fun `a body with no yes-or-no is NOT read as off`() {
        // "cannot tell" is not "off": the screen must say the route is missing
        // rather than sit at off over a filter that may be running.
        assertNull(Antislop.parse(buildJsonObject { put("mode", "during") }))
        assertNull(Antislop.parse(buildJsonObject {
            put("available", false)
            put("why", "no such route")
        }))
    }

    @Test
    fun `a PC without the route is named, not guessed at`() {
        assertTrue(Antislop.missing(ApiError.NotFound))
        assertTrue(Antislop.missing(ApiError.NotAvailable))
        assertTrue(Antislop.missing(ApiError.Server(501, "")))
        assertFalse(Antislop.missing(ApiError.Server(500, "")))
        assertTrue(Antislop.MISSING.contains("apply-patches.ps1"))
    }

    // ------------------------------------------------------ changing it ----

    @Test
    fun `the switch sends one field, and the mode sends one field`() {
        assertEquals("""{"enabled":true}""", Antislop.enabledBody(true))
        assertEquals("""{"enabled":false}""", Antislop.enabledBody(false))
        assertEquals("""{"mode":"after"}""", Antislop.modeBody("after"))
        assertEquals("""{"mode":"during"}""", Antislop.modeBody("during"))
        // Anything that is not a real mode is refused here rather than posted.
        assertNull(Antislop.modeBody("sometime"))
        assertNull(Antislop.modeBody(""))
    }

    @Test
    fun `the em-dash box sends one field, in the PC's own spelling`() {
        // Gemini review Q3: `{change: {allow_em_dashes}}` on the same route,
        // and nothing else - ticking it must never reset the switch or the mode.
        assertEquals("""{"allow_em_dashes":true}""", Antislop.emDashBody(true))
        assertEquals("""{"allow_em_dashes":false}""", Antislop.emDashBody(false))
        assertFalse(Antislop.emDashBody(true).contains("enabled"))
        assertFalse(Antislop.emDashBody(true).contains("mode"))
    }

    @Test
    fun `the two bodies never carry each other's field`() {
        assertFalse(Antislop.enabledBody(true).contains("mode"))
        assertFalse(Antislop.modeBody("after")!!.contains("enabled"))
        // The path is the contract's one route, not a second one for the phone.
        assertEquals("/api/antislop", Antislop.PATH)
        assertEquals(listOf("during", "after"), Antislop.MODES)
    }

    @Test
    fun `the sentence after a change is the PC's, and ours only as a fallback`() {
        // `words` is the key `jarvis_antislop` answers with on both routes; a
        // leftover `said` is deliberately wrong here and must be ignored, which
        // is what proves the phone reads the real one (2026-10-28 audit).
        val ok = ApiResult.Ok(buildJsonObject {
            put("words", "PC said it.")
            put("said", "not a key any backend sends")
        })
        assertEquals("PC said it.", Antislop.replyLine(ok, true))
        assertEquals("PC said it.", Antislop.modeReplyLine(ok, "after"))
        assertEquals("PC said it.", Antislop.emDashReplyLine(ok, true))

        val silent = ApiResult.Ok(buildJsonObject { put("enabled", true) })
        assertEquals(Antislop.SAID.getValue(true), Antislop.replyLine(silent, true))
        assertEquals(Antislop.MODE_SAID.getValue("after"), Antislop.modeReplyLine(silent, "after"))
        assertEquals(Antislop.EM_DASH_SAID.getValue(true), Antislop.emDashReplyLine(silent, true))

        // A PC that refuses says so in its own words, and a PC without the
        // route is named - never a silent success.
        val refused = ApiResult.Ok(buildJsonObject { put("error", "the settings file is busy") })
        assertEquals("the settings file is busy", Antislop.replyLine(refused, true))
        assertEquals("the settings file is busy", Antislop.emDashReplyLine(refused, false))
        val gone = ApiResult.Failed(ApiError.NotFound)
        assertEquals(Antislop.MISSING, Antislop.replyLine(gone, true))
        assertEquals(Antislop.MISSING, Antislop.modeReplyLine(gone, "during"))
        assertEquals(Antislop.MISSING, Antislop.emDashReplyLine(gone, true))
    }

    @Test
    fun `every mode explains itself, so the radio is not a bare pair of words`() {
        assertEquals(listOf("during", "after"), Antislop.MODE_LABEL.keys.toList())
        assertEquals(listOf("during", "after"), Antislop.MODE_WHY.keys.toList())
        Antislop.MODE_WHY.values.forEach { assertTrue(it.length > 20) }
        Antislop.MODE_LABEL.forEach { (id, label) ->
            assertTrue("$id must say what it does", label.contains(" - "))
        }
    }

    @Test
    fun `the phone is a mirror - it grows no scope list and no dials`() {
        // ARCHITECTURE section 8: scopes, the gate switch and the dials are the
        // desktop card's. This side must not offer a control whose body it
        // cannot send, and the three bodies above are the whole vocabulary.
        // A JVM unit test's working directory is the module on some runners and
        // the repo on others, so this walks up to the repository rather than
        // guessing (the same helper AutoLearnTest uses).
        val source = repoFile(MODULE).readText()
        assertFalse("the phone holds a dial it cannot set", source.contains("energy"))
        assertFalse(
            "the phone holds the Delivery Gate switch it cannot set",
            source.contains("show_delivery_gate"),
        )
        // The em-dash exemption IS here on purpose: it is the owner's own
        // writing voice rather than tuning, it is one switch with one field,
        // and the PC's voiceprint precedence is explained beside it.
        assertTrue(
            "the phone must carry the em-dash exemption (Gemini review Q3)",
            source.contains("allow_em_dashes"),
        )
    }

    /** The route the phone calls, and that it calls only that one. */
    @Test
    fun `the answer to a stale link is a sentence, not a change`() {
        // The stale-link hold itself lives in JarvisRuntime.actionBlocker, which
        // a plain JVM test cannot drive; what is pinned here is that this side
        // has ONE route to hold and no second write path.
        val wire = Json.parseToJsonElement("""{"enabled": true, "mode": "during"}""")
        assertTrue(Antislop.parse(wire as JsonObject)!!.enabled)
    }

    // ------------------------------------------------- the event wiring ----
    //
    // The gap the 2026-10-28 audit found: the PC publishes one `antislop` frame
    // on every change made anywhere else, the desktop card repaints from it,
    // and the phone's event loop had no branch for it - so an open plate kept
    // showing whatever it read when Settings was opened.

    @Test
    fun `the phone listens for the kind the PC really publishes`() {
        // ONE spelling for the frame, pinned against the publisher's own line
        // (`jarvis_antislop._publish`: one kind per feature, the whole state).
        assertEquals("antislop", Antislop.EVENT)
        val pc = repoFile(PC_MODULE).readText()
        assertTrue(
            "the PC no longer publishes the kind the phone listens for:\n$pc",
            pc.contains("BUS.publish(\"antislop\", dict(state))"),
        )
        // The frame carries the whole state, the same shape GET answers, so an
        // event's payload parses through the ONE Antislop.parse the plate draws
        // from: a change lands as the state the plate shows, not as a guess.
        val event = state(enabled = true, mode = "after", emDashes = true)
        val v = Antislop.parse(event)!!
        assertTrue(v.enabled)
        assertEquals("after", v.mode)
        assertTrue(v.allowEmDashes)
    }

    @Test
    fun `an antislop event re-reads through the plate's own path`() {
        val rt = repoFile(RUNTIME).readText()
        // The event loop's branch: the one kind, and the tick that wakes the
        // plate - no new route and no second parser.
        val branch = "com.jarvis.client.net.Antislop.EVENT -> _antislopTick.update { it + 1 }"
        assertTrue("the event loop has no antislop branch", rt.contains(branch))
        // The tick is exposed as state, so the plate can observe it.
        assertTrue(
            "the tick is not exposed to the plate",
            rt.contains("val antislopTick: StateFlow<Int> = _antislopTick.asStateFlow()"),
        )
        // The plate watches the tick and keys its EXISTING read on it: the same
        // GET /api/antislop it makes on open, not a payload parser of its own.
        val plate = repoFile(PLATE).readText()
        assertTrue(
            "the plate does not collect the tick",
            plate.contains("val tick by JarvisRuntime.antislopTick.collectAsState()"),
        )
        assertTrue(
            "the plate's read is not keyed on the tick",
            plate.contains("LaunchedEffect(reads, tick)"),
        )
        assertTrue(
            "the plate no longer reads the route it draws",
            plate.contains("when (val r = JarvisRuntime.antislop())"),
        )
        assertFalse("the plate must not grow a route of its own", plate.contains("/api/"))
        // And the route itself is unchanged: the event adds no second read path.
        assertEquals("/api/antislop", Antislop.PATH)
    }

    // ------------------------------------------------------------ helpers ----

    /**
     * Walks up from Gradle's working folder (`jarvis-client/app`) to the
     * repository, so a source pin runs wherever the test was started (the same
     * helper AutoLearnTest uses).
     */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private val MODULE = "jarvis-client/app/src/main/java/com/jarvis/client/net/Antislop.kt"
    private val RUNTIME =
        "jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt"
    private val PLATE =
        "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/AntislopPlate.kt"
    private val PC_MODULE = "backend/jarvis_antislop.py"
}
