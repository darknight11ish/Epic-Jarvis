package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PlainErrors
import com.jarvis.client.net.SecondCard
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The Mind screen's "Second graphics card" plate, read from what the PC
 * REALLY answers.
 *
 * `contract/second-card-cases.json` is the real `status()` output
 * (`GET /api/second-card`) for six situations, written by
 * tools/gen_second_card_cases.py - the same file the desktop builds against,
 * checked byte for byte by backend/test_second_card.py.
 * `contract/phone-second-card-cases.json` carries the real POST answers
 * (`post_replies`), written by backend/test_phone_second_card_contract.py.
 * Nothing here is a shape typed to suit this client.
 */
class SecondCardContractTest {

    private fun load(name: String): JsonObject {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/$name")) {
            "contract/$name is missing - run tools/gen_second_card_cases.py and " +
                "backend/test_phone_second_card_contract.py --write"
        }.readText()
        return JarvisJson.parseToJsonElement(text) as JsonObject
    }

    private val cases = load("second-card-cases.json")["cases"]!!.jsonObject
    private val phone = load("phone-second-card-cases.json")

    private fun status(case: String): SecondCard.Status =
        requireNotNull(SecondCard.parse(cases[case]!!.jsonObject)) { "$case did not parse" }

    private fun switch(s: SecondCard.Status, id: String): SecondCard.SwitchView =
        SecondCard.switches(s).first { it.id == id }

    @Test
    fun `all seven cases are read, with the five features in the PC's order`() {
        // Seven since 2026-09-26: one_card_reads_words (the PC reads the
        // words in a picture).
        assertEquals(7, cases.size)
        for (name in cases.keys) {
            val s = status(name)
            assertEquals(name, listOf("long_context", "vision", "learning", "browser_control", "wiki"),
                s.features.map { it.id })
            s.features.forEach { assertTrue("$name ${it.id}: a line under it", it.why.isNotBlank()) }
        }
    }

    @Test
    fun `one card - every switch shown, none can be turned on, and it says why`() {
        val s = status("one_card")
        assertFalse(s.capable)
        assertTrue(s.detectedWhy.contains("only one graphics card"))
        val master = SecondCard.master(s)
        assertFalse(master.canTurnOn)
        assertTrue(master.blocked!!.contains(s.detectedWhy))
        SecondCard.switches(s).forEach {
            assertFalse(it.id, it.canTurnOn)
            assertTrue(it.id, it.line.contains("Needs a capable second graphics card"))
            // No card to size a model for: no model line, no install hint.
            assertNull(it.modelLine)
        }
        assertFalse(SecondCard.visionAvailable(SecondCard.Read.Loaded(s)))
        // Nothing to pin with one card, so no "run it on your PC".
        assertFalse(SecondCard.pinNeedsPc(s))
        assertNotNull(s.pinNote)
    }

    @Test
    fun `capable and off - the main switch can be asked for, the features wait for it`() {
        val s = status("capable_off")
        assertTrue(s.capable)
        assertTrue(SecondCard.master(s).canTurnOn)
        SecondCard.switches(s).forEach {
            assertFalse(it.id, it.canTurnOn)
            assertTrue(it.id, it.blocked!!.contains(SecondCard.MASTER_NAME))
        }
        // Two cards found, each said in words with its role.
        val lines = SecondCard.cardLines(s)
        assertEquals(2, lines.size)
        assertTrue(lines[0], lines[0].contains("RTX 2080 SUPER (8 GB) - main card"))
        assertTrue(lines[1], lines[1].contains("RTX 2060 (12 GB) - second card"))
    }

    @Test
    fun `a model that is not installed says the exact name to type, and nothing else`() {
        val s = status("capable_off")
        val vision = switch(s, "vision")
        val line = vision.modelLine!!
        assertTrue(line, line.contains("qwen2.5vl:7b - not installed"))
        assertTrue(line, line.contains("type qwen2.5vl:7b into the Install box"))
        assertTrue(switch(s, "long_context").modelLine!!.startsWith("Model: qwen3:8b (installed)."))
    }

    @Test
    fun `browser control shows what it needs`() {
        val s = status("capable_pending")
        val browser = switch(s, "browser_control")
        assertEquals("Needs: \"Longer conversations\".", browser.needsLine)
        // Main switch on, Longer conversations not on yet: blocked by that.
        assertTrue(browser.blocked!!.contains("Longer conversations"))
        assertNull(switch(s, "vision").needsLine)
    }

    /**
     * AP-6: `last`, as backend/jarvis_second_card.py's status() sends it
     * (fix-b2): {feature, outcome, why, at}, or null. Added to a real case
     * here, because the fixture this branch carries predates it.
     */
    private fun withLast(case: String, last: String): SecondCard.Status {
        val obj = cases[case]!!.jsonObject.toMutableMap()
        obj["last"] = JarvisJson.parseToJsonElement(last)
        return requireNotNull(SecondCard.parse(JsonObject(obj)))
    }

    @Test
    fun `how the last card ended is said under that switch, and only there`() {
        val denied = withLast(
            "capable_off",
            """{"feature": "vision", "outcome": "denied",
                "why": "You said no, so \"Pictures\" stays off.", "at": 1800000000}""",
        )
        assertEquals(SecondCard.LastCard("vision", "denied", "You said no, so \"Pictures\" stays off."), denied.last)
        assertEquals("You said no, so \"Pictures\" stays off.", switch(denied, "vision").lastLine)
        assertNull("another switch's card is not this one's news", switch(denied, "long_context").lastLine)
        assertNull(SecondCard.master(denied).lastLine)

        // The PC's own sentence is used; without one, a plain fallback per outcome.
        val timedOut = withLast("capable_off", """{"feature": "master", "outcome": "timed_out", "at": 1}""")
        assertEquals(
            "Nobody answered the card in time, so \"Use the second graphics card\" stays off.",
            SecondCard.master(timedOut).lastLine,
        )
        val failed = withLast("capable_off", """{"feature": "vision", "outcome": "failed", "why": ""}""")
        assertTrue(switch(failed, "vision").lastLine!!.contains("could not be turned on"))
        val withdrawn = withLast("capable_off", """{"feature": "vision", "outcome": "withdrawn"}""")
        assertTrue(switch(withdrawn, "vision").lastLine!!.contains("changed nothing"))
        val odd = withLast("capable_off", """{"feature": "vision", "outcome": "rolled_back"}""")
        assertTrue("a new word is shown, not dropped", switch(odd, "vision").lastLine!!.contains("rolled back"))

        // "Turned on" is not news: the switch says "On." itself.
        val on = withLast("running_long_context", """{"feature": "long_context", "outcome": "enabled", "why": "On."}""")
        assertNull(switch(on, "long_context").lastLine)
        // A newer card waiting for that switch: its "Waiting" line, not the old outcome.
        val waiting = withLast("capable_pending", """{"feature": "long_context", "outcome": "denied", "why": "No."}""")
        assertNull(switch(waiting, "long_context").lastLine)
    }

    @Test
    fun `no last - null, absent or junk - reads exactly as before`() {
        for (name in cases.keys) {
            val s = status(name)
            assertNull(name, s.last)
            assertNull(name, SecondCard.master(s).lastLine)
            SecondCard.switches(s).forEach { assertNull("$name ${it.id}", it.lastLine) }
        }
        assertNull(withLast("capable_off", "null").last)
        assertNull(withLast("capable_off", "\"denied\"").last)
        assertNull(withLast("capable_off", """{"outcome": "denied"}""").last)
    }

    @Test
    fun `a card waiting - the wake-word wording, and no second ask`() {
        val s = status("capable_pending")
        assertEquals(listOf("long_context"), s.pending)
        val long = switch(s, "long_context")
        assertTrue(long.waiting)
        assertFalse(long.on)
        assertEquals("Waiting for your approval. Approve it on your PC or on this phone's Home screen.", long.line)
        assertFalse(long.canTurnOn)
        // The main switch is on, and the everyday Ollama is already pinned.
        assertTrue(SecondCard.master(s).on)
        assertFalse(SecondCard.pinNeedsPc(s))
    }

    @Test
    fun `running - the switch is on, working, and the lane says so`() {
        val s = status("running_long_context")
        val long = switch(s, "long_context")
        assertTrue(long.on)
        assertTrue(long.line, long.line.startsWith("Working: qwen3:8b"))
        assertTrue(SecondCard.laneLine(s).startsWith("Running: running on 127.0.0.1:11435"))
        // Pictures is off, so chat offers no photo.
        assertFalse(SecondCard.visionAvailable(SecondCard.Read.Loaded(s)))
    }

    @Test
    fun `the card has gone - switches stay on, waiting, and can still be turned off`() {
        val s = status("card_missing_but_enabled")
        val long = switch(s, "long_context")
        assertTrue("never flipped off by the phone", long.on)
        assertTrue(long.line, long.line.startsWith("On, but it cannot run"))
        assertNotNull(long.blocked)
        assertTrue(SecondCard.master(s).line.startsWith("On, but it cannot run"))
        // Not on: learning cannot be asked for.
        assertFalse(switch(s, "learning").canTurnOn)
    }

    @Test
    fun `an old card is named as not used, with the reason`() {
        val s = status("not_capable_old_card")
        val lines = SecondCard.cardLines(s)
        assertTrue(lines[1], lines[1].contains("GTX 1080 (8 GB) - not used: "))
        assertTrue(lines[1], lines[1].contains("older than Turing"))
        // A command exists and the everyday Ollama is not pinned: say where to run it.
        assertTrue(SecondCard.pinNeedsPc(s))
    }

    @Test
    fun `the pin command is never part of what the phone shows`() {
        for (name in cases.keys) {
            val raw = cases[name]!!.jsonObject
            val s = status(name)
            val cmd = raw["pin_command"]?.let { if (it is kotlinx.serialization.json.JsonNull) null else it.jsonPrimitive.content }
            if (cmd == null) continue
            val shown = listOfNotNull(s.pinNote, SecondCard.PIN_ON_PC, SecondCard.laneLine(s)) +
                SecondCard.switches(s).flatMap { listOfNotNull(it.line, it.modelLine, it.blocked) }
            shown.forEach { assertFalse("$name shows the command", it.contains("SetEnvironmentVariable")) }
        }
    }

    // ------------------------------------------------------------- reads --

    @Test
    fun `an older backend, a missing module and no network are each said plainly`() {
        val older = SecondCard.readOf(ApiResult.Failed(ApiError.NotFound))
        assertEquals(SecondCard.Read.OlderBackend, older)
        assertTrue(SecondCard.readLine(older)!!.contains("apply-patches.ps1"))
        val missing = SecondCard.readOf(ApiResult.Failed(ApiError.NotAvailable))
        assertEquals(SecondCard.Read.NotInstalled, missing)
        assertTrue(SecondCard.readLine(missing)!!.contains("jarvis_second_card.py"))
        val net = SecondCard.readOf(ApiResult.Failed(ApiError.Unreachable("timeout", "read_timeout")))
        // The plain words both apps use (PlainErrors), never the raw "timeout".
        assertEquals(PlainErrors.shown("timeout").text, SecondCard.readLine(net))
        // A 200 that is not status() is a failed read, never "no second card".
        val odd = SecondCard.readOf(ApiResult.Ok(JarvisJson.parseToJsonElement("{\"ok\":true}") as JsonObject))
        assertTrue(odd is SecondCard.Read.Failed)
        assertFalse(SecondCard.visionAvailable(odd))
    }

    // ------------------------------------------------------------ writes --

    @Test
    fun `the POST body is exactly feature and enabled`() {
        val body = JarvisJson.parseToJsonElement(SecondCard.postBody("vision", true)).jsonObject
        assertEquals(setOf("feature", "enabled"), body.keys)
        assertEquals("vision", body["feature"]!!.jsonPrimitive.content)
        assertTrue(body["enabled"]!!.jsonPrimitive.boolean)
    }

    @Test
    fun `every real POST answer is read the way the plate needs`() {
        val replies = phone["post_replies"]!!.jsonArray.map { it.jsonObject }
        assertTrue(replies.size >= 6)
        for (r in replies) {
            val name = r["name"]!!.jsonPrimitive.content
            val code = r["status"]!!.jsonPrimitive.int
            val body = r["body"]!!.jsonObject
            val result = SecondCard.classifyPost(code, body)
            assertTrue("$name: an answer, not a transport failure", result is ApiResult.Ok)
            val line = SecondCard.replyLine(result)
            val error = body["error"]?.jsonPrimitive?.content
            if (error != null) {
                // Shown word for word (docs/JARVIS-API.md section 12).
                assertEquals(name, error, line)
            } else {
                // A card is up, it is off, or it was already on: the plate,
                // re-read from the PC, says which - never this reply.
                assertNull(name, line)
            }
        }
    }

    @Test
    fun `an older backend, a missing module and a bad token on POST`() {
        val older = SecondCard.classifyPost(404, null)
        assertEquals(ApiResult.Failed(ApiError.NotFound), older)
        assertTrue(SecondCard.replyLine(older)!!.contains("apply-patches.ps1"))
        val missing = SecondCard.classifyPost(
            503,
            JarvisJson.parseToJsonElement("{\"available\":false,\"error\":\"ImportError: x\"}").jsonObject,
        )
        assertEquals(ApiResult.Failed(ApiError.NotAvailable), missing)
        assertEquals(ApiResult.Failed(ApiError.BadToken), SecondCard.classifyPost(401, null))
        val down = SecondCard.replyLine(ApiResult.Failed(ApiError.Unreachable("no route")))!!
        assertTrue(down, down.startsWith("Nothing changed. "))
    }
}
