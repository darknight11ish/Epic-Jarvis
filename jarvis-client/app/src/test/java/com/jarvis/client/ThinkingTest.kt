package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Thinking
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ThinkingTest {

    @Test
    fun `thinking levels and default values match specification`() {
        assertEquals(listOf("off", "quick", "deep", "auto"), Thinking.LEVELS)
        assertEquals("off", Thinking.DEFAULT)
        assertEquals("Thinking levels", Thinking.TITLE)
        assertTrue(Thinking.NOTICE.contains("conversation room"))
        for (lvl in Thinking.LEVELS) {
            assertTrue(Thinking.LEVEL_LABELS.containsKey(lvl))
            assertTrue(Thinking.WHY.containsKey(lvl))
        }
    }

    @Test
    fun `parse valid thinking response`() {
        val json = JsonObject(
            mapOf(
                "title" to JsonPrimitive("Thinking levels"),
                "detail" to JsonPrimitive("Lets Jarvis think"),
                "notice" to JsonPrimitive("Uses conversation room"),
                "models" to JsonArray(
                    listOf(
                        JsonObject(
                            mapOf(
                                "role" to JsonPrimitive("everyday"),
                                "name" to JsonPrimitive("Everyday chat"),
                                "model" to JsonPrimitive("jarvis-primary"),
                                "level" to JsonPrimitive("quick"),
                                "supported" to JsonArray(listOf(JsonPrimitive("off"), JsonPrimitive("quick"), JsonPrimitive("deep"), JsonPrimitive("auto"))),
                                "why" to JsonPrimitive("Quick thinking."),
                            )
                        ),
                        JsonObject(
                            mapOf(
                                "role" to JsonPrimitive("second"),
                                "name" to JsonPrimitive("Second card lane"),
                                "model" to JsonPrimitive("plain-model"),
                                "level" to JsonPrimitive("off"),
                                "supported" to JsonArray(listOf(JsonPrimitive("off"))),
                                "why" to JsonPrimitive("Off."),
                            )
                        )
                    )
                )
            )
        )

        val view = Thinking.parse(json)
        assertNotNull(view)
        assertEquals("Thinking levels", view!!.title)
        assertEquals(2, view.models.size)

        val m1 = view.models[0]
        assertEquals("everyday", m1.role)
        assertEquals("Everyday chat", m1.name)
        assertEquals("jarvis-primary", m1.model)
        assertEquals("quick", m1.level)
        assertEquals(4, m1.supported.size)

        val m2 = view.models[1]
        assertEquals("second", m2.role)
        assertEquals("Second card lane", m2.name)
        assertEquals("off", m2.level)
        assertEquals(listOf("off"), m2.supported)
    }

    @Test
    fun `parse unavailable or malformed returns null`() {
        val unavailable = JsonObject(mapOf("available" to JsonPrimitive(false)))
        assertNull(Thinking.parse(unavailable))

        val malformed = JsonObject(mapOf("something" to JsonPrimitive("else")))
        assertNull(Thinking.parse(malformed))
    }

    @Test
    fun `missing helper identifies missing setting`() {
        assertTrue(Thinking.missing(ApiError.NotFound))
        assertTrue(Thinking.missing(ApiError.NotAvailable))
        assertTrue(Thinking.missing(ApiError.Server(404, "Not Found")))
        assertTrue(Thinking.missing(ApiError.Server(501, "Not Implemented")))
        assertTrue(Thinking.missing(ApiError.Server(503, "Unavailable")))
        assertFalse(Thinking.missing(ApiError.Server(400, "Bad Request")))
    }

    @Test
    fun `bodyString creates valid JSON and enforces levels`() {
        val body = Thinking.bodyString("everyday", "deep")
        assertTrue(body.contains("\"role\":\"everyday\""))
        assertTrue(body.contains("\"level\":\"deep\""))
    }

    @Test
    fun `replyLine extracts message or fallback`() {
        val okResp = ApiResult.Ok(JsonObject(mapOf("message" to JsonPrimitive("Thinking set to deep."))))
        assertEquals("Thinking set to deep.", Thinking.replyLine(okResp, "deep"))

        val failedMissing = ApiResult.Failed(ApiError.NotFound)
        assertEquals(Thinking.MISSING, Thinking.replyLine(failedMissing, "deep"))
    }
}
