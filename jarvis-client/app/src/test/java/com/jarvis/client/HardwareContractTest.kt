package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Hardware
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The Mind screen's "Hardware" plate, read from what the PC REALLY answers.
 *
 * `contract/hardware-cases.json` is the real `GET /api/hardware` answer
 * (jarvis_hardware.status()) and the POST answers, written by
 * tools/gen_hardware_cases.py - byte for byte the file the desktop builds
 * against (backend/test_hardware.py checks). Nothing here is a shape typed
 * to suit this client.
 */
class HardwareContractTest {

    private val cases: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/hardware-cases.json")) {
            "contract/hardware-cases.json is missing - run tools/gen_hardware_cases.py"
        }.readText()
        (JarvisJson.parseToJsonElement(text) as JsonObject)["cases"]!!.jsonObject
    }

    private fun status(case: String): Hardware.Status =
        requireNotNull(Hardware.parse(cases[case]!!.jsonObject)) { "$case did not parse" }

    private fun post(case: String): ApiResult<JsonObject> {
        val c = cases[case]!!.jsonObject
        return Hardware.classifyPost(c["status"]!!.jsonPrimitive.int, c["body"]!!.jsonObject)
    }

    @Test
    fun `every GET case is read, with the three setups in the PC's order`() {
        val gets = cases.keys.filter { !it.startsWith("post_") }
        assertTrue(gets.size >= 6)
        for (name in gets) {
            val s = status(name)
            assertEquals(name, listOf("fast", "smart", "features"), s.presets.map { it.id })
            assertEquals(name, 1, s.presets.count { it.recommended }.coerceAtMost(1))
            assertTrue(name, s.found.isNotBlank())
        }
    }

    @Test
    fun `every card's health is its own line, in the PC's words - the second card too`() {
        val pair = status("planned_pair")
        assertEquals(
            "Now: 84 °C, using 247 of 250 watts, fan at 78%, 99% busy. " +
                "It is slowing itself down because it is hot.",
            Hardware.healthLine(pair.cards[0]),
        )
        assertEquals("Now: 38 °C, using 10 of 184 watts, 0% busy.", Hardware.healthLine(pair.cards[1]))
        // Built-in graphics nvidia-smi does not see: nothing is said.
        assertNull(Hardware.healthLine(status("today_one_card").cards[1]))
    }

    @Test
    fun `today's PC - names and memory, Custom, and the recommended setup with its reason`() {
        val s = status("today_one_card")
        assertEquals("NVIDIA GeForce RTX 2080 SUPER, 8 GB", Hardware.cardLine(s.cards[0]))
        assertTrue(Hardware.cardLine(s.cards[1]).endsWith(" - not used by Ollama"))
        assertEquals("Custom (your own setup)", s.nowLabel)
        assertTrue(s.nowWords, s.nowWords.contains("calculated about 0.60 GB over the card"))
        assertEquals(91, s.nowOnCardPercent)
        val smart = s.preset("smart")!!
        assertTrue(smart.recommended)
        assertEquals("smart", s.recommended)
        assertTrue(smart.recommendedWhy!!.startsWith("It keeps the 8B everyday model"))
        assertEquals("Calculated, not measured.", Hardware.measuredLine(smart))
        assertNull("nothing is chosen, so there are no steps", s.applying)
    }

    @Test
    fun `the words for a setup are the desktop's`() {
        val fast = status("today_one_card").preset("fast")!!
        val lines = Hardware.presetLines(fast)
        assertEquals(
            "Chat: qwen3:4b, 32K, compact format, on the NVIDIA GeForce RTX 2080 SUPER. " +
                "It remembers about 24 pages of conversation (an estimate).",
            lines[0],
        )
        assertEquals("Long conversations: chat itself (32K).", lines[1])
        assertEquals(Hardware.NO_PICTURES, lines[2])
        assertTrue(fast.off.isNotEmpty())
        val features = status("today_one_card").preset("features")!!
        assertTrue(Hardware.presetLines(features)[2].endsWith("It takes turns with chat: a picture unloads chat for a moment."))
    }

    @Test
    fun `the steps - in order, only the next can be asked for, and only by the PC's own route`() {
        val s = status("chosen_first_step")
        val steps = s.applying!!.steps
        assertEquals(listOf("install", "create", "switch", "command"), steps.map { it.kind })
        assertEquals(listOf("next", "later", "later", "later"), steps.map { it.state })
        assertEquals(Hardware.STEP_NEXT, Hardware.stepWords(steps[0]))
        assertEquals(Hardware.STEP_LATER, Hardware.stepWords(steps[1]))
        assertEquals(Hardware.STEP_COMMAND, Hardware.stepWords(steps[3]))
        val ask = Hardware.stepRequest(s, "install:qwen3:4b")
        assertTrue(ask is Hardware.StepAsk.Post)
        ask as Hardware.StepAsk.Post
        assertEquals("/api/models/install", ask.route)
        assertEquals("""{"ref":"qwen3:4b"}""", ask.body)
        assertTrue(Hardware.stepRequest(s, "create:jarvis-chat") is Hardware.StepAsk.No)
        assertTrue(Hardware.stepRequest(s, "nope") is Hardware.StepAsk.No)
        assertFalse("the chosen setup cannot be chosen again", Hardware.canChoose(s, s.preset("fast")!!))
    }

    @Test
    fun `a waiting step says so and cannot be asked for twice`() {
        val s = status("create_waiting")
        val make = s.applying!!.steps.first { it.kind == "create" }
        assertEquals("waiting", make.state)
        assertEquals(Hardware.WAITING, Hardware.stepWords(make))
        val no = Hardware.stepRequest(s, make.id)
        assertTrue(no is Hardware.StepAsk.No && no.reason.contains("already waiting"))
        assertTrue(s.waiting)
    }

    @Test
    fun `a forged step naming any other route is never posted`() {
        val s = status("chosen_first_step")
        val forged = s.copy(applying = s.applying!!.copy(steps = listOf(
            Hardware.Step("x", "install", "x", null, "next", "/api/shutdown", JsonObject(emptyMap())),
        )))
        assertTrue(Hardware.stepRequest(forged, "x") is Hardware.StepAsk.No)
        assertEquals(4, Hardware.STEP_ROUTES.size)
    }

    @Test
    fun `the one line is there to read, with its undo and the check line`() {
        val s = status("planned_pair")
        assertTrue(s.commandLine!!.startsWith("[Environment]::SetEnvironmentVariable('OLLAMA_KV_CACHE_TYPE', 'q8_0', 'User'); "))
        assertFalse(s.commandLine.contains("\n"))
        assertNotNull(s.undoLine)
        assertTrue(s.checkLine!!.startsWith("foreach (\$n in "))
        assertEquals("features", s.recommended)
    }

    @Test
    fun `best effort on an AMD card is said on every setup`() {
        val s = status("amd_vulkan")
        for (p in s.presets) assertTrue(p.id, p.bestEffortWhy.any { it.contains("AMD card") })
    }

    @Test
    fun `the PC's POST answers - pending is waiting, a refusal is its own sentence`() {
        assertEquals(Hardware.WAITING, Hardware.replyLine(post("post_create_pending")))
        assertEquals(
            "Download qwen3:4b first (the step before this one); making jarvis-chat never downloads anything.",
            Hardware.replyLine(post("post_create_not_downloaded")),
        )
        assertTrue(Hardware.replyLine(post("post_apply_ok")).contains("Nothing has changed yet"))
        assertTrue(Hardware.replyLine(post("post_apply_unknown")).startsWith("There is no preset called"))
        assertTrue(Hardware.replyLine(post("post_measure_started")).startsWith("Measuring."))
        assertEquals("""{"preset":"smart"}""", Hardware.applyBody("smart"))
        assertEquals("""{"preset":null}""", Hardware.applyBody(null))
    }

    @Test
    fun `an older PC, or a module that did not load, says to update`() {
        assertEquals(Hardware.Read.OlderBackend, Hardware.readOf(ApiResult.Failed(ApiError.NotFound)))
        assertEquals(Hardware.Read.NotInstalled, Hardware.readOf(ApiResult.Failed(ApiError.NotAvailable)))
        assertEquals(Hardware.UPDATE, Hardware.readLine(Hardware.Read.OlderBackend))
        val odd = Hardware.readOf(ApiResult.Ok(JsonObject(emptyMap())))
        assertTrue(odd is Hardware.Read.Failed)
    }
}
