package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.FocusPresets
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
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
 * fixture `backend/fixtures/work_presets.json` (tools/gen_work_presets.py from
 * backend/jarvis_presets.py - never hand-edited). The merged answer carries the
 * five rows plus `hardware`/`questionnaire`/`recommendations`, and the saved
 * `chosen` id when the PC has one; this test reads that whole shape.
 *
 * The list is deliberately generic: the owner added a fifth preset
 * (general_uncensored), and Agentic+Vision's model may change after a
 * measurement, so the parser must not hardcode a count or a model; the fixture
 * test still pins the five rows the screens actually draw.
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

    /**
     * The documented live GET answer (jarvis_presets.live_status): the same
     * canonical rows plus `apply_route` on each apply action, `hardware` as the
     * detected block, top-level `questionnaire`, and chosen/active_lane/paths.
     * The fixture stays canonical; this is what the PC answers until its
     * follow-up regenerates the fixture.
     */
    private val live: FocusPresets.View by lazy {
        val hardware = fixture["hardware"] as JsonObject
        val rows = (fixture["presets"] as JsonArray).map { row ->
            val p = row as JsonObject
            val apply = p["apply"] as JsonObject
            JsonObject(
                p + ("apply" to JsonObject(apply + ("apply_route" to JsonPrimitive("/api/work/apply")))),
            )
        }
        requireNotNull(
            FocusPresets.parse(
                buildJsonObject {
                    put("found", "5 focus presets")
                    put("presets", JsonArray(rows))
                    put("hardware", hardware["detected"]!!)
                    put("questionnaire", hardware["questionnaire"]!!)
                    put("recommendations", fixture["recommendations"]!!)
                    put("chosen", "coding")
                    put("chosen_preset", "coding")
                    put("chosen_model", "qwen3-coder-30b-a3b-ud-q3-k-xl")
                    put("active_lane", buildJsonObject {
                        put("key", "main")
                        put("base_url", "http://127.0.0.1:11436")
                    })
                    put("apply_path", "/api/work/apply")
                    put("switch_path", "/api/models/switch")
                    put("auto", false)
                },
            ),
        ) { "the documented live shape did not parse" }
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
    fun `the merged answer carries five rows and the hardware, questionnaire and recommendations blocks`() {
        // The chip and the plate render one row per preset; the merged contract
        // has exactly the owner's five today.
        assertEquals(5, view.presets.size)

        val hardware = requireNotNull(view.hardware) { "hardware block missing" }
        assertTrue("detected" in hardware)
        assertTrue("questionnaire" in hardware)
        val q = requireNotNull(view.questionnaire) { "questionnaire missing" }
        assertEquals(
            listOf("general", "general_uncensored", "coding", "agentic_vision", "fast"),
            (q["focus_choices"] as JsonArray).map { (it as JsonPrimitive).content },
        )
        assertEquals(
            listOf("speed", "quality", "long_context", "vision"),
            (q["priority_choices"] as JsonArray).map { (it as JsonPrimitive).content },
        )

        val rec = requireNotNull(view.recommendations) { "recommendations missing" }
        assertTrue((rec["basis"] as? JsonPrimitive)?.content?.isNotBlank() == true)
        val by = requireNotNull(rec["by_gpu_count"] as? JsonObject)
        assertEquals(setOf("1", "2", "3"), by.keys)
        for ((_, rows) in by) {
            val row = rows as JsonObject
            assertEquals(
                "each GPU count has one row per preset",
                view.presets.map { it.id }.toSet(),
                row.keys,
            )
        }

        // The GET answer adds the saved id; a contract without one still parses,
        // and the chip then honestly says no preset is chosen.
        val chosen = requireNotNull(
            FocusPresets.parse(
                buildJsonObject {
                    put("presets", fixture["presets"]!!)
                    put("chosen", "coding")
                },
            ),
        )
        assertEquals("coding", chosen.chosen)
        assertEquals("Coding", FocusPresets.chipLabel(chosen))
    }

    @Test
    fun `the live GET answer - hardware, questionnaire, chosen, active lane and paths - parses`() {
        assertEquals(5, live.presets.size)
        assertEquals("coding", live.chosen)
        assertEquals("Coding", FocusPresets.chipLabel(live))
        assertEquals("main", (live.activeLane!!["key"] as JsonPrimitive).content)
        assertEquals("/api/work/apply", live.applyPath)
        assertEquals("/api/models/switch", live.switchPath)
        assertNotNull(live.detected)
        assertNotNull(live.questionnaire)
        assertNotNull(live.recommendations)
        for (p in live.presets) {
            assertEquals(p.id, FocusPresets.APPLY_PATH, FocusPresets.applyRoute(p))
            assertEquals(p.id, "{\"preset\":\"${p.id}\"}", FocusPresets.applyBody(p).toString())
        }
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
        // Heavy mode cannot be used until the PC's pooled lane support lands:
        // the plate must show the refusal, not an enabled Use button.
        assertEquals(
            FocusPresets.HEAVY,
            FocusPresets.blocker(view, coding, stale = false, linkUp = true),
        )
        assertNull(FocusPresets.blocker(view, fast, stale = false, linkUp = true))
    }

    @Test
    fun `the merged apply action is the apply route and its preset body`() {
        for (p in live.presets) {
            assertFalse(p.id, p.apply.auto)
            assertEquals(p.id, FocusPresets.APPLY_PATH, FocusPresets.applyRoute(p))
            assertEquals(
                p.id,
                "{\"preset\":\"${p.id}\"}",
                FocusPresets.applyBody(p).toString(),
            )
        }
    }

    @Test
    fun `an older contract without apply_route keeps the switch fallback`() {
        // Deliberately strip apply_route, so the fallback is tested on its own
        // and cannot pass just because the installed contract is the old one.
        val oldRows = (fixture["presets"] as JsonArray).map { row ->
            val p = row as JsonObject
            val apply = p["apply"] as JsonObject
            JsonObject(p + ("apply" to JsonObject(apply - "apply_route")))
        }
        val old = requireNotNull(
            FocusPresets.parse(buildJsonObject { put("presets", JsonArray(oldRows)) }),
        )
        val general = requireNotNull(old.preset("general"))
        assertEquals("/api/models/switch", FocusPresets.applyRoute(general))
        assertEquals("{\"ref\":\"qwen3.5:9b\"}", FocusPresets.applyBody(general).toString())
        assertNull(FocusPresets.blocker(old, general, stale = false, linkUp = true))
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
    fun `the apply answer is said honestly - asked, changed, or refused`() {
        assertEquals(
            FocusPresets.WAITING,
            FocusPresets.replyLine(202, buildJsonObject { }),
        )
        assertEquals(
            "Preset applied. Your PC switched its chat lane; nothing else changed.",
            FocusPresets.replyLine(
                200,
                buildJsonObject {
                    put("ok", true)
                    put("changed", true)
                },
            ),
        )
        assertEquals(
            "Not changed. the model switch did not happen",
            FocusPresets.replyLine(
                409,
                buildJsonObject { put("error", "the model switch did not happen") },
            ),
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
