package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.FocusPresets
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The focus-presets contract (net/FocusPresets.kt), against the REAL generated
 * fixture `backend/fixtures/work_presets.json` (tools/gen_work_cases.py from
 * backend/jarvis_presets.py - never hand-edited). The contract lives on the
 * backend branch until it lands; this test reads the same path both apps will.
 *
 * The list is deliberately generic: the owner added a fifth preset
 * (general_uncensored, pending), and Agentic+Vision's model may change after a
 * measurement, so nothing here may hardcode four ids, a count, or a model.
 */
class FocusPresetsTest {

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private val fixture: JsonObject by lazy {
        JarvisJson.parseToJsonElement(
            repoFile("backend/fixtures/work_presets.json").readText(),
        ) as JsonObject
    }

    private val view: FocusPresets.View by lazy {
        requireNotNull(FocusPresets.parse(fixture)) { "the generated fixture did not parse" }
    }

    @Test
    fun `the contract is one list, parsed generically - no id or count hardcoded`() {
        // At least the owner's five named presets are present, in the PC's order.
        val ids = view.presets.map { it.id }
        assertTrue("General", "general" in ids)
        assertTrue("General Uncensored", "general_uncensored" in ids)
        assertTrue("Coding", "coding" in ids)
        assertTrue("Agentic+Vision", "agentic_vision" in ids)
        assertTrue("Fast", "fast" in ids)
        assertEquals("the fixture's own order is kept", ids, view.presets.map { it.id })

        // A client never invents the list: one extra unknown preset parses too.
        val extra = buildJsonObject {
            put("presets", kotlinx.serialization.json.buildJsonArray {
                add(buildJsonObject {
                    put("id", "owner_added_one")
                    put("title", "Owner Added One")
                    put("lane", buildJsonObject { put("card", "Some card") })
                    put("apply", buildJsonObject { put("action", "Use this preset") })
                })
            })
        }
        val generic = requireNotNull(FocusPresets.parse(extra))
        assertEquals(listOf("owner_added_one"), generic.presets.map { it.id })
    }

    @Test
    fun `every word the screen shows is the contract's - never a hardcoded preset`() {
        for (p in view.presets) {
            assertTrue(p.id, p.title.isNotBlank())
            assertTrue(p.id, p.focus.isNotBlank())
            assertTrue(p.id, p.what.isNotBlank())
            assertTrue(p.id, p.cost.isNotBlank())
            assertTrue(p.id, p.worse.isNotBlank())
            assertTrue(p.id, p.model.isNotBlank())
            assertTrue(p.id, p.lane.card.isNotBlank())
            assertTrue(p.id, p.lane.words.isNotBlank())
            assertEquals(p.id, "Use this preset", p.apply.action)
            assertFalse(p.id, p.apply.auto)
        }
        // The exact strings the fixture really carries, so a changed contract
        // is caught here rather than silently reworded on the phone alone.
        assertEquals("General", view.preset("general")!!.title)
        assertEquals("everyday questions, writing, life admin", view.preset("general")!!.focus)
        assertEquals("qwen3.5:9b", view.preset("general")!!.model)
        assertEquals("RTX 2060", view.preset("general")!!.lane.card)
        assertEquals("the long-context card", view.preset("general")!!.lane.words)
    }

    @Test
    fun `General Uncensored is a measured preset after the contract landed`() {
        val uncensored = requireNotNull(view.preset("general_uncensored"))
        assertEquals("General Uncensored", uncensored.title)
        assertFalse("the model ref is confirmed now", uncensored.pending)
        assertTrue(uncensored.model.startsWith("hf.co/"))
        assertNotNull("measured figures are carried now", uncensored.measured)
        assertFalse("the cost line no longer says PENDING", uncensored.cost.startsWith("PENDING:"))
        assertFalse(uncensored.heavyMode)
        // The words are still the PC's, and the row is rendered normally.
        assertNull(FocusPresets.blocker(view, uncensored, stale = false, linkUp = true))
        assertNotNull(FocusPresets.applyRoute(uncensored))
    }

    @Test
    fun `a contract that still marks a preset pending draws it as being prepared and never postable`() {
        // The old fixture's shape, kept as the generic rule: General Uncensored
        // was exactly this until its measurement landed.
        val pending = buildJsonObject {
            put("presets", kotlinx.serialization.json.buildJsonArray {
                add(buildJsonObject {
                    put("id", "being_prepared")
                    put("title", "Being Prepared")
                    put("model", "pending")
                    put("cost", "PENDING: waiting for the model ref.")
                    put("pending", true)
                    put("lane", buildJsonObject { put("card", "card") })
                    put("apply", buildJsonObject {
                        put("action", "Use this preset")
                        put("switch_route", "/api/models/switch")
                    })
                })
            })
        }
        val v = requireNotNull(FocusPresets.parse(pending))
        val p = v.presets.single()
        assertTrue(p.pending)
        assertEquals(
            FocusPresets.PENDING + ". PENDING: waiting for the model ref.",
            FocusPresets.blocker(v, p, stale = false, linkUp = true),
        )
    }

    @Test
    fun `Fast is qwen3_8b on the 2080 SUPER, and Coding is the heavy both-card preset`() {
        val fast = requireNotNull(view.preset("fast"))
        assertEquals("qwen3:8b", fast.model)
        assertEquals("coding", fast.lane.key)
        assertEquals("RTX 2080 SUPER", fast.lane.card)
        assertEquals(16384, fast.context)
        assertTrue("the fast lane starts on demand", fast.apply.laneStart)
        assertFalse(fast.heavyMode)

        val coding = requireNotNull(view.preset("coding"))
        assertEquals("qwen3-coder-30b-a3b-ud-q3-k-xl", coding.model)
        assertEquals("RTX 2060", coding.lane.card)
        assertEquals(28672, coding.context)
        assertTrue("Coding needs both cards while it runs", coding.heavyMode)
        assertNull("no second worker is planned in this contract", coding.helper)
    }

    @Test
    fun `the apply action is one asked action, never automatic`() {
        for (p in view.presets) {
            assertFalse(p.id, p.apply.auto)
            val route = FocusPresets.applyRoute(p)
            assertNotNull(p.id, route)
            assertTrue(p.id, route!!.startsWith("/api/"))
        }
        // The fixture's fallback route is the existing approval-gated switch.
        assertEquals("/api/models/switch", FocusPresets.applyRoute(view.preset("general")!!))
        assertEquals("{\"ref\":\"qwen3.5:9b\"}", FocusPresets.applyBody(view.preset("general")!!).toString())
    }

    @Test
    fun `a stale link blocks the action, and a pending preset is never offered as ready`() {
        val general = requireNotNull(view.preset("general"))
        assertEquals(
            FocusPresets.STALE,
            FocusPresets.blocker(view, general, stale = true, linkUp = true),
        )
        assertEquals(
            FocusPresets.STALE,
            FocusPresets.blocker(view, general, stale = false, linkUp = false),
        )
        assertNull(FocusPresets.blocker(view, general, stale = false, linkUp = true))
    }

    @Test
    fun `the chip reads the current preset from the contract, or says none`() {
        val chosen = FocusPresets.View(view.presets, chosen = "coding", found = null, switchPath = null)
        assertEquals("Coding", FocusPresets.chipLabel(chosen))
        assertEquals("general", FocusPresets.View(view.presets, "general", null, null).current!!.id)
        assertEquals(FocusPresets.NO_CHOICE, FocusPresets.chipLabel(null))
        assertEquals(FocusPresets.NO_CHOICE, FocusPresets.chipLabel(view.copy(chosen = null)))
    }

    @Test
    fun `a contract with a non-api apply route is not postable`() {
        val unsafe = buildJsonObject {
            put("presets", kotlinx.serialization.json.buildJsonArray {
                add(buildJsonObject {
                    put("id", "x")
                    put("title", "X")
                    put("lane", buildJsonObject { put("card", "card") })
                    put("apply", buildJsonObject {
                        put("action", "Use this preset")
                        put("route", "https://evil.example/apply")
                    })
                })
            })
        }
        val v = requireNotNull(FocusPresets.parse(unsafe))
        assertNull(FocusPresets.applyRoute(v.presets.single()))
        assertEquals(
            FocusPresets.APPLY_UNPUBLISHED,
            FocusPresets.blocker(v, v.presets.single(), stale = false, linkUp = true),
        )
    }

    @Test
    fun `a missing presets list is a refused read, not an empty menu`() {
        assertNull(FocusPresets.parse(buildJsonObject { put("found", "nothing") }))
        assertEquals(
            FocusPresets.UPDATE,
            (FocusPresets.readOf(ApiResult.Ok(buildJsonObject { })) as FocusPresets.Read.Failed).words,
        )
        assertEquals(
            FocusPresets.UPDATE,
            (FocusPresets.readOf(ApiResult.Failed(ApiError.NotFound)) as FocusPresets.Read.Failed).words,
        )
    }
}
