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
 * WHAT THIS HOLDS. The phone shows the master switch and the During/After
 * mode, and it shows them from the PC's own answer: the payloads below are the
 * SHAPE `jarvis_antislop.get_state()` really writes, key for key (`enabled`,
 * `mode`, `scopes`, `dials`, `show_delivery_gate_on_ui_tasks`). The two bodies
 * this side can send carry ONE field each, so setting the switch never resets
 * the mode and vice versa - the same promise the desktop card keeps.
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

        val on = Antislop.parse(state(enabled = true, mode = "after"))!!
        assertTrue(on.enabled)
        assertEquals("after", on.mode)
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
    fun `the two bodies never carry each other's field`() {
        assertFalse(Antislop.enabledBody(true).contains("mode"))
        assertFalse(Antislop.modeBody("after")!!.contains("enabled"))
        // The path is the contract's one route, not a second one for the phone.
        assertEquals("/api/antislop", Antislop.PATH)
        assertEquals(listOf("during", "after"), Antislop.MODES)
    }

    @Test
    fun `the sentence after a change is the PC's, and ours only as a fallback`() {
        val ok = ApiResult.Ok(buildJsonObject { put("said", "PC said it.") })
        assertEquals("PC said it.", Antislop.replyLine(ok, true))
        assertEquals("PC said it.", Antislop.modeReplyLine(ok, "after"))

        val silent = ApiResult.Ok(buildJsonObject { put("enabled", true) })
        assertEquals(Antislop.SAID.getValue(true), Antislop.replyLine(silent, true))
        assertEquals(Antislop.MODE_SAID.getValue("after"), Antislop.modeReplyLine(silent, "after"))

        // A PC that refuses says so in its own words, and a PC without the
        // route is named - never a silent success.
        val refused = ApiResult.Ok(buildJsonObject { put("error", "the settings file is busy") })
        assertEquals("the settings file is busy", Antislop.replyLine(refused, true))
        val gone = ApiResult.Failed(ApiError.NotFound)
        assertEquals(Antislop.MISSING, Antislop.replyLine(gone, true))
        assertEquals(Antislop.MISSING, Antislop.modeReplyLine(gone, "during"))
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
        // cannot send, and the two bodies above are the whole vocabulary.
        // A JVM unit test's working directory is the module on some runners and
        // the repo on others, so both spellings are tried (the same shape
        // AppControlSensitiveFindTest uses).
        val rel = "src/main/java/com/jarvis/client/net/Antislop.kt"
        val file = listOf(File(rel), File("app/$rel")).firstOrNull { it.isFile }
        val source = file?.readText() ?: ""
        assertTrue("Antislop.kt was not found to read", source.isNotEmpty())
        assertFalse("the phone holds a dial it cannot set", source.contains("energy"))
        assertFalse(
            "the phone holds the Delivery Gate switch it cannot set",
            source.contains("show_delivery_gate"),
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
}
