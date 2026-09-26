package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.ChatChunkParser
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Manner
import com.jarvis.client.net.PlainErrors
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.int
import kotlinx.serialization.json.intOrNull
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
 * Plain words when something goes wrong, and "How Jarvis talks" - checked
 * word for word against `contract/plain-error-cases.json`, which
 * tools/gen_plain_error_cases.py writes from the one list (the desktop's
 * tests/plain-errors.mjs reads the same file). Nothing here is typed to
 * suit this client.
 */
class PlainErrorsTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/plain-error-cases.json")) {
            "contract/plain-error-cases.json is missing - run tools/gen_plain_error_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    private fun JsonObject.s(key: String): String = this[key]!!.jsonPrimitive.content

    @Test
    fun `every kind's words are the contract's, word for word`() {
        val kinds = doc["kinds"]!!.jsonObject
        assertEquals(kinds.keys, PlainErrors.KINDS.keys)
        for ((kind, k) in kinds) {
            val o = k.jsonObject
            val mine = PlainErrors.KINDS.getValue(kind)
            assertEquals(kind, o.s("says"), mine.says)
            assertEquals(kind, o.s("fix"), mine.fix)
            assertEquals(kind, o.s("action"), mine.action)
            assertEquals(kind, o.s("button"), mine.button)
        }
        val buttons = doc["buttons"]!!.jsonObject
        assertEquals(buttons.mapValues { it.value.jsonPrimitive.content }, PlainErrors.BUTTONS)
        val statuses = doc["statuses"]!!.jsonObject
        assertEquals(statuses.mapValues { it.value.jsonPrimitive.content }, PlainErrors.STATUSES)
        val codes = doc["codes"]!!.jsonObject
        assertEquals(codes.mapValues { it.value.jsonPrimitive.content }, PlainErrors.CODES)
        assertEquals(doc["details_max"]!!.jsonPrimitive.int, PlainErrors.DETAILS_MAX)
    }

    @Test
    fun `each failure picks the kind the contract says (the desktop runs the same cases)`() {
        for (c in doc["classify"]!!.jsonArray) {
            val o = c.jsonObject
            val i = o["input"]!!.jsonObject
            fun str(k: String) = (i[k] as? JsonPrimitive)?.takeIf { it.isString }?.content
            fun flag(k: String) = (i[k] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull
            val input = PlainErrors.Input(
                network = str("network"),
                http = (i["http"] as? JsonPrimitive)?.intOrNull,
                said = str("said"),
                available = flag("available"),
                code = str("code"),
                stale = flag("stale") == true,
                notPaired = flag("not_paired") == true,
                malformed = flag("malformed") == true,
                notJarvis = flag("not_jarvis") == true,
                keyStore = flag("key_store") == true,
            )
            assertEquals(o.s("name"), o.s("kind"), PlainErrors.classify(input))
        }
    }

    @Test
    fun `Details - every secret gone, what a bug report needs kept`() {
        for (c in doc["scrub"]!!.jsonArray) {
            val o = c.jsonObject
            val out = PlainErrors.scrubDetails(o.s("input"))
            for (g in o["gone"]!!.jsonArray) {
                assertFalse("${g.jsonPrimitive.content} survived: $out", out.contains(g.jsonPrimitive.content))
            }
            for (k in o["kept"]!!.jsonArray) {
                assertTrue("${k.jsonPrimitive.content} was lost: $out", out.contains(k.jsonPrimitive.content))
            }
        }
        val t = doc["scrub_known_token"]!!.jsonObject
        val out = PlainErrors.scrubDetails(t.s("input"), t.s("token"))
        for (g in t["gone"]!!.jsonArray) assertFalse(out, out.contains(g.jsonPrimitive.content))
        for (k in t["kept"]!!.jsonArray) assertTrue(out, out.contains(k.jsonPrimitive.content))
        assertTrue(PlainErrors.scrubDetails("x".repeat(5000)).length <= PlainErrors.DETAILS_MAX)
    }

    @Test
    fun `the phone tells a sleeping PC from a stopped Jarvis from a wrong name`() {
        val cases = mapOf(
            ("ConnectException" to "failed to connect to /100.64.1.2 (port 8765) from /100.64.1.9 " +
                "(port 40000) after 10000ms: isConnected failed: ECONNREFUSED (Connection refused)") to "refused",
            ("SocketTimeoutException" to "failed to connect to /100.64.1.2 (port 8765) after 10000ms") to
                "connect_timeout",
            ("SocketTimeoutException" to "timeout") to "read_timeout",
            ("UnknownHostException" to "Unable to resolve host \"desktop\": No address associated with hostname")
                to "unknown_host",
            ("ConnectException" to "failed to connect ... ENETUNREACH (Network is unreachable)") to "no_network",
            ("NoRouteToHostException" to "No route to host") to "no_route",
            ("SSLHandshakeException" to "Connection closed by peer") to "dropped",
            ("IOException" to "unexpected end of stream") to "dropped",
        )
        for ((given, want) in cases) {
            assertEquals(given.toString(), want, PlainErrors.networkKind(given.first, given.second))
        }
        assertEquals("jarvis_not_running", PlainErrors.classify(PlainErrors.Input(network = "refused")))
        assertEquals("pc_unreachable", PlainErrors.classify(PlainErrors.Input(network = "connect_timeout")))
        assertEquals("name_not_found", PlainErrors.classify(PlainErrors.Input(network = "unknown_host")))
    }

    @Test
    fun `a request's failure never shows the raw error or a status number`() {
        val raw = "failed to connect to /100.64.1.2 (port 8765) after 10000ms"
        val down = PlainErrors.forApiError(ApiError.Unreachable(raw, "connect_timeout"))
        assertEquals(PlainErrors.KINDS.getValue("pc_unreachable").says, down.says)
        assertFalse(down.text.contains("10000ms"))
        assertTrue("the raw error is kept behind Details", down.details.contains("10000ms"))
        val server = PlainErrors.forApiError(ApiError.Server(503, "{\"error\": \"the model is still loading\"}"))
        assertEquals("The model is still loading.", server.text)
        assertFalse(server.text.contains("503"))
        assertTrue(server.details.contains("HTTP 503"))
        val older = PlainErrors.forApiError(ApiError.Server(503, "{\"available\": false}"))
        assertEquals("backend_too_old", older.kind)
        assertEquals("token_wrong", PlainErrors.forApiError(ApiError.BadToken).kind)
        assertEquals("not_jarvis", PlainErrors.forApiError(ApiError.NotFound, handshake = true).kind)
        assertEquals("backend_too_old", PlainErrors.forApiError(ApiError.NotFound).kind)
        assertEquals("not_paired",
            PlainErrors.forApiError(ApiError.Unreachable("No desktop address set", PlainErrors.NOT_PAIRED)).kind)
        // This app's own sentence (a blocker) is shown as it is.
        val own = PlainErrors.forApiError(ApiError.Unreachable("That request is no longer pending."))
        assertEquals("That request is no longer pending.", own.text)
        val stale = PlainErrors.shown("link_stale")
        assertEquals("Reconnect", stale.button)
    }

    @Test
    fun `the stream's code reaches the plain words - from the PC's real failures`() {
        val stream = run {
            val text = requireNotNull(javaClass.classLoader?.getResource("chat-stream-cases.json")).readText()
            JarvisJson.parseToJsonElement(text) as JsonObject
        }
        var seen = 0
        for (c in stream["cases"]!!.jsonArray) {
            val o = c.jsonObject
            val body = o.s("body")
            val code = Regex("\"code\":\"([a-z_]+)\"").find(body)?.groupValues?.get(1) ?: continue
            val line = body.lines().first { it.startsWith("data:") }
            val r = ChatChunkParser.consume(line)
            assertTrue(r is ChatChunkParser.Result.Failed)
            r as ChatChunkParser.Result.Failed
            assertEquals(code, r.code)
            val shown = PlainErrors.forInput(PlainErrors.Input(code = r.code, said = r.message), r.message)
            val kind = doc["codes"]!!.jsonObject.s(code)
            assertEquals(PlainErrors.KINDS.getValue(kind).says, shown.says)
            assertTrue("the PC's sentence behind Details", shown.details.contains(r.message.take(30)))
            seen++
        }
        assertTrue("the fixture has the PC's coded failures", seen >= 2)
    }

    @Test
    fun `How Jarvis talks - the PC's words, word for word`() {
        val m = doc["manner"]!!.jsonObject
        assertEquals(m.s("title"), Manner.TITLE)
        assertEquals(m.s("detail"), Manner.DETAIL)
        assertEquals(m.s("spoken"), Manner.SPOKEN)
        assertEquals(m.s("default"), Manner.DEFAULT)
        val choices = m["choices"]!!.jsonArray.map { it.jsonObject }
        assertEquals(choices.map { it.s("id") }, Manner.MANNERS)
        for (c in choices) {
            assertEquals(c.s("label"), Manner.LABEL[c.s("id")])
            assertEquals(c.s("why"), Manner.WHY[c.s("id")])
        }
        val said = m["said"]!!.jsonObject
        assertEquals(said.mapValues { it.value.jsonPrimitive.content }, Manner.SAID)
        // The contract's words ARE a GET /api/manner answer (with the setting added).
        val view = Manner.parse(JarvisJson.parseToJsonElement(
            m.toString().dropLast(1) + ",\"manner\":\"plain\",\"available\":true}") as JsonObject)
        assertNotNull(view)
        assertEquals("plain", view!!.manner)
        assertNull(Manner.parse(JarvisJson.parseToJsonElement("{\"available\":false}") as JsonObject))
        assertEquals("{\"manner\":\"warm\"}", Manner.body("warm"))
        assertNull(Manner.body("rude"))
        assertTrue(Manner.missing(ApiError.NotFound))
        assertEquals(Manner.MISSING, Manner.replyLine(ApiResult.Failed(ApiError.NotFound), "plain"))
        val ok = JarvisJson.parseToJsonElement("{\"ok\":true,\"said\":\"PC said it.\"}") as JsonObject
        assertEquals("PC said it.", Manner.replyLine(ApiResult.Ok(ok), "plain"))
    }
}
