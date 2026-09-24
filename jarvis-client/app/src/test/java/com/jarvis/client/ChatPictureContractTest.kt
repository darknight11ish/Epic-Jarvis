package com.jarvis.client

import com.jarvis.client.net.ChatChunkParser
import com.jarvis.client.net.ChatHistory
import com.jarvis.client.net.ChatPicture
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.SecondCard
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Base64

/**
 * A photo in chat, built by the phone's own encoder and compared with the
 * request the desktop sends - and the second card's route line.
 *
 * `contract/phone-second-card-cases.json` is written by
 * backend/test_phone_second_card_contract.py: it builds each request the
 * desktop's way (main.js `send`, commands.rs `stream_chat`), runs it through
 * the PC's own `newest_turn_has_image`, `choose_lane` and router, and records
 * the body. Here the same inputs go through [ChatHistory.requestBody] and
 * [ChatPicture], and must come out as the same JSON.
 *
 * Not tested here: shrinking the photo itself (ImageDecoder and
 * Bitmap.compress are Android and do not run in a JVM test).
 */
class ChatPictureContractTest {

    private val fixture: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/phone-second-card-cases.json")) {
            "contract/phone-second-card-cases.json is missing - run " +
                "backend/test_phone_second_card_contract.py --write"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    @Test
    fun `each request is exactly the desktop's, built with the phone's encoder`() {
        val requests = fixture["requests"]!!.jsonArray.map { it.jsonObject }
        assertTrue(requests.size >= 3)
        for (r in requests) {
            val name = r["name"]!!.jsonPrimitive.content
            val window = r["history"]!!.jsonArray.map {
                val o = it.jsonObject
                ChatHistory.Exchange(o["question"]!!.jsonPrimitive.content, o["answer"]!!.jsonPrimitive.content)
            }
            val question = r["question"]!!.jsonPrimitive.content
            val jpeg = r["jpeg_b64"].let { if (it == null || it is JsonNull) null else it.jsonPrimitive.content }
            val picture = jpeg?.let { ChatPicture.dataUri(Base64.getDecoder().decode(it)) }
            val asking = ChatHistory.asking(question, picture = picture != null)
            val built = JarvisJson.parseToJsonElement(ChatHistory.requestBody(window, asking, picture)).jsonObject
            assertEquals(name, r["body"], withoutHistoryFields(built))
            // The picture's words say so.
            val last = built["messages"]!!.jsonArray.last().jsonObject
            val want = if (picture != null) "picture_caption" else "typed"
            assertEquals(name, want, last["provenance"]!!.jsonPrimitive.content)
        }
    }

    /**
     * The request minus what chat history on the PC added on 2026-09-24
     * (docs/JARVIS-API.md section 18): `conversation_id`, `device`, and
     * `provenance` on each user message. The fixture was recorded before
     * those existed, and the PC strips all three before anything routes on
     * the body or reaches a model - so everything else must still match
     * byte for byte.
     */
    private fun withoutHistoryFields(body: JsonObject): JsonObject = JsonObject(
        body.filterKeys { it != "conversation_id" && it != "device" }.mapValues { (k, v) ->
            if (k != "messages") {
                v
            } else {
                JsonArray(v.jsonArray.map { m -> JsonObject(m.jsonObject.filterKeys { it != "provenance" }) })
            }
        },
    )

    @Test
    fun `the phone's picture numbers are the desktop's, and fit what the PC accepts`() {
        val limits = fixture["limits"]!!.jsonObject
        assertEquals(limits["max_long_edge"]!!.jsonPrimitive.int, ChatPicture.MAX_LONG_EDGE)
        assertEquals(limits["jpeg_quality"]!!.jsonPrimitive.int, ChatPicture.JPEG_QUALITY)
        assertEquals(limits["max_jpeg_bytes"]!!.jsonPrimitive.int, ChatPicture.MAX_JPEG_BYTES)
        assertEquals(limits["backend_max_body"]!!.jsonPrimitive.int, ChatPicture.BACKEND_MAX_BODY)
        // Base64 grows the JPEG by a third; the rest is room for the words.
        assertTrue(ChatPicture.MAX_JPEG_BYTES * 4 / 3 + 200_000 < ChatPicture.BACKEND_MAX_BODY)
    }

    @Test
    fun `the long edge is capped and the shape is kept`() {
        assertEquals(1920 to 1440, ChatPicture.targetSize(4000, 3000))
        assertEquals(1080 to 1920, ChatPicture.targetSize(2250, 4000))
        assertEquals(800 to 600, ChatPicture.targetSize(800, 600))
        assertEquals(1024 to 768, ChatPicture.targetSize(4000, 3000, 1024))
        assertEquals(1 to 1, ChatPicture.targetSize(0, 10))
    }

    @Test
    fun `a picture never lands in the conversation that is sent again`() {
        val window = ChatHistory.commit(emptyList(), "what is this?", "A cat.")
        val next = JarvisJson.parseToJsonElement(ChatHistory.requestBody(window, ChatHistory.asking("and now?")))
            .jsonObject
        assertFalse(next.toString().contains("data:image"))
        assertEquals(false, next["has_image"]!!.jsonPrimitive.content.toBoolean())
    }

    @Test
    fun `the ready picture never prints its bytes`() {
        val p = ChatPicture.Ready(ChatPicture.dataUri(ByteArray(10) { 7 }), 8, 6, 10)
        assertFalse(p.toString().contains("base64"))
    }

    @Test
    fun `the second card's route line comes from the real X-Jarvis-Route`() {
        val rows = fixture["route_headers"]!!.jsonArray.map { it.jsonObject }
        assertTrue(rows.size >= 3)
        for (r in rows) {
            val name = r["name"]!!.jsonPrimitive.content
            val header = r["header"]!!.jsonPrimitive.content
            val exp = r["expect"]!!.jsonObject
            val want = exp["second_card"].let { if (it == null || it is JsonNull) null else it.jsonPrimitive.content }
            val route = SecondCard.routeFromHeader(header)
            assertEquals(name, want, route?.feature)
            if (want != null) {
                assertEquals(name, exp["model"]!!.jsonPrimitive.content, route!!.model)
                val note = SecondCard.routeNote(route)
                assertTrue(note, note.startsWith("Answered on the second graphics card (${route.model})"))
            }
            // Still this PC: the Local/Cloud reading is unchanged.
            assertEquals(name, "local", ChatChunkParser.whereFromRouteHeader(header))
        }
        assertNull(SecondCard.routeFromHeader(null))
        assertNull(SecondCard.routeFromHeader("not json"))
    }
}
