package com.jarvis.client

import com.jarvis.client.net.ActivityEvent
import com.jarvis.client.net.ChatChunkParser
import com.jarvis.client.net.Feedback
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The phone's chat reader against what the desktop REALLY sends.
 *
 * `chat-stream-cases.json` is written by running the backend's producer
 * (`backend/test_chat_stream_contract.py --write`): Ollama's real
 * `/v1/chat/completions` stream, relayed by both branches of `/api/chat`, with
 * the keepalive and `: jarvis-status approval` lines, an answer cut short at
 * the length limit, and the desktop's own error sentences. That script fails
 * if this copy is stale, so these cases are what the server sends today.
 *
 * Before this, ApiContractTest checked the reader against "Hello there." as
 * text/plain - a body no server of this project has ever sent.
 *
 * Each case's lines go through [ChatChunkParser.consume] and are folded the
 * way [com.jarvis.client.net.ChatSession.send]'s `handle` folds them: text
 * appended, stop at the end marker, a failure is the error shown.
 */
class ChatStreamContractTest {

    private val fixture: JsonObject =
        Json.parseToJsonElement(
            requireNotNull(javaClass.classLoader?.getResourceAsStream("chat-stream-cases.json")) {
                "chat-stream-cases.json is missing from test resources"
            }.bufferedReader().readText(),
        ).jsonObject

    private data class Read(
        val text: String,
        val ended: Boolean,
        val cutShort: Boolean,
        val error: String?,
        val statuses: List<String>,
    )

    private fun read(body: String): Read {
        val text = StringBuilder()
        var ended = false
        var cutShort = false
        var error: String? = null
        val statuses = mutableListOf<String>()
        for (line in body.split('\n')) {
            val stop = when (val r = ChatChunkParser.consume(line)) {
                is ChatChunkParser.Result.Text -> {
                    text.append(r.delta)
                    if (r.cutShort) cutShort = true
                    if (r.terminal) ended = true
                    r.terminal
                }
                ChatChunkParser.Result.Terminal -> {
                    ended = true
                    true
                }
                ChatChunkParser.Result.CutShort -> {
                    ended = true
                    cutShort = true
                    true
                }
                is ChatChunkParser.Result.Status -> {
                    statuses += r.word
                    false
                }
                is ChatChunkParser.Result.Failed -> {
                    error = r.message
                    true
                }
                ChatChunkParser.Result.Ignored -> false
            }
            if (stop) break
        }
        return Read(text.toString(), ended, cutShort, error, statuses)
    }

    private fun JsonObject.str(key: String): String? = (this[key] as? JsonPrimitive)?.contentOrNull

    @Test
    fun `every real reply reads as what the model said`() {
        val cases = fixture["cases"]!!.jsonArray.map { it.jsonObject }
        assertTrue("no cases in the fixture", cases.size >= 10)
        for (c in cases) {
            val name = c.str("name")
            val exp = c["expect"]!!.jsonObject
            val got = read(c.str("body")!!)
            val wantError = exp.str("error")
            if (wantError != null) {
                assertEquals("$name: the desktop's sentence is the error shown", wantError, got.error)
                continue
            }
            assertEquals("$name: no error", null, got.error)
            assertEquals("$name: the words", exp.str("text"), got.text)
            assertEquals("$name: it said it finished", exp["ended"]!!.jsonPrimitive.boolean, got.ended)
            assertEquals("$name: cut short", exp["length"]!!.jsonPrimitive.boolean, got.cutShort)
            val wantStatuses = exp["statuses"]!!.jsonArray.map { it.jsonPrimitive.content }
            for (w in wantStatuses) {
                assertTrue("$name: status '$w' was not read, got ${got.statuses}", w in got.statuses)
            }
        }
    }

    @Test
    fun `the approval status is read, and a keepalive is not text`() {
        assertEquals(ChatChunkParser.Result.Status("approval"), ChatChunkParser.consume(": jarvis-status approval"))
        assertEquals(ChatChunkParser.Result.Ignored, ChatChunkParser.consume(": keepalive"))
    }

    @Test
    fun `where and the turn id come from the real X-Jarvis-Route`() {
        val routes = fixture["route_headers"]!!.jsonArray.map { it.jsonObject }
        assertTrue(routes.isNotEmpty())
        for (r in routes) {
            val header = r.str("header")
            val exp = r["expect"]!!.jsonObject
            assertEquals("${r.str("name")}: where", exp.str("where"), ChatChunkParser.whereFromRouteHeader(header))
            assertEquals("${r.str("name")}: turn id", exp.str("turn_id"), Feedback.turnIdFromRouteHeader(header))
        }
    }

    @Test
    fun `the activity sentence comes from where the real bus puts it`() {
        val events = fixture["activity_events"]!!.jsonArray.map { it.jsonObject }
        assertTrue(events.isNotEmpty())
        for (e in events) {
            val want = e["expect"]!!.jsonObject.str("detail")
            assertEquals(e.str("name"), want, ActivityEvent.detail(e["data"], 500))
        }
    }
}
